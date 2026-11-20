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


# ---------------------------------------------------------------------------------------
# Tradução por IA local (TranslateGemma via Ollama ou servidor compatível com llama.cpp)
# ---------------------------------------------------------------------------------------

_LANG_NAMES = {Lang.PT: ("Portuguese", "pt-BR"), Lang.UK: ("Ukrainian", "uk-UA")}
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def translategemma_prompt(text: str, src: Lang, tgt: Lang) -> str:
    """Prompt idêntico ao chat template oficial do TranslateGemma (Google)."""
    s_name, s_code = _LANG_NAMES[src]
    t_name, t_code = _LANG_NAMES[tgt]
    body = (
        f"You are a professional {s_name} ({s_code}) to {t_name} ({t_code}) translator. "
        f"Your goal is to accurately convey the meaning and nuances of the original {s_name} text "
        f"while adhering to {t_name} grammar, vocabulary, and cultural sensitivities.\n"
        f"Produce only the {t_name} translation, without any additional explanations or commentary. "
        f"Please translate the following {s_name} text into {t_name}:\n\n\n{text.strip()}"
    )
    return f"<start_of_turn>user\n{body}<end_of_turn>\n<start_of_turn>model\n"


def clean_output(text: str) -> str:
    text = text.split("<end_of_turn>", 1)[0].strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'«“":
        text = text[1:-1].strip()
    return text


class LlmTranslator:
    """Traduz com um modelo de linguagem rodando localmente.

    backend "ollama": http://127.0.0.1:11434 (/api/generate em modo raw)
    backend "openai": servidor compatível (llama.cpp / LM Studio), /v1/completions

    Se o servidor não responder, usa o `fallback` (NLLB) e tenta a IA de novo depois de
    `retry_after_s` — a conversa nunca fica sem legenda.
    """

    def __init__(
        self,
        model: str,
        url: str = "http://127.0.0.1:11434",
        backend: str = "ollama",
        fallback: Translator | None = None,
        timeout_s: float = 10.0,
        retry_after_s: float = 30.0,
        allow_remote: bool = False,
    ):
        from urllib.parse import urlparse

        host = urlparse(url).hostname or ""
        if host not in _LOCAL_HOSTS and not allow_remote:
            raise ValueError(
                f"O tradutor por IA deve rodar neste computador (endereço recebido: {host}). "
                "Enviar o texto para outra máquina quebraria a promessa de privacidade."
            )
        if backend not in ("ollama", "openai"):
            raise ValueError("backend deve ser 'ollama' ou 'openai'")
        self.model, self.url, self.backend = model, url.rstrip("/"), backend
        self.fallback = fallback
        self.timeout_s, self.retry_after_s = timeout_s, retry_after_s
        self._down_until = 0.0
        self.last_engine = "ia"
        self.failures = 0

    def _post(self, path: str, payload: dict) -> dict:
        import json
        import urllib.request

        req = urllib.request.Request(
            self.url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # nunca via proxy
        with opener.open(req, timeout=self.timeout_s) as r:
            return json.loads(r.read().decode("utf-8"))

    def _generate(self, prompt: str) -> str:
        if self.backend == "ollama":
            data = self._post(
                "/api/generate",
                {
                    "model": self.model,
                    "prompt": prompt,
                    "raw": True,
                    "stream": False,
                    "keep_alive": "30m",
                    "options": {"temperature": 0, "num_predict": 300, "stop": ["<end_of_turn>"]},
                },
            )
            return data.get("response", "")
        data = self._post(
            "/v1/completions",
            {"model": self.model, "prompt": prompt, "max_tokens": 300, "temperature": 0,
             "stop": ["<end_of_turn>"]},
        )
        return data["choices"][0]["text"]

    def check(self) -> str | None:
        """Tenta uma tradução curta; devolve None se ok, ou a mensagem de erro."""
        try:
            out = clean_output(self._generate(translategemma_prompt("Olá.", Lang.PT, Lang.UK)))
            return None if out else "resposta vazia"
        except Exception as e:  # pragma: no cover - depende da máquina
            return f"{type(e).__name__}: {e}"

    def translate(self, text: str, src: Lang, tgt: Lang) -> str:
        import time

        if not text.strip():
            return ""
        if time.monotonic() >= self._down_until:
            try:
                out = clean_output(self._generate(translategemma_prompt(text, src, tgt)))
                if out:
                    self.last_engine = "ia"
                    return out
            except Exception:
                self.failures += 1
                self._down_until = time.monotonic() + self.retry_after_s
        if self.fallback is None:
            raise RuntimeError("Tradutor por IA indisponível e sem alternativa configurada")
        self.last_engine = "nllb"
        return self.fallback.translate(text, src, tgt)


class CheckedTranslator:
    """Traduz com o principal (IA) e confere números, dias e meses.

    - Fatos conferem → usa a tradução da IA.
    - Não conferem → tenta o secundário (NLLB); se ele conferir, usa o NLLB.
    - Nenhum confere → mantém a da IA, mas devolve o aviso para a legenda marcar "≈".
    """

    def __init__(self, primary: Translator, secondary: Translator | None = None):
        self.primary, self.secondary = primary, secondary
        self.swaps = 0

    @property
    def last_engine(self) -> str:
        return getattr(self.primary, "last_engine", "principal")

    def translate(self, text: str, src: Lang, tgt: Lang) -> str:
        return self.translate_checked(text, src, tgt)[0]

    def translate_checked(self, text: str, src: Lang, tgt: Lang) -> tuple[str, list[str]]:
        from .factcheck import check

        out = self.primary.translate(text, src, tgt)
        problems = check(text, out, src, tgt)
        if not problems or self.secondary is None:
            return out, problems
        alt = self.secondary.translate(text, src, tgt)
        if not check(text, alt, src, tgt):
            self.swaps += 1
            return alt, []
        return out, problems


class RoutedTranslator:
    """Escolhe o tradutor por direção.

    Nos testes do BRIDGE com frases de conversa de casal:
    - uk→pt: a IA (TranslateGemma) escreve português do Brasil; o NLLB, de Portugal.
    - pt→uk: o NLLB usa o "ти" íntimo; a IA às vezes usa o formal "ви".
    """

    def __init__(self, routes: dict[tuple[Lang, Lang], Translator]):
        self.routes = routes

    def _pick(self, src: Lang, tgt: Lang) -> Translator:
        return self.routes[(src, tgt)]

    def translate(self, text: str, src: Lang, tgt: Lang) -> str:
        return self._pick(src, tgt).translate(text, src, tgt)

    def translate_checked(self, text: str, src: Lang, tgt: Lang) -> tuple[str, list[str]]:
        t = self._pick(src, tgt)
        if hasattr(t, "translate_checked"):
            return t.translate_checked(text, src, tgt)
        from .factcheck import check

        out = t.translate(text, src, tgt)
        return out, check(text, out, src, tgt)
