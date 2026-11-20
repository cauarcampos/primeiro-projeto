"""Compara tradutores com frases paralelas traduzidas por humanos (FLEURS/FLORES).

Nota chrF++ (0–100): quanto maior, mais próxima da tradução humana.

Uso:
  python -m bridge_poc.bench_traducao --fleurs-pt PASTA/pt_br --fleurs-uk PASTA/uk_ua -n 40
  python -m bridge_poc.bench_traducao ... --tradutor ia --ia-modelo translategemma
"""

from __future__ import annotations

import argparse
import csv
import os
import statistics
import time

from .config import add_model_args, build_translator
from .domain import Lang


def load_parallel(pt_dir: str, uk_dir: str, split: str = "dev") -> list[tuple[str, str]]:
    def load(folder):
        out = {}
        with open(os.path.join(folder, f"{split}.tsv"), encoding="utf-8") as f:
            for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                out.setdefault(row[0], row[2].strip())
        return out

    pt, uk = load(pt_dir), load(uk_dir)
    return [(pt[k], uk[k]) for k in sorted(set(pt) & set(uk), key=int)]


def main(argv: list[str] | None = None) -> None:
    import sacrebleu

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--fleurs-pt", required=True)
    ap.add_argument("--fleurs-uk", required=True)
    ap.add_argument("-n", type=int, default=40)
    ap.add_argument("--mostrar", type=int, default=3)
    add_model_args(ap)
    args = ap.parse_args(argv)

    pairs = load_parallel(args.fleurs_pt, args.fleurs_uk)[: args.n]
    translator = build_translator(args)
    print(f"Tradutor: {args.tradutor} · {len(pairs)} frases por direção")

    for src, tgt in ((Lang.PT, Lang.UK), (Lang.UK, Lang.PT)):
        hyps, refs, times = [], [], []
        for i, (pt, uk) in enumerate(pairs):
            source, ref = (pt, uk) if src is Lang.PT else (uk, pt)
            t0 = time.monotonic()
            hyp = translator.translate(source, src, tgt)
            times.append(time.monotonic() - t0)
            hyps.append(hyp)
            refs.append(ref)
            if i < args.mostrar:
                print(f"\n  {src.value}: {source}\n  ref: {ref}\n  sai: {hyp}")
        chrf = sacrebleu.corpus_chrf(hyps, [refs], word_order=2).score
        print(
            f"\n>>> {src.value}→{tgt.value}: chrF++ {chrf:.1f} · "
            f"tempo mediano {statistics.median(times):.2f}s"
        )


if __name__ == "__main__":
    main()
