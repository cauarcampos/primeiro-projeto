"""Benchmark: precisão do reconhecimento (WER), acerto do idioma, tempo e exemplos de tradução.

Uso:
  python -m bridge_poc.bench --fleurs PASTA_FLEURS/uk_ua --lang uk -n 30
  python -m bridge_poc.bench --pasta MINHAS_GRAVACOES --lang pt     (arquivos .wav + .txt de mesmo nome)

Nada é enviado para fora do computador.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import statistics
import time
import unicodedata

from .audio import read_wav
from .config import add_model_args, build_transcriber, build_translator
from .domain import Lang
from .vad import SAMPLE_RATE


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().replace("’", "'").replace("ʼ", "'")
    text = re.sub(r"[^\w\s']", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_fleurs(folder: str, split: str = "dev") -> list[tuple[str, str]]:
    items, seen = [], set()
    with open(os.path.join(folder, f"{split}.tsv"), encoding="utf-8") as f:
        for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            wav = os.path.join(folder, split, row[1])
            if row[1] not in seen and os.path.exists(wav):
                seen.add(row[1])
                items.append((wav, row[2]))
    return items


def load_folder(folder: str) -> list[tuple[str, str]]:
    items = []
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith(".wav"):
            txt = os.path.join(folder, name[:-4] + ".txt")
            ref = open(txt, encoding="utf-8").read().strip() if os.path.exists(txt) else ""
            items.append((os.path.join(folder, name), ref))
    return items


def main(argv: list[str] | None = None) -> None:
    import jiwer

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--fleurs", help="pasta de um idioma do FLEURS (com dev.tsv e dev/)")
    ap.add_argument("--pasta", help="pasta com .wav e .txt")
    ap.add_argument("--lang", choices=["pt", "uk"], required=True)
    ap.add_argument("-n", type=int, default=30, help="quantidade de amostras")
    ap.add_argument("--sem-traducao", action="store_true")
    ap.add_argument("--mostrar", type=int, default=5, help="exemplos impressos")
    add_model_args(ap)
    args = ap.parse_args(argv)

    items = load_fleurs(args.fleurs) if args.fleurs else load_folder(args.pasta)
    items = items[: args.n]
    lang = Lang(args.lang)

    t = time.monotonic()
    stt = build_transcriber(args)
    translator = None if args.sem_traducao else build_translator(args)
    print(f"Modelos carregados em {time.monotonic() - t:.1f}s (dispositivo: {stt.device})")

    refs, hyps, lid_ok, rtf, trans_t, lows, shown = [], [], 0, [], [], 0, 0
    for wav, ref in items:
        audio = read_wav(wav)
        dur = len(audio) / SAMPLE_RATE
        t0 = time.monotonic()
        detected, prob = stt.detect_language(audio)
        tr = stt.transcribe(audio, lang)
        stt_s = time.monotonic() - t0
        rtf.append(stt_s / dur)
        lid_ok += detected == lang
        lows += tr.low_confidence
        if ref:
            refs.append(normalize(ref))
            hyps.append(normalize(tr.text) or "-")
        translation = ""
        if translator and tr.text:
            t1 = time.monotonic()
            translation = translator.translate(tr.text, lang, lang.other)
            trans_t.append(time.monotonic() - t1)
        if shown < args.mostrar:
            shown += 1
            print(f"\n[{os.path.basename(wav)}] {dur:.1f}s · idioma detectado={detected.value} ({prob:.2f})")
            print(f"  referência : {ref}")
            print(f"  reconhecido: {tr.text}{'   (baixa confiança)' if tr.low_confidence else ''}")
            if translation:
                print(f"  tradução   : {translation}")

    n = len(items)
    print("\n================ RESULTADO ================")
    print(f"Amostras: {n} · idioma: {lang.value}")
    if refs:
        print(f"WER (erro por palavra): {jiwer.wer(refs, hyps) * 100:.1f}%")
    print(f"Idioma detectado corretamente: {lid_ok}/{n} ({lid_ok / n * 100:.0f}%)")
    print(f"Marcadas como baixa confiança: {lows}/{n}")
    print(f"Tempo de reconhecimento / duração do áudio (RTF): mediana {statistics.median(rtf):.2f}")
    if trans_t:
        print(f"Tempo de tradução: mediana {statistics.median(trans_t):.2f}s")


if __name__ == "__main__":
    main()
