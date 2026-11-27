# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Yakalanmayan istisnalar: kullaniciya KOD + KAYIT NO doner, ham metin donmez; ayrinti ariza kaydina ve dosya gunlugune gider."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app import ariza
from app.session import current_user


async def genel_istisna(request: Request, exc: Exception) -> JSONResponse:
    kod = ariza.siniflandir(exc)
    kullanici = current_user(request)
    kayit = await run_in_threadpool(
        lambda: ariza.kaydet(
            kod,
            exc=exc,
            kaynak=f"{request.method} {request.url.path}",
            kullanici=kullanici.username if kullanici else "",
            arka_plan=kod == "TL-DB-02",  # DB kilitli: satir kilit kalkinca yazilir, 503 hemen doner
        )
    )
    return JSONResponse(
        {"detail": ariza.mesaj(kod, kayit), "hata_kodu": kod, "kayit_no": kayit},
        status_code=503 if kod == "TL-DB-02" else 500,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
