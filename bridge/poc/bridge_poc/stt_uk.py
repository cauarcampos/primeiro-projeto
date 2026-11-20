"""Reconhecimento especializado em ucraniano: Parakeet UK + conferência pelo Whisper.

Parakeet UK (ihnatov-yuri/parakeet-tdt-0.6b-v3-uk, CC-BY-4.0) foi ajustado com ~740 h de
ucraniano, boa parte conversa. Nos testes do BRIDGE (FLEURS, 20 frases) errou 5,8% das palavras,
contra 7,1% do Whisper turbo.

Ele não informa a confiança de cada palavra. Por isso o Whisper transcreve o mesmo trecho e as
palavras em que os dois discordam são marcadas como incertas — dois "ouvidos" independentes.

Requer o pacote opcional: torch + transformers (instalar_ucraniano.bat).
"""

from __future__ import annotations

import difflib
import logging
import re
import unicodedata

import numpy as np

from .domain import Lang, Transcript, Word
from .stt import ConfidenceConfig, Transcriber, is_hallucination

log = logging.getLogger("bridge.stt_uk")


def parakeet_available() -> bool:
    try:
        import torch  # noqa: F401
        from transformers import AutoModelForTDT  # noqa: F401
    except Exception:
        return False
    return True


class ParakeetRecognizer:
    def __init__(self, model_dir: str, device: str = "auto", threads: int = 0):
        import torch
        from transformers import AutoModelForTDT, AutoProcessor

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        if threads:
            torch.set_num_threads(threads)
        self._torch = torch
        self._proc = AutoProcessor.from_pretrained(model_dir)
        dtype = torch.float16 if device == "cuda" else torch.float32
        self._model = AutoModelForTDT.from_pretrained(model_dir, dtype=dtype).to(device).eval()
        self._dtype = dtype

    def __call__(self, audio: np.ndarray) -> str:
        inputs = self._proc(audio=[audio], sampling_rate=16000, return_tensors="pt")
        inputs = {
            k: (v.to(self.device, self._dtype) if v.is_floating_point() else v.to(self.device))
            for k, v in inputs.items()
        }
        with self._torch.inference_mode():
            out = self._model.generate(**inputs)
        return self._proc.batch_decode(out.sequences, skip_special_tokens=True)[0].strip()


def _norm_word(w: str) -> str:
    w = unicodedata.normalize("NFKC", w).lower().replace("’", "'").replace("ʼ", "'")
    return re.sub(r"[^\w']", "", w)


def merge_with_reference(
    text: str, reference: Transcript, cfg: ConfidenceConfig = ConfidenceConfig()
) -> Transcript:
    """Usa `text` (Parakeet) e marca como incertas as palavras que o Whisper não confirmou."""
    tokens = text.split()
    ref_words = [w for w in reference.words if _norm_word(w.text)]
    a = [_norm_word(t) for t in tokens]
    b = [_norm_word(w.text) for w in ref_words]
    confirmed: dict[int, float] = {}
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            confirmed[blk.a + k] = ref_words[blk.b + k].probability
    words = []
    for i, tok in enumerate(tokens):
        ok = i in confirmed or not a[i]  # pontuação solta não conta
        prob = confirmed.get(i, 0.0 if a[i] else 1.0)
        # palavra confirmada mas com probabilidade muito baixa no Whisper continua "certa":
        # dois modelos independentes concordaram
        words.append(Word(" " + tok, prob, uncertain=not ok))
    content = [w for w, n in zip(words, a) if n]
    agreement = (sum(not w.uncertain for w in content) / len(content)) if content else 0.0
    low = agreement < 0.75 or reference.is_empty
    return Transcript(
        text=text,
        lang=Lang.UK,
        lang_probability=reference.lang_probability,
        words=tuple(words),
        avg_logprob=reference.avg_logprob,
        no_speech_prob=reference.no_speech_prob,
        low_confidence=low,
    )


class UkrainianBoostedTranscriber:
    """Whisper para português e detecção de idioma; Parakeet UK + Whisper para ucraniano."""

    def __init__(self, whisper: Transcriber, parakeet: ParakeetRecognizer, max_failures: int = 3):
        self.whisper = whisper
        self.parakeet = parakeet
        self.device = getattr(whisper, "device", "cpu")
        self.failures = 0
        self.max_failures = max_failures

    @property
    def parakeet_enabled(self) -> bool:
        return self.failures < self.max_failures

    def detect_language(self, audio: np.ndarray):
        return self.whisper.detect_language(audio)

    def transcribe(self, audio: np.ndarray, lang: Lang, fast: bool = False) -> Transcript:
        if lang is not Lang.UK or not self.parakeet_enabled:
            return self.whisper.transcribe(audio, lang, fast)
        try:
            text = self.parakeet(audio)
        except Exception:
            # nunca deixa a legenda parar: volta ao Whisper (e desliga o Parakeet após 3 falhas)
            self.failures += 1
            log.exception("Parakeet UK falhou (%d/%d); usando o Whisper", self.failures, self.max_failures)
            return self.whisper.transcribe(audio, lang, fast)
        if fast:  # legenda parcial: só o Parakeet, sem conferência
            words = tuple(Word(" " + t, 1.0, False) for t in text.split())
            return Transcript(text, lang, 1.0, words, 0.0, 0.0, False)
        reference = self.whisper.transcribe(audio, lang, fast=False)
        if not text or is_hallucination(text):
            return Transcript("", lang, 1.0, (), reference.avg_logprob, reference.no_speech_prob, True)
        if reference.is_empty and reference.no_speech_prob > ConfidenceConfig().drop_no_speech_prob:
            # o Whisper acha que nem é fala: provável ruído/eco — descarta
            return Transcript("", lang, 1.0, (), reference.avg_logprob, reference.no_speech_prob, True)
        return merge_with_reference(text, reference)
