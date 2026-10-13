import os
from simple_wb.parser import InputParser
from simple_wb.models import PartOfSpeech, Gender
from simple_wb.dictionary import GermanDictionary
from simple_wb.storage import WordStorage
from simple_wb.translator import WordTranslator


def test_parser_examples():
    parser = InputParser()

    # 1. Explicit article
    e1 = parser.parse_line("das Kind - child")
    assert e1 is not None and e1.german == "Kind" and e1.gender == Gender.NEUTER
    assert e1.auto_detected is False

    # 2. Auto-detect noun from dict
    e2 = parser.parse_line("Kind - child")
    assert e2 is not None and e2.gender == Gender.NEUTER and e2.auto_detected is True

    # 3. Feminine suffix -ung (dict or heuristic)
    e3 = parser.parse_line("Zeitung - newspaper")
    assert e3 is not None and e3.gender == Gender.FEMININE

    # 4. Heuristic -ung on unknown word
    e4 = parser.parse_line("Wunderung - marvel")
    assert e4 is not None and e4.gender == Gender.FEMININE and e4.auto_detected is True

    # 5. Manual verb prefix
    e5 = parser.parse_line("verb machen - to do")
    assert e5 is not None and e5.german == "machen" and e5.pos == PartOfSpeech.VERB

    # 6. Auto verb from dict with haben and forms
    e6 = parser.parse_line("machen - to do")
    assert e6 is not None and e6.german == "machen" and e6.pos == PartOfSpeech.VERB
    assert e6.hilfsverb == "haben"
    assert e6.praeteritum == "machte"
    assert e6.partizip2 == "gemacht"

    # 7. Verb with sein (fahren)
    e7 = parser.parse_line("fahren - to drive")
    assert e7 is not None and e7.pos == PartOfSpeech.VERB
    assert e7.hilfsverb == "sein"
    assert e7.praeteritum == "fuhr"
    assert e7.partizip2 == "gefahren"

    # 8. Partizip II auto-detected (gefahren)
    e8 = parser.parse_line("gefahren - driven")
    assert e8 is not None and e8.pos == PartOfSpeech.VERB
    assert e8.verb_form == "p2"
    assert e8.lemma == "fahren"
    assert e8.hilfsverb == "sein"

    # 9. Präteritum auto-detected (fuhr)
    e9 = parser.parse_line("fuhr - drove")
    assert e9 is not None and e9.pos == PartOfSpeech.VERB
    assert e9.verb_form == "prat"
    assert e9.lemma == "fahren"
    assert e9.hilfsverb == "sein"

    # 10. Manual P2 prefix
    e10 = parser.parse_line("p2 gemacht - done")
    assert e10 is not None and e10.pos == PartOfSpeech.VERB
    assert e10.verb_form == "p2"
    assert e10.lemma == "machen"
    assert e10.hilfsverb == "haben"

    # 11. Manual Präteritum prefix
    e11 = parser.parse_line("prat liebte - loved")
    assert e11 is not None and e11.pos == PartOfSpeech.VERB
    assert e11.verb_form == "prat"

    # 12. Separable verb: explicit pipe notation
    e12 = parser.parse_line("auf|machen - to open")
    assert e12 is not None and e12.german == "aufmachen"
    assert e12.verb_prefix == "auf"
    assert e12.is_separable is True
    assert e12.pos == PartOfSpeech.VERB

    # 13. Separable verb: auto-detected from full infinitive
    e13 = parser.parse_line("aufstehen - to get up")
    assert e13 is not None and e13.verb_prefix == "auf"
    assert e13.hilfsverb == "sein"
    assert e13.praeteritum == "stand auf"
    assert e13.partizip2 == "aufgestanden"

    # 14. Separable Partizip II auto-detected (aufgestanden)
    e14 = parser.parse_line("aufgestanden - stood up")
    assert e14 is not None and e14.pos == PartOfSpeech.VERB
    assert e14.verb_form == "p2"
    assert e14.lemma == "aufstehen"
    assert e14.hilfsverb == "sein"
    assert e14.verb_prefix == "auf"

    # 15. Separable Präteritum auto-detected (stand auf)
    e15 = parser.parse_line("stand auf - got up")
    assert e15 is not None and e15.pos == PartOfSpeech.VERB
    assert e15.verb_form == "prat"
    assert e15.lemma == "aufstehen"
    assert e15.hilfsverb == "sein"

    # 16. Manual adj prefix & auto adj
    e16 = parser.parse_line("adj schön - beautiful")
    assert e16 is not None and e16.pos == PartOfSpeech.ADJ
    e17 = parser.parse_line("schön - beautiful")
    assert e17 is not None and e17.pos == PartOfSpeech.ADJ

    # 17. Operator syntax: machen > gemacht >> machte
    e18 = parser.parse_line("machen > gemacht >> machte - to do")
    assert e18 is not None and e18.german == "machen"
    assert e18.pos == PartOfSpeech.VERB
    assert e18.partizip2 == "gemacht"
    assert e18.praeteritum == "machte"
    assert e18.hilfsverb == "haben"

    # 18. Operator syntax reversed order: machen >> machte > gemacht
    e19 = parser.parse_line("machen >> machte > gemacht - to do")
    assert e19 is not None and e19.german == "machen"
    assert e19.pos == PartOfSpeech.VERB
    assert e19.partizip2 == "gemacht"
    assert e19.praeteritum == "machte"

    # 19. Separable verb with operator syntax: auf|stehen > aufgestanden >> stand auf
    e20 = parser.parse_line("auf|stehen > aufgestanden >> stand auf - to get up")
    assert e20 is not None and e20.german == "aufstehen"
    assert e20.is_separable is True
    assert e20.verb_prefix == "auf"
    assert e20.partizip2 == "aufgestanden"
    assert e20.praeteritum == "stand auf"

    # 20. Dictionary wildcard search
    d = GermanDictionary()
    search_results = d.search_dict("*machen", limit=10)
    words = [r.word for r in search_results]
    assert "machen" in words
    assert any(w in words for w in ("aufmachen", "anmachen", "abmachen", "zumachen"))

    # 21. Storage update (editing word)
    test_db = "/tmp/test_storage_edit.db"
    if os.path.exists(test_db):
        os.remove(test_db)
    storage = WordStorage(test_db)
    saved = storage.add_word(e1)
    assert saved.id is not None
    loaded = storage.get_word_by_id(saved.id)
    assert loaded is not None and loaded.german == "Kind"
    # Update word
    loaded.translation = "a young child"
    assert storage.update_word(loaded) is True
    updated = storage.get_word_by_id(saved.id)
    assert updated is not None and updated.translation == "a young child"

    # 22. print_help markup validation
    from simple_wb.ui import print_help
    print_help()  # ensures no MarkupError or Rich parsing exceptions

    # 23. Translator batch offline lookup
    t = WordTranslator()
    batch_trans = t.translate_batch(["machen", "aufmachen"])
    assert "machen" in batch_trans
    assert "aufmachen" in batch_trans

    print("All 23 tests passed ✓")


if __name__ == "__main__":
    test_parser_examples()
