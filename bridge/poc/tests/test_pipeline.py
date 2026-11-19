import logging
import time

import numpy as np

from bridge_poc.domain import Lang, Speaker
from bridge_poc.history import History
from bridge_poc.pipeline import Pipeline, SourceRole
from bridge_poc.vad import EnergyVad, SegmentEvent, SegmenterConfig

from .fakes import FakeTranscriber, FakeTranslator, silence, tone

ME = Speaker("Cauã", Lang.PT, is_me=True)
HER = Speaker("Katya", Lang.UK)
PT_TONE, UK_TONE = 220.0, 440.0


def make(roles, **kw):
    out, discarded = [], []
    stt, tr = FakeTranscriber(), FakeTranslator()
    p = Pipeline(
        stt,
        tr,
        (ME, HER),
        roles,
        out.append,
        EnergyVad,
        SegmenterConfig(partial_interval_s=0),
        on_discard=lambda s, i: discarded.append((s, i)),
        **kw,
    )
    return p, out, discarded, stt, tr


def ev(source, audio, final=True, seg=1):
    return SegmentEvent(source, seg, audio, is_final=final, speech_end_wall=time.monotonic())


def test_computer_mode_speaker_comes_from_channel_and_translates_both_ways():
    p, out, _, _, tr = make([SourceRole("mic", speaker=ME), SourceRole("sistema", speaker=HER)])
    p.process(ev("sistema", tone(1, UK_TONE), seg=1))
    p.process(ev("mic", tone(1, PT_TONE), seg=2))
    assert [u.speaker.name for u in out] == ["Katya", "Cauã"]
    assert out[0].translation == "<pt>привіт коханий!" and out[0].target_lang is Lang.PT
    assert out[1].translation == "<uk>olá amor." and out[1].target_lang is Lang.UK
    assert tr.calls[0][1:] == (Lang.UK, Lang.PT)


def test_echo_of_partner_voice_on_my_microphone_is_rejected():
    p, out, discarded, _, _ = make([SourceRole("mic", speaker=ME, check_language=True)])
    assert p.process(ev("mic", tone(1, UK_TONE))) is None
    assert out == [] and p.stats.dropped_echo == 1 and discarded == [("mic", 1)]
    assert p.process(ev("mic", tone(1, PT_TONE), seg=2)) is not None


def test_ambient_mode_identifies_speaker_by_language():
    p, out, _, _, _ = make([SourceRole("amb")])
    p.process(ev("amb", tone(1, UK_TONE), seg=1))
    p.process(ev("amb", tone(1, PT_TONE), seg=2))
    assert [u.speaker for u in out] == [HER, ME]


def test_partials_are_not_translated_and_late_partials_are_ignored():
    p, out, _, stt, tr = make([SourceRole("mic", speaker=ME)])
    p.process(ev("mic", tone(1), final=False, seg=7))
    assert out[-1].translation is None and stt.calls[-1] == (Lang.PT, True)
    p.process(ev("mic", tone(1), final=True, seg=7))
    assert p.process(ev("mic", tone(1), final=False, seg=7)) is None
    assert len(tr.calls) == 1


def test_empty_final_signals_discard():
    p, out, discarded, _, _ = make([SourceRole("mic", speaker=ME)])
    p.process(ev("mic", np.zeros(0, dtype=np.float32), seg=3))
    assert out == [] and discarded == [("mic", 3)]


def test_history_off_by_default_and_clearable():
    p, _, _, _, _ = make([SourceRole("mic", speaker=ME)])
    p.process(ev("mic", tone(1)))
    assert len(p.history) == 0

    p, _, _, _, _ = make([SourceRole("mic", speaker=ME)], history=History(enabled=True))
    p.process(ev("mic", tone(1), seg=1))
    p.process(ev("mic", tone(1), seg=2))
    assert len(p.history) == 2
    p.history.clear()
    assert len(p.history) == 0


def test_history_expires_old_items():
    h = History(enabled=True, ttl_s=0.05)
    p, _, _, _, _ = make([SourceRole("mic", speaker=ME)], history=h)
    p.process(ev("mic", tone(1)))
    time.sleep(0.1)
    assert len(h) == 0


