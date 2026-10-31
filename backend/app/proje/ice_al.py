"""Takip Edilen Projeler Excel ice aktarma (2026-10-31 kullanici: "Berat Kagan'daki excelden alip import edecektik; herkesinki bos,
millet bir daha manuel girmek istemeyebilir"). Giris noktasi Veri Girisi > Import (CLAUDE.md: panelin tek Excel/CSV girisi).

Kaynak: "Proje calisma Ddos opt. calismasi DC tasima Topoloji iyilestirme sayi ve detaylari <yil>.xlsm" bicimi. Q1..Q4 sayfalarinda
her TAM bir bloktur (TAM sutununda ad, sonraki TAM adina kadar); kategori basliklari (Proje, Calisma, Ddos Optimizasyon, DC Tasimasi,
Topoloji iyilestirme) altinda "Sayi" ve "Detay" sutunlari. Her dolu Detay hucresi bir proje kaydi olur:
  - sorumlu = TAM (yalniz TAM personeli; ad Turkce harf/buyuk-kucuk farksiz eslesir). Eslesmeyen TAM'in satirlari onizlemede
    'tam_yok' durur; `atamalar` ile secilen kisiye acilir ve aciklamaya asil TAM adi yazilir. TOPLAM satiri atlanir.
  - durum Acik (kullanici karari), baslangic tarihi = ceyregin ilk gunu (yil dosya adindan; yoksa bu yil).
  - baslik = detayin ilk 200 karakteri (tek satir), aciklama = detayin tamami.
  - Ayni sorumlu + kategori + baslik + ceyrek zaten kayitliysa 'var', dosyada tekrar ediyorsa 'tekrar': ikinci yukleme bir sey eklemez.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.gelir_uretim.ayristir import baslik_anahtari, katla
from app.gelir_uretim.ice_al import kisi_dizini
from app.kullanicilar import personel
from app.models import AppUser, ProjectItem
from app.ortak import simdi
from app.proje import servis
from app.session import Principal

AZAMI_BAYT = 5 * 1024 * 1024
AZAMI_ACIK = 100 * 1024 * 1024  # zip icindeki toplam acik boyut (zip bombasina karsi)
EN_COK_KAYIT = 2000
OKUNAN_SATIR_SINIRI = 3000
BASLIK_SINIRI = 200
KATEGORI_BASLIKLARI = {"proje": "proje", "calisma": "calisma", "ddos optimizasyon": "ddos", "dc tasimasi": "dc_tasima", "topoloji iyilestirme": "topoloji"}
TOPLAM_SATIRI = "toplam"


def anahtar(metin: object) -> str:
    """TAM adi karsilastirmasi: Turkce harf / buyuk-kucuk / bosluk farki yok sayilir."""
    return " ".join(katla(str(metin if metin is not None else "")).split())


def _metin(deger: object) -> str:
    if deger is None:
        return ""
    if isinstance(deger, float) and deger.is_integer():
        return str(int(deger))
    return str(deger).replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ").strip()


@dataclass
class Kayit:
    satir: int
    ceyrek: int
    tam: str
    kategori: str
    detay: str
    durum: str = "yeni"  # yeni | var | tekrar | tam_yok
    sahip_id: int | None = None
    sahip: str = ""

    @property
    def baslik(self) -> str:
        tek = " ".join(self.detay.split())
        return tek if len(tek) <= BASLIK_SINIRI else tek[: BASLIK_SINIRI - 1] + "…"


@dataclass
class Plan:
    dosya: str
    yil: int
    kayitlar: list[Kayit] = field(default_factory=list)
    eslesmeyen: dict[str, int] = field(default_factory=dict)  # asil TAM adi -> kayit sayisi

    def sayilar(self) -> dict[str, int]:
        sayac = {"toplam": len(self.kayitlar), "yeni": 0, "var": 0, "tekrar": 0, "tam_yok": 0}
        for k in self.kayitlar:
            sayac[k.durum] += 1
        return sayac


def ceyrek_basi(yil: int, ceyrek: int) -> date:
    return date(yil, 3 * (ceyrek - 1) + 1, 1)


def _sayfa_kayitlari(sayfa: object, ceyrek: int) -> list[Kayit]:
    """Kategori baslik satirini bulur (ilk 10 satir), bir alttaki 'Detay' sutunlarini kategoriye baglar; TAM sutunu 'TAM' basligi (yoksa B)."""
    satirlar: list[tuple[int, list[object]]] = []
    for no, hucreler in enumerate(sayfa.iter_rows(values_only=True), start=1):  # type: ignore[attr-defined]
        if no > OKUNAN_SATIR_SINIRI:
            break
        satirlar.append((no, list(hucreler)))
    tam_sutunu, baslik_i = 1, None
    for i, (_, hucreler) in enumerate(satirlar[:10]):
        anahtarlar = [anahtar(h) for h in hucreler]
        if "tam" in anahtarlar:
            tam_sutunu = anahtarlar.index("tam")
        if sum(1 for a in anahtarlar if a in KATEGORI_BASLIKLARI) >= 3:
            baslik_i = i
            break
    if baslik_i is None or baslik_i + 1 >= len(satirlar):
        return []
    kategori_sutunlari = [(j, KATEGORI_BASLIKLARI[anahtar(h)]) for j, h in enumerate(satirlar[baslik_i][1]) if anahtar(h) in KATEGORI_BASLIKLARI]
    alt = [anahtar(h) for h in satirlar[baslik_i + 1][1]]
    detay_sutunlari: list[tuple[int, str]] = []
    for n, (j, kategori) in enumerate(kategori_sutunlari):
        son = kategori_sutunlari[n + 1][0] if n + 1 < len(kategori_sutunlari) else len(alt)
        detay = next((x for x in range(j, son) if alt[x] == "detay"), None)
        if detay is not None:
            detay_sutunlari.append((detay, kategori))
    kayitlar: list[Kayit] = []
    tam = ""
    for no, hucreler in satirlar[baslik_i + 2 :]:
        ad = _metin(hucreler[tam_sutunu]) if tam_sutunu < len(hucreler) else ""
        if ad:
            tam = ad
        if not tam or anahtar(tam) == TOPLAM_SATIRI:
            continue
        for j, kategori in detay_sutunlari:
            detay = _metin(hucreler[j]) if j < len(hucreler) else ""
            if detay:
                kayitlar.append(Kayit(satir=no, ceyrek=ceyrek, tam=tam, kategori=kategori, detay=detay))
    return kayitlar


def excel_oku(veri: bytes) -> list[Kayit]:
    import openpyxl
    from openpyxl.utils.exceptions import InvalidFileException

    if not veri:
        raise servis.ProjeHata(400, "Dosya seçilmedi.")
    try:
        if sum(b.file_size for b in zipfile.ZipFile(io.BytesIO(veri)).infolist()) > AZAMI_ACIK:
            raise ValueError("boyut")
        kitap = openpyxl.load_workbook(io.BytesIO(veri), read_only=True, data_only=True)  # makrolar calistirilmaz
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as exc:
        raise servis.ProjeHata(400, "Excel dosyası okunamadı. .xlsx / .xlsm biçiminde bir dosya seçin.") from exc
    try:
        kayitlar: list[Kayit] = []
        for sayfa in kitap.worksheets:
            eslesme = re.fullmatch(r"\s*Q([1-4])\s*", sayfa.title, re.IGNORECASE)
            if eslesme:
                if hasattr(sayfa, "reset_dimensions"):
                    sayfa.reset_dimensions()
                kayitlar.extend(_sayfa_kayitlari(sayfa, int(eslesme.group(1))))
    finally:
        kitap.close()
    if not kayitlar:
        raise servis.ProjeHata(400, "Q1–Q4 sayfalarında proje / çalışma detayı bulunamadı.")
    if len(kayitlar) > EN_COK_KAYIT:
        raise servis.ProjeHata(413, f"Dosyada en fazla {EN_COK_KAYIT} kayıt olabilir.")
    return kayitlar


def _yil(dosya: str) -> int:
    bulunan = re.findall(r"20\d\d", dosya or "")
    return int(bulunan[-1]) if bulunan else simdi().year


def plan_hazirla(db: Session, veri: bytes, dosya: str, atamalar: dict[str, int] | None = None) -> Plan:
    """atamalar: eslesmeyen TAM'in ad anahtari (`anahtar`) -> kisi kimligi (yalniz TAM personeli gecerli)."""
    plan = Plan(dosya=dosya, yil=_yil(dosya), kayitlar=excel_oku(veri))
    kisiler = personel(db)
    dizin = kisi_dizini(kisiler)
    kimlikle = {k.id: k for k in kisiler}
    atamalar = atamalar or {}
    mevcut = {(p.owner_id, p.category, baslik_anahtari(p.title), p.start_date) for p in db.scalars(select(ProjectItem))}
    gorulen: set[tuple] = set()
    for k in plan.kayitlar:
        adaylar = dizin.get(anahtar(k.tam), [])
        kisi: AppUser | None = adaylar[0] if len(adaylar) == 1 else kimlikle.get(atamalar.get(anahtar(k.tam), 0))
        if kisi is None:
            k.durum = "tam_yok"
            plan.eslesmeyen[k.tam] = plan.eslesmeyen.get(k.tam, 0) + 1
            continue
        k.sahip_id, k.sahip = kisi.id, kisi.display_name or kisi.username
        tekil = (kisi.id, k.kategori, baslik_anahtari(k.baslik), ceyrek_basi(plan.yil, k.ceyrek))
        if tekil in mevcut:
            k.durum = "var"
        elif tekil in gorulen:
            k.durum = "tekrar"
        gorulen.add(tekil)
    return plan


