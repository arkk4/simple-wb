"""
Script to build the offline SQLite German dictionary from the Kaikki Wiktionary dump.

Source:
  https://kaikki.org/dictionary/German/kaikki.org-dictionary-German.jsonl.gz
  (Extracted from Wiktionary using wiktextract)

Tables created:
1. 'dictionary':
   - word        TEXT NOT NULL (cased)
   - pos         TEXT NOT NULL ('noun', 'verb', 'adj', 'adv', ...)
   - gender      TEXT          ('m', 'f', 'n' for nouns)
   - plural      TEXT          (noun plural OR verb hilfsverb 'haben'/'sein')
   - word_lower  TEXT NOT NULL (lowercase for search)
   - lemma       TEXT          (for inflected forms: lemma / infinitive)
   - form        TEXT          ('inf', 'p2', 'prat', 'pl', or NULL)

2. 'verb_forms':
   - infinitive  TEXT PRIMARY KEY
   - praeteritum TEXT          (ich-form, e.g. 'machte', 'fuhr')
   - partizip2   TEXT          (e.g. 'gemacht', 'gefahren')
   - hilfsverb   TEXT          ('haben' or 'sein')
"""

import gzip
import json
import os
import shutil
import sqlite3
import sys
import time
import urllib.request

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DEFAULT_DUMP = os.path.join(DATA_DIR, "kaikki-german.jsonl.gz")
DEFAULT_DB = os.path.join(DATA_DIR, "dictionary.db")
KAIKKI_URL = "https://kaikki.org/dictionary/German/kaikki.org-dictionary-German.jsonl.gz"


def ensure_dump(dump_path: str = DEFAULT_DUMP):
    """Ensure the Kaikki German dump exists; download if missing."""
    if os.path.exists(dump_path):
        return
    os.makedirs(os.path.dirname(dump_path), exist_ok=True)
    print(f"Downloading Kaikki German Wiktionary dump (~94 MB)...")
    print(f"  URL: {KAIKKI_URL}")
    req = urllib.request.Request(KAIKKI_URL, headers={"User-Agent": "simple-wb/1.0"})
    tmp_path = dump_path + ".tmp"
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp_path, "wb") as f_out:
        shutil.copyfileobj(resp, f_out)
    os.replace(tmp_path, dump_path)
    print(f"Downloaded to {dump_path}.")


