"""Final skor motorunun veri kaynaklari: uretim kutucuklar/utilizasyon/veri_kaynaklari.py, DEV veritabanina uyarlandi.

Her kaynak musteri basina METRIK uretir; motor metrikleri kriter kurallarina (barem hucreleri) gore puana cevirir. Oncelik (metrik
basina, ilk hazir olan kullanilir; hata veren kaynak atlanir, siradakine gecilir):
  Secilen veri kaynagi (kriterdeki kaynak_secimi) > OneDesk > Urun-Tutar Excel > ONENT > Panel
  sikayet_talep   : OneDesk (gunluk ozet: son 12 ayda KAPANAN sikayet + talep, 2026-11-21) > Panel
  lokasyon_sayisi : Urun-Tutar Excel > ONENT (gunluk ozet: aktif CI'larin farkli lokasyonu) > Panel (Envanter alani - YEDEK)
  servisler       : Urun-Tutar Excel (musterinin servis/urun adlari)
  segment         : Panel (kartta secilen segment; SEGMENTLER disindaki deger veri sayilmaz)
  baglanti        : Urun-Tutar Excel (baglanti tipleri)
  fatura_bedeli   : Urun-Tutar Excel > Panel (kart FT Hacim - YEDEK; 0 = veri yok)
  rapor_sayisi    : Panel (bu yil aylik rapor hazirlanan ay sayisi; 2026-11-21 itibariyla PUANA YANSIMAZ, Raporlama elle secilir)

Panel verisi DEV veritabanindandir: kart sayaclari (Onedesk kayitlari ve Veri Girisi dagitimi doldurur: REPORTDB / CSV / Oracle
ice alma), Envanter, FT Hacim, segment ve gonderilmis aylik raporlar (report). DB kaynaklari (REPORTDB / ONENTDB)
uretimdeki gibi sozlesme bekler: baglanti ayarli degilse 'hazir degil', ayarliysa 'sorgu henuz yazilmadi' uyarisi; tampona alinmis
bu verileri skora baglamanin yolu kriterdeki veri kaynagi secimidir.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dil import m as dm
from app.models import Customer, Report
from app.ortak import rapor_donemi
from app.skor import kaynak_secimi, urun_tutar

# musteri.servis.SEGMENTLER ile ayni (paket yonu: skor musteriyi import etmez; esitlik testte kilitli).
SEGMENTLER = ("SMB", "SA", "MA", "PA", "WHOLESALE", "CONNCAR")


class KaynakHazirDegil(RuntimeError):
    """Kaynak henuz baglanmadi / erisilemedi (mesaj kullaniciya gosterilir)."""


class KaynakDegeri:
    """Kaynagin bir metrik degeri + ekranda gosterilecek kaynak adi (ornek 'csv_urun #12')."""

    __slots__ = ("deger", "kaynak")

    def __init__(self, deger: Any, kaynak: str) -> None:
        self.deger, self.kaynak = deger, kaynak


def tutar_ayikla(metin: object) -> float:
    """Kart tutari ('1.234.567,89 ₺') -> 1234567.89; okunamazsa 0. Turkce bicim: nokta binlik, virgul ondalik."""
    temiz = re.sub(r"[^0-9.,]", "", str(metin or ""))
    try:
        return float(temiz.replace(".", "").replace(",", ".")) if temiz else 0.0
    except ValueError:
        return 0.0


def rapor_birimi_mi(musteri: Customer) -> bool:
    """musteri.servis.rapor_birimi_mi ile ayni: cati ya da 'ayri rapor' secilmis istirak."""
    return musteri.parent_id is None or bool(musteri.separate_report)


def yillik_rapor_aylari(db: Session, yil: int | None = None) -> dict[int, int]:
    """{rapor birimi customer_id: bu yil aylik rapor hazirlanan AY sayisi} - tek sorgu. Catisina dahil istirak icin hazirlanan
    rapor catinin sayilir (rapor.servis.durum_ozeti ile ayni tanim). Rapor kaydi = gonderilmis, geri alinmamis rapor."""
    yil = yil or rapor_donemi(datetime.now(UTC))[0]  # Ocak'ta gonderilen Aralik raporu onceki yila sayilir
    aylar: dict[int, set[int]] = {}
    for cid, ust, ayri, ay in db.execute(
        select(Customer.id, Customer.parent_id, Customer.separate_report, Report.report_month)
        .join(Report, Report.customer_id == Customer.id)
        .where(Report.report_year == yil)
        .distinct()
    ):
        birim = cid if (ust is None or ayri) else ust
        aylar.setdefault(birim, set()).add(ay)
    return {k: len(v) for k, v in aylar.items()}


def panel_sayilari(musteriler: Sequence[Customer], rapor_aylari: dict[int, int]) -> dict[str, float]:
    """Panel verisinden sayilar (tek tanim): sikayet / talep = bu yil kapanan + su an acik; rapor = bu yil rapor hazirlanan ay
    sayisi; fatura = kart FT Hacim toplami (TL)."""
    return {
        "alarm": sum((c.alarm_count or 0) + (c.alarm_closed_count or 0) for c in musteriler),
        "sikayet": sum((c.complaint_count or 0) + (c.complaint_closed_count or 0) for c in musteriler),
        "talep": sum((c.request_count or 0) + (c.request_closed_count or 0) for c in musteriler),
        "envanter": sum((c.inventory_count or 0) for c in musteriler),
        "rapor": sum(rapor_aylari.get(c.id, 0) for c in musteriler),
        "fatura": round(sum(tutar_ayikla(c.ft_volume) for c in musteriler), 2),
    }


class Kaynak:
    ad = ""
    metrikler: tuple[str, ...] = ()

    def hazir(self, db: Session) -> tuple[bool, str]:
        return True, ""

    def yapilandirildi(self) -> bool:
        """Baglanti ayarli mi (uretim: .env URL dolu). Hazir olmayan kaynagin hatasi yalniz ayarliysa uyari olur."""
        return False

    def oku_uyarili(self, db: Session, musteriler: list[Customer]) -> tuple[dict[int, dict], list[str]]:
        hazir, neden = self.hazir(db)
        if not hazir:
            raise KaynakHazirDegil(neden)
        return self._oku(db, musteriler), []

    def _oku(self, db: Session, musteriler: list[Customer]) -> dict[int, dict]:
        raise NotImplementedError


class PanelKaynagi(Kaynak):
    """Panelin kendi verisi: kart sayaclari (acik + bu yil kapanan sikayet/talep), kartta secilen segment, gonderilmis aylik
    raporlar, Envanter (lokasyon icin YEDEK) ve FT Hacim (fatura bedeli icin YEDEK)."""

    ad = "Panel (kart + aylık rapor)"
    metrikler = ("sikayet_talep", "lokasyon_sayisi", "segment", "rapor_sayisi", "fatura_bedeli")

    def _oku(self, db: Session, musteriler: list[Customer]) -> dict[int, dict]:
        rapor_aylari = yillik_rapor_aylari(db)
        sonuc = {}
        for c in musteriler:
            s = panel_sayilari([c], rapor_aylari)
            # FT Hacim girilmemisse (0,00 ₺) veri YOK sayilir - 0 TL fatura degil.
            sonuc[c.id] = {
                "sikayet_talep": s["sikayet"] + s["talep"],
                "lokasyon_sayisi": s["envanter"],
                "segment": c.segment if c.segment in SEGMENTLER else None,
                "rapor_sayisi": s["rapor"],
                "fatura_bedeli": s["fatura"] or None,
            }
        return sonuc


class _GunlukOzetKaynagi(Kaynak):
    """Gunluk isci ozeti (skor/gunluk.py, her sabah 06:00): util_source_summary. Cati musterinin degeri = cati + istirakleri.
    Ozet hic yazilmadiysa (isci henuz calismadi) hazir degil; o sutunu okunamamis musteri siradaki kaynaga duser."""

    alan = ""

    def yapilandirildi(self) -> bool:
        return True

    def hazir(self, db: Session) -> tuple[bool, str]:
        from app.models import UtilSourceSummary

        if db.scalar(select(UtilSourceSummary.customer_id).limit(1)) is not None:
            return True, ""
        return False, dm(f"{self.ad}: günlük veri turu henüz çalışmadı.", f"{self.ad}: the daily data run has not run yet.")

    def _deger(self, ozet: dict, cati: Customer, istirakler: list[Customer]) -> Any:
        raise NotImplementedError

    def _oku(self, db: Session, musteriler: list[Customer]) -> dict[int, dict]:
        from app.skor import gunluk

        ozet = gunluk.ozetler(db)
        kimlikler = [c.id for c in musteriler]
        istirak: dict[int, list[Customer]] = {}
        for c in db.scalars(select(Customer).where(Customer.parent_id.in_(kimlikler))) if kimlikler else []:
            istirak.setdefault(c.parent_id, []).append(c)
        sonuc = {}
        for c in musteriler:
            deger = self._deger(ozet, c, istirak.get(c.id, []))
            if deger is not None:
                sonuc[c.id] = {self.metrikler[0]: deger}
        return sonuc


class OneDeskKaynagi(_GunlukOzetKaynagi):
    """OneDesk: son 12 ayda KAPANAN sikayet + talep (2026-11-21 kullanici: "durumu closed olmuslarla skor hesabi yapacagiz")."""

    ad = "OneDesk (kapanan şikayet + talep)"
    metrikler = ("sikayet_talep",)

    def _deger(self, ozet: dict, cati: Customer, istirakler: list[Customer]) -> Any:
        from app.skor.gunluk import grup_toplami

        s, t = grup_toplami(ozet, cati, istirakler, "sikayet"), grup_toplami(ozet, cati, istirakler, "talep")
        return None if s is None and t is None else (s or 0) + (t or 0)


class OnentKaynagi(_GunlukOzetKaynagi):
    """ONENT musteri envanteri: farkli kurumsal lokasyon sayisi (aktif CI'lar); lokasyon bilgisi yoksa aktif CI sayisi."""

    ad = "ONENT (aktif CI lokasyonu)"
    metrikler = ("lokasyon_sayisi",)

    def _deger(self, ozet: dict, cati: Customer, istirakler: list[Customer]) -> Any:
        from app.skor.gunluk import grup_toplami

        lok, ci = grup_toplami(ozet, cati, istirakler, "lokasyon"), grup_toplami(ozet, cati, istirakler, "ci")
        return (lok or ci) or None


class UrunTutarExcelKaynagi(Kaynak):
    """Utilizasyon > Urun-Tutar Excel yuklemesinin ozeti (urun_tutar_ozet). Yalniz dosyasi yuklenmis musteriler icin metrik verir;
    aktif satiri olmayan ozet veri sayilmaz (yalniz kapali sozlesmeler); digerleri siradaki kaynaga duser."""

    ad = "Ürün-Tutar (Excel)"
    metrikler = ("servisler", "lokasyon_sayisi", "baglanti", "fatura_bedeli")

    def _oku(self, db: Session, musteriler: list[Customer]) -> dict[int, dict]:
        sonuc = {}
        for cid, kayit in urun_tutar.hepsi(db, [c.id for c in musteriler]).items():
            o = kayit.get("ozet") or {}
            if not o.get("aktif_satir"):
                continue
            sonuc[cid] = {
                "servisler": o.get("servisler") or [],
                "lokasyon_sayisi": o.get("lokasyon_sayisi") or 0,
                "baglanti": o.get("baglanti") or [],
                "fatura_bedeli": o.get("fatura_bedeli") or None,
            }
        return sonuc


class KriterSecimKaynagi(Kaynak):
    """Kriterlerdeki "Veri kaynagi" secimi: secilmisse metrik OZELLIKLE oradan gelir; secimi olmayan kriter icin bir sey uretmez."""

    ad = "Seçilen veri kaynağı"

    def __init__(self, kriterler: list[dict] | None) -> None:
        self.secimli = kaynak_secimi.secimli_kriterler(kriterler)
        self.metrikler = tuple(dict.fromkeys(m for _, m, _, _ in self.secimli))

    def hazir(self, db: Session) -> tuple[bool, str]:
        return (
            (True, "") if self.secimli else (False, dm("Kriterlerde veri kaynağı seçimi yok.", "No data source selected in the criteria."))
        )

    def oku_uyarili(self, db: Session, musteriler: list[Customer]) -> tuple[dict[int, dict], list[str]]:
        if not self.secimli:
            raise KaynakHazirDegil("Kriterlerde veri kaynağı seçimi yok.")
        sonuc, uyarilar = kaynak_secimi.hesapla(db, self.secimli, musteriler)
        return {cid: {m: KaynakDegeri(d, ad) for m, (d, ad) in metrikler.items()} for cid, metrikler in sonuc.items()}, uyarilar


def kaynaklar(kriterler: list[dict] | None) -> list[Kaynak]:
    """Oncelik sirasi: listede ONCE gelen hazir kaynak metrigi saglar."""
    return [KriterSecimKaynagi(kriterler), OneDeskKaynagi(), UrunTutarExcelKaynagi(), OnentKaynagi(), PanelKaynagi()]


AD_EN = {
    "Panel (kart + aylık rapor)": "Panel (card + monthly report)",
    "Ürün-Tutar (Excel)": "Product-Amount (Excel)",
    "Seçilen veri kaynağı": "Selected data source",
    "OneDesk (kapanan şikayet + talep)": "OneDesk (closed complaints + requests)",
    "ONENT (aktif CI lokasyonu)": "ONENT (active CI locations)",
}


def kaynak_durumlari(db: Session, kriterler: list[dict] | None) -> list[dict]:
    """Arayuz icin: [{'ad', 'metrikler', 'hazir', 'neden'}]."""
    durum = []
    for k in kaynaklar(kriterler):
        hazir, neden = k.hazir(db)
        durum.append({"ad": dm(k.ad, AD_EN.get(k.ad, k.ad)), "metrikler": list(k.metrikler), "hazir": hazir, "neden": neden})
    return durum


def birlesik_metrikler(db: Session, musteriler: list[Customer], kriterler: list[dict] | None) -> tuple[dict[int, dict], list[str]]:
    """{customer_id: {metrik: {'deger', 'kaynak'}}}, uyarilar - her metrik oncelikli ilk hazir kaynaktan. Bir kaynak hata verirse
    (erisim kopuk) siradakine gecilir."""
    sonuc: dict[int, dict] = {c.id: {} for c in musteriler}
    uyarilar: list[str] = []
    for kaynak in kaynaklar(kriterler):
        eksik = [m for m in kaynak.metrikler if any(m not in sonuc[c.id] for c in musteriler)]
        if not eksik:
            continue
        try:
            veri, kaynak_uyarilari = kaynak.oku_uyarili(db, musteriler)
        except KaynakHazirDegil as e:
            if kaynak.yapilandirildi():
                uyarilar.append(str(e))
            continue
        uyarilar.extend(kaynak_uyarilari)
        for cid, metrikler in (veri or {}).items():
            for m, deger in metrikler.items():
                kaynak_adi = kaynak.ad
                if isinstance(deger, KaynakDegeri):
                    kaynak_adi, deger = deger.kaynak, deger.deger
                if m in eksik and cid in sonuc and m not in sonuc[cid] and deger is not None:
                    sonuc[cid][m] = {"deger": deger, "kaynak": kaynak_adi}
    return sonuc, uyarilar