def test_logs_never_contain_speech_content(caplog):
    p, _, _, _, _ = make([SourceRole("mic", speaker=ME), SourceRole("sistema", speaker=HER)])
    with caplog.at_level(logging.DEBUG):
        p.process(ev("mic", tone(1, PT_TONE), seg=1))
        p.process(ev("sistema", tone(1, UK_TONE), seg=2))
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "latencia" in logged  # há métricas…
    for secret in ("olá", "amor", "привіт", "коханий"):  # …mas nenhum conteúdo
        assert secret not in logged


def test_end_to_end_threads_pause_and_resume():
    p, out, _, _, _ = make([SourceRole("mic", speaker=ME)])
    p.start()
    try:
        p.feed("mic", np.concatenate([tone(1.0), silence(1.0)]))
        assert p.wait_idle(5)
        assert len(out) == 1

        p.pause()
        p.feed("mic", np.concatenate([tone(1.0), silence(1.0)]))
        assert p.wait_idle(5)
        assert len(out) == 1  # nada processado durante a pausa

        p.resume()
        p.feed("mic", np.concatenate([tone(1.0), silence(1.0)]))
        assert p.wait_idle(5)
        assert len(out) == 2
    finally:
        p.stop()


def test_cut_sentence_fragments_are_joined_before_translating():
    p, out, _, stt, tr = make([SourceRole("mic", speaker=ME)])
    stt.texts[Lang.PT] = "Então, o Pedro"
    assert p.process(ev("mic", tone(1), seg=1)) is None  # fragmento: espera continuação
    stt.texts[Lang.PT] = "tomou a frente para cantar."
    utt = p.process(ev("mic", tone(1), seg=2))
    assert utt.transcript.text == "Então, o Pedro tomou a frente para cantar."
    assert len(tr.calls) == 1 and tr.calls[0][0] == utt.transcript.text
    assert [u.is_final for u in out] == [True]


def test_fragment_is_released_when_nothing_follows():
    p, out, _, stt, _ = make([SourceRole("mic", speaker=ME)], merge_window_s=0.05)
    stt.texts[Lang.PT] = "sim"
    p.start()
    try:
        p.feed("mic", np.concatenate([tone(1.0), silence(1.0)]))
        assert p.wait_idle(5)
    finally:
        p.stop()
    assert [u.transcript.text for u in out] == ["sim"]


def test_fragment_from_other_speaker_is_not_merged():
    p, out, _, stt, _ = make([SourceRole("amb")])
    stt.texts = {Lang.PT: "então", Lang.UK: "так, звичайно."}
    p.process(ev("amb", tone(1, PT_TONE), seg=1))
    p.process(ev("amb", tone(1, UK_TONE), seg=2))
    assert [(u.speaker.name, u.transcript.text) for u in out] == [("Cauã", "então"), ("Katya", "так, звичайно.")]


def test_glossary_corrects_transcript_and_translation():
    from bridge_poc.glossary import Glossary

    g = Glossary.parse("Kátia => Katya\nКатія => Катя")
    p, out, _, stt, tr = make([SourceRole("mic", speaker=ME)], glossary=g)
    stt.texts[Lang.PT] = "oi Kátia, tudo bem?"
    tr.translate = lambda text, s, t: "привіт Катія, як справи?"
    utt = p.process(ev("mic", tone(1)))
    assert utt.transcript.text == "oi Katya, tudo bem?"
    assert utt.translation == "привіт Катя, як справи?"


def test_ellipsis_is_removed_when_joining():
    p, out, _, stt, tr = make([SourceRole("mic", speaker=ME)])
    stt.texts[Lang.PT] = "Então o Pedro..."
    p.process(ev("mic", tone(1), seg=1))
    stt.texts[Lang.PT] = "tomou a frente."
    utt = p.process(ev("mic", tone(1), seg=2))
    assert utt.transcript.text == "Então o Pedro tomou a frente."
    assert "".join(w.text for w in utt.transcript.words).strip() == utt.transcript.text
