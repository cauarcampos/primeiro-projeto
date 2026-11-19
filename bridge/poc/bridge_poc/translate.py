"""Tradução português ⇄ ucraniano.

Padrão: NLLB-200 (Meta) convertido para CTranslate2, rodando 100% no computador.
Nenhum texto sai da máquina. Licença do modelo: CC-BY-NC 4.0 (uso privado/não comercial).
"""

from __future__ import annotations

import os
import re
from typing import Protocol

from .domain import Lang


class Translator(Protocol):
    def translate(self, text: str, src: Lang, tgt: Lang) -> str: ...


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def split_sentences(text: str) -> list[str]:
    """Divide em frases (o NLLB traduz melhor frase a frase e não 'resume' textos longos)."""
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text.strip())]
    return [p for p in parts if p]


class NllbTranslator:
    def __init__(self, model_dir: str, device: str = "auto", beam_size: int = 4):
        import ctranslate2
        import sentencepiece as spm

        from .stt import resolve_device

        self.device, _ = resolve_device(device)
        compute_type = "int8_float16" if self.device == "cuda" else "int8"
        sp_path = os.path.join(model_dir, "sentencepiece.bpe.model")
        if not os.path.exists(sp_path):
            raise FileNotFoundError(f"Tokenizador não encontrado em {sp_path}")
        self._sp = spm.SentencePieceProcessor(model_file=sp_path)
        self._tr = ctranslate2.Translator(model_dir, device=self.device, compute_type=compute_type)
        self._beam = beam_size

    def translate(self, text: str, src: Lang, tgt: Lang) -> str:
        sentences = split_sentences(text)
        if not sentences:
            return ""
        batch = [[src.nllb_code] + self._sp.encode(s, out_type=str) + ["</s>"] for s in sentences]
        results = self._tr.translate_batch(
            batch,
            target_prefix=[[tgt.nllb_code]] * len(batch),
            beam_size=self._beam,
            max_decoding_length=256,
            # evita repetições em loop (falha conhecida de modelos de tradução)
            repetition_penalty=1.1,
            no_repeat_ngram_size=4,
        )
        out = []
        for r in results:
            tokens = r.hypotheses[0]
            if tokens and tokens[0] == tgt.nllb_code:
                tokens = tokens[1:]
            out.append(self._sp.decode(tokens))
        return " ".join(s.strip() for s in out if s.strip())
