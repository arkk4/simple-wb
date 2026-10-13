import os
import sqlite3
from datetime import datetime, date
from typing import List, Optional, Dict
from .models import WordEntry, PartOfSpeech, Gender

DEFAULT_STORAGE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "words.db"
)


class WordStorage:
    def __init__(self, db_path: str = DEFAULT_STORAGE_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS words (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    german      TEXT NOT NULL,
                    translation TEXT NOT NULL,
                    pos         TEXT NOT NULL,
                    gender      TEXT,
                    plural      TEXT,
                    hilfsverb   TEXT,
                    verb_prefix TEXT,
                    verb_form   TEXT,
                    lemma       TEXT,
                    praeteritum TEXT,
                    partizip2   TEXT,
                    auto_detected INTEGER NOT NULL DEFAULT 0,
                    detection_reason TEXT,
                    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            # Schema migration: add any missing columns for existing databases
            existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(words)")}
            for col, typedef in [
                ("hilfsverb", "TEXT"),
                ("verb_prefix", "TEXT"),
                ("verb_form", "TEXT"),
                ("lemma", "TEXT"),
                ("praeteritum", "TEXT"),
                ("partizip2", "TEXT"),
            ]:
                if col not in existing_cols:
                    cur.execute(f"ALTER TABLE words ADD COLUMN {col} {typedef}")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_words_created ON words (created_at)")
            conn.commit()

    def add_word(self, entry: WordEntry) -> WordEntry:
        now = datetime.now()
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO words
                    (german, translation, pos, gender, plural, hilfsverb, verb_prefix,
                     verb_form, lemma, praeteritum, partizip2,
                     auto_detected, detection_reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    entry.german,
                    entry.translation,
                    entry.pos.value,
                    entry.gender.value if entry.gender else None,
                    entry.plural,
                    entry.hilfsverb,
                    entry.verb_prefix,
                    entry.verb_form,
                    entry.lemma,
                    entry.praeteritum,
                    entry.partizip2,
                    1 if entry.auto_detected else 0,
                    entry.detection_reason,
                    now.isoformat(),
                ),
            )
            entry.id = cur.lastrowid
            conn.commit()
        entry.created_at = now
        return entry

    def delete_word(self, word_id: int) -> bool:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM words WHERE id = ?", (word_id,))
            conn.commit()
            return cur.rowcount > 0

    def get_word_by_id(self, word_id: int) -> Optional[WordEntry]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM words WHERE id = ?", (word_id,))
            row = cur.fetchone()
            return self._row_to_entry(row) if row else None

    def update_word(self, entry: WordEntry) -> bool:
        if entry.id is None:
            return False
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE words SET
                    german = ?,
                    translation = ?,
                    pos = ?,
                    gender = ?,
                    plural = ?,
                    hilfsverb = ?,
                    verb_prefix = ?,
                    verb_form = ?,
                    lemma = ?,
                    praeteritum = ?,
                    partizip2 = ?,
                    auto_detected = ?,
                    detection_reason = ?
                WHERE id = ?
            """,
                (
                    entry.german,
                    entry.translation,
                    entry.pos.value,
                    entry.gender.value if entry.gender else None,
                    entry.plural,
                    entry.hilfsverb,
                    entry.verb_prefix,
                    entry.verb_form,
                    entry.lemma,
                    entry.praeteritum,
                    entry.partizip2,
                    1 if entry.auto_detected else 0,
                    entry.detection_reason,
                    entry.id,
                ),
            )
            conn.commit()
            return cur.rowcount > 0

    def _row_to_entry(self, row: sqlite3.Row) -> WordEntry:
        try:
            created_dt = datetime.fromisoformat(row["created_at"])
        except Exception:
            created_dt = datetime.now()

        pos_val = row["pos"]
        pos = PartOfSpeech(pos_val) if pos_val in PartOfSpeech._value2member_map_ else PartOfSpeech.OTHER
        gender = Gender.from_str(row["gender"]) if row["gender"] else None
        keys = row.keys()

        return WordEntry(
            id=row["id"],
            german=row["german"],
            translation=row["translation"],
            pos=pos,
            gender=gender,
            plural=row["plural"],
            hilfsverb=row["hilfsverb"] if "hilfsverb" in keys else None,
            verb_prefix=row["verb_prefix"] if "verb_prefix" in keys else None,
            verb_form=row["verb_form"] if "verb_form" in keys else None,
            lemma=row["lemma"] if "lemma" in keys else None,
            praeteritum=row["praeteritum"] if "praeteritum" in keys else None,
            partizip2=row["partizip2"] if "partizip2" in keys else None,
            auto_detected=bool(row["auto_detected"]),
            detection_reason=row["detection_reason"],
            created_at=created_dt,
        )

    def get_all_words(self, order: str = "ASC") -> List[WordEntry]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM words ORDER BY created_at {order}, id {order}")
            return [self._row_to_entry(r) for r in cur.fetchall()]

    def get_words_for_day(self, target_date: date) -> List[WordEntry]:
        date_prefix = target_date.strftime("%Y-%m-%d")
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM words WHERE created_at LIKE ? ORDER BY created_at ASC, id ASC",
                (f"{date_prefix}%",),
            )
            return [self._row_to_entry(r) for r in cur.fetchall()]

    def get_words_grouped_by_day(self, limit_days: Optional[int] = None) -> Dict[date, List[WordEntry]]:
        words = self.get_all_words(order="ASC")
        grouped: Dict[date, List[WordEntry]] = {}
        for w in words:
            d = w.created_at.date() if w.created_at else date.today()
            grouped.setdefault(d, []).append(w)

        if limit_days is not None and len(grouped) > limit_days:
            sorted_dates = sorted(grouped.keys())[-limit_days:]
            grouped = {d: grouped[d] for d in sorted_dates}

        return grouped

    def search(self, query: str) -> List[WordEntry]:
        pattern = f"%{query.strip()}%"
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM words WHERE german LIKE ? OR translation LIKE ? OR lemma LIKE ? ORDER BY created_at DESC",
                (pattern, pattern, pattern),
            )
            return [self._row_to_entry(r) for r in cur.fetchall()]

    def get_stats(self) -> dict:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM words")
            total = cur.fetchone()[0]
            cur.execute("SELECT pos, COUNT(*) FROM words GROUP BY pos")
            by_pos = {r[0]: r[1] for r in cur.fetchall()}
            cur.execute("SELECT gender, COUNT(*) FROM words WHERE gender IS NOT NULL GROUP BY gender")
            by_gender = {r[0]: r[1] for r in cur.fetchall()}
            today_prefix = date.today().strftime("%Y-%m-%d")
            cur.execute("SELECT COUNT(*) FROM words WHERE created_at LIKE ?", (f"{today_prefix}%",))
            today_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM words WHERE verb_prefix IS NOT NULL")
            separable_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM words WHERE verb_form IN ('p2', 'prat')")
            verb_forms_count = cur.fetchone()[0]
            return {
                "total": total,
                "today": today_count,
                "by_pos": by_pos,
                "by_gender": by_gender,
                "separable_verbs": separable_count,
                "conjugated_verbs": verb_forms_count,
            }
