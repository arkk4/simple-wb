from typing import Optional, Tuple
from .models import PartOfSpeech, Gender

# Unambiguous feminine noun suffixes (die)
UNAMBIGUOUS_FEMININE_SUFFIXES = [
    "-ung", "-heit", "-keit", "-schaft", "-tion", "-sion", "-tät", "-ik",
    "-ie", "-ei", "-ur", "-enz", "-anz", "-ade", "-age", "-in", "-thek"
]

# Masculine noun suffixes (der)
MASCULINE_SUFFIXES = [
    "-ling", "-ismus", "-ist", "-or", "-ant", "-ent", "-eur", "-ör",
    "-ich", "-ig", "-ast"
]

# Neuter noun suffixes (das)
NEUTER_SUFFIXES = [
    "-chen", "-lein", "-ment", "-um", "-tum", "-ma", "-ium"
]


class GermanDetector:
    """
    Rules and heuristics for auto-detecting German part of speech and gender.
    """

    @classmethod
    def detect(cls, raw_word: str) -> Tuple[PartOfSpeech, Optional[Gender], Optional[str], Optional[str]]:
        """
        Returns: (pos, gender, corrected_word, reason)
        """
        word = raw_word.strip()
        if not word:
            return PartOfSpeech.OTHER, None, word, None

        # Multi-word phrase
        if " " in word and not word.startswith(("der ", "die ", "das ")):
            if word.endswith(("en", "eln", "ern")):
                return PartOfSpeech.PHRASE, None, word, "phrase (inf)"
            return PartOfSpeech.PHRASE, None, word, "phrase"

        word_lower = word.lower()
        is_capitalized = word[0].isupper()

        # 1. Lowercase word:
        if not is_capitalized:
            # A. Feminine noun suffixes (user forgot capitalization: zeitung -> die Zeitung)
            for sfx in UNAMBIGUOUS_FEMININE_SUFFIXES:
                ending = sfx.lstrip("-")
                if word_lower.endswith(ending) and len(word_lower) > len(ending) + 1:
                    corrected = word[0].upper() + word[1:]
                    return PartOfSpeech.NOUN, Gender.FEMININE, corrected, f"suffix {sfx}"

            for sfx in ("-ismus", "-ling", "-ist"):
                ending = sfx.lstrip("-")
                if word_lower.endswith(ending) and len(word_lower) > len(ending) + 1:
                    corrected = word[0].upper() + word[1:]
                    return PartOfSpeech.NOUN, Gender.MASCULINE, corrected, f"suffix {sfx}"

            # B. Verb infinitive: ends with -en, -eln, -ern
            if word_lower.endswith(("en", "eln", "ern")) and len(word_lower) >= 4:
                return PartOfSpeech.VERB, None, word, "verb ending (-en/-eln/-ern)"

            # C. Partizip II pattern: ge-...-t or ge-...-en (e.g. gemacht, gereist, gelaufen)
            if word_lower.startswith("ge") and (word_lower.endswith("t") or word_lower.endswith("en")) and len(word_lower) >= 5:
                return PartOfSpeech.VERB, None, word, "participle pattern (ge-...)"

            # D. Adjectives: typical suffixes
            adj_endings = ("lich", "isch", "ig", "bar", "sam", "haft", "los", "voll", "abel", "ibel")
            for sfx in adj_endings:
                if word_lower.endswith(sfx) and len(word_lower) > len(sfx) + 1:
                    return PartOfSpeech.ADJ, None, word, f"adj suffix -{sfx}"

            return PartOfSpeech.OTHER, None, word, None

        # 2. Capitalized word (Nomen):
        # A. Feminine
        for sfx in UNAMBIGUOUS_FEMININE_SUFFIXES:
            ending = sfx.lstrip("-")
            if word_lower.endswith(ending) and len(word_lower) > len(ending) + 1:
                return PartOfSpeech.NOUN, Gender.FEMININE, word, f"suffix {sfx}"

        # B. Neuter
        for sfx in NEUTER_SUFFIXES:
            ending = sfx.lstrip("-")
            if word_lower.endswith(ending) and len(word_lower) > len(ending) + 1:
                return PartOfSpeech.NOUN, Gender.NEUTER, word, f"suffix {sfx}"

        # Prefix Ge- (Gebäude, Gefühl, Gespräch, Gesetz)
        if word.startswith("Ge") and len(word) > 4:
            if word.endswith("e") or word.endswith(("el", "er", "t")):
                return PartOfSpeech.NOUN, Gender.NEUTER, word, "prefix Ge-"

        # -nis (das Ergebnis, das Geheimnis)
        if word.endswith("nis") and len(word) > 4:
            return PartOfSpeech.NOUN, Gender.NEUTER, word, "suffix -nis"

        # -o for loanwords: das Auto, das Foto, das Kino, das Büro
        if word.endswith("o") and len(word) >= 3:
            return PartOfSpeech.NOUN, Gender.NEUTER, word, "ending -o (neuter)"

        # C. Masculine
        for sfx in MASCULINE_SUFFIXES:
            ending = sfx.lstrip("-")
            if word_lower.endswith(ending) and len(word_lower) > len(ending) + 1:
                return PartOfSpeech.NOUN, Gender.MASCULINE, word, f"suffix {sfx}"

        # -er (der Fahrer, Lehrer, Wecker)
        if word.endswith("er") and len(word) > 4:
            return PartOfSpeech.NOUN, Gender.MASCULINE, word, "suffix -er (masculine)"

        # -e (die Lampe, die Sonne, die Frage)
        if word.endswith("e") and len(word) >= 4:
            return PartOfSpeech.NOUN, Gender.FEMININE, word, "ending -e (feminine)"

        # Default capitalized word is Nomen
        return PartOfSpeech.NOUN, None, word, "capital letter (noun)"