def build_database(dump_path: str = DEFAULT_DUMP, db_path: str = DEFAULT_DB):
    ensure_dump(dump_path)

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    tmp_db_path = db_path + ".tmp"
    if os.path.exists(tmp_db_path):
        os.remove(tmp_db_path)

    conn = sqlite3.connect(tmp_db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA synchronous = OFF")
    cur.execute("PRAGMA journal_mode = MEMORY")

    cur.execute(
        """
        CREATE TABLE dictionary (
            word        TEXT NOT NULL,
            pos         TEXT NOT NULL,
            gender      TEXT,
            plural      TEXT,
            word_lower  TEXT NOT NULL,
            lemma       TEXT,
            form        TEXT
        )
    """
    )

    cur.execute(
        """
        CREATE TABLE verb_forms (
            infinitive   TEXT PRIMARY KEY,
            praeteritum  TEXT,
            partizip2    TEXT,
            hilfsverb    TEXT
        )
    """
    )

    print(f"Parsing {dump_path} ...")
    start_time = time.time()

    dict_batch = []
    vf_batch = []
    seen_dict = set()
    seen_vf = set()
    entries_read = 0

    with gzip.open(dump_path, "rt", encoding="utf-8") as f:
        for line in f:
            entries_read += 1
            if entries_read % 100000 == 0:
                elapsed = time.time() - start_time
                print(f"  {entries_read:,} entries scanned ({elapsed:.1f}s) ...")

            try:
                e = json.loads(line)
            except Exception:
                continue

            word = (e.get("word") or "").strip()
            pos = e.get("pos")
            lang_code = e.get("lang_code")
            if not word or not pos or lang_code != "de":
                continue

            head_args = [h.get("args", {}).get("2") for h in e.get("head_templates", [])]
            is_form = any("form" in str(a) for a in head_args) or any(
                "form-of" in s.get("tags", []) for s in e.get("senses", [])
            )

            # ──────────────────────────────────────────
            # 1. NOUNS
            # ──────────────────────────────────────────
            if pos == "noun":
                if is_form:
                    continue

                # Gender
                gender = None
                for s in e.get("senses", []):
                    st = s.get("tags", [])
                    if "masculine" in st:
                        gender = "m"
                        break
                    if "feminine" in st:
                        gender = "f"
                        break
                    if "neuter" in st:
                        gender = "n"
                        break

                if not gender:
                    for h in e.get("head_templates", []):
                        a1 = h.get("args", {}).get("1", "")
                        if a1.startswith("m"):
                            gender = "m"
                            break
                        elif a1.startswith("f"):
                            gender = "f"
                            break
                        elif a1.startswith("n"):
                            gender = "n"
                            break

                # Plural form
                plural = None
                plurals_list = []
                for f_item in e.get("forms", []):
                    tags = f_item.get("tags", [])
                    if "plural" in tags:
                        val = (f_item.get("form") or "").strip()
                        if val and val not in ("strong", "weak", "de-ndecl", "-", "no-plural", "plural"):
                            if not plural:
                                plural = val
                            plurals_list.append(val)

                key = (word.lower(), "noun", None)
                if key not in seen_dict:
                    seen_dict.add(key)
                    dict_batch.append((word, "noun", gender, plural, word.lower(), None, None))

                # Index plural forms to point back to the lemma
                for p_val in plurals_list:
                    p_key = (p_val.lower(), "noun", "pl")
                    if p_key not in seen_dict:
                        seen_dict.add(p_key)
                        dict_batch.append((p_val, "noun", gender, None, p_val.lower(), word, "pl"))

            # ──────────────────────────────────────────
            # 2. VERBS
            # ──────────────────────────────────────────
            elif pos == "verb":
                if is_form:
                    continue

                forms = e.get("forms", [])

                # Präteritum
                past = None
                for f_item in forms:
                    tags = f_item.get("tags", [])
                    if "past" in tags and ("first-person" in tags or "third-person" in tags) and "singular" in tags:
                        past = (f_item.get("form") or "").strip()
                        break
                if not past:
                    for f_item in forms:
                        tags = f_item.get("tags", [])
                        if "past" in tags:
                            val = (f_item.get("form") or "").strip()
                            if val and val not in ("weak", "strong", "de-conj"):
                                past = val
                                break

                # Partizip II
                p2 = None
                for f_item in forms:
                    tags = f_item.get("tags", [])
                    if "participle" in tags and "past" in tags:
                        p2 = (f_item.get("form") or "").strip()
                        break

                # Auxiliary verb (haben / sein)
                aux = "haben"
                aux_list = [(f_item.get("form") or "").strip() for f_item in forms if "auxiliary" in f_item.get("tags", [])]
                if "sein" in aux_list:
                    aux = "sein"
                elif "haben" in aux_list:
                    aux = "haben"

                # Insert into verb_forms
                if word not in seen_vf:
                    seen_vf.add(word)
                    vf_batch.append((word, past or None, p2 or None, aux))

                # Infinitive
                inf_key = (word.lower(), "verb", "inf")
                if inf_key not in seen_dict:
                    seen_dict.add(inf_key)
                    dict_batch.append((word, "verb", None, aux, word.lower(), None, "inf"))

                # Partizip II form
                if p2 and p2 != word:
                    p2_key = (p2.lower(), "verb", "p2")
                    if p2_key not in seen_dict:
                        seen_dict.add(p2_key)
                        dict_batch.append((p2, "verb", None, aux, p2.lower(), word, "p2"))

                # Präteritum form
                if past and past != word:
                    prat_key = (past.lower(), "verb", "prat")
                    if prat_key not in seen_dict:
                        seen_dict.add(prat_key)
                        dict_batch.append((past, "verb", None, aux, past.lower(), word, "prat"))

            # ──────────────────────────────────────────
            # 3. ADJECTIVES
            # ──────────────────────────────────────────
            elif pos == "adj":
                if is_form:
                    continue
                adj_key = (word.lower(), "adj", None)
                if adj_key not in seen_dict:
                    seen_dict.add(adj_key)
                    dict_batch.append((word, "adj", None, None, word.lower(), None, None))

            # ──────────────────────────────────────────
            # 4. ADVERBS
            # ──────────────────────────────────────────
            elif pos == "adv":
                if is_form:
                    continue
                adv_key = (word.lower(), "adv", None)
                if adv_key not in seen_dict:
                    seen_dict.add(adv_key)
                    dict_batch.append((word, "adv", None, None, word.lower(), None, None))

            if len(dict_batch) >= 10000:
                cur.executemany("INSERT INTO dictionary VALUES (?, ?, ?, ?, ?, ?, ?)", dict_batch)
                dict_batch.clear()

            if len(vf_batch) >= 10000:
                cur.executemany("INSERT INTO verb_forms VALUES (?, ?, ?, ?)", vf_batch)
                vf_batch.clear()

    if dict_batch:
        cur.executemany("INSERT INTO dictionary VALUES (?, ?, ?, ?, ?, ?, ?)", dict_batch)
    if vf_batch:
        cur.executemany("INSERT INTO verb_forms VALUES (?, ?, ?, ?)", vf_batch)

    print("Building indexes...")
    cur.execute("CREATE INDEX idx_dict_word ON dictionary (word)")
    cur.execute("CREATE INDEX idx_dict_lower ON dictionary (word_lower)")
    cur.execute("CREATE INDEX idx_dict_lemma ON dictionary (lemma) WHERE lemma IS NOT NULL")
    cur.execute("CREATE INDEX idx_vf_p2 ON verb_forms (partizip2)")
    cur.execute("CREATE INDEX idx_vf_prat ON verb_forms (praeteritum)")

    conn.commit()
    cur.execute("SELECT COUNT(*) FROM dictionary")
    total_dict = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM verb_forms")
    total_vf = cur.fetchone()[0]
    conn.close()

    # Atomically replace final file
    os.replace(tmp_db_path, db_path)

    elapsed = time.time() - start_time
    size_mb = os.path.getsize(db_path) / (1024 * 1024)
    print(f"\nDone in {elapsed:.1f}s!")
    print(f"  Target database:    {db_path}")
    print(f"  Dictionary entries: {total_dict:,}")
    print(f"  Verb forms:         {total_vf:,}")
    print(f"  Database file size: {size_mb:.2f} MB")


if __name__ == "__main__":
    build_database()
