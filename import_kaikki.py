#!/usr/bin/env python3
"""
Import German→English translations from kaikki.org Wiktionary dump into cache.

Download: https://kaikki.org/dictionary/German/kaikki.org-dictionary-German.jsonl.gz
Usage:    python3 import_kaikki.py [path/to/kaikki-german.jsonl.gz]
"""

import gzip
import json
import os
import re
import sqlite3
import sys
import time

CACHE_PATH = "data/translations_cache.db"
DEFAULT_DUMP = "data/kaikki-german.jsonl.gz"


def clean_gloss(text: str) -> str | None:
    """Strip HTML, wiki markup, and extraneous content from a gloss string."""
    if not text:
        return None
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text).strip()
    # Strip MediaWiki CSS junk
    text = re.sub(r"\.mw-parser-output[^}]*\}[^.]*", "", text).strip()
    # Strip bracketed qualifiers like [auxiliary sein], [with an X]
    text = re.sub(r"\[auxiliary\s+\w+\]", "", text, flags=re.I).strip()
    text = re.sub(r"\[with an?\s+[^\]]+\]", "", text).strip()
    # Strip leading/trailing punctuation
    text = re.sub(r"^[-–—:;\s]+|[-–—:;\s]+$", "", text).strip()
    # Strip trailing orphan closing paren like "to drink  by mouth)"
    text = re.sub(r"\s+\w[\w\s]*\)$", "", text).strip()
    if not text or len(text) <= 1 or text in ("...", "n/a", "none", "null"):
        return None
    return text



SKIP_TAGS = {
    "obsolete", "dated", "archaic", "rare", "dialectal",
    "derogatory", "offensive", "vulgar", "obscene",
    "euphemistic", "form-of", "alt-of", "abbreviation",
    "clipping", "in-compounds",
}


def pick_best_gloss(senses: list) -> str | None:
    """
    Pick the best English gloss from a list of senses.
    Strategy: take the first sense that has no 'bad' tags
    (derogatory, euphemistic, form-of, etc.), fall back to
    first available if all senses are tagged.
    """
    def process_gloss(gloss: str) -> str | None:
        cleaned = clean_gloss(gloss)
        if not cleaned or len(cleaned) <= 2:
            return None
        # Take primary meaning before first semicolon
        primary = cleaned.split(";")[0].strip()
        # Remove parenthetical qualifiers (complete parentheses only)
        primary = re.sub(r"\(.*?\)", "", primary).strip()
        # Strip any trailing unclosed paren fragments like " (collection of..."
        primary = re.sub(r"\s*\([^)]*$", "", primary).strip()
        # Truncate very long definitions
        if len(primary) > 80:
            primary = primary[:80].rsplit(" ", 1)[0]
        # Clean up extra whitespace
        primary = re.sub(r"\s+", " ", primary).strip()
        return primary if len(primary) > 2 else None

    good_candidates = []  # senses without problematic tags
    all_candidates = []   # fallback: any sense

    for sense in senses:
        tags = {t.lower() for t in (sense.get("tags") or [])}
        glosses = sense.get("glosses") or []
        has_bad_tag = bool(tags & SKIP_TAGS)

        for gloss in glosses:
            processed = process_gloss(gloss)
            if processed:
                if not has_bad_tag:
                    good_candidates.append(processed)
                all_candidates.append(processed)
                break  # one gloss per sense is enough

    # Prefer primary (first) from good candidates, then fallback
    return good_candidates[0] if good_candidates else (all_candidates[0] if all_candidates else None)



def normalize(result: str) -> str:
    """Lowercase initial letter unless proper noun."""
    if len(result) > 1 and result[0].isupper() and result[1].islower() and result != "I":
        result = result[0].lower() + result[1:]
    return result


def strip_article(word: str) -> str:
    return re.sub(r"^(der|die|das)\s+", "", word, flags=re.I).strip()


def main():
    dump_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DUMP

    if not os.path.exists(dump_path):
        print(f"ERROR: Dump file not found: {dump_path}")
        print(f"Download with:")
        print(f"  curl -L -o {dump_path} https://kaikki.org/dictionary/German/kaikki.org-dictionary-German.jsonl.gz")
        sys.exit(1)

    # Connect to cache
    conn = sqlite3.connect(CACHE_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS translations (
            word_lower  TEXT PRIMARY KEY,
            translation TEXT NOT NULL
        )
    """)
    conn.commit()

    # Load already-cached words
    cur = conn.cursor()
    cur.execute("SELECT word_lower FROM translations")
    cached = {row[0] for row in cur.fetchall()}
    print(f"Already cached: {len(cached)} entries")

    # Process dump
    opener = gzip.open if dump_path.endswith(".gz") else open
    total = 0
    imported = 0
    skipped_cached = 0
    skipped_no_gloss = 0
    batch = []
    BATCH_SIZE = 1000

    print(f"Reading {dump_path} ...")
    start = time.time()

    with opener(dump_path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            total += 1
            if total % 50000 == 0:
                elapsed = time.time() - start
                print(f"  {total:,} entries read | {imported:,} imported | {elapsed:.0f}s")

            word = entry.get("word", "").strip()
            lang = entry.get("lang_code", "")
            if not word or lang != "de":
                continue

            clean = strip_article(word.lower())
            if clean in cached:
                skipped_cached += 1
                continue

            senses = entry.get("senses") or []
            gloss = pick_best_gloss(senses)
            if not gloss:
                skipped_no_gloss += 1
                continue

            gloss = normalize(gloss)
            batch.append((clean, gloss))
            cached.add(clean)
            imported += 1

            if len(batch) >= BATCH_SIZE:
                conn.executemany(
                    "INSERT OR REPLACE INTO translations (word_lower, translation) VALUES (?, ?)",
                    batch,
                )
                conn.commit()
                batch.clear()

    # Final batch
    if batch:
        conn.executemany(
            "INSERT OR REPLACE INTO translations (word_lower, translation) VALUES (?, ?)",
            batch,
        )
        conn.commit()

    elapsed = time.time() - start
    cur.execute("SELECT COUNT(*) FROM translations")
    total_cached = cur.fetchone()[0]
    conn.close()

    print(f"\n✅ Done in {elapsed:.1f}s")
    print(f"   Entries read:      {total:,}")
    print(f"   Imported:          {imported:,}")
    print(f"   Already cached:    {skipped_cached:,}")
    print(f"   No usable gloss:   {skipped_no_gloss:,}")
    print(f"   Total cache now:   {total_cached:,}")


if __name__ == "__main__":
    main()
