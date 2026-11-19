"""BRIDGE — legendas traduzidas pt-BR ⇄ uk-UA em tempo real, 100% no seu computador.

Modos:
  computador  Microfone = você · som do computador (loopback) = a outra pessoa.
              Use com a chamada do Instagram aberta no navegador. Recomendado: fone de ouvido.
  ambiente    Um microfone ouve os dois (ex.: celular em viva-voz ao lado do PC).
              Quem fala é deduzido pelo idioma.
  arquivo     Testa com um arquivo .wav (não usa microfone).

Exemplos:
  python -m bridge_poc computador
  python -m bridge_poc ambiente --microfone "Headset"
  python -m bridge_poc arquivo --wav teste.wav --sem-interface
  python -m bridge_poc --listar-dispositivos
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from .config import add_model_args, build_transcriber, build_translator, load_glossary
from .domain import Lang, Speaker, Utterance
from .history import History
from .pipeline import Pipeline, SourceRole
from .vad import SegmenterConfig, SileroStreamingVad


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="python -m bridge_poc", description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    ap.add_argument("modo", nargs="?", choices=["computador", "ambiente", "arquivo"], default="computador")
    ap.add_argument("--listar-dispositivos", action="store_true")
    ap.add_argument("--diagnostico", action="store_true", help="mostra se a GPU foi encontrada")

    p = ap.add_argument_group("pessoas")
    p.add_argument("--eu-nome", default="Cauã")
    p.add_argument("--eu-idioma", choices=["pt", "uk"], default="pt")
    p.add_argument("--parceiro-nome", default="Katya")

    a = ap.add_argument_group("áudio")
    a.add_argument("--microfone", help="parte do nome do microfone (padrão: o do Windows)")
    a.add_argument("--saida", help="parte do nome da saída de som para o loopback (padrão: a do Windows)")
    a.add_argument("--wav", help="arquivo para o modo arquivo")
    a.add_argument("--wav-quem", choices=["parceiro", "eu", "auto"], default="auto",
                   help="no modo arquivo: de quem é a voz (auto = pelo idioma)")
    a.add_argument("--sem-filtro-eco", action="store_true",
                   help="não descarta, no microfone, falas no idioma da outra pessoa")
    a.add_argument("--silencio-ms", type=int, default=550, help="pausa que encerra uma fala")
    a.add_argument("--juntar-ms", type=int, default=1500,
                   help="espera por continuação de frases cortadas (0 = desliga)")

    u = ap.add_argument_group("exibição")
    u.add_argument("--sem-interface", action="store_true", help="mostra as legendas no terminal")
    u.add_argument("--so-traducao", action="store_true")
    u.add_argument("--esconder-minhas-falas", action="store_true")
    u.add_argument("--sem-parciais", action="store_true", help="não mostra o texto enquanto a pessoa fala")
    u.add_argument("--historico", action="store_true", help="liga o histórico (só na memória)")
    u.add_argument("--transparencia", type=float, default=0.90)
    u.add_argument("--metricas", action="store_true", help="mostra tempos (sem conteúdo) no terminal")

    add_model_args(ap)
    return ap.parse_args(argv)


def print_utterance(u: Utterance, show_original: bool = True) -> None:
    if not u.is_final:
        return
    flag = " (≈ baixa confiança)" if u.low_confidence else ""
    if show_original:
        marked = "".join(f"[{w.text.strip()}?] " if w.uncertain else w.text for w in u.transcript.words)
        print(f"\n{u.speaker.name.upper()} — ORIGINAL ({u.transcript.lang.label_pt}): {marked.strip()}")
    label = u.target_lang.label_pt if u.target_lang else ""
    print(f"TRADUÇÃO — {label}: {u.translation}{flag}", flush=True)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.metricas else logging.WARNING,
        format="%(asctime)s %(name)s: %(message)s",
    )

    if args.listar_dispositivos:
        from .audio import list_devices

        print(list_devices())
        return 0
    if args.diagnostico:
        from .gpu import describe

        print(describe())
        return 0

    my_lang = Lang(args.eu_idioma)
    me = Speaker(args.eu_nome, my_lang, is_me=True)
    partner = Speaker(args.parceiro_nome, my_lang.other)

    from .audio import ArrayAudioSource, SoundcardSource, read_wav

    if args.modo == "computador":
        sources = [
            SoundcardSource("mic", loopback=False, device_name=args.microfone),
            SoundcardSource("sistema", loopback=True, device_name=args.saida),
        ]
        roles = [
            SourceRole("mic", speaker=me, check_language=not args.sem_filtro_eco),
            SourceRole("sistema", speaker=partner),
        ]
        labels = {"mic": me.name, "sistema": partner.name}
    elif args.modo == "ambiente":
        sources = [SoundcardSource("mic", loopback=False, device_name=args.microfone)]
        roles = [SourceRole("mic")]
        labels = {"mic": "microfone"}
    else:
        if not args.wav:
            print("Informe o arquivo: --wav caminho.wav", file=sys.stderr)
            return 2
        sources = [ArrayAudioSource("arquivo", read_wav(args.wav), realtime=not args.sem_interface)]
        who = {"parceiro": partner, "eu": me, "auto": None}[args.wav_quem]
        roles = [SourceRole("arquivo", speaker=who)]
        labels = {"arquivo": "arquivo"}

    print("Carregando modelos (a primeira vez pode levar ~30 s)…", flush=True)
    t0 = time.monotonic()
    stt = build_transcriber(args)
    translator = build_translator(args)
    print(f"Pronto em {time.monotonic() - t0:.0f}s · processamento: {stt.device.upper()} · nada sai deste computador.")

    seg_cfg = SegmenterConfig(
        min_silence_ms=args.silencio_ms,
        # no terminal só as falas finais são mostradas: não gasta processamento com parciais
        partial_interval_s=0 if (args.sem_parciais or args.sem_interface) else 1.0,
    )
    history = History(enabled=args.historico)

    window = None
    if args.sem_interface:
        on_utt, on_discard = (lambda u: print_utterance(u, not args.so_traducao)), None
    else:
        from .ui import SubtitleWindow

        holder: dict = {}
        on_utt = lambda u: holder["w"].post(u)  # noqa: E731
        on_discard = lambda s, i: holder["w"].discard(s, i)  # noqa: E731

    glossary = load_glossary(args)
    if glossary:
        print(f"Glossário: {len(glossary.names)} nomes, {len(glossary.corrections)} correções.")
    pipeline = Pipeline(
        stt, translator, (me, partner), roles, on_utt, SileroStreamingVad, seg_cfg, history,
        on_discard, glossary=glossary, merge_window_s=args.juntar_ms / 1000,
    )
    if not args.sem_interface:
        window = SubtitleWindow(
            pipeline,
            labels,
            show_original=not args.so_traducao,
            show_mine=not args.esconder_minhas_falas,
            alpha=args.transparencia,
        )
        holder["w"] = window

    pipeline.start()
    for s in sources:
        s.start(pipeline.callback_for(s.source_id))
    try:
        if window:
            window.run()
        elif args.modo == "arquivo":
            sources[0].finished.wait()
            pipeline.flush()
            pipeline.wait_idle(timeout=600)
        else:
            print("Ouvindo… (Ctrl+C para sair)")
            while True:
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for s in sources:
            s.stop()
        pipeline.stop()
        history.clear()
    st = pipeline.stats
    print(f"\nEncerrado. Falas: {st.finals} · descartadas (vazias/ruído): {st.dropped_empty} · eco filtrado: {st.dropped_echo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
