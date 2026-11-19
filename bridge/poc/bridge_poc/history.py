"""Histórico temporário da conversa — somente em memória RAM.

Desligado por padrão. Nunca é gravado em disco; some ao fechar o programa ou ao clicar em limpar.
Itens mais antigos que `ttl_s` são descartados automaticamente.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from .domain import Utterance


class History:
    def __init__(self, enabled: bool = False, max_items: int = 500, ttl_s: float = 6 * 3600):
        self._enabled = enabled
        self._items: deque[Utterance] = deque(maxlen=max_items)
        self._ttl = ttl_s
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = value
        if not value:
            self.clear()

    def add(self, utt: Utterance) -> None:
        if not self._enabled or not utt.is_final:
            return
        with self._lock:
            self._items.append(utt)
            self._expire()

    def items(self) -> list[Utterance]:
        with self._lock:
            self._expire()
            return list(self._items)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def _expire(self) -> None:
        limit = time.monotonic() - self._ttl
        while self._items and self._items[0].created_at < limit:
            self._items.popleft()

    def __len__(self) -> int:
        return len(self.items())
