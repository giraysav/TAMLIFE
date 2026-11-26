"""One audit stream. Secret field names are refused and never stored."""

from __future__ import annotations

import logging
from collections.abc import Callable

FORBIDDEN = (
    "pin_code",
    "totp_secret",
    "password",
    "bind_password",
    "set-cookie",
    "session_token",
)


class SecretAuditError(ValueError):
    pass


def guard(detail: str) -> str:
    lowered = detail.lower()
    for token in FORBIDDEN:
        if token in lowered:
            raise SecretAuditError("audit detail refused")
    return detail[:500]


_log = logging.getLogger("tamlife.denetim")


class AuditLog:
    """Denetim olayini dogrular ve KALICI yaziciya (sink) verir.

    sink uygulama kurulurken verilir (yonetim.gunlukler.kalici_yaz); yazilamazsa istegi dusurmez.
    """

    def __init__(self) -> None:
        self.sink: Callable[[dict[str, str]], None] | None = None

    def remember(
        self,
        *,
        actor: str,
        action: str,
        outcome: str,
        module_key: str = "",
        detail: str = "",
        ip: str = "",
    ) -> dict[str, str]:
        row = {
            "actor": actor[:120],
            "action": action[:80],
            "outcome": outcome[:40],
            "module_key": module_key[:80],
            "detail": guard(detail),
            "ip": (ip or "")[:64],  # giris olaylarinda istemci IP'si
        }
        if self.sink is not None:
            try:
                self.sink(row)
            except Exception:  # noqa: BLE001 - denetim yazilamasa da istek dusmemeli
                _log.warning("denetim olayi kalici yazilamadi", exc_info=True)
        return row


audit_log = AuditLog()
