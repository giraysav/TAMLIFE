"""Moduller arasi ozet sozlesmesi. Is kurali yok."""

from __future__ import annotations

from typing import Protocol


class SummaryCard(Protocol):
    def card(self, user_id: int) -> dict: ...
