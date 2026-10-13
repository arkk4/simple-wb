import re
from typing import Optional, Tuple
from .models import PartOfSpeech, Gender, WordEntry, detect_separable_prefix
from .dictionary import GermanDictionary
from .detector import GermanDetector
from .translator import WordTranslator


def _parse_form_operators(raw_str: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Extract stem, Partizip II (>) and Präteritum (>>) from strings with operators.
    Example:
        machen > gemacht >> machte     -> stem='machen', p2='gemacht', prat='machte'
        machen >> machte > gemacht     -> stem='machen', p2='gemacht', prat='machte'
        auf|stehen > aufgestanden >> stand auf -> stem='auf|stehen', p2='aufgestanden', prat='stand auf'
    """
    if ">" not in raw_str:
        return raw_str, None, None

    # Replace >> with a distinct placeholder \x01 so single > is unambiguous
    s = raw_str.replace(">>", "\x01")
    parts = re.split(r"([\x01>])", s)
    stem = parts[0].strip()

    single_form = None  # form following single >
    double_form = None  # form following double >> (\x01)

    current_op = None
    for part in parts[1:]:
        if part in ("\x01", ">"):
            current_op = part
        elif current_op:
            val = part.strip()
            if current_op == "\x01":
                double_form = val
            elif current_op == ">":
                single_form = val
            current_op = None

    # By convention: > is Partizip II, >> is Präteritum
    p2 = single_form
    prat = double_form

    # Smart disambiguation:
    # If p2 looks like Präteritum (e.g. ends with -te or no ge-) and prat starts with ge-:
    if p2 and prat:
        p2_lower = p2.lower()
        prat_lower = prat.lower()
        if not p2_lower.startswith("ge") and prat_lower.startswith("ge"):
            p2, prat = prat, p2
        elif (p2_lower.endswith("te") or p2_lower.endswith("ten")) and not (prat_lower.endswith("te") or prat_lower.endswith("ten")):
            p2, prat = prat, p2

    return stem, p2, prat


class InputParser:
    def __init__(
        self,
        dictionary: Optional[GermanDictionary] = None,
        translator: Optional[WordTranslator] = None,
    ):
        self.dictionary = dictionary or GermanDictionary()
        self.translator = translator or WordTranslator()

    def parse_line(self, line: str) -> Optional[WordEntry]:
        """
        Parse a user input line. Supported formats:

        Nouns:
            das Kind - child          (explicit article)
            Kind - child              (auto-detect via dict → ~das)
            Zeitung                   (auto-detect via dict + auto-translation)

        Verbs (Infinitive / Partizip II / Präteritum):
            machen - to do            (auto-detect via dict → ~verb, shows [haben], (machte, hat gemacht))
            machen > gemacht >> machte - to do   (fast operator syntax for P2 and Präteritum)
            machen >> machte > gemacht           (same, auto-translated if no translation)
            auf|stehen > aufgestanden >> stand auf - to get up
            gefahren - driven         (auto-detect via dict → ~verb [sein] (P2 of fahren))
            p2 gefahren - driven      (manual prefix: p2/partizip)
            fuhr - drove              (auto-detect via dict → ~verb [sein] (Prät of fahren))
            prat fuhr - drove         (manual prefix: prat/prät/pret)

        Adjectives:
            adj schön - beautiful     (manual prefix)
            schön - beautiful         (auto-detect via dict or suffix)
        """
        line = line.strip()
        if not line or line.startswith("#"):
            return None

        # Split on separator: - — – : =
        match = re.split(r"\s*(?:[-—–:=])\s*", line, maxsplit=1)
        if len(match) == 2:
            left_part, translation = match[0].strip(), match[1].strip()
        else:
            parts = line.split(maxsplit=1)
            # If second part contains non-ASCII and first is a German word
            if len(parts) == 2 and any(ord(c) > 127 for c in parts[1]):
                left_part, translation = parts[0].strip(), parts[1].strip()
            else:
                left_part, translation = line, ""

        if not left_part:
            return None

        pos: Optional[PartOfSpeech] = None
        gender: Optional[Gender] = None
        auto_detected = False
        reason: Optional[str] = None
        plural: Optional[str] = None
        hilfsverb: Optional[str] = None
        verb_prefix: Optional[str] = None
        verb_form: Optional[str] = None
        lemma: Optional[str] = None
        praeteritum: Optional[str] = None
        partizip2: Optional[str] = None

        explicit_verb_form: Optional[str] = None
        raw_german = left_part

        # 0. Check for form operators > (Partizip II) and >> (Präteritum)
        explicit_p2 = None
        explicit_prat = None
        if ">" in raw_german:
            stem, explicit_p2, explicit_prat = _parse_form_operators(raw_german)
            raw_german = stem
            pos = PartOfSpeech.VERB
            partizip2 = explicit_p2
            praeteritum = explicit_prat

        # 1. Check for explicit separable notation: auf|machen
        pipe_match = re.match(r"^([a-zäöüß]+)\|([a-zäöüßA-ZÄÖÜ].+)$", raw_german)
        if pipe_match:
            verb_prefix = pipe_match.group(1).lower()
            stem = pipe_match.group(2)
            raw_german = verb_prefix + stem   # reconstruct full infinitive
            pos = PartOfSpeech.VERB
            auto_detected = False
            # Look up in dict for hilfsverb and forms
            if self.dictionary.is_available():
                dict_res = self.dictionary.lookup(raw_german)
                if dict_res and dict_res.pos == PartOfSpeech.VERB:
                    hilfsverb = dict_res.extra
                    if dict_res.verb_info:
                        praeteritum = explicit_prat or dict_res.verb_info.praeteritum
                        partizip2 = explicit_p2 or dict_res.verb_info.partizip2
                        hilfsverb = dict_res.verb_info.hilfsverb or hilfsverb

        # 2. Manual POS / form prefixes:
        #    verb machen / adj schön / noun Tisch / p2 gefahren / prat fuhr
        if pos is None:
            prefix_match = re.match(
                r"^(adj|adjektiv|a|verb|v|nomen|noun|n|subst|adv|phrase|p2|partizip2?|prat|prät|pret|präteritum)\s+(.+)$",
                raw_german,
                flags=re.IGNORECASE,
            )
            if prefix_match:
                prefix = prefix_match.group(1).lower()
                raw_german = prefix_match.group(2).strip()
                if prefix in ("adj", "adjektiv", "a"):
                    pos = PartOfSpeech.ADJ
                elif prefix in ("verb", "v"):
                    pos = PartOfSpeech.VERB
                elif prefix in ("p2", "partizip", "partizip2"):
                    pos = PartOfSpeech.VERB
                    explicit_verb_form = "p2"
                elif prefix in ("prat", "prät", "pret", "präteritum"):
                    pos = PartOfSpeech.VERB
                    explicit_verb_form = "prat"
                elif prefix in ("nomen", "noun", "n", "subst"):
                    pos = PartOfSpeech.NOUN
                elif prefix == "adv":
                    pos = PartOfSpeech.ADV
                elif prefix == "phrase":
                    pos = PartOfSpeech.PHRASE

                # Try looking up in dictionary to populate forms/hilfsverb
                if self.dictionary.is_available():
                    dict_res = self.dictionary.lookup(raw_german)
                    if dict_res:
                        if pos == PartOfSpeech.VERB and dict_res.verb_info:
                            vi = dict_res.verb_info
                            hilfsverb = vi.hilfsverb or dict_res.extra
                            praeteritum = explicit_prat or vi.praeteritum
                            partizip2 = explicit_p2 or vi.partizip2
                            lemma = dict_res.lemma or (vi.infinitive if vi.form != "inf" else None)
                            verb_form = explicit_verb_form or vi.form
                        elif pos == PartOfSpeech.NOUN and dict_res.pos == PartOfSpeech.NOUN:
                            gender = dict_res.gender
                            plural = dict_res.extra

        # 3. Explicit article: der Hund / die Katze / das Haus
        art_match = re.match(r"^(der|die|das)\s+(.+)$", raw_german, flags=re.IGNORECASE)
        if art_match and pos is None:
            article_str = art_match.group(1).lower()
            raw_german = art_match.group(2).strip()
            gender = Gender.from_article(article_str)
            pos = PartOfSpeech.NOUN
            auto_detected = False
            if self.dictionary.is_available():
                dict_res = self.dictionary.lookup(raw_german)
                if dict_res and dict_res.pos == PartOfSpeech.NOUN:
                    plural = dict_res.extra

        # 4. Dictionary lookup (when POS/gender still unknown)
        if gender is None and (pos is None or (pos == PartOfSpeech.VERB and (hilfsverb is None or partizip2 is None))):
            dict_found = False
            if self.dictionary.is_available():
                dict_res = self.dictionary.lookup(raw_german)
                if dict_res:
                    dict_found = True
                    if pos is None:
                        pos = dict_res.pos
                    if dict_res.pos == PartOfSpeech.NOUN:
                        plural = dict_res.extra
                        if dict_res.gender:
                            gender = dict_res.gender
                            auto_detected = True
                            reason = "dict"
                    elif dict_res.pos == PartOfSpeech.VERB:
                        hilfsverb = hilfsverb or dict_res.extra
                        if pos != PartOfSpeech.VERB:
                            auto_detected = True
                        if dict_res.verb_info:
                            vi = dict_res.verb_info
                            praeteritum = explicit_prat or praeteritum or vi.praeteritum
                            partizip2 = explicit_p2 or partizip2 or vi.partizip2
                            hilfsverb = vi.hilfsverb or hilfsverb
                            verb_form = explicit_verb_form or verb_form or vi.form
                            if vi.form == "p2" and not explicit_p2:
                                lemma = dict_res.lemma or vi.infinitive
                                reason = f"dict (P2 of {lemma})"
                            elif vi.form == "prat" and not explicit_prat:
                                lemma = dict_res.lemma or vi.infinitive
                                reason = f"dict (Prät of {lemma})"
                            else:
                                verb_form = "inf"
                                reason = reason or "dict (verb)"
                        else:
                            verb_form = verb_form or "inf"
                            reason = reason or "dict (verb)"
                    elif dict_res.pos == PartOfSpeech.ADJ:
                        auto_detected = True
                        reason = "dict (adj)"

            # 5. Heuristic fallback
            if not dict_found or (pos == PartOfSpeech.NOUN and gender is None):
                heur_pos, heur_gender, corrected_word, heur_reason = GermanDetector.detect(raw_german)
                raw_german = corrected_word
                if pos is None:
                    pos = heur_pos
                    if heur_pos != PartOfSpeech.OTHER:
                        auto_detected = True
                        reason = heur_reason
                if gender is None and heur_gender is not None:
                    gender = heur_gender
                    auto_detected = True
                    reason = heur_reason

        # 6. Verb separable prefix handling
        if pos == PartOfSpeech.VERB:
            verb_form = explicit_verb_form or verb_form or "inf"
            base_for_prefix = lemma if lemma else raw_german
            if verb_prefix is None:
                detected_pfx = detect_separable_prefix(base_for_prefix)
                if detected_pfx:
                    verb_prefix = detected_pfx

            # If still missing forms or hilfsverb, try lookup with infinitive/base
            if (hilfsverb is None or (praeteritum is None and partizip2 is None)) and self.dictionary.is_available():
                query_target = lemma if lemma else raw_german
                dict_res = self.dictionary.lookup(query_target)
                if dict_res and dict_res.verb_info:
                    vi = dict_res.verb_info
                    if hilfsverb is None:
                        hilfsverb = vi.hilfsverb
                    if praeteritum is None and not explicit_prat:
                        praeteritum = vi.praeteritum
                    if partizip2 is None and not explicit_p2:
                        partizip2 = vi.partizip2

        if pos is None:
            pos = PartOfSpeech.OTHER

        # Capitalize noun lemma if user forgot
        if pos == PartOfSpeech.NOUN and raw_german and raw_german[0].islower():
            raw_german = raw_german[0].upper() + raw_german[1:]

        # Auto-translation fallback if user didn't provide a translation
        if not translation and self.translator:
            # Query translator using clean word
            trans_lookup = raw_german
            if pos == PartOfSpeech.NOUN and gender:
                trans_lookup = f"{gender.article} {raw_german}"
            auto_trans = self.translator.translate(trans_lookup)
            if auto_trans:
                translation = auto_trans

        return WordEntry(
            id=None,
            german=raw_german,
            translation=translation,
            pos=pos,
            gender=gender,
            plural=plural,
            hilfsverb=hilfsverb,
            verb_prefix=verb_prefix,
            verb_form=verb_form,
            lemma=lemma,
            praeteritum=praeteritum,
            partizip2=partizip2,
            auto_detected=auto_detected,
            detection_reason=reason,
        )
