"""Maskeleme varsayilan acik. Deger repoda yok."""

from __future__ import annotations

from app.core.config import Settings
from app.modules.musteri.schemas import mask_text


def test_masking_default_on() -> None:
    assert Settings().masking is True
    assert mask_text("Ada") == "A***a"
    assert mask_text("a@ornek.example") == "a***@ornek.example"
    assert mask_text("Ada", enabled=False) == "Ada"
