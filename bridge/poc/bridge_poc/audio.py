"""Fontes de áudio. Todas entregam float32 mono a 16 kHz, só em memória (nada é gravado em disco).

- Microfone: sua voz.
- Loopback (Windows/WASAPI): tudo que o computador reproduz — inclui a voz da outra pessoa na
  chamada do Instagram Web. Exige que a chamada saia pelo dispositivo de saída escolhido.
- Arquivo WAV: para testes e benchmark.
"""

from __future__ import annotations

import threading
import time
import warnings
from typing import Callable, Protocol

import numpy as np

from .vad import SAMPLE_RATE

Callback = Callable[[np.ndarray], None]


class AudioSource(Protocol):
    source_id: str

    def start(self, callback: Callback) -> None: ...

    def stop(self) -> None: ...


class _Resampler:
    def __init__(self, in_rate: int):
        self.in_rate = in_rate
        self._stream = None
        if in_rate != SAMPLE_RATE:
            import soxr

            self._stream = soxr.ResampleStream(in_rate, SAMPLE_RATE, 1, dtype="float32")

    def __call__(self, mono: np.ndarray, last: bool = False) -> np.ndarray:
        mono = np.ascontiguousarray(mono, dtype=np.float32)
        if self._stream is None:
            return mono
        return self._stream.resample_chunk(mono, last=last)


def to_mono(data: np.ndarray) -> np.ndarray:
    if data.ndim == 2:
        return data.mean(axis=1)
    return data


class SoundcardSource:
    """Microfone ou loopback via biblioteca `soundcard` (WASAPI no Windows)."""

    def __init__(
        self,
        source_id: str,
        loopback: bool,
        device_name: str | None = None,
        samplerate: int = 48000,
        block_ms: int = 30,
    ):
        self.source_id = source_id
        self.loopback = loopback
        self.device_name = device_name
        self.samplerate = samplerate
        self.block = int(samplerate * block_ms / 1000)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _device(self):
        import soundcard as sc

        if self.loopback:
            speaker = (
                sc.get_speaker(self.device_name) if self.device_name else sc.default_speaker()
            )
            return sc.get_microphone(id=str(speaker.name), include_loopback=True)
        return sc.get_microphone(self.device_name) if self.device_name else sc.default_microphone()

    def start(self, callback: Callback) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(callback,), name=f"audio-{self.source_id}", daemon=True
        )
        self._thread.start()

    def _run(self, callback: Callback) -> None:
        # Sem nada tocando, o loopback do WASAPI fica sem dados e o soundcard avisa
        # "data discontinuity" — esperado, não é erro.
        warnings.filterwarnings("ignore", message=".*discontinuity.*")
        try:  # WASAPI exige COM inicializado em cada thread (só no Windows)
            import ctypes

            ctypes.windll.ole32.CoInitializeEx(None, 0)  # type: ignore[attr-defined]
        except Exception:
            pass
        resample = _Resampler(self.samplerate)
        with self._device().recorder(samplerate=self.samplerate) as rec:
            while not self._stop.is_set():
                data = rec.record(numframes=self.block)
                if data.size:
                    callback(resample(to_mono(data)))

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)


def _parse_riff(blob: bytes) -> tuple[int, int, int, int, bytes]:
    """Leitor mínimo de WAV: (formato, canais, taxa, bits, dados). Aceita PCM e float."""
    import struct

    if blob[:4] != b"RIFF" or blob[8:12] != b"WAVE":
        raise ValueError("não é um arquivo WAV")
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(blob):
        cid, size = blob[pos : pos + 4], struct.unpack("<I", blob[pos + 4 : pos + 8])[0]
        body = blob[pos + 8 : pos + 8 + size]
        if cid == b"fmt ":
            tag, ch, rate, _, _, bits = struct.unpack("<HHIIHH", body[:16])
            if tag == 0xFFFE and len(body) >= 26:  # WAVE_FORMAT_EXTENSIBLE
                tag = struct.unpack("<H", body[24:26])[0]
            fmt = (tag, ch, rate, bits)
        elif cid == b"data":
            data = body
        pos += 8 + size + (size & 1)
    if fmt is None or data is None:
        raise ValueError("WAV sem cabeçalho ou dados")
    return (*fmt, data)


def read_wav(path: str) -> np.ndarray:
    """Lê WAV (PCM 8/16/32 bits ou float 32/64) e devolve float32 mono 16 kHz."""
    with open(path, "rb") as f:
        tag, ch, rate, bits, raw = _parse_riff(f.read())
    if tag == 3:
        data = np.frombuffer(raw, dtype=np.float32 if bits == 32 else np.float64)
        data = data.astype(np.float32)
    elif tag == 1:
        dtype = {8: np.uint8, 16: np.int16, 32: np.int32}[bits]
        data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
        data = (data - 128) / 128.0 if bits == 8 else data / float(2 ** (bits - 1))
    else:
        raise ValueError(f"formato WAV não suportado: {tag}")
    if ch > 1:
        data = data[: len(data) // ch * ch].reshape(-1, ch).mean(axis=1)
    return _Resampler(rate)(data, last=True)


class ArrayAudioSource:
    """Entrega um array (ex.: arquivo WAV) em blocos, em tempo real ou o mais rápido possível."""

    def __init__(
        self,
        source_id: str,
        audio: np.ndarray,
        realtime: bool = True,
        block_ms: int = 30,
        trailing_silence_s: float = 1.5,
    ):
        self.source_id = source_id
        pad = np.zeros(int(trailing_silence_s * SAMPLE_RATE), dtype=np.float32)
        self.audio = np.concatenate([audio.astype(np.float32), pad])
        self.realtime = realtime
        self.block = int(SAMPLE_RATE * block_ms / 1000)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.finished = threading.Event()

    def start(self, callback: Callback) -> None:
        self._thread = threading.Thread(target=self._run, args=(callback,), daemon=True)
        self._thread.start()

    def _run(self, callback: Callback) -> None:
        t0 = time.monotonic()
        for i in range(0, len(self.audio), self.block):
            if self._stop.is_set():
                break
            callback(self.audio[i : i + self.block])
            if self.realtime:
                delay = t0 + (i + self.block) / SAMPLE_RATE - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
        self.finished.set()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)


def list_devices() -> str:
    import soundcard as sc

    lines = ["Microfones:"]
    lines += [f"  - {m.name}" for m in sc.all_microphones()]
    lines.append("Saídas (para loopback):")
    lines += [f"  - {s.name}" for s in sc.all_speakers()]
    lines.append(f"Microfone padrão: {sc.default_microphone().name}")
    lines.append(f"Saída padrão: {sc.default_speaker().name}")
    return "\n".join(lines)
