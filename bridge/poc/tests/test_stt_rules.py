from bridge_poc.domain import Lang
from bridge_poc.stt import assess, is_hallucination, restrict_language
from bridge_poc.translate import split_sentences


def test_language_is_restricted_to_pt_and_uk():
    lang, prob = restrict_language([("en", 0.6), ("uk", 0.3), ("pt", 0.1)])
    assert lang is Lang.UK and prob > 0.7


def test_russian_counts_as_evidence_for_ukrainian():
    lang, _ = restrict_language([("ru", 0.5), ("en", 0.3), ("pt", 0.1), ("uk", 0.05)])
    assert lang is Lang.UK


def test_spanish_counts_as_evidence_for_portuguese():
    lang, _ = restrict_language([("es", 0.6), ("uk", 0.1), ("pt", 0.05)])
    assert lang is Lang.PT


def test_uncertain_words_are_marked_not_removed():
    tr = assess([(" eu", 0.95), (" amo", 0.2), (" você", 0.9)], -0.3, 0.01, Lang.PT, 1.0)
    assert tr.text == "eu amo você"
    assert [w.uncertain for w in tr.words] == [False, True, False]


def test_many_uncertain_words_mean_low_confidence():
    tr = assess([(" a", 0.2), (" b", 0.3), (" c", 0.9)], -0.3, 0.01, Lang.PT, 1.0)
    assert tr.low_confidence


def test_bad_logprob_means_low_confidence():
    assert assess([(" oi", 0.9)], -1.2, 0.01, Lang.PT, 1.0).low_confidence
    assert not assess([(" oi", 0.9)], -0.3, 0.01, Lang.PT, 1.0).low_confidence


def test_probable_non_speech_is_dropped():
    tr = assess([(" obrigado", 0.5)], -1.5, 0.9, Lang.PT, 1.0)
    assert tr.is_empty


def test_known_hallucinations_are_dropped():
    assert is_hallucination("Legendas pela comunidade Amara.org")
    assert is_hallucination("Дякую за перегляд!")
    assert not is_hallucination("Obrigado, amor")
    assert assess([(" Субтитри", 0.9), (" зроблені", 0.9)], -0.2, 0.1, Lang.UK, 1.0).is_empty


def test_split_sentences():
    assert split_sentences("Oi. Tudo bem? Sim!  ") == ["Oi.", "Tudo bem?", "Sim!"]
    assert split_sentences("   ") == []
