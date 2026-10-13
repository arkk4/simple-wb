import os
import sqlite3
from typing import NamedTuple, Optional, List
from .models import PartOfSpeech, Gender, detect_separable_prefix

DEFAULT_DICT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "dictionary.db"
)


class VerbInfo(NamedTuple):
    infinitive: str
    praeteritum: Optional[str]
    partizip2: Optional[str]
    hilfsverb: Optional[str]
    form: str  # "inf", "p2", "prat"


class DictResult(NamedTuple):
    pos: PartOfSpeech
    gender: Optional[Gender]
    extra: Optional[str]                 # noun → plural form; verb → hilfsverb (haben/sein); adj → None
    lemma: Optional[str]                 # verb form → infinitive it belongs to; None if this IS base form
    verb_info: Optional[VerbInfo] = None # full verb details (infinitive, praeteritum, partizip2, hilfsverb)


class DictSearchResult(NamedTuple):
    word: str
    pos: PartOfSpeech
    gender: Optional[Gender]
    extra: Optional[str]
    lemma: Optional[str]
    form: Optional[str]
    verb_info: Optional[VerbInfo]
    display_german: str
    matched_form: Optional[str] = None


class GermanDictionary:
    def __init__(self, db_path: str = DEFAULT_DICT_PATH):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> Optional[sqlite3.Connection]:
        if self._conn is None:
            if os.path.exists(self.db_path):
                self._conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        return self._conn

    def is_available(self) -> bool:
        return os.path.exists(self.db_path)

    def _fetch_verb_info(self, cur: sqlite3.Cursor, lemma_or_word: str, form: Optional[str], fallback_hilfsverb: Optional[str]) -> Optional[VerbInfo]:
        """Fetch complete verb conjugation details from verb_forms table."""
        cur.execute(
            "SELECT infinitive, praeteritum, partizip2, hilfsverb FROM verb_forms WHERE infinitive = ? LIMIT 1",
            (lemma_or_word,),
        )
        row = cur.fetchone()
        if not row:
            cur.execute(
                "SELECT infinitive, praeteritum, partizip2, hilfsverb FROM verb_forms WHERE lower(infinitive) = lower(?) LIMIT 1",
                (lemma_or_word,),
            )
            row = cur.fetchone()
        if row:
            inf, prat, p2, hv = row
            return VerbInfo(
                infinitive=inf,
                praeteritum=prat,
                partizip2=p2,
                hilfsverb=hv or fallback_hilfsverb,
                form=form or "inf",
            )
        return VerbInfo(
            infinitive=lemma_or_word,
            praeteritum=None,
            partizip2=None,
            hilfsverb=fallback_hilfsverb,
            form=form or "inf",
        )

    def lookup(self, word: str) -> Optional[DictResult]:
        """
        Look up a word in the offline dictionary.

        Returns DictResult or None.
        - For nouns: extra = plural form, lemma = None
        - For infinitives: extra = hilfsverb, lemma = None, verb_info = VerbInfo(...)
        - For Partizip II / Präteritum: extra = hilfsverb, lemma = infinitive, verb_info = VerbInfo(...)
        - For adjectives: extra = None, lemma = None
        """
        conn = self._get_conn()
        if not conn:
            return None

        clean = word.strip()
        if not clean:
            return None

        cur = conn.cursor()

        # 1. Exact match
        cur.execute(
            "SELECT pos, gender, plural, lemma, form, word FROM dictionary WHERE word = ? LIMIT 1", (clean,)
        )
        row = cur.fetchone()
        if row:
            pos_str, gender_str, extra, lemma, form, orig_word = row
            pos = PartOfSpeech(pos_str) if pos_str in PartOfSpeech._value2member_map_ else PartOfSpeech.OTHER
            gender = Gender.from_str(gender_str) if gender_str else None
            verb_info = None
            if pos == PartOfSpeech.VERB:
                infinitive_to_lookup = lemma if lemma else orig_word
                verb_info = self._fetch_verb_info(cur, infinitive_to_lookup, form, extra)
            return DictResult(pos=pos, gender=gender, extra=extra, lemma=lemma, verb_info=verb_info)

        # 2. Case-insensitive match
        cur.execute(
            "SELECT pos, gender, plural, lemma, form, word FROM dictionary WHERE word_lower = ? LIMIT 1",
            (clean.lower(),),
        )
        row = cur.fetchone()
        if row:
            pos_str, gender_str, extra, lemma, form, orig_word = row
            pos = PartOfSpeech(pos_str) if pos_str in PartOfSpeech._value2member_map_ else PartOfSpeech.OTHER
            gender = Gender.from_str(gender_str) if gender_str else None
            verb_info = None
            if pos == PartOfSpeech.VERB:
                infinitive_to_lookup = lemma if lemma else orig_word
                verb_info = self._fetch_verb_info(cur, infinitive_to_lookup, form, extra)
            return DictResult(pos=pos, gender=gender, extra=extra, lemma=lemma, verb_info=verb_info)

        # 3. Compound noun fallback (Haustür → find Tür)
        if len(clean) > 5 and clean[0].isupper():
            for i in range(4, len(clean) - 2):
                suffix = clean[i:]
                suffix_cap = suffix[0].upper() + suffix[1:] if suffix[0].islower() else suffix
                cur.execute(
                    "SELECT pos, gender, plural, lemma, form, word FROM dictionary WHERE word = ? AND pos = 'noun' LIMIT 1",
                    (suffix_cap,),
                )
                row = cur.fetchone()
                if row:
                    pos_str, gender_str, extra, lemma, form, orig_word = row
                    pos = PartOfSpeech(pos_str) if pos_str in PartOfSpeech._value2member_map_ else PartOfSpeech.OTHER
                    gender = Gender.from_str(gender_str) if gender_str else None
                    return DictResult(pos=pos, gender=gender, extra=extra, lemma=lemma, verb_info=None)

        return None

    def search_dict(self, pattern: str, limit: int = 25) -> List[DictSearchResult]:
        """
        Wildcard, inflected form, and substring search in offline dictionary.
        Supports:
            ging        → finds 'gehen' (with matched form note 'ging, Prät')
            Häuser      → finds 'das Haus' (with matched form note 'Häuser, Pl')
            *ging       → words whose forms end with 'ging' (e.g. gehen, begehen, umgehen)
            *machen     → words ending with 'machen' (e.g. aufmachen, anmachen)
            machen*     → words starting with 'machen'
            haus        → exact match, prefix, and substring matches
        """
        conn = self._get_conn()
        if not conn:
            return []

        cur = conn.cursor()
        raw = pattern.strip()
        if not raw:
            return []

        clean = raw.lower().replace("*", "")
        is_wildcard = "*" in raw

        if is_wildcard:
            sql_pat = raw.replace("*", "%").lower()
        else:
            sql_pat = f"%{clean}%"

        def _fmt_form(form_code: Optional[str]) -> str:
            return {"prat": "Prät", "p2": "P2", "pl": "Pl"}.get(form_code or "", form_code or "")

        candidates = []
        seen = set()

        def _add(orig_word: str, pos_str: str, gender_str: Optional[str], extra: Optional[str],
                 lemma: Optional[str], form: Optional[str], matched_form_str: Optional[str] = None,
                 priority: int = 2):
            pos = PartOfSpeech(pos_str) if pos_str in PartOfSpeech._value2member_map_ else PartOfSpeech.OTHER
            gender = Gender.from_str(gender_str) if gender_str else None
            key = (orig_word.lower(), pos)
            if key in seen:
                return
            seen.add(key)

            display = orig_word
            verb_info = None
            if pos == PartOfSpeech.VERB:
                verb_info = self._fetch_verb_info(cur, orig_word, form or "inf", extra)
                pfx = detect_separable_prefix(orig_word)
                if pfx and orig_word.lower().startswith(pfx) and len(orig_word) > len(pfx):
                    display = f"{pfx}|{orig_word[len(pfx):]}"
            elif pos == PartOfSpeech.NOUN and gender:
                display = f"{gender.article} {orig_word}"

            candidates.append((
                priority,
                len(orig_word),
                orig_word,
                DictSearchResult(
                    word=orig_word,
                    pos=pos,
                    gender=gender,
                    extra=extra,
                    lemma=lemma,
                    form=form,
                    verb_info=verb_info,
                    display_german=display,
                    matched_form=matched_form_str,
                )
            ))

        # 1. Exact match on inflected forms (e.g. 'ging' -> resolves to base 'gehen')
        if not is_wildcard:
            cur.execute(
                """
                SELECT DISTINCT d_base.word, d_base.pos, d_base.gender, d_base.plural,
                                d_base.lemma, d_base.form, d_form.word, d_form.form
                FROM dictionary d_form
                JOIN dictionary d_base ON lower(d_form.lemma) = d_base.word_lower
                     AND (d_base.form IS NULL OR d_base.form = 'inf')
                WHERE d_form.word_lower = ? AND d_form.lemma IS NOT NULL
                """,
                (clean,),
            )
            for row in cur.fetchall():
                bw, bp, bg, be, bl, bf, fw, ff = row
                flabel = _fmt_form(ff)
                mf = f"{fw}, {flabel}" if flabel else fw
                _add(bw, bp, bg, be, bl, bf, matched_form_str=mf, priority=0)

            # Exact match on base word itself (e.g. 'gehen' -> 'gehen')
            cur.execute(
                """
                SELECT word, pos, gender, plural, lemma, form
                FROM dictionary
                WHERE word_lower = ? AND (form IS NULL OR form = 'inf')
                """,
                (clean,),
            )
            for row in cur.fetchall():
                _add(*row, priority=0)

        # 2. Form matches via wildcard / pattern (e.g. '*ging' finds 'begehen', 'umgehen', etc.)
        cur.execute(
            """
            SELECT DISTINCT d_base.word, d_base.pos, d_base.gender, d_base.plural,
                            d_base.lemma, d_base.form, d_form.word, d_form.form
            FROM dictionary d_form
            JOIN dictionary d_base ON lower(d_form.lemma) = d_base.word_lower
                 AND (d_base.form IS NULL OR d_base.form = 'inf')
            WHERE d_form.word_lower LIKE ? AND d_form.lemma IS NOT NULL
            LIMIT ?
            """,
            (sql_pat, limit * 2),
        )
        for row in cur.fetchall():
            bw, bp, bg, be, bl, bf, fw, ff = row
            flabel = _fmt_form(ff)
            mf = f"{fw}, {flabel}" if flabel else fw
            prio = 1 if fw.lower().startswith(clean) else 2
            _add(bw, bp, bg, be, bl, bf, matched_form_str=mf, priority=prio)

        # 3. Base word matches
        cur.execute(
            """
            SELECT DISTINCT word, pos, gender, plural, lemma, form
            FROM dictionary
            WHERE word_lower LIKE ? AND (form IS NULL OR form = 'inf')
            LIMIT ?
            """,
            (sql_pat, limit * 2),
        )
        for row in cur.fetchall():
            w = row[0]
            prio = 1 if w.lower().startswith(clean) else 2
            _add(*row, priority=prio)

        # Sort: priority (0=exact, 1=prefix, 2=substring), then word length, then alphabetical
        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        return [item[3] for item in candidates[:limit]]

    def get_verb_forms(self, verb_or_form: str) -> Optional[VerbInfo]:
        """Look up verb conjugation details directly by infinitive or conjugated form."""
        conn = self._get_conn()
        if not conn:
            return None
        cur = conn.cursor()
        clean = verb_or_form.strip().lower()

        # Check verb_forms directly by infinitive
        cur.execute(
            "SELECT infinitive, praeteritum, partizip2, hilfsverb FROM verb_forms WHERE lower(infinitive) = ? LIMIT 1",
            (clean,),
        )
        row = cur.fetchone()
        if row:
            inf, prat, p2, hv = row
            return VerbInfo(infinitive=inf, praeteritum=prat, partizip2=p2, hilfsverb=hv, form="inf")

        # Check by partizip2 or praeteritum
        cur.execute(
            "SELECT infinitive, praeteritum, partizip2, hilfsverb FROM verb_forms WHERE lower(partizip2) = ? LIMIT 1",
            (clean,),
        )
        row = cur.fetchone()
        if row:
            inf, prat, p2, hv = row
            return VerbInfo(infinitive=inf, praeteritum=prat, partizip2=p2, hilfsverb=hv, form="p2")

        cur.execute(
            "SELECT infinitive, praeteritum, partizip2, hilfsverb FROM verb_forms WHERE lower(praeteritum) = ? LIMIT 1",
            (clean,),
        )
        row = cur.fetchone()
        if row:
            inf, prat, p2, hv = row
            return VerbInfo(infinitive=inf, praeteritum=prat, partizip2=p2, hilfsverb=hv, form="prat")

        return None
