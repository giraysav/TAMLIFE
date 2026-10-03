"""One audit stream. Secret field names are refused and never stored."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

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


class AuditLog:
    def __init__(self) -> None:
        self.events: list[dict[str, str]] = []

    def remember(
        self,
        *,
        actor: str,
        action: str,
        outcome: str,
        module_key: str = "",
        detail: str = "",
        db: Session | None = None,
    ) -> dict[str, str]:
        row = {
            "actor": actor[:120],
            "action": action[:80],
            "outcome": outcome[:40],
            "module_key": module_key[:80],
            "detail": guard(detail),
        }
        self.events.append(row)
        if db is not None:
            from app.models import AuditEvent

            db.add(
                AuditEvent(
                    at=datetime.now(timezone.utc),
                    actor=row["actor"],
                    action=row["action"],
                    outcome=row["outcome"],
                    module_key=row["module_key"],
                    detail=row["detail"],
                )
            )
        return row


audit_log = AuditLog()
