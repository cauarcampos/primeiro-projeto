"""Reconhecimento de fala (Speech-to-Text) com sinalização de incerteza.

Regras importantes:
- Idiomas restritos a português e ucraniano (o Whisper confunde ucraniano com russo se puder escolher).
- Palavras com baixa probabilidade são marcadas como incertas, nunca escondidas.
- Frases típicas de "alucinação" do Whisper em ruído/silêncio são descartadas.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol, Sequence

import numpy as np

from .domain import SUPPORTED_LANGS, Lang, Transcript, Word


@dataclass(frozen=True)
class ConfidenceConfig:
    word_uncertain_below: float = 0.40
    low_avg_logprob: float = -0.80
    max_uncertain_ratio: float = 0.25
    min_lang_probability: float = 0.70
    # descarta o segmento (provável não-fala), regra do próprio Whisper
    drop_no_speech_prob: float = 0.60
    drop_avg_logprob: float = -1.00


# Frases que o Whisper costuma inventar em silêncio/ruído (vindas de legendas de vídeos).
_HALLUCINATIONS = (
    "amara org",
    "legendas pela comunidade",
    "legenda por",
    "legendas por",
    "obrigado por assistir",
    "inscreva se no canal",
    "субтитри",
    "субтитрів",
    "дякую за перегляд",
    "підписуйтесь на канал",
    "продовження наступне",
)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_hallucination(text: str) -> bool:
    norm = _normalize(text)
    return any(h in norm for h in _HALLUCINATIONS)


# Idiomas "parentes": quando o Whisper hesita, ucraniano costuma sair como russo/polonês/bielorrusso
# e português como espanhol/galego. Como só existem duas pessoas, essa evidência conta para o idioma
# da família correspondente.
_FAMILY: dict[Lang, tuple[str, ...]] = {
    Lang.UK: ("uk", "ru", "be", "pl", "bg", "sk", "cs", "sr", "hr", "sl", "mk", "bs"),
    Lang.PT: ("pt", "es", "gl", "ca", "it", "ro", "fr"),
}


def restrict_language(
    all_probs: Sequence[tuple[str, float]], allowed: Sequence[Lang] = SUPPORTED_LANGS
) -> tuple[Lang, float]:
    """Escolhe o idioma só entre os permitidos; devolve a probabilidade renormalizada.

    A língua exata vale peso 1; parentes próximos valem peso 0,5.
    """
    probs = {code: p for code, p in all_probs}
    scores = {}
    for lang in allowed:
        exact = float(probs.get(lang.value, 0.0))
        related = sum(float(probs.get(c, 0.0)) for c in _FAMILY.get(lang, ()) if c != lang.value)
        scores[lang] = exact + 0.5 * related
    total = sum(scores.values())
    best = max(scores, key=scores.get)
    if total <= 0:
        return best, 0.0
    return best, scores[best] / total


def assess(
    words: Sequence[tuple[str, float]],
    avg_logprob: float,
    no_speech_prob: float,
    lang: Lang,
    lang_probability: float,
    cfg: ConfidenceConfig = ConfidenceConfig(),
) -> Transcript:
    """Monta o Transcript aplicando as regras de confiança e descarte."""
    marked = tuple(
        Word(text=w, probability=p, uncertain=p < cfg.word_uncertain_below) for w, p in words
    )
    text = "".join(w.text for w in marked).strip()

    drop = (no_speech_prob > cfg.drop_no_speech_prob and avg_logprob < cfg.drop_avg_logprob) or (
        is_hallucination(text)
    )
    if drop:
        return Transcript("", lang, lang_probability, (), avg_logprob, no_speech_prob, True)

    uncertain_ratio = sum(w.uncertain for w in marked) / len(marked) if marked else 0.0
    low = (
        avg_logprob < cfg.low_avg_logprob
        or uncertain_ratio > cfg.max_uncertain_ratio
        or lang_probability < cfg.min_lang_probability
    )
    return Transcript(text, lang, lang_probability, marked, avg_logprob, no_speech_prob, low)


class Transcriber(Protocol):
    def detect_language(self, audio: np.ndarray) -> tuple[Lang, float]: ...

    def transcribe(self, audio: np.ndarray, lang: Lang, fast: bool = False) -> Transcript: ...


def resolve_device(device: str) -> tuple[str, str]:
    """'auto' usa a GPU NVIDIA se disponível; devolve (device, compute_type)."""
    if device == "auto":
        try:
            import ctranslate2

            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"
    return device, ("float16" if device == "cuda" else "int8")


class FasterWhisperTranscriber:
    def __init__(
        self,
        model: str = "large-v3-turbo",
        device: str = "auto",
        download_root: str | None = None,
        initial_prompt: str | None = None,
        confidence: ConfidenceConfig = ConfidenceConfig(),
        cpu_threads: int = 0,
    ):
        from faster_whisper import WhisperModel

        self.device, compute_type = resolve_device(device)
        self._model = WhisperModel(
            model,
            device=self.device,
            compute_type=compute_type,
            download_root=download_root,
            cpu_threads=cpu_threads,
        )
        self._prompt = initial_prompt
        self._cfg = confidence

    def detect_language(self, audio: np.ndarray) -> tuple[Lang, float]:
        _, _, all_probs = self._model.detect_language(audio)
        return restrict_language(all_probs)

    def transcribe(self, audio: np.ndarray, lang: Lang, fast: bool = False) -> Transcript:
        segments, _info = self._model.transcribe(
            audio,
            language=lang.value,
            beam_size=1 if fast else 5,
            temperature=0.0 if fast else (0.0, 0.2, 0.4),
            condition_on_previous_text=False,
            vad_filter=False,
            word_timestamps=not fast,
            initial_prompt=self._prompt,
            without_timestamps=fast,
        )
        segments = list(segments)
        if not segments:
            return Transcript("", lang, 1.0, (), 0.0, 1.0, True)

        if fast:
            words = [(s.text, 1.0) for s in segments]
        else:
            words = [(w.word, w.probability) for s in segments for w in (s.words or [])]
            if not words:
                words = [(s.text, 1.0) for s in segments]
        n = sum(max(1, len(s.tokens)) for s in segments)
        avg_logprob = sum(s.avg_logprob * max(1, len(s.tokens)) for s in segments) / n
        no_speech = max(s.no_speech_prob for s in segments)
        return assess(words, avg_logprob, no_speech, lang, 1.0, self._cfg)
