"""Baixa os modelos de IA (uma única vez) para uso 100% offline.

Uso:  python -m bridge_poc.modelos                 (Whisper turbo + NLLB 1.3B, ~3 GB)
      python -m bridge_poc.modelos --listar
      python -m bridge_poc.modelos whisper-small nllb-600m

As revisões são fixas (commit do Hugging Face): o que é baixado não muda sem atualização deste arquivo.
Depois de baixados, nenhum dado é enviado a lugar nenhum.
"""

from __future__ import annotations

import argparse
import os

from .config import MODELS, default_models_dir

DEFAULT = ["whisper-large-v3-turbo", "nllb-1.3b"]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("modelos", nargs="*", help=f"opções: {', '.join(MODELS)}")
    ap.add_argument("--pasta-modelos", default=default_models_dir())
    ap.add_argument("--listar", action="store_true")
    args = ap.parse_args(argv)
    unknown = [m for m in args.modelos if m not in MODELS]
    if unknown:
        ap.error(f"modelo desconhecido: {', '.join(unknown)} (opções: {', '.join(MODELS)})")

    if args.listar:
        for key, m in MODELS.items():
            print(f"{key:24} {m.license:14} {m.note}")
        return

    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    from huggingface_hub import snapshot_download

    os.makedirs(args.pasta_modelos, exist_ok=True)
    for key in args.modelos or DEFAULT:
        m = MODELS[key]
        dest = os.path.join(args.pasta_modelos, m.folder)
        print(f"→ {key}: {m.note}\n  licença: {m.license}\n  destino: {dest}")
        snapshot_download(
            m.repo,
            revision=m.revision,
            local_dir=dest,
            allow_patterns=["*.bin", "*.json", "*.txt", "*.model"],
        )
        print("  ok")
    print("\nPronto. Modelos em:", args.pasta_modelos)
    if any(MODELS[k].license.startswith("CC-BY-NC") for k in args.modelos or DEFAULT):
        print("Aviso: NLLB é licenciado CC-BY-NC 4.0 — uso pessoal/não comercial.")


if __name__ == "__main__":
    main()
