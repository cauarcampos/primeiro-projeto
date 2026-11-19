"""Configuração de modelos e construção dos componentes."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

from .gpu import prepare_cuda


def app_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "bridge")


def default_models_dir() -> str:
    return os.path.join(app_dir(), "modelos")


def default_glossary_path() -> str:
    return os.path.join(app_dir(), "glossario.txt")


@dataclass(frozen=True)
class ModelSpec:
    repo: str
    revision: str  # commit fixo: o arquivo baixado não muda sem revisão humana
    folder: str
    license: str
    note: str = ""


# Revisões fixadas em 2026-11-19.
MODELS: dict[str, ModelSpec] = {
    "whisper-large-v3-turbo": ModelSpec(
        "dropbox-dash/faster-whisper-large-v3-turbo",
        "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf",
        "faster-whisper-large-v3-turbo",
        "MIT",
        "Whisper large-v3-turbo (OpenAI) em formato CTranslate2, ~1,6 GB",
    ),
    "whisper-small": ModelSpec(
        "Systran/faster-whisper-small",
        "536b0662742c02347bc0e980a01041f333bce120",
        "faster-whisper-small",
        "MIT",
        "modelo leve (pior em ucraniano), ~0,5 GB",
    ),
    "nllb-1.3b": ModelSpec(
        "JustFrederik/nllb-200-distilled-1.3B-ct2-int8",
        "30c36268408177b0fce2bfcfa205d877accd327d",
        "nllb-200-distilled-1.3B-ct2-int8",
        "CC-BY-NC-4.0",
        "NLLB-200 1.3B (Meta) convertido para CTranslate2 int8, ~1,4 GB",
    ),
    "nllb-600m": ModelSpec(
        "JustFrederik/nllb-200-distilled-600M-ct2-int8",
        "302d78f00e6fdb50a1064059df7c392b735e9d05",
        "nllb-200-distilled-600M-ct2-int8",
        "CC-BY-NC-4.0",
        "versão menor, tradução pior, ~0,6 GB",
    ),
}


def model_path(key_or_path: str, models_dir: str) -> str:
    if key_or_path in MODELS:
        return os.path.join(models_dir, MODELS[key_or_path].folder)
    return key_or_path


def add_model_args(ap: argparse.ArgumentParser) -> None:
    g = ap.add_argument_group("modelos")
    g.add_argument("--whisper", default="whisper-large-v3-turbo", help="chave do modelo ou pasta")
    g.add_argument("--nllb", default="nllb-1.3b", help="chave do modelo ou pasta")
    g.add_argument("--dispositivo", default="auto", choices=["auto", "cuda", "cpu"])
    g.add_argument("--pasta-modelos", default=default_models_dir())
    g.add_argument("--nomes", default="Cauã, Katya", help="nomes próprios que ajudam o reconhecimento")
    g.add_argument(
        "--glossario",
        default=default_glossary_path(),
        help="arquivo com nomes e correções (veja glossario.exemplo.txt)",
    )


def load_glossary(args):
    from .glossary import Glossary

    return Glossary.load(getattr(args, "glossario", None))


def _check(path: str) -> str:
    if not os.path.isdir(path):
        raise SystemExit(
            f"Modelo não encontrado em: {path}\n"
            "Baixe os modelos primeiro:  python -m bridge_poc.modelos"
        )
    return path


def build_transcriber(args):
    from .stt import FasterWhisperTranscriber

    if args.dispositivo != "cpu":
        prepare_cuda()
    return FasterWhisperTranscriber(
        _check(model_path(args.whisper, args.pasta_modelos)),
        device=args.dispositivo,
        initial_prompt=load_glossary(args).prompts(args.nomes),
    )


def build_translator(args):
    from .translate import NllbTranslator

    if args.dispositivo != "cpu":
        prepare_cuda()
    return NllbTranslator(_check(model_path(args.nllb, args.pasta_modelos)), device=args.dispositivo)
