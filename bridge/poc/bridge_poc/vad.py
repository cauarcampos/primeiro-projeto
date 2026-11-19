"""Detecção de voz (VAD) em streaming e segmentação de falas.

O segmentador recebe áudio contínuo (float32, 16 kHz, mono), em pedaços de qualquer tamanho,
e emite eventos de segmento parcial (fala em andamento) e final (fala terminou).
Sem VAD o Whisper "inventa" frases durante o silêncio, por isso ele é obrigatório.
"""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Protocol

import numpy as np

SAMPLE_RATE = 16000
FRAME = 512  # 32 ms a 16 kHz (tamanho exigido pelo Silero VAD)
_CONTEXT = 64


class Vad(Protocol):
    def __call__(self, frame: np.ndarray) -> float:
        """Probabilidade de fala (0..1) para um quadro de FRAME amostras."""

    def reset(self) -> None: ...


class SileroStreamingVad:
    """Silero VAD v6 (ONNX, distribuído com o faster-whisper), com estado entre quadros."""

    def __init__(self, model_path: str | None = None):
        import onnxruntime

        if model_path is None:
            from faster_whisper.utils import get_assets_path

            model_path = os.path.join(get_assets_path(), "silero_vad_v6.onnx")
        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.log_severity_level = 4
        self._session = onnxruntime.InferenceSession(
            model_path, providers=["CPUExecutionProvider"], sess_options=opts
        )
        self.reset()

    def reset(self) -> None:
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._context = np.zeros(_CONTEXT, dtype=np.float32)

    def __call__(self, frame: np.ndarray) -> float:
        x = np.concatenate([self._context, frame.astype(np.float32)])[None, :]
        out, self._h, self._c = self._session.run(None, {"input": x, "h": self._h, "c": self._c})
        self._context = frame[-_CONTEXT:].astype(np.float32)
        return float(np.asarray(out).reshape(-1)[0])


class EnergyVad:
    """VAD simples por energia. Usado em testes e como alternativa sem modelo."""

    def __init__(self, threshold_db: float = -40.0):
        self.threshold_db = threshold_db

    def reset(self) -> None:
        pass

    def __call__(self, frame: np.ndarray) -> float:
        rms = float(np.sqrt(np.mean(np.square(frame), dtype=np.float64)) + 1e-12)
        db = 20 * np.log10(rms)
        return 1.0 if db > self.threshold_db else 0.0


@dataclass(frozen=True)
class SegmenterConfig:
    threshold: float = 0.5  # probabilidade para iniciar fala
    neg_threshold: float = 0.35  # abaixo disso conta como silêncio
    min_speech_ms: int = 250  # falas menores são descartadas (estalos, tosse)
    min_silence_ms: int = 550  # silêncio que encerra a fala
    max_segment_s: float = 12.0  # corta falas muito longas
    pre_pad_ms: int = 200  # áudio mantido antes do início detectado
    partial_interval_s: float = 1.0  # intervalo entre legendas parciais (0 = desligado)
    min_partial_s: float = 1.0


@dataclass
class SegmentEvent:
    source_id: str
    segment_id: int
    audio: np.ndarray
    is_final: bool
    speech_end_wall: float  # time.monotonic() no fim da fala (finais) ou do pedaço (parciais)

    @property
    def duration_s(self) -> float:
        return len(self.audio) / SAMPLE_RATE


