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
    "parakeet-uk": ModelSpec(
        "ihnatov-yuri/parakeet-tdt-0.6b-v3-uk",
        "5c4bcfaca501587beaedfd23b72a678bf7194de1",
        "parakeet-tdt-0.6b-v3-uk",
        "CC-BY-4.0",
        "Parakeet UK: reconhecimento especializado em ucraniano, ~2,5 GB (requer instalar_ucraniano.bat)",
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


# TranslateGemma 4B (Google, jan/2026), quantizado Q4_K_M, baixado pelo Ollama direto do Hugging Face.
DEFAULT_LLM = "hf.co/bullerwins/translategemma-4b-it-GGUF:Q4_K_M"


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
    g.add_argument("--ucraniano", choices=["auto", "parakeet", "whisper"], default="auto",
                   help="reconhecimento do ucraniano: auto = Parakeet UK se instalado")
    g.add_argument("--tradutor", choices=["auto", "ia", "nllb"], default="auto",
                   help="auto = IA local se disponível, senão NLLB")
    g.add_argument("--ia-modelo", default=DEFAULT_LLM)
    g.add_argument("--ia-direcoes", choices=["uk-pt", "ambas"], default="uk-pt",
                   help="em quais direções usar a IA (padrão: só ucraniano→português)")
    g.add_argument("--ia-url", default="http://127.0.0.1:11434")
    g.add_argument("--ia-backend", choices=["ollama", "openai"], default="ollama")
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


def build_transcriber(args, verbose: bool = True):
    from .stt import FasterWhisperTranscriber

    if args.dispositivo != "cpu":
        prepare_cuda()
    whisper = FasterWhisperTranscriber(
        _check(model_path(args.whisper, args.pasta_modelos)),
        device=args.dispositivo,
        initial_prompt=load_glossary(args).prompts(args.nomes),
    )
    mode = getattr(args, "ucraniano", "whisper")
    if mode == "whisper":
        return whisper

    from .stt_uk import ParakeetRecognizer, UkrainianBoostedTranscriber, parakeet_available

    folder = model_path("parakeet-uk", args.pasta_modelos)
    ready = parakeet_available() and os.path.isdir(folder)
    if not ready:
        if mode == "parakeet":
            raise SystemExit(
                "Reconhecimento especializado em ucraniano não instalado. Rode instalar_ucraniano.bat"
            )
        if verbose:
            print("Ucraniano: Whisper (rode instalar_ucraniano.bat para mais precisão).")
        return whisper
    device = "cpu" if args.dispositivo == "cpu" else "auto"
    parakeet = ParakeetRecognizer(folder, device=device)
    if verbose:
        print(f"Ucraniano: Parakeet UK ({parakeet.device.upper()}) conferido pelo Whisper.")
    return UkrainianBoostedTranscriber(whisper, parakeet)


class LazyTranslator:
    """Carrega o NLLB só quando for preciso (economiza memória da placa de vídeo)."""

    def __init__(self, factory):
        self._factory, self._t = factory, None

    def translate(self, text, src, tgt):
        if self._t is None:
            self._t = self._factory()
        return self._t.translate(text, src, tgt)


def build_nllb(args):
    from .translate import NllbTranslator

    if args.dispositivo != "cpu":
        prepare_cuda()
    return NllbTranslator(_check(model_path(args.nllb, args.pasta_modelos)), device=args.dispositivo)


def build_translator(args, verbose: bool = True):
    """'auto': usa a IA local (TranslateGemma) se estiver rodando; senão, o NLLB."""
    from .domain import Lang
    from .translate import CheckedTranslator, LlmTranslator, RoutedTranslator

    mode = getattr(args, "tradutor", "nllb")
    if mode == "nllb":
        return build_nllb(args)
    nllb = LazyTranslator(lambda: build_nllb(args))  # só carrega se for preciso
    llm = LlmTranslator(args.ia_modelo, url=args.ia_url, backend=args.ia_backend, fallback=nllb)
    problem = llm.check()
    if problem is None:
        checked = CheckedTranslator(llm, nllb)
        if args.ia_direcoes == "ambas":
            if verbose:
                print(f"Tradução: IA local ({args.ia_modelo}) nas duas direções, com conferência de fatos.")
            return checked
        if verbose:
            print("Tradução: ucraniano→português pela IA local (português do Brasil); "
                  "português→ucraniano pelo NLLB. Ambas com conferência de números e datas.")
        return RoutedTranslator({(Lang.UK, Lang.PT): checked, (Lang.PT, Lang.UK): nllb})
    if mode == "ia":
        raise SystemExit(
            f"A IA de tradução não respondeu em {args.ia_url} ({problem}).\n"
            "Abra o Ollama ou rode instalar_ia.bat. Para usar o tradutor simples: --tradutor nllb"
        )
    if verbose:
        print("Tradução: NLLB (IA local não encontrada — rode instalar_ia.bat para mais precisão).")
    return build_nllb(args)
