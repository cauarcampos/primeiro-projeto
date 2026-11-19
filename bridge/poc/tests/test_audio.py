import struct

import numpy as np
import pytest

from bridge_poc.audio import ArrayAudioSource, read_wav


def write_wav(path, data: bytes, tag: int, ch: int, rate: int, bits: int):
    block = ch * bits // 8
    fmt = struct.pack("<HHIIHH", tag, ch, rate, rate * block, block, bits)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)


def test_reads_pcm16_stereo_48k_as_mono_16k(tmp_path):
    t = np.arange(48000) / 48000
    mono = 0.5 * np.sin(2 * np.pi * 300 * t)
    stereo = np.stack([mono, mono], axis=1)
    write_wav(tmp_path / "a.wav", (stereo * 32767).astype("<i2").tobytes(), 1, 2, 48000, 16)
    out = read_wav(str(tmp_path / "a.wav"))
    assert out.dtype == np.float32
    assert len(out) == pytest.approx(16000, abs=50)
    assert np.max(np.abs(out)) == pytest.approx(0.5, abs=0.05)


def test_reads_float32_16k(tmp_path):
    data = np.linspace(-0.5, 0.5, 1600, dtype="<f4")
    write_wav(tmp_path / "b.wav", data.tobytes(), 3, 1, 16000, 32)
    out = read_wav(str(tmp_path / "b.wav"))
    assert np.allclose(out, data)


def test_rejects_non_wav(tmp_path):
    (tmp_path / "c.wav").write_bytes(b"nao sou wav")
    with pytest.raises(ValueError):
        read_wav(str(tmp_path / "c.wav"))


def test_array_source_delivers_all_audio_plus_trailing_silence():
    audio = np.ones(16000, dtype=np.float32)
    got = []
    src = ArrayAudioSource("x", audio, realtime=False, trailing_silence_s=0.5)
    src.start(got.append)
    assert src.finished.wait(5)
    total = np.concatenate(got)
    assert len(total) == 16000 + 8000
    assert total[:16000].sum() == 16000