class Segmenter:
    def __init__(
        self,
        source_id: str,
        vad: Vad,
        on_event: Callable[[SegmentEvent], None],
        config: SegmenterConfig = SegmenterConfig(),
        id_factory: Callable[[], int] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        from .domain import next_id

        self.source_id = source_id
        self.vad = vad
        self.on_event = on_event
        self.cfg = config
        self._next_id = id_factory or next_id
        self._clock = clock
        self._pending = np.zeros(0, dtype=np.float32)
        self._pre = deque(maxlen=max(1, config.pre_pad_ms * SAMPLE_RATE // 1000 // FRAME))
        self.last_probability = 0.0
        self._reset_segment()

    # -- estado -------------------------------------------------------------------------
    def _reset_segment(self) -> None:
        self._in_speech = False
        self._frames: list[np.ndarray] = []
        self._speech_frames = 0
        self._silence_frames = 0
        self._segment_id = 0
        self._last_partial_len = 0

    def reset(self) -> None:
        """Descarta tudo (usado ao pausar). Nenhum áudio é mantido."""
        self._pending = np.zeros(0, dtype=np.float32)
        self._pre.clear()
        self.vad.reset()
        self._reset_segment()

    @property
    def in_speech(self) -> bool:
        return self._in_speech

    # -- processamento ------------------------------------------------------------------
    def feed(self, audio: np.ndarray) -> None:
        if audio.size == 0:
            return
        buf = np.concatenate([self._pending, audio.astype(np.float32, copy=False)])
        n = len(buf) // FRAME
        for i in range(n):
            self._process_frame(buf[i * FRAME : (i + 1) * FRAME])
        self._pending = buf[n * FRAME :].copy()

    def flush(self) -> None:
        """Encerra a fala em andamento (fim do arquivo / parada)."""
        if self._in_speech:
            self._finish()

    def _ms_to_frames(self, ms: float) -> int:
        return max(1, int(ms * SAMPLE_RATE / 1000 / FRAME))

    def _process_frame(self, frame: np.ndarray) -> None:
        p = self.vad(frame)
        self.last_probability = p
        if not self._in_speech:
            if p >= self.cfg.threshold:
                self._in_speech = True
                self._segment_id = self._next_id()
                self._frames = list(self._pre) + [frame]
                self._speech_frames = 1
                self._silence_frames = 0
                self._pre.clear()
            else:
                self._pre.append(frame)
            return

        self._frames.append(frame)
        if p < self.cfg.neg_threshold:
            self._silence_frames += 1
        else:
            self._silence_frames = 0
            self._speech_frames += 1

        if self._silence_frames >= self._ms_to_frames(self.cfg.min_silence_ms):
            self._finish()
            return
        if len(self._frames) * FRAME >= self.cfg.max_segment_s * SAMPLE_RATE:
            self._finish()
            return
        self._maybe_partial()

    def _maybe_partial(self) -> None:
        if self.cfg.partial_interval_s <= 0:
            return
        total = len(self._frames) * FRAME
        if total < self.cfg.min_partial_s * SAMPLE_RATE:
            return
        if total - self._last_partial_len >= self.cfg.partial_interval_s * SAMPLE_RATE:
            self._last_partial_len = total
            self.on_event(
                SegmentEvent(
                    self.source_id,
                    self._segment_id,
                    np.concatenate(self._frames),
                    is_final=False,
                    speech_end_wall=self._clock(),
                )
            )

    def _finish(self) -> None:
        enough = self._speech_frames >= self._ms_to_frames(self.cfg.min_speech_ms)
        if enough:
            # remove a maior parte do silêncio final, mantendo ~150 ms
            keep_tail = self._ms_to_frames(150)
            trim = max(0, self._silence_frames - keep_tail)
            frames = self._frames[: len(self._frames) - trim] if trim else self._frames
            silence_s = trim * FRAME / SAMPLE_RATE
            self.on_event(
                SegmentEvent(
                    self.source_id,
                    self._segment_id,
                    np.concatenate(frames),
                    is_final=True,
                    speech_end_wall=self._clock() - silence_s,
                )
            )
        elif self._last_partial_len:
            # já houve legenda parcial: avisa que a fala foi descartada (áudio vazio)
            self.on_event(
                SegmentEvent(
                    self.source_id,
                    self._segment_id,
                    np.zeros(0, dtype=np.float32),
                    is_final=True,
                    speech_end_wall=self._clock(),
                )
            )
        self._reset_segment()