def onizleme(db: Session, veri: bytes, dosya: str, atamalar: dict[str, int] | None = None) -> dict:
    """Hicbir sey yazmaz. Eslesmeyen TAM'lar ve atanabilecek kisiler de doner."""
    plan = plan_hazirla(db, veri, dosya, atamalar)
    return {
        "dosya": plan.dosya,
        "yil": plan.yil,
        "plan": plan.sayilar(),
        "eslesmeyen": [{"ad": ad, "anahtar": anahtar(ad), "kayit": n} for ad, n in sorted(plan.eslesmeyen.items())],
        "kisiler": [{"id": k.id, "ad": k.display_name or k.username} for k in personel(db)],
        "satirlar": [
            {"satir": k.satir, "ceyrek": f"Q{k.ceyrek}", "tam": k.tam, "sahip": k.sahip, "kategori": k.kategori, "baslik": k.baslik, "durum": k.durum}
            for k in plan.kayitlar
        ],
    }


def uygula(db: Session, user: Principal, veri: bytes, dosya: str, atamalar: dict[str, int] | None = None) -> dict:
    """Yalniz 'yeni' kayitlari acar (commit cagirana aittir); servis.kalem_ekle ile: sorumlu dogrulamasi ve acilis aksiyonu ayni."""
    plan = plan_hazirla(db, veri, dosya, atamalar)
    eklenen = 0
    for k in plan.kayitlar:
        if k.durum != "yeni" or k.sahip_id is None:
            continue
        aciklama = k.detay if anahtar(k.sahip) == anahtar(k.tam) else f"Asıl TAM: {k.tam}\n{k.detay}"
        veri_ = {"owner_id": k.sahip_id, "category": k.kategori, "title": k.baslik, "description": aciklama, "start_date": ceyrek_basi(plan.yil, k.ceyrek)}
        kimlik = servis.kalem_ekle(db, user, veri_)
        servis.aksiyon_ekle(db, user, kimlik, f"Excel'den aktarıldı: {plan.dosya or 'dosya'} · Q{k.ceyrek} {plan.yil}")
        eklenen += 1
    return {**plan.sayilar(), "eklendi": eklenen}
