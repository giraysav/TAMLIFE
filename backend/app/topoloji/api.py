"""TopoMaker HTTP katmani. Gorme: uretimdeki gibi musteri modulu (@modul_gerekli('musteri')); topoloji katalogda menude
olmadigi icin rol gorunumu duzenleyicisinde secilemez, bu yuzden kapi 'musteri'dir. Dosya saklanmaz.

  PUT /topoloji/analiz?dosya=  -> ham CSV/XLSX govdesi (en fazla 10 MB) -> dugum/kenar/SPoF/il dagilimi
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from starlette.concurrency import run_in_threadpool

from app.audit import audit_log
from app.erisim import Erisim, modul_erisim
from app.ortak import ok
from app.topoloji import servis

router = APIRouter(prefix="/api/v1/topoloji", tags=["topoloji"])
topoloji_erisim = modul_erisim("musteri")
BUYUK = "Dosya 10 MB sınırını aşıyor."


@router.put("/analiz")
async def analiz(request: Request, dosya: str = Query(default="", max_length=200), e: Erisim = Depends(topoloji_erisim)) -> dict:
    if dosya and not dosya.lower().endswith((".csv", ".xlsx")):
        raise servis.TopolojiHata(400, "CSV veya XLSX dosyası seçin.")
    bildirilen = request.headers.get("content-length", "")
    if bildirilen.isdigit() and int(bildirilen) > servis.AZAMI_BAYT:
        raise servis.TopolojiHata(413, BUYUK)
    parcalar: list[bytes] = []
    boyut = 0
    async for parca in request.stream():
        boyut += len(parca)
        if boyut > servis.AZAMI_BAYT:
            raise servis.TopolojiHata(413, BUYUK)
        parcalar.append(parca)
    sonuc = await run_in_threadpool(servis.analiz, b"".join(parcalar))
    audit_log.remember(
        actor=e.user.username, action="topoloji.analiz", outcome="allow", module_key="topoloji",
        detail=f"satir={sonuc['satir']} lokasyon={sonuc['lokasyon']} spof={len(sonuc['spof_noktalari'])}",
    )
    return ok(sonuc)
