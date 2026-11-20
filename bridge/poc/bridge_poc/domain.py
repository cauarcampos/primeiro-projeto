"""Tipos de domínio do BRIDGE (independentes de modelo, áudio ou interface)."""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from enum import Enum


class Lang(str, Enum):
    PT = "pt"
    UK = "uk"

    @property
    def other(self) -> "Lang":
        return Lang.UK if self is Lang.PT else Lang.PT

    @property
    def nllb_code(self) -> str:
        return {Lang.PT: "por_Latn", Lang.UK: "ukr_Cyrl"}[self]

    @property
    def label_pt(self) -> str:
        """Nome do idioma em português (para os rótulos da legenda)."""
        return {Lang.PT: "PORTUGUÊS", Lang.UK: "UCRANIANO"}[self]


SUPPORTED_LANGS: tuple[Lang, ...] = (Lang.PT, Lang.UK)


@dataclass(frozen=True)
class Speaker:
    name: str
    lang: Lang
    is_me: bool = False


@dataclass(frozen=True)
class Word:
    text: str
    probability: float
    uncertain: bool


@dataclass(frozen=True)
class Transcript:
    """Resultado do reconhecimento de fala de um segmento."""

    text: str
    lang: Lang
    lang_probability: float
    words: tuple[Word, ...]
    avg_logprob: float
    no_speech_prob: float
    low_confidence: bool

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


_ids = itertools.count(1)


def next_id() -> int:
    return next(_ids)


@dataclass
class Utterance:
    """Uma fala exibida na legenda (parcial ou final)."""

    segment_id: int
    source_id: str
    speaker: Speaker
    transcript: Transcript
    is_final: bool
    translation: str | None = None
    target_lang: Lang | None = None
    speech_end_wall: float = 0.0  # instante (time.monotonic) em que a fala terminou
    timings: dict[str, float] = field(default_factory=dict)
    created_at: float = field(default_factory=time.monotonic)

    @property
    def low_confidence(self) -> bool:
        return self.transcript.low_confidence
