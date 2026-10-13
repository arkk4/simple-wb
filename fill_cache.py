#!/usr/bin/env python3
"""
Bulk-fill the translation cache from the offline dictionary.
Strategy: Wiktionary first (no rate limit), MyMemory as fallback.
Skips words already in cache. Resumes safely on Ctrl+C.
"""

import html
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

DICT_PATH = "data/dictionary.db"
CACHE_PATH = "data/translations_cache.db"

TIMEOUT = 3.0
DELAY_BETWEEN_REQUESTS = 0.8  # seconds between requests (~75/min, ~100k in ~22h)


def clean_gloss(raw_text: str) -> Optional[str]:
    if not raw_text:
        return None
    text = html.unescape(raw_text).strip()
    # Strip HTML tags
    text = re.sub(r"<[^>]+>", "", text).strip()
    # Strip MediaWiki junk like ".mw-parser-output .foo{...}"
    text = re.sub(r"\.mw-parser-output[^}]*\}[^.]*", "", text).strip()
    text = re.sub(r"\[auxiliary\s+\w+\]", "", text, flags=re.I).strip()
    # Strip bracketed meta like [with an X]
    text = re.sub(r"\[with an?\s+[^\]]+\]", "", text).strip()
    text = re.sub(r"^[-–—:;\s]+|[-–—:;\s]+$", "", text).strip()
    if len(text) <= 1 or text in ("...", "n/a", "none", "null"):
        return None
    return text


def fetch_wiktionary(word: str) -> Optional[str]:
    url = f"https://en.wiktionary.org/api/rest_v1/page/definition/{urllib.parse.quote(word)}"
    req = urllib.request.Request(url, headers={"User-Agent": "simple-wb/1.0 cache-filler"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                if "de" in data:
                    for item in data["de"]:
                        for d in item.get("definitions", []):
                            raw = d.get("definition", "")
                            cleaned = clean_gloss(raw)
                            if cleaned:
                                first = cleaned.split(";")[0].strip()
                                first = re.sub(r"\(.*?\)", "", first).strip()
                                # Truncate very long definitions at first comma or 80 chars
                                if len(first) > 80:
                                    first = first[:80].rsplit(" ", 1)[0]
                                if first:
                                    return first
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                time.sleep(10)  # back off 10s on rate limit
                continue
        except Exception:
            pass
        break
    return None


def fetch_mymemory(word: str) -> Optional[str]:
    url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(word)}&langpair=de|en"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "simple-wb/1.0 cache-filler", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            res_data = data.get("responseData") or {}
            trans = res_data.get("translatedText")
            cleaned = clean_gloss(trans)
            if cleaned and cleaned.lower() != word.lower():
                return cleaned
    except Exception:
        pass
    return None


def normalize(result: str) -> str:
    if len(result) > 1 and result[0].isupper() and result[1].islower() and result != "I":
        result = result[0].lower() + result[1:]
    return result


def get_cached_words(cache_conn: sqlite3.Connection) -> set:
    cur = cache_conn.cursor()
    cur.execute("SELECT word_lower FROM translations")
    return {row[0] for row in cur.fetchall()}


def save_cache(cache_conn: sqlite3.Connection, word: str, translation: str):
    cache_conn.execute(
        "INSERT OR REPLACE INTO translations (word_lower, translation) VALUES (?, ?)",
        (word.lower().strip(), translation.strip()),
    )
    cache_conn.commit()


def get_base_words(dict_conn: sqlite3.Connection):
    """Get all base-form words: nouns, verb infinitives, adjectives."""
    cur = dict_conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT word_lower, pos, gender
        FROM dictionary
        WHERE form IS NULL OR form = 'inf'
        ORDER BY
            CASE pos WHEN 'verb' THEN 0 WHEN 'noun' THEN 1 ELSE 2 END,
            word_lower
        """
    )
    return cur.fetchall()


def strip_article(word: str, gender: Optional[str]) -> str:
    """Remove article prefix if present in word_lower (shouldn't be, but just in case)."""
    return re.sub(r"^(der|die|das)\s+", "", word, flags=re.I).strip()


def main():
    dict_conn = sqlite3.connect(f"file:{DICT_PATH}?mode=ro", uri=True)
    cache_conn = sqlite3.connect(CACHE_PATH)

    # Ensure table exists
    cache_conn.execute("""
        CREATE TABLE IF NOT EXISTS translations (
            word_lower  TEXT PRIMARY KEY,
            translation TEXT NOT NULL
        )
    """)
    cache_conn.commit()

    print("Loading dictionary words...")
    all_words = get_base_words(dict_conn)
    total = len(all_words)
    print(f"Total base words: {total}")

    print("Loading cache...")
    cached = get_cached_words(cache_conn)
    print(f"Already cached: {len(cached)}")

    to_process = [
        (word, pos, gender) for (word, pos, gender) in all_words
        if strip_article(word, gender) not in cached
    ]
    print(f"To translate: {len(to_process)}")
    print()

    found = 0
    missed = 0
    errors = 0
    start_time = time.time()

    try:
        for i, (word_lower, pos, gender) in enumerate(to_process):
            clean_word = strip_article(word_lower, gender)

            # Skip if cached (could have been added during this run)
            if clean_word in cached:
                continue

            # Progress line
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta_secs = (len(to_process) - i) / rate if rate > 0 else 0
            eta_str = f"{int(eta_secs // 3600)}h{int((eta_secs % 3600) // 60)}m" if eta_secs > 60 else f"{int(eta_secs)}s"

            sys.stdout.write(
                f"\r[{i+1}/{len(to_process)}] {pos:4s} {clean_word[:30]:<30s} "
                f"✓{found} ✗{missed} ⚡{rate:.1f}/s ETA:{eta_str}   "
            )
            sys.stdout.flush()

            # Wiktionary first (no rate limit)
            result = fetch_wiktionary(clean_word)

            # MyMemory fallback
            if not result:
                result = fetch_mymemory(clean_word)
                if result:
                    time.sleep(0.5)  # slight delay for MyMemory

            if result:
                result = normalize(result)
                save_cache(cache_conn, clean_word, result)
                cached.add(clean_word)
                found += 1
            else:
                missed += 1

            time.sleep(DELAY_BETWEEN_REQUESTS)

    except KeyboardInterrupt:
        print(f"\n\nInterrupted. Progress saved.")

    total_elapsed = time.time() - start_time
    print(f"\n\nDone in {total_elapsed:.0f}s")
    print(f"  Translated: {found}")
    print(f"  Not found:  {missed}")
    print(f"  Total cache entries: {len(cached)}")

    dict_conn.close()
    cache_conn.close()


if __name__ == "__main__":
    main()
