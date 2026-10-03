"""Musteri DTO. Q25: ad ve iletisim maskesi varsayilan acik."""

from __future__ import annotations

from pydantic import BaseModel


def mask_text(value: str, enabled: bool = True) -> str:
    if not enabled or value == "":
        return value
    if "@" in value:
        local, _, domain = value.partition("@")
        return (local[:1] + "***@" + domain) if local else "***@" + domain
    if len(value) <= 2:
        return "*" * len(value)
    return value[0] + "***" + value[-1]


class CustomerCard(BaseModel):
    id: int
    name: str
    contact: str | None = None
