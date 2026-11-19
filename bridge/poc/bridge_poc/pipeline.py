"""Pipeline: fontes de áudio → VAD/segmentação → STT → tradução → legendas.

Um único trabalhador usa a GPU em sequência. Falas finais têm prioridade; de cada fonte
só a legenda parcial mais recente é processada (as antigas são descartadas).

Privacidade: nenhum texto ou áudio é registrado em log; só métricas (tempos, contagens).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

import numpy as np

from .domain import Lang, Speaker, Transcript, Utterance, Word
from .glossary import Glossary
from .history import History
from .stt import Transcriber
from .translate import Translator
from .vad import SAMPLE_RATE, SegmentEvent, Segmenter, SegmenterConfig, Vad

log = logging.getLogger("bridge.pipeline")

_FLUSH = object()  # sinal interno: entregar fragmentos cujo prazo venceu

_TERMINAL = (".", "!", "?", "…", "»", '"')


def is_fragment(text: str, max_words: int = 4) -> bool:
    """Trecho curto sem pontuação final, ou terminado em vírgula: provavelmente a frase continua."""
    t = text.strip()
    if t.endswith(("...", "…")):  # o Whisper usa reticências quando a fala foi interrompida
        return True
    if not t or t.endswith(_TERMINAL):
        return False
    return t.endswith((",", ";", ":", "—", "-")) or len(t.split()) <= max_words


def merge_utterances(a: Utterance, b: Utterance) -> Utterance:
    """Junta dois trechos finais da mesma pessoa numa única fala."""
    ta, tb = a.transcript, b.transcript
    words_b = tb.words
    if words_b and not words_b[0].text.startswith(" "):
        first = words_b[0]
        words_b = (Word(" " + first.text, first.probability, first.uncertain), *words_b[1:])
    na, nb = max(1, len(ta.words)), max(1, len(tb.words))
    head, words_a = ta.text.strip(), ta.words
    if head.endswith(("...", "…")):  # "Então..." + "tomou" → "Então tomou"
        head = head.rstrip(".…").rstrip()
        if words_a:
            last = words_a[-1]
            words_a = (*words_a[:-1], Word(last.text.rstrip(".…"), last.probability, last.uncertain))
    merged = Transcript(
        text=f"{head} {tb.text.strip()}",
        lang=tb.lang,
        lang_probability=min(ta.lang_probability, tb.lang_probability),
        words=words_a + words_b,
        avg_logprob=(ta.avg_logprob * na + tb.avg_logprob * nb) / (na + nb),
        no_speech_prob=max(ta.no_speech_prob, tb.no_speech_prob),
        low_confidence=ta.low_confidence or tb.low_confidence,
    )
    timings = dict(b.timings)
    for k in ("audio_s", "stt_s", "lid_s"):
        timings[k] = a.timings.get(k, 0.0) + b.timings.get(k, 0.0)
    return Utterance(
        segment_id=b.segment_id,
        source_id=b.source_id,
        speaker=b.speaker,
        transcript=merged,
        is_final=True,
        speech_end_wall=b.speech_end_wall,
        timings=timings,
    )


@dataclass
class SourceRole:
    """Como interpretar o áudio de uma fonte.

    - `speaker` definido: o falante é fixo (modo Computador: canal = pessoa).
      Se `check_language` estiver ligado, falas detectadas no idioma do OUTRO participante
      com alta confiança são descartadas (eco/vazamento da caixa de som no microfone).
    - `speaker` None: o falante é deduzido pelo idioma (modo Ambiente: um microfone para os dois).
    """

    source_id: str
    speaker: Speaker | None = None
    check_language: bool = False
    echo_reject_probability: float = 0.80


@dataclass
class PipelineStats:
    finals: int = 0
    partials: int = 0
    dropped_empty: int = 0
    dropped_echo: int = 0
    last_latency_s: float = 0.0


class Pipeline:
    def __init__(
        self,
        transcriber: Transcriber,
        translator: Translator,
        speakers: tuple[Speaker, Speaker],
        roles: list[SourceRole],
        on_utterance: Callable[[Utterance], None],
        vad_factory: Callable[[], Vad],
        segmenter_config: SegmenterConfig = SegmenterConfig(),
        history: History | None = None,
        on_discard: Callable[[str, int], None] | None = None,
        glossary: Glossary | None = None,
        merge_window_s: float = 1.5,
    ):
        self.stt = transcriber
        self.translator = translator
        self.speakers = {s.lang: s for s in speakers}
        self.roles = {r.source_id: r for r in roles}
        self.on_utterance = on_utterance
        self.on_discard = on_discard or (lambda source_id, segment_id: None)
        self.history = history if history is not None else History(enabled=False)
        self.stats = PipelineStats()
        self.glossary = glossary if glossary is not None else Glossary()
        self.merge_window_s = merge_window_s
        self._held: dict[str, tuple[Utterance, float]] = {}
        self._held_lock = threading.Lock()

        self.segmenters = {
            r.source_id: Segmenter(r.source_id, vad_factory(), self._enqueue, segmenter_config)
            for r in roles
        }
        self.levels: dict[str, float] = {r.source_id: 0.0 for r in roles}
        self._finals: deque[SegmentEvent] = deque()
        self._partials: dict[str, SegmentEvent] = {}
        self._finalized: deque[tuple[str, int]] = deque(maxlen=256)
        self._cv = threading.Condition()
        self._paused = threading.Event()
        self._stopped = threading.Event()
        self._busy = threading.Event()
        self._worker: threading.Thread | None = None

    # -- controle -----------------------------------------------------------------------
    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    @property
    def busy(self) -> bool:
        return self._busy.is_set()

    def pause(self) -> None:
        self._paused.set()
        with self._cv:
            self._finals.clear()
            self._partials.clear()
        with self._held_lock:
            self._held.clear()
        for s in self.segmenters.values():
            s.reset()

    def resume(self) -> None:
        self._paused.clear()

    def start(self) -> None:
        self._stopped.clear()
        self._worker = threading.Thread(target=self._run, name="bridge-worker", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._stopped.set()
        with self._cv:
            self._cv.notify_all()
        if self._worker:
            self._worker.join(timeout=5)

    def flush(self) -> None:
        """Encerra falas em andamento; fragmentos pendentes saem quando o prazo vencer."""
        for s in self.segmenters.values():
            s.flush()

    def wait_idle(self, timeout: float = 60.0) -> bool:
        """Espera a fila esvaziar (usado em testes/benchmark)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self._cv:
                empty = not self._finals and not self._partials
            with self._held_lock:
                empty = empty and not self._held
            if empty and not self.busy:
                return True
            time.sleep(0.02)
        return False

    # -- entrada de áudio ---------------------------------------------------------------
    def feed(self, source_id: str, audio: np.ndarray) -> None:
        if audio.size:
            rms = float(np.sqrt(np.mean(np.square(audio), dtype=np.float64)))
            self.levels[source_id] = 0.7 * self.levels.get(source_id, 0.0) + 0.3 * rms
        if self.paused:
            return
        self.segmenters[source_id].feed(audio)

    def callback_for(self, source_id: str) -> Callable[[np.ndarray], None]:
        return lambda audio: self.feed(source_id, audio)

    def _enqueue(self, ev: SegmentEvent) -> None:
        with self._cv:
            if ev.is_final:
                self._partials.pop(ev.source_id, None)
                self._finals.append(ev)
            else:
                self._partials[ev.source_id] = ev
            self._cv.notify()

    # -- trabalhador --------------------------------------------------------------------
    def _next_event(self) -> SegmentEvent | None:
        with self._cv:
            while not self._stopped.is_set():
                if self._finals:
                    return self._finals.popleft()
                if self._partials:
                    _, ev = self._partials.popitem()
                    return ev
                dl = self._next_deadline()
                if dl is not None and dl <= time.monotonic():
                    return _FLUSH
                timeout = 0.5 if dl is None else max(0.01, min(0.5, dl - time.monotonic()))
                self._cv.wait(timeout=timeout)
        return None

    def _run(self) -> None:
        while True:
            ev = self._next_event()
            if ev is None:
                return
            self._busy.set()
            try:
                if ev is _FLUSH:
                    self.flush_held(only_expired=True)
                else:
                    self.process(ev)
            except Exception:  # nunca derruba o app; registra só o tipo do erro
                log.exception("falha ao processar segmento (conteúdo omitido)")
            finally:
                self._busy.clear()

    # -- processamento (público para testes) --------------------------------------------
    def process(self, ev: SegmentEvent) -> Utterance | None:
        key = (ev.source_id, ev.segment_id)
        if not ev.is_final and key in self._finalized:
            return None  # parcial atrasado de uma fala já finalizada
        if ev.is_final:
            self._finalized.append(key)
            if ev.audio.size == 0:
                self.on_discard(ev.source_id, ev.segment_id)
                return None

        role = self.roles[ev.source_id]
        t0 = time.monotonic()
        timings: dict[str, float] = {}

        speaker, lang, lang_prob = self._resolve_speaker(role, ev.audio, ev.is_final)
        timings["lid_s"] = time.monotonic() - t0
        if speaker is None:  # eco rejeitado
            self.stats.dropped_echo += 1
            if ev.is_final:
                self.on_discard(ev.source_id, ev.segment_id)
            return None

        t1 = time.monotonic()
        tr = self.stt.transcribe(ev.audio, lang, fast=not ev.is_final)
        timings["stt_s"] = time.monotonic() - t1
        tr = _with_lang_probability(tr, lang_prob)

        if tr.is_empty:
            if ev.is_final:
                self.stats.dropped_empty += 1
                self.on_discard(ev.source_id, ev.segment_id)
            return None

        utt = Utterance(
            segment_id=ev.segment_id,
            source_id=ev.source_id,
            speaker=speaker,
            transcript=tr,
            is_final=ev.is_final,
            speech_end_wall=ev.speech_end_wall,
            timings=timings,
        )
        if not ev.is_final:
            self.stats.partials += 1
            self.on_utterance(utt)
            return utt

        utt.transcript = self.glossary.correct_transcript(utt.transcript)
        timings["audio_s"] = len(ev.audio) / SAMPLE_RATE
        with self._held_lock:
            held = self._held.pop(ev.source_id, None)
        if held is not None:
            prev = held[0]
            if prev.speaker == utt.speaker:
                utt = merge_utterances(prev, utt)
            else:
                self._emit_final(prev)
        if self.merge_window_s > 0 and is_fragment(utt.transcript.text):
            with self._held_lock:
                self._held[ev.source_id] = (utt, time.monotonic() + self.merge_window_s)
            with self._cv:
                self._cv.notify()
            return None  # aguarda a continuação da frase
        return self._emit_final(utt)

    def _emit_final(self, utt: Utterance) -> Utterance:
        """Traduz e entrega uma fala final."""
        tr = utt.transcript
        t2 = time.monotonic()
        utt.target_lang = tr.lang.other
        translation = self.translator.translate(tr.text, tr.lang, tr.lang.other)
        utt.translation = self.glossary.correct_text(translation)
        timings = utt.timings
        timings["translate_s"] = time.monotonic() - t2
        timings["latency_s"] = time.monotonic() - utt.speech_end_wall
        self.stats.finals += 1
        self.stats.last_latency_s = timings["latency_s"]
        self.history.add(utt)
        log.info(
            "fala final: fonte=%s idioma=%s audio=%.1fs stt=%.2fs trad=%.2fs latencia=%.2fs",
            utt.source_id,
            tr.lang.value,
            timings.get("audio_s", 0.0),
            timings.get("stt_s", 0.0),
            timings["translate_s"],
            timings["latency_s"],
        )
        self.on_utterance(utt)
        return utt

    def flush_held(self, only_expired: bool = False) -> list[Utterance]:
        """Entrega fragmentos que esperavam continuação (todos, ou só os vencidos)."""
        now = time.monotonic()
        with self._held_lock:
            keys = [k for k, (_, dl) in self._held.items() if not only_expired or dl <= now]
            items = [self._held.pop(k)[0] for k in keys]
        return [self._emit_final(u) for u in items]

    def _next_deadline(self) -> float | None:
        with self._held_lock:
            return min((dl for _, dl in self._held.values()), default=None)

    def _resolve_speaker(
        self, role: SourceRole, audio: np.ndarray, final: bool
    ) -> tuple[Speaker | None, Lang, float]:
        if role.speaker is not None:
            if not role.check_language or not final:  # parciais não pagam a detecção extra
                return role.speaker, role.speaker.lang, 1.0
            detected, prob = self.stt.detect_language(audio)
            if detected != role.speaker.lang and prob >= role.echo_reject_probability:
                return None, detected, prob
            return role.speaker, role.speaker.lang, prob if detected == role.speaker.lang else 1 - prob
        detected, prob = self.stt.detect_language(audio)
        return self.speakers[detected], detected, prob


def _with_lang_probability(tr: Transcript, prob: float) -> Transcript:
    from dataclasses import replace

    from .stt import ConfidenceConfig

    low = tr.low_confidence or prob < ConfidenceConfig().min_lang_probability
    return replace(tr, lang_probability=prob, low_confidence=low)
