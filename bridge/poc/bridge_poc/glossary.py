"""Glossário pessoal: nomes que o reconhecimento deve conhecer e correções automáticas.

Formato do arquivo (UTF-8, uma regra por linha):

    # comentário
    Katya                      ← nome/palavra: ajuda o Whisper a reconhecer
    Kátia => Katya             ← correção: aplicada no texto reconhecido e na tradução
    Катія => Катя

Correções diferenciam palavras inteiras e ignoram maiúsculas/minúsculas.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace

from .domain import Lang, Transcript, Word

_CYRILLIC = re.compile(r"[\u0400-\u04FF]")


def is_cyrillic(text: str) -> bool:
    return bool(_CYRILLIC.search(text))


@dataclass
class Glossary:
    names: list[str] = field(default_factory=list)
    corrections: list[tuple[re.Pattern, str]] = field(default_factory=list)

    @classmethod
    def parse(cls, text: str) -> "Glossary":
        g = cls()
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            if "=>" in line:
                wrong, right = (p.strip() for p in line.split("=>", 1))
                if wrong and right:
                    pattern = re.compile(rf"(?<!\w){re.escape(wrong)}(?!\w)", re.IGNORECASE)
                    g.corrections.append((pattern, right))
                    if right not in g.names:
                        g.names.append(right)
            elif line not in g.names:
                g.names.append(line)
        return g

    @classmethod
    def load(cls, path: str | None) -> "Glossary":
        if not path or not os.path.exists(path):
            return cls()
        with open(path, encoding="utf-8-sig") as f:
            return cls.parse(f.read())

    def __bool__(self) -> bool:
        return bool(self.names or self.corrections)

    def prompt(self, extra: str | None = None, lang: Lang | None = None) -> str | None:
        """Texto de contexto para o Whisper (aumenta a chance de acertar esses nomes).

        Com `lang`, usa só nomes escritos no alfabeto do idioma: nomes em cirílico na dica do
        português fariam o Whisper escrever português em cirílico (e vice-versa).
        """
        parts = [p.strip() for p in (extra or "").split(",") if p.strip()]
        parts += [n for n in self.names if n not in parts]
        if lang is not None:
            parts = [p for p in parts if is_cyrillic(p) == (lang is Lang.UK)]
        return ", ".join(parts) + "." if parts else None

    def prompts(self, extra: str | None = None) -> dict[Lang, str | None]:
        return {lang: self.prompt(extra, lang) for lang in Lang}

    def correct_text(self, text: str | None) -> str | None:
        if not text or not self.corrections:
            return text
        for pattern, right in self.corrections:
            text = pattern.sub(right, text)
        return text

    def correct_transcript(self, tr: Transcript) -> Transcript:
        if not self.corrections:
            return tr
        new_text = self.correct_text(tr.text)
        if new_text == tr.text:
            return tr
        words = []
        for w in tr.words:
            fixed = self.correct_text(w.text)
            # palavra corrigida pelo glossário deixa de ser "incerta"
            words.append(Word(fixed, w.probability, w.uncertain and fixed == w.text))
        if "".join(w.text for w in words).strip() != new_text.strip():
            # correção que atravessa palavras: mantém o texto corrigido como um bloco
            uncertain = any(w.uncertain for w in tr.words)
            words = [Word(" " + new_text.strip(), min((w.probability for w in tr.words), default=1.0), uncertain)]
        return replace(tr, text=new_text, words=tuple(words))
