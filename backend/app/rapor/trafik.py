"""Aylik rapor trafik grafikleri: ReportDB sayisal verisi -> panelde Apache ECharts 6.1.0 ile cizim.

2026-11-19 kullanici: "lookouteyes islerini panelde kendimiz uretecegiz; reportdb'den alacagimiz sayisal verilerle musteri
icin ekledigimiz trafik grafiginin gorsellestirmesini panelde yapacagiz" + "Apache ECharts 6.1.0'i panele uyarla".

Cizim tarayicida, React paketinden AYRI kodla yapilir (ekran-react/dist/rapor-trafik.js + echarts-6.1.0.min.js); cikan PNG
gorseller rapor onizlemesindeki grafik listesine katilir, PDF akisi (html2canvas + jsPDF) degismez. Bu modul yalniz veriyi verir.

Veri sozlesmesi (GET /api/v1/musteri/{id}/rapor/trafik?donem=YYYY-MM):
  {"yil": 2026, "ay": 10, "kaynak_hazir": bool,
   "devreler": [{"anahtar": str, "baslik": str, "ci": str, "hiz_bps": int | None,
                 "noktalar": [[epoch_ms, giris_bps, cikis_bps], ...]}]}
Birim bit/sn; zaman UTC epoch milisaniye; eksik olcum null olabilir (grafikte bosluk).

ReportDB trafik kaynagi tanimlanana kadar kaynak_hazir=False, devreler bos: rapor onizlemesi hicbir sey eklemez.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.musteri.servis import musteri_getir
from app.session import Principal


def kaynak_hazir() -> bool:
    """ReportDB trafik sorgusu tanimli mi. Kaynak bilgisi henuz gelmedi (2026-11-19)."""
    return False


def devreler(musteri_id: int, yil: int, ay: int) -> list[dict[str, Any]]:
    """Musterinin donemdeki devre trafik serileri (sozlesme: modul aciklamasi). Kaynak hazir degilse bos."""
    if not kaynak_hazir():
        return []
    return []


def getir(db: Session, user: Principal, musteri_id: int, donem_kodu: str | None = None) -> dict[str, Any]:
    from app.rapor.servis import donem

    musteri = musteri_getir(db, user, musteri_id)
    yil, ay = donem(donem_kodu)
    return {"yil": yil, "ay": ay, "kaynak_hazir": kaynak_hazir(), "devreler": devreler(musteri.id, yil, ay)}
