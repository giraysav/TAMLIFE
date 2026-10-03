"""Sahte AD. ldap3 ve ag cagrisi yok."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DirectoryHit:
    username: str
    role: str
    is_admin: bool


class FakeDirectory:
    def __init__(self) -> None:
        self.lookups = 0
        self.ldap_calls = 0

    def authenticate(self, username: str, password: str) -> DirectoryHit | None:
        del username, password
        self.lookups += 1
        return None


directory = FakeDirectory()
