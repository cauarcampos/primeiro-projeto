"""Verificação de fatos da tradução: números, dias da semana e meses.

Modelos de IA às vezes trocam um fato mantendo a frase fluente
(ex.: "quinta-feira" → "п'ятниця"/sexta-feira). Esta checagem é determinística:
não "acha" nada, só compara o que é verificável.
"""

from __future__ import annotations

import re
import unicodedata

from .domain import Lang

# "segunda", "quinta", "sexta"… também são ordinais ("segunda vez"); só contam como dia
# com "-feira" ou depois de palavras como "na", "toda", "próxima".
_PT_DAY_CONTEXT = r"(?:na|nesta|nessa|numa|próxima|proxima|última|ultima|toda|até|ate|desta|dessa|essa|esta|de|às|as)\s+"


def _pt_day(stem: str) -> str:
    return rf"(?:{stem})[- ]feira|{_PT_DAY_CONTEXT}(?:{stem})(?!\w)"


# Cada conceito: (padrões pt, padrões uk). Padrões são radicais em minúsculas.
_WEEKDAYS = {
    "seg": (_pt_day("segunda"), r"понеділ"),
    "ter": (_pt_day("terça|terca"), r"вівтор"),
    "qua": (_pt_day("quarta"), r"серед[аиуі]"),
    "qui": (_pt_day("quinta"), r"четвер"),
    "sex": (_pt_day("sexta"), r"п'?ятниц"),
    "sab": (r"sábado|sabado", r"субот"),
    "dom": (r"domingo", r"(?<!по)неділ"),  # "понеділок" contém "неділ"
}
_MONTHS = {
    "01": (r"janeiro", r"січ(ень|ня|ні)"),
    "02": (r"fevereiro", r"лют(ий|ого|ому)"),
    "03": (r"março|marco", r"берез(ень|ня|ні)"),
    "04": (r"abril", r"квіт(ень|ня|ні)"),
    "05": (r"maio", r"трав(ень|ня|ні)"),
    "06": (r"junho", r"черв(ень|ня|ні)"),
    "07": (r"julho", r"лип(ень|ня|ні)"),
    "08": (r"agosto", r"серп(ень|ня|ні)"),
    "09": (r"setembro", r"верес(ень|ня|ні)"),
    "10": (r"outubro", r"жовт(ень|ня|ні)"),
    "11": (r"novembro", r"листопад"),
    "12": (r"dezembro", r"груд(ень|ня|ні)"),
}
_IDX = {Lang.PT: 0, Lang.UK: 1}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    return text.replace("’", "'").replace("ʼ", "'").replace("`", "'")


def _concepts(text: str, lang: Lang, table: dict) -> set[str]:
    t = _norm(text)
    i = _IDX[lang]
    # em ucraniano o radical pode vir com prefixo ("щопонеділка"), então não exige início de palavra
    boundary = r"(?<!\w)" if lang is Lang.PT else ""
    return {key for key, pats in table.items() if re.search(rf"{boundary}(?:{pats[i]})", t)}


def numbers(text: str) -> set[str]:
    """Números escritos com algarismos (sem zeros à esquerda; 3,5 e 3.5 viram 3.5)."""
    found = set()
    for m in re.findall(r"\d+(?:[.,]\d+)?", text):
        m = m.replace(",", ".")
        if "." in m:
            whole, frac = m.split(".", 1)
            if len(frac) == 3:  # 1.000 / 1,000 = milhar
                found.add(str(int(whole + frac)))
                continue
            found.add(f"{int(whole)}.{frac}")
        else:
            found.add(str(int(m)))
    return found


def check(source: str, translation: str, src: Lang, tgt: Lang) -> list[str]:
    """Lista de problemas encontrados (vazia = nada de errado detectado)."""
    problems = []
    missing = numbers(source) - numbers(translation)
    # "15h" → "15:00" gera 0 extra; só faltas importam
    if missing:
        problems.append("número ausente ou trocado: " + ", ".join(sorted(missing)))
    for label, table in (("dia da semana", _WEEKDAYS), ("mês", _MONTHS)):
        a, b = _concepts(source, src, table), _concepts(translation, tgt, table)
        if a != b:
            problems.append(f"{label} diferente")
    return problems
