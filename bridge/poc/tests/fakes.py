"""Implementações falsas para testar o pipeline sem modelos de IA."""

from __future__ import annotations

import numpy as np

from bridge_poc.domain import Lang, Transcript, Word
from bridge_poc.stt import assess

SR = 16000


def tone(seconds: float, freq: float = 220.0, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SR), dtype=np.float32)


class FakeTranscriber:
    """O 'idioma' do áudio é codificado na frequência do tom: 220 Hz = pt, 440 Hz = uk."""

    device = "cpu"

    def __init__(self, texts: dict[Lang, str] | None = None, lang_prob: float = 0.95):
        self.texts = texts or {Lang.PT: "olá amor", Lang.UK: "привіт коханий"}
        self.lang_prob = lang_prob
        self.calls: list[tuple[Lang, bool]] = []

    @staticmethod
    def _freq(audio: np.ndarray) -> float:
        spec = np.abs(np.fft.rfft(audio))
        return float(np.argmax(spec) * SR / len(audio))

    def detect_language(self, audio: np.ndarray):
        lang = Lang.PT if self._freq(audio) < 330 else Lang.UK
        return lang, self.lang_prob

    def transcribe(self, audio: np.ndarray, lang: Lang, fast: bool = False) -> Transcript:
        self.calls.append((lang, fast))
        words = [(" " + w, 0.9) for w in self.texts[lang].split()]
        return assess(words, -0.2, 0.01, lang, 1.0)


class FakeTranslator:
    def __init__(self):
        self.calls: list[tuple[str, Lang, Lang]] = []

    def translate(self, text: str, src: Lang, tgt: Lang) -> str:
        self.calls.append((text, src, tgt))
        return f"<{tgt.value}>{text}"


def make_transcript(text: str, lang: Lang = Lang.PT) -> Transcript:
    return Transcript(text, lang, 1.0, (Word(text, 0.9, False),), -0.2, 0.0, False)
