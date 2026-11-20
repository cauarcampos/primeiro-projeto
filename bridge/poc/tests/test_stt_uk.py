from bridge_poc.domain import Lang, Transcript, Word
from bridge_poc.stt import assess
from bridge_poc.stt_uk import UkrainianBoostedTranscriber, merge_with_reference

from .fakes import FakeTranscriber, tone


def ref(text, probs=None):
    toks = text.split()
    probs = probs or [0.9] * len(toks)
    return assess([(" " + t, p) for t, p in zip(toks, probs)], -0.3, 0.01, Lang.UK, 1.0)


def test_words_confirmed_by_whisper_are_certain():
    tr = merge_with_reference("Привіт, коханий! Як справи?", ref("привіт коханий як справи"))
    assert tr.text == "Привіт, коханий! Як справи?"
    assert not any(w.uncertain for w in tr.words)
    assert not tr.low_confidence


def test_disagreeing_words_are_marked_uncertain():
    tr = merge_with_reference("Я купила хліб у Сільпо", ref("я купила хліб у сільського"))
    flags = {w.text.strip(): w.uncertain for w in tr.words}
    assert flags["Сільпо"] is True and flags["хліб"] is False


def test_mostly_disagreeing_is_low_confidence():
    tr = merge_with_reference("один два три чотири", ref("п'ять шість сім чотири"))
    assert tr.low_confidence


class FakeParakeet:
    def __init__(self, text):
        self.text, self.calls = text, 0

    def __call__(self, audio):
        self.calls += 1
        return self.text


def test_portuguese_goes_to_whisper_only():
    p = FakeParakeet("не має значення")
    t = UkrainianBoostedTranscriber(FakeTranscriber(), p)
    assert t.transcribe(tone(1), Lang.PT).text == "olá amor."
    assert p.calls == 0


def test_ukrainian_uses_parakeet_text_checked_by_whisper():
    w = FakeTranscriber({Lang.PT: "x", Lang.UK: "привіт коханий!"})
    t = UkrainianBoostedTranscriber(w, FakeParakeet("Привіт, коханий!"))
    tr = t.transcribe(tone(1), Lang.UK)
    assert tr.text == "Привіт, коханий!" and not tr.low_confidence
    partial = t.transcribe(tone(1), Lang.UK, fast=True)
    assert partial.text == "Привіт, коханий!"
    assert w.calls[-1] == (Lang.UK, False)  # parcial não chamou o Whisper


def test_parakeet_hallucination_is_dropped():
    t = UkrainianBoostedTranscriber(FakeTranscriber(), FakeParakeet("Дякую за перегляд!"))
    assert t.transcribe(tone(1), Lang.UK).is_empty
