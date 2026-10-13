import concurrent.futures
import html
import json
import os
import re
import sqlite3
import urllib.parse
import urllib.request
from typing import Dict, List, Optional

DEFAULT_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "translations_cache.db"
)


class WordTranslator:
    """
    Offline-first translator with caching for German -> English.
    Tries MyMemory first, then Wiktionary definition API as high-quality fallback.
    Caches all results in SQLite locally.
    Supports instant batch cache lookup and parallel fetching for search results.
    Gracefully returns None if offline or timeout.
    """

    def __init__(self, cache_path: str = DEFAULT_CACHE_PATH, enable_remote: bool = False):
        self.cache_path = cache_path
        self.enable_remote = enable_remote
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        self._init_cache()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.cache_path)

    def _init_cache(self):
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS translations (
                    word_lower  TEXT PRIMARY KEY,
                    translation TEXT NOT NULL
                )
            """
            )
            conn.commit()

    def _clean_lookup_word(self, text: str) -> str:
        """Strip separators, articles, and whitespace to extract core lookup word."""
        clean = text.strip().replace("|", "")
        clean_core = re.sub(r"^(der|die|das)\s+", "", clean, flags=re.IGNORECASE).strip()
        return clean_core.lower()

    def _get_cached(self, word: str) -> Optional[str]:
        """
        Lookup in local SQLite cache.
        Returns translation string if present and non-empty.
        Returns "" if negative-cached (confirmed not found).
        Returns None if not in cache at all.
        """
        clean_key = self._clean_lookup_word(word)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT translation FROM translations WHERE word_lower = ?", (clean_key,))
            row = cur.fetchone()
            return row[0] if row else None

    def _save_cache(self, word: str, translation: str):
        clean_key = self._clean_lookup_word(word)
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO translations (word_lower, translation) VALUES (?, ?)",
                (clean_key, translation.strip() if translation else ""),
            )
            conn.commit()

    def _clean_gloss(self, raw_text: str) -> Optional[str]:
        """Clean up translation text, removing auxiliary tags and html."""
        if not raw_text:
            return None
        text = html.unescape(raw_text).strip()
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text).strip()
        # Remove auxiliary info like [auxiliary sein]
        text = re.sub(r"\[auxiliary\s+\w+\]", "", text, flags=re.I).strip()
        # Remove leading/trailing symbols
        text = re.sub(r"^[-–—:;\s]+|[-–—:;\s]+$", "", text).strip()
        # Discard invalid single-character or garbage strings
        if len(text) <= 1 or text in ("...", "n/a", "none", "null"):
            return None
        return text

    def _fetch_mymemory(self, clean_word: str, timeout: float = 2.0) -> Optional[str]:
        url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(clean_word)}&langpair=de|en"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "simple-wb/1.0 (German vocabulary CLI)",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                res_data = data.get("responseData") or {}
                trans = res_data.get("translatedText")
                cleaned = self._clean_gloss(trans)
                if cleaned and cleaned.lower() != clean_word.lower():
                    return cleaned
        except Exception:
            pass
        return None

    def _fetch_wiktionary(self, clean_word: str, timeout: float = 2.0) -> Optional[str]:
        url = f"https://en.wiktionary.org/api/rest_v1/page/definition/{urllib.parse.quote(clean_word)}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "simple-wb/1.0 (German vocabulary CLI)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                if "de" in data:
                    for item in data["de"]:
                        for d in item.get("definitions", []):
                            raw = d.get("definition", "")
                            cleaned = self._clean_gloss(raw)
                            if cleaned:
                                # Keep primary meaning
                                first_meaning = cleaned.split(";")[0].strip()
                                first_meaning = re.sub(r"\(.*?\)", "", first_meaning).strip()
                                if first_meaning:
                                    return first_meaning
        except Exception:
            pass
        return None

    def _fetch_remote_single(self, clean_word: str, timeout: float = 1.5) -> Optional[str]:
        """Fetch remote translation without accessing SQLite."""
        result = self._fetch_mymemory(clean_word, timeout=timeout)
        if not result:
            result = self._fetch_wiktionary(clean_word, timeout=timeout)
        if result:
            if len(result) > 1 and result[0].isupper() and result[1].islower() and result != "I":
                result = result[0].lower() + result[1:]
        return result

    def translate(self, text: str, timeout: float = 2.0) -> Optional[str]:
        """
        Translate German word or short text to English using offline cache.
        If enable_remote is False (default), only local cache is queried.
        """
        if not text or not text.strip():
            return None

        clean_core = self._clean_lookup_word(text)
        if not clean_core:
            return None

        # 1. Local Cache
        cached = self._get_cached(clean_core)
        if cached is not None:
            return cached if cached != "" else None

        # If remote translation is disabled, do not perform network requests
        if not self.enable_remote:
            return None

        # 2. Remote API lookup (only if enable_remote is True)
        result = self._fetch_remote_single(clean_core, timeout=timeout)

        # 3. Cache result
        self._save_cache(clean_core, result or "")
        return result

    def translate_batch(
        self,
        words: List[str],
        fetch_remote: Optional[bool] = None,
        remote_timeout: float = 0.8,
        max_remote_fetch: int = 10,
    ) -> Dict[str, str]:
        """
        Fast batch translation for multiple search results:
        1. Queries local SQLite cache in a single batch query (<1ms).
        2. If fetch_remote is True (or enable_remote is True), concurrently fetches
           missing translations in parallel with a strict total timeout.
        """
        if not words:
            return {}

        word_map: Dict[str, List[str]] = {}
        for w in words:
            clean = self._clean_lookup_word(w)
            if clean:
                word_map.setdefault(clean, []).append(w)

        if not word_map:
            return {}

        translations: Dict[str, str] = {}
        cached_keys = set()

        # Step 1: Batch SQLite cache lookup (runs in < 1ms)
        with self._get_conn() as conn:
            cur = conn.cursor()
            keys = list(word_map.keys())
            placeholders = ",".join("?" * len(keys))
            cur.execute(
                f"SELECT word_lower, translation FROM translations WHERE word_lower IN ({placeholders})",
                keys,
            )
            for row in cur.fetchall():
                w_lower, trans = row
                cached_keys.add(w_lower)
                if trans:  # Non-empty means valid translation
                    for orig in word_map.get(w_lower, []):
                        translations[orig] = trans

        should_fetch_remote = self.enable_remote if fetch_remote is None else fetch_remote

        # Step 2: Concurrently fetch missing words (only if remote is enabled)
        missing_keys = [k for k in word_map.keys() if k not in cached_keys]
        if should_fetch_remote and missing_keys:
            to_fetch = missing_keys[:max_remote_fetch]
            workers = min(len(to_fetch), 5)
            futures_map = {}

            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                for k in to_fetch:
                    fut = executor.submit(self._fetch_remote_single, k, timeout=remote_timeout)
                    futures_map[fut] = k

                done, _ = concurrent.futures.wait(
                    futures_map.keys(), timeout=remote_timeout
                )

                to_cache = []
                for fut in done:
                    k = futures_map[fut]
                    try:
                        res = fut.result()
                        to_cache.append((k, res or ""))
                        if res:
                            for orig in word_map.get(k, []):
                                translations[orig] = res
                    except Exception:
                        pass

                # Batch save newly fetched results into cache
                if to_cache:
                    with self._get_conn() as conn:
                        conn.executemany(
                            "INSERT OR REPLACE INTO translations (word_lower, translation) VALUES (?, ?)",
                            to_cache,
                        )
                        conn.commit()

        return translations
