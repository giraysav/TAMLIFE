"""TopoMaker HTTP katmani. Gorme: uretimdeki gibi musteri modulu (@modul_gerekli('musteri')); topoloji katalogda menude
olmadigi icin rol gorunumu duzenleyicisinde secilemez, bu yuzden kapi 'musteri'dir. Dosya saklanmaz.

  PUT /topoloji/analiz?dosya=  -> ham CSV/XLSX govdesi (en fazla 10 MB) -> dugum/kenar/SPoF/il dagilimi
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.audit import audit_log
from app.db import get_db
from app.erisim import Erisim, musteri_alani_erisim
from app.musteri import servis as musteri_servis
from app.ortak import govde_oku, ok
from app.topoloji import servis

router = APIRouter(prefix="/api/v1/topoloji", tags=["topoloji"])
topoloji_erisim = musteri_alani_erisim()
BUYUK = "Dosya 10 MB sınırını aşıyor."


@router.put("/analiz")
async def analiz(
    request: Request,
    musteri: int = Query(gt=0),
    dosya: str = Query(default="", max_length=200),
    e: Erisim = Depends(topoloji_erisim),
    db: Session = Depends(get_db),
) -> dict:
    if dosya and not dosya.lower().endswith((".csv", ".xlsx")):
        raise servis.TopolojiHata(400, "CSV veya XLSX dosyası seçin.")
    kayit = musteri_servis.musteri_getir(db, e.user, musteri)
    sonuc = await run_in_threadpool(servis.analiz, await govde_oku(request, servis.AZAMI_BAYT, BUYUK))
    sonuc["musteri"] = {"id": kayit.id, "unvan": kayit.name}
    audit_log.remember(
        actor=e.user.username, action="topoloji.analiz", outcome="allow", module_key="topoloji",
        detail=f"musteri={musteri} satir={sonuc['satir']} lokasyon={sonuc['lokasyon']} spof={len(sonuc['spof_noktalari'])}",
    )
    return ok(sonuc)
