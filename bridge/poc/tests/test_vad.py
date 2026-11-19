import numpy as np
import pytest

from bridge_poc.vad import FRAME, EnergyVad, Segmenter, SegmenterConfig, SileroStreamingVad

from .fakes import SR, silence, tone

NO_PARTIALS = SegmenterConfig(partial_interval_s=0)


def run(audio, cfg=NO_PARTIALS, chunk=480):
    events = []
    seg = Segmenter("x", EnergyVad(), events.append, cfg)
    for i in range(0, len(audio), chunk):  # pedaços que não coincidem com FRAME
        seg.feed(audio[i : i + chunk])
    seg.flush()
    return events


def test_two_utterances_separated_by_pause():
    audio = np.concatenate([silence(0.5), tone(1.0), silence(1.0), tone(2.0), silence(1.0)])
    finals = [e for e in run(audio) if e.is_final]
    assert len(finals) == 2
    assert finals[0].duration_s == pytest.approx(1.0 + 0.2 + 0.15, abs=0.12)
    assert finals[1].duration_s == pytest.approx(2.0 + 0.2 + 0.15, abs=0.12)
    assert finals[0].segment_id != finals[1].segment_id


def test_short_pause_does_not_split():
    audio = np.concatenate([tone(1.0), silence(0.3), tone(1.0), silence(1.0)])
    assert len([e for e in run(audio) if e.is_final]) == 1


def test_click_is_discarded():
    audio = np.concatenate([silence(0.5), tone(0.1), silence(1.0)])
    assert run(audio) == []


def test_long_speech_is_cut_at_max_length():
    cfg = SegmenterConfig(partial_interval_s=0, max_segment_s=3.0)
    finals = [e for e in run(np.concatenate([tone(7.0), silence(1.0)]), cfg) if e.is_final]
    assert len(finals) == 3
    assert all(e.duration_s <= 3.05 for e in finals)


def test_partials_are_emitted_while_speaking_and_share_segment_id():
    cfg = SegmenterConfig(partial_interval_s=1.0, min_partial_s=1.0)
    events = run(np.concatenate([tone(3.5), silence(1.0)]), cfg)
    partials = [e for e in events if not e.is_final]
    finals = [e for e in events if e.is_final]
    assert len(partials) >= 2
    assert len(finals) == 1
    assert {e.segment_id for e in partials} == {finals[0].segment_id}


def test_unfinished_speech_is_flushed():
    events = run(tone(1.5))
    assert len(events) == 1 and events[0].is_final


def test_reset_drops_audio_in_progress():
    events = []
    seg = Segmenter("x", EnergyVad(), events.append, NO_PARTIALS)
    seg.feed(tone(1.0))
    assert seg.in_speech
    seg.reset()
    seg.feed(silence(1.0))
    seg.flush()
    assert events == []


def test_silero_vad_distinguishes_silence_from_noise_floor():
    vad = SileroStreamingVad()
    rng = np.random.default_rng(0)
    probs = [vad(rng.normal(0, 1e-4, FRAME).astype(np.float32)) for _ in range(30)]
    assert max(probs) < 0.5
    assert len(silence(1.0)) == SR
