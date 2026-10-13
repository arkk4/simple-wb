from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class PartOfSpeech(str, Enum):
    NOUN = "noun"
    VERB = "verb"
    ADJ = "adj"
    ADV = "adv"
    PHRASE = "phrase"
    OTHER = "other"


class Gender(str, Enum):
    MASCULINE = "m"  # der
    FEMININE = "f"   # die
    NEUTER = "n"     # das

    @property
    def article(self) -> str:
        if self == Gender.MASCULINE:
            return "der"
        if self == Gender.FEMININE:
            return "die"
        if self == Gender.NEUTER:
            return "das"
        return ""

    @classmethod
    def from_article(cls, article: str) -> Optional["Gender"]:
        art = article.strip().lower()
        if art == "der":
            return cls.MASCULINE
        if art == "die":
            return cls.FEMININE
        if art == "das":
            return cls.NEUTER
        return None

    @classmethod
    def from_str(cls, val: str) -> Optional["Gender"]:
        val = val.strip().lower()
        if val in ("m", "masc", "masculine", "der"):
            return cls.MASCULINE
        if val in ("f", "fem", "feminine", "die"):
            return cls.FEMININE
        if val in ("n", "neut", "neuter", "das"):
            return cls.NEUTER
        return None


# Known separable prefixes (trennbare Verben)
SEPARABLE_PREFIXES = frozenset([
    "ab", "an", "auf", "aus", "bei", "da", "dar", "ein", "empor", "fest",
    "fort", "frei", "heim", "her", "hin", "hoch", "los", "mit", "nach",
    "nieder", "vor", "weg", "weiter", "wieder", "zu", "zurück", "zusammen",
    "durch", "über", "um", "unter",  # can be separable
])


def detect_separable_prefix(infinitive: str) -> Optional[str]:
    """Return the separable prefix if the verb is trennbar, else None."""
    word = infinitive.lower()
    for prefix in sorted(SEPARABLE_PREFIXES, key=len, reverse=True):
        if word.startswith(prefix) and len(word) > len(prefix) + 2:
            return prefix
    return None


@dataclass
class WordEntry:
    id: Optional[int]
    german: str                           # Word as entered (or lemma/infinitive)
    translation: str
    pos: PartOfSpeech
    gender: Optional[Gender] = None
    plural: Optional[str] = None          # Plural form for nouns
    hilfsverb: Optional[str] = None       # "haben" or "sein" for verbs
    verb_prefix: Optional[str] = None     # Separable prefix, e.g. "auf" for aufmachen
    verb_form: Optional[str] = None       # "inf", "p2", "prat"
    lemma: Optional[str] = None           # Infinitive lemma for verb forms
    praeteritum: Optional[str] = None     # Präteritum form (e.g. "fuhr")
    partizip2: Optional[str] = None       # Partizip II form (e.g. "gefahren")
    auto_detected: bool = False           # Whether POS/gender was auto-inferred
    detection_reason: Optional[str] = None
    created_at: Optional[datetime] = None

    @property
    def article(self) -> Optional[str]:
        return self.gender.article if self.gender else None

    @property
    def is_separable(self) -> bool:
        return self.verb_prefix is not None

    @property
    def display_german(self) -> str:
        """German word with article for nouns, or auf|machen for separable verbs."""
        if self.is_separable and not self.lemma and self.verb_prefix:
            if self.german.startswith(self.verb_prefix):
                stem = self.german[len(self.verb_prefix):]
                return f"{self.verb_prefix}|{stem}"
        if self.gender:
            return f"{self.article} {self.german}"
        return self.german
