"""Hata govdesi ve govde boyu siniri. Q13: JSON 1 MiB, yukleme 20 MiB."""

from __future__ import annotations

import uuid

from fastapi import FastAPI

JSON_LIMIT = 1024 * 1024
UPLOAD_LIMIT = 20 * 1024 * 1024


def error_body(code: str, message: str) -> dict:
    return {
        "status": "error",
        "code": code,
        "message": message,
        "reference": uuid.uuid4().hex[:8],
    }


class BodyLimitMiddleware:
    def __init__(self, app, json_limit: int = JSON_LIMIT, upload_limit: int = UPLOAD_LIMIT) -> None:
        self.app = app
        self.json_limit = json_limit
        self.upload_limit = upload_limit

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}
            raw = headers.get("content-length", "")
            if raw.isdigit():
                size = int(raw)
                ctype = headers.get("content-type", "")
                limit = self.upload_limit if ctype.startswith("multipart/") else self.json_limit
                if size > limit:
                    body = b'{"status":"error","code":"TL-VAL-01","message":"Govde cok buyuk","reference":"size"}'
                    await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json")]})
                    await send({"type": "http.response.body", "body": body})
                    return
        await self.app(scope, receive, send)


def setup(app: FastAPI) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    app.state.settings = settings
    app.add_middleware(BodyLimitMiddleware, json_limit=settings.json_limit, upload_limit=settings.upload_limit)
