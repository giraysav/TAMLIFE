"""Eski panel (Flask) SecureDB verisini yeni panele tasir: kullanicilar, musteriler (sorumlu TAM, cati/istirak), ekip-iletisim ve
ReportDB tamponu (Musteri Radar'i besler).

  cd backend; ..\\.venv\\Scripts\\python.exe -m app.eski_aktar --kaynak E:\\Secure_DB\\veritabani            KURU DENEME (hicbir sey yazilmaz)
  cd backend; ..\\.venv\\Scripts\\python.exe -m app.eski_aktar --kaynak E:\\Secure_DB\\veritabani --uygula   yazar

--kaynak: eski panelin veritabani klasoru (panel.db ve ham_veri.db) ya da panel.db dosyasi. Eski dosyalar YALNIZ OKUNUR
(sqlite salt okunur baglanti; acilamazsa gecici kopya okunur ve silinir); eski panele ve uretim DB'lerine yazilmaz, Oracle'a baglanilmaz.
Cikti yalniz SAYILARDIR: musteri adi, kisi adi ya da satir icerigi yazdirilmaz.

Kurallar (tekrar calistirmak guvenli: ayni veri ikinci kez cogalmaz):
  * Kullanici: kullanici adi (kucuk harf) ile eslesir. Yeni kisiye eski ad-soyad, rol, aktiflik, son giris (eski sistem gunlugundeki
    'giris' kaydi) yazilir. PIN, TOTP ve modul/yetki JSON'u TASINMAZ (sir ya da eski yetki modeli; yeni panel rol gorunumu kullanir).
    Yeni panelde zaten olan kisinin rolu, aktifligi ve parolasina dokunulmaz; yalniz adi bossa ya da kullanici adindan uretilmisse
    gercek ad-soyad yazilir. Giris yalniz AD ile olur: eski kaydi AD kullanicisi olmayanlar girissiz tasinir (--ad-hepsi hepsini AD yapar).
  * Musteri: unvan (buyuk/kucuk harf, I/i, bosluk farksiz) ile eslesir. Yeni musteri olusur; panelde olan musteride yalniz BOS alanlar
    doldurulur. Sorumlu TAM (eski user_id -> kullanici adi), cati/istirak, segment, sektor, Musteri No, NCST, ayri rapor, final skora
    dahil, envanter, FT, sayaclar ve cacti adresleri gelir. Ayni unvanli ikinci eski kayit ilkine birlestirilir (sayilir).
  * Iletisim: eski destech_contacts, unvan eslesmesiyle musteri kartinin ekip/iletisim bolumune; yalniz bos alanlar doldurulur.
  * Tampon: eski ham_veri.db'deki ReportDB tamponu (reportdb_tampon) yeni tampona 'ready' parti olarak alinir; Musteri Radar'i hemen
    doldurur. Kartlara yazilmaz (dagitim kurallari kapali kalir). Ayni veri zamani ikinci kez alinmaz.
Tasinmayanlar: rapor alicilari, raporlar, takvim, projeler, gelirler, talepler (ayri adimlar).
Uygulamadan once SQLite panel veritabaninin yedegi alinir (--yedek-yok ile kapatilir). Cikis: 0 tamam | 1 hata | 2 kullanim.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import kullanicilar, musteri_alani
from app.config import env_dosyasi_yukle
from app.db import engine, oturum
from app.models import AffiliateFinalFlag, AppUser, AuditEvent, Customer, CustomerTeam, IngestBatch
from app.musteri.servis import ILETISIM_ALANLARI, VARSAYILAN_TUTAR
from app.ortak import eslestirme_anahtari, simdi
from app.tampon import depo, reportdb
from app.tampon.musteri_aktar import _segment_kodu

ADIMLAR = ("kullanici", "musteri", "iletisim", "tampon")
TR = timezone(timedelta(hours=3))  # eski panelin yerel saati (Turkiye, yaz saati yok)
AZAMI_CACTI, AZAMI_URL = 20, 500
ROL_YONETICI = {"teammngr", "teammanager", "manager", "yonetici"}


# --- eski veritabani (salt okunur) ----------------------------------------------------------------------
class Kaynak:
    """Eski SQLite dosyasi: salt okunur. Dosya acilamazsa (WAL / kilit) gecici kopya uzerinden okunur ve kapanista silinir."""

    def __init__(self, yol: Path) -> None:
        self.yol = yol
        self._gecici: Path | None = None
        try:
            self.b = sqlite3.connect(f"{yol.resolve().as_uri()}?mode=ro", uri=True, timeout=10)
            self.b.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
        except sqlite3.OperationalError:
            self._gecici = Path(tempfile.mkdtemp(prefix="tamlife_eski_"))
            for ek in ("", "-wal", "-shm"):
                if (yol.parent / (yol.name + ek)).exists():
                    shutil.copy2(yol.parent / (yol.name + ek), self._gecici / (yol.name + ek))
            self.b = sqlite3.connect(self._gecici / yol.name)
            print(f"  not: {yol.name} dogrudan acilamadi, gecici kopya okunuyor (isim bitince silinir).")
        self.b.row_factory = sqlite3.Row

    def kapat(self) -> None:
        self.b.close()
        if self._gecici is not None:
            shutil.rmtree(self._gecici, ignore_errors=True)

    def sutunlar(self, tablo: str) -> set[str]:
        return {r[1] for r in self.b.execute(f'PRAGMA table_info("{tablo}")')}

    def tablo_var(self, tablo: str) -> bool:
        return bool(self.b.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tablo,)).fetchone())

    def satirlar(self, tablo: str, istenen: tuple[str, ...]) -> list[dict[str, Any]]:
        """Tablodaki satirlar; tabloda olmayan sutun None gelir (eski surumler arasi fark). Ad ve sutunlar koddaki sabitlerdir."""
        if not self.tablo_var(tablo):
            return []
        var = self.sutunlar(tablo)
        secilen = [c for c in istenen if c in var]
        if not secilen:
            return []
        sorgu = "SELECT " + ", ".join(f'"{c}"' for c in secilen) + f' FROM "{tablo}"'
        return [{**dict.fromkeys(istenen), **dict(r)} for r in self.b.execute(sorgu)]


# --- yardimcilar ----------------------------------------------------------------------------------------
def _ad(deger: object, azami: int) -> str:
    return " ".join(str(deger or "").split())[:azami]


def _bos(deger: object) -> bool:
    return deger is None or deger == "" or deger == 0 or deger == []


def _tamsayi(deger: object) -> int:
    try:
        return max(0, int(float(deger or 0)))
    except (TypeError, ValueError):
        return 0


def _json(ham: object) -> Any:
    try:
        return json.loads(ham) if isinstance(ham, str) and ham.strip() else None
    except ValueError:
        return None


def _zaman(ham: object) -> datetime | None:
    """Eski 'olusturuldu' (UTC, saat dilimsiz) -> UTC farkindalikli."""
    try:
        z = datetime.fromisoformat(str(ham))
    except (TypeError, ValueError):
        return None
    return z.replace(tzinfo=UTC) if z.tzinfo is None else z.astimezone(UTC)


def _rol(yonetici: object, rol: object) -> str:
    r = str(rol or "").strip().lower()
    if yonetici or r in {"admin", "administrator"}:
        return "admin"
    return "TeamMngr" if r in ROL_YONETICI else "TeamMember"


def _doldur(hedef: Any, alan: str, deger: Any) -> bool:
    """Yalniz hedefteki alan bossa yazar (yeni panelde elle girilen korunur). Degisiklik oldu mu."""
    if _bos(deger) or not _bos(getattr(hedef, alan)):
        return False
    setattr(hedef, alan, deger)
    return True


# --- kullanicilar ---------------------------------------------------------------------------------------
def _son_girisler(eski: Kaynak) -> dict[str, datetime]:
    if not eski.tablo_var("sistem_loglari") or not {"kullanici_adi", "eylem", "olusturuldu"} <= eski.sutunlar("sistem_loglari"):
        return {}
    sonuc: dict[str, datetime] = {}
    for r in eski.b.execute(
        "SELECT lower(kullanici_adi) AS ad, MAX(olusturuldu) AS son FROM sistem_loglari "
        "WHERE eylem = 'giris' AND kullanici_adi IS NOT NULL GROUP BY lower(kullanici_adi)"
    ):
        z = _zaman(r["son"])
        if z is not None:
            sonuc[r["ad"]] = z
    return sonuc


def kullanicilari_aktar(db: Session, eski: Kaynak, say: Counter, yaz: bool, ad_hepsi: bool) -> dict[int, int]:
    """{eski kullanici id: yeni app_user id}. `yaz` False ise yeni kisi olusturulmaz, yalniz mevcutlarla eslesir."""
    satirlar = eski.satirlar("users", ("id", "username", "full_name", "is_admin", "role", "is_active", "ad_domain", "is_ad_user"))
    girisler = _son_girisler(eski)
    mevcut = {u.username.lower(): u for u in db.scalars(select(AppUser))}
    harita: dict[int, int] = {}
    for r in sorted(satirlar, key=lambda x: x["id"] or 0):
        ad = _ad(r["username"], 120).lower()
        if not ad or r["id"] is None:
            say["kullanici_atlanan"] += 1
            continue
        tam_ad = _ad(r["full_name"], 200) or kullanicilar.tam_ad_uret(ad)
        son = girisler.get(ad)
        u = mevcut.get(ad)
        if u is None:
            if not yaz:
                continue
            rol = _rol(r["is_admin"], r["role"])
            ad_kullanicisi = bool(ad_hepsi or r["is_ad_user"])
            u = AppUser(
                username=ad,
                display_name=tam_ad,
                role=rol,
                is_admin=rol == "admin",
                active=r["is_active"] is None or bool(r["is_active"]),
                last_login_at=son,
                is_ad_user=ad_kullanicisi,
                ad_domain=_ad(r["ad_domain"], 120).lower() if ad_kullanicisi else "",
            )
            db.add(u)
            db.flush()
            mevcut[ad] = u
            say["kullanici_yeni"] += 1
            if not ad_kullanicisi:
                say["kullanici_ad_degil"] += 1
        else:
            degisti = False
            if u.display_name in ("", u.username, kullanicilar.tam_ad_uret(u.username)) and tam_ad != u.display_name:
                u.display_name, degisti = tam_ad, True
            if son is not None and (u.last_login_at is None or (u.last_login_at.replace(tzinfo=UTC) if u.last_login_at.tzinfo is None else u.last_login_at) < son):
                u.last_login_at, degisti = son, True
            say["kullanici_guncellenen" if degisti else "kullanici_ayni"] += 1
        harita[r["id"]] = u.id
    return harita


# --- musteriler -----------------------------------------------------------------------------------------
def _cacti(ham: object) -> list[str]:
    liste = _json(ham)
    if not isinstance(liste, list):
        return []
    sonuc: list[str] = []
    for u in liste:
        u = str(u).strip()
        if u.lower().startswith(("http://", "https://")) and len(u) <= AZAMI_URL and " " not in u and u not in sonuc:
            sonuc.append(u)
    return sonuc[:AZAMI_CACTI]


_MUSTERI_SUTUNLARI = (
    "id", "name", "user_id", "parent_customer_id", "customer_no", "segment", "sector", "score", "envanter_count", "ft_hacim", "tam_ft",
    "alarm_count", "sikayet_count", "talep_count", "alarm_closed_count", "sikayet_closed_count", "talep_closed_count", "report_count",
    "cacti_urls", "pinned_entries",
)  # fmt: skip


@musteri_alani.tum_alanlarda  # kart eslesmesi tum modullerde (WHOLESALE kart Toptan'da)
def musterileri_aktar(db: Session, eski: Kaynak, kisiler: dict[int, int], say: Counter) -> tuple[dict[int, int], dict[str, int]]:
    """({eski musteri id: yeni musteri id}, {unvan anahtari: yeni musteri id}) - ikincisi iletisim eslemesi icin."""
    satirlar = sorted(eski.satirlar("customers", _MUSTERI_SUTUNLARI), key=lambda x: x["id"] or 0)
    mevcut: dict[str, Customer] = {}
    for c in db.scalars(select(Customer).order_by(Customer.id)):
        mevcut.setdefault(eslestirme_anahtari(c.name or ""), c)
    dis_anahtarlar = {c.external_key for c in db.scalars(select(Customer))}
    bu_calismada: set[int] = set()
    harita: dict[int, int] = {}
    ayarlar: dict[int, dict] = {}
    ebeveyn: dict[int, int | None] = {}

    for r in satirlar:
        ad = _ad(r["name"], 200)
        if not ad or r["id"] is None:
            say["musteri_atlanan"] += 1
            continue
        anahtar = eslestirme_anahtari(ad)
        c = mevcut.get(anahtar)
        yeni = c is None
        if c is not None and c.id in bu_calismada:
            harita[r["id"]] = c.id  # ayni unvanli ikinci eski kayit: ilkine birlesir
            say["musteri_ad_cakismasi"] += 1
            continue
        if c is None:
            dis = f"panel-{anahtar}"[:80]
            if dis in dis_anahtarlar:
                dis = f"panel-{r['id']}-{anahtar}"[:80]
            c = Customer(external_key=dis, name=ad, segment="", status="")
            db.add(c)
            dis_anahtarlar.add(dis)
            mevcut[anahtar] = c
        pin = _json(r["pinned_entries"])
        pin = pin if isinstance(pin, dict) else {}
        segment = ""
        if _ad(r["segment"], 100):
            segment = _segment_kodu(_ad(r["segment"], 100)) or ""
            if not segment:
                say["musteri_segment_tanimsiz"] += 1
        degisti = False
        degerler = {
            "customer_no": _ad(r["customer_no"], 200) or None,
            "segment": segment,
            "sector": _ad(r["sector"], 100) or None,
            "inventory_count": _tamsayi(r["envanter_count"]),
            "alarm_count": _tamsayi(r["alarm_count"]),
            "complaint_count": _tamsayi(r["sikayet_count"]),
            "request_count": _tamsayi(r["talep_count"]),
            "alarm_closed_count": _tamsayi(r["alarm_closed_count"]),
            "complaint_closed_count": _tamsayi(r["sikayet_closed_count"]),
            "request_closed_count": _tamsayi(r["talep_closed_count"]),
            "report_count": _tamsayi(r["report_count"]),
            "cacti_urls": _cacti(r["cacti_urls"]),
            "ncst": _ad(pin.get("ncst"), 50),
        }
        for alan, deger in degerler.items():
            degisti |= _doldur(c, alan, deger)
        for alan, ham in (("ft_volume", r["ft_hacim"]), ("tam_ft", r["tam_ft"])):
            metin = _ad(ham, 100)
            if metin and metin != VARSAYILAN_TUTAR and c.__getattribute__(alan) in ("", VARSAYILAN_TUTAR, None):
                setattr(c, alan, metin)
                degisti = True
        puan = r["score"]
        if isinstance(puan, int | float) and puan > 0 and not r["parent_customer_id"]:
            degisti |= _doldur(c, "score", float(puan))
        sahip = kisiler.get(r["user_id"]) if r["user_id"] is not None else None
        if sahip is None:
            say["musteri_sorumlusuz"] += 1
        else:
            degisti |= _doldur(c, "owner_id", sahip)
        if pin.get("ayri_rapor") and r["parent_customer_id"] and not c.separate_report:
            c.separate_report, degisti = True, True
        db.flush()
        bu_calismada.add(c.id)
        harita[r["id"]] = c.id
        ayarlar[r["id"]] = pin
        ebeveyn[r["id"]] = r["parent_customer_id"]
        say["musteri_yeni" if yeni else ("musteri_guncellenen" if degisti else "musteri_ayni")] += 1

    # cati/istirak: ust zincir en ustteki catiya duzlestirilir (yeni panelde tek seviye var)
    def kok(eski_id: int) -> int | None:
        gorulen = {eski_id}
        ust = ebeveyn.get(eski_id)
        for _ in range(8):
            if ust is None or ust not in harita:
                return None
            ust_ust = ebeveyn.get(ust)
            if ust_ust is None or ust_ust in gorulen:
                return ust
            gorulen.add(ust)
            ust = ust_ust
        return None

    for eski_id, ust_hedef in ebeveyn.items():
        if not ust_hedef:
            continue
        ust_eski = kok(eski_id)
        c, ust = db.get(Customer, harita[eski_id]), (db.get(Customer, harita[ust_eski]) if ust_eski is not None else None)
        if ust is None or ust.id == c.id:
            say["musteri_catisiz_istirak"] += 1
            continue
        if c.parent_id is None and c.id in bu_calismada:
            c.parent_id = ust.id
            say["musteri_istirak"] += 1
        _doldur(c, "segment", ust.segment)
        _doldur(c, "owner_id", ust.owner_id)
        if ayarlar.get(eski_id, {}).get("final_dahil"):
            bayrak = db.get(AffiliateFinalFlag, c.id)
            if bayrak is None:
                db.add(AffiliateFinalFlag(customer_id=c.id, included=True))
                say["musteri_final_dahil"] += 1
            elif not bayrak.included:
                bayrak.included = True
                say["musteri_final_dahil"] += 1
    db.flush()
    return harita, {k: c.id for k, c in mevcut.items()}


# --- ekip / iletisim ------------------------------------------------------------------------------------
@musteri_alani.tum_alanlarda  # kart eslesmesi tum modullerde (WHOLESALE kart Toptan'da)
def iletisimi_aktar(db: Session, eski: Kaynak, unvanlar: dict[str, int], say: Counter) -> None:
    satirlar = eski.satirlar("destech_contacts", ("id", "customer_name", *ILETISIM_ALANLARI))
    gorulen: set[int] = set()
    for r in sorted(satirlar, key=lambda x: x["id"] or 0):
        kimlik = unvanlar.get(eslestirme_anahtari(_ad(r["customer_name"], 200)))
        if kimlik is None:
            say["iletisim_eslesmeyen"] += 1
            continue
        if kimlik in gorulen:
            say["iletisim_tekrar"] += 1
            continue
        gorulen.add(kimlik)
        ekip = db.get(CustomerTeam, kimlik)
        yeni = ekip is None
        if ekip is None:
            ekip = CustomerTeam(customer_id=kimlik)
            db.add(ekip)
        degisti = False
        for alan, (_, azami) in ILETISIM_ALANLARI.items():
            ham = r[alan]
            metin = str(ham).strip()[:azami] if alan == "mobil_kmt_detail" and ham else _ad(ham, azami)
            degisti |= _doldur(ekip, alan, metin or None)
        say["iletisim_yeni" if yeni else ("iletisim_guncellenen" if degisti else "iletisim_ayni")] += 1
    db.flush()


# --- ReportDB tamponu (Musteri Radar) -------------------------------------------------------------------
def tamponu_aktar(ham_yol: Path | None, uygula: bool, say: Counter) -> None:
    if ham_yol is None or not ham_yol.exists():
        print("  tampon: ham_veri.db bulunamadi, atlandi.")
        return
    eski = Kaynak(ham_yol)
    try:
        if not eski.tablo_var("reportdb_tampon"):
            print("  tampon: eski dosyada reportdb_tampon tablosu yok, atlandi.")
            return
        satirlar = eski.satirlar(
            "reportdb_tampon", ("musteri_no", "unvan", "aktif", "biletli_aktif", "kapanan", "biletli_kapanan", "en_eski", "son_kapanis")
        )
        durum = eski.b.execute("SELECT son_basari, veri_zamani FROM reportdb_durum WHERE id = 1").fetchone() if eski.tablo_var("reportdb_durum") else None
    finally:
        eski.kapat()
    satirlar.sort(key=lambda s: (-(_tamsayi(s["aktif"]) + _tamsayi(s["kapanan"])), str(s["musteri_no"])))
    veri_zamani = str(durum["veri_zamani"] or "") if durum else ""
    say["tampon_satir"] = len(satirlar)
    if not satirlar:
        print("  tampon: eski tamponda satir yok (eski panel ReportDB verisi hic almamis), atlandi.")
        return
    etiket = f"Eski panel tamponu {veri_zamani}".strip()[:200]
    if not uygula:
        say["tampon_yazilacak"] = 1
        return
    with oturum() as db:
        if db.scalar(select(IngestBatch.id).where(IngestBatch.source_key == reportdb.KAYNAK, IngestBatch.label == etiket)) is not None:
            say["tampon_zaten_alinmis"] = 1
            return
        parti = depo.parti_olustur(db, reportdb.KAYNAK, etiket, "eski_aktar")
        db.commit()
        rows = [
            [s["musteri_no"], s["unvan"], _tamsayi(s["aktif"]), _tamsayi(s["biletli_aktif"]), _tamsayi(s["kapanan"]), _tamsayi(s["biletli_kapanan"]),
             s["en_eski"], s["son_kapanis"], veri_zamani or None]
            for s in satirlar
        ]  # fmt: skip
        parti = depo.ice_al(db, parti, reportdb.BASLIKLAR, rows)
        yerel = None
        try:
            yerel = datetime.fromisoformat(str(durum["son_basari"])).replace(tzinfo=TR).astimezone(UTC) if durum and durum["son_basari"] else None
        except ValueError:
            yerel = None
        if yerel is not None:
            parti.received_at = parti.finished_at = yerel  # veri gercek yasiyla gorunsun (taze degil)
            db.commit()
        say["tampon_alindi" if parti.status == "ready" else "tampon_reddedildi"] = 1


# --- komut satiri ---------------------------------------------------------------------------------------
def _yedek_al(etiket: str = "eski_aktar") -> str | None:
    """SQLite panel veritabaninin tutarli kopyasi (sqlite yedekleme arayuzu). PostgreSQL'de operator yedek alir."""
    url = engine().url
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    kaynak = Path(url.database)
    if not kaynak.exists():
        return None
    klasor = kaynak.parent / "yedek"
    klasor.mkdir(parents=True, exist_ok=True)
    hedef = klasor / f"{kaynak.stem}-{etiket}-{datetime.now():%Y%m%d-%H%M%S}.db"
    with sqlite3.connect(kaynak) as k, sqlite3.connect(hedef) as h:
        k.backup(h)
    return str(hedef)


def _yollar(ham: str) -> tuple[Path, Path | None]:
    yol = Path(ham).expanduser()
    if yol.is_dir():
        panel = yol / "panel.db"
        if not panel.exists() and (yol / "veritabani" / "panel.db").exists():
            panel = yol / "veritabani" / "panel.db"
    else:
        panel = yol
    return panel, panel.parent / "ham_veri.db"


def _yazdir(say: Counter) -> None:
    gruplar = (
        ("Kullanici", ("kullanici_yeni", "kullanici_guncellenen", "kullanici_ayni", "kullanici_atlanan", "kullanici_ad_degil")),
        (
            "Musteri",
            ("musteri_yeni", "musteri_guncellenen", "musteri_ayni", "musteri_ad_cakismasi", "musteri_istirak", "musteri_catisiz_istirak",
             "musteri_final_dahil", "musteri_sorumlusuz", "musteri_segment_tanimsiz", "musteri_atlanan"),
        ),
        ("Iletisim", ("iletisim_yeni", "iletisim_guncellenen", "iletisim_ayni", "iletisim_tekrar", "iletisim_eslesmeyen")),
        ("Tampon", ("tampon_satir", "tampon_yazilacak", "tampon_alindi", "tampon_zaten_alinmis", "tampon_reddedildi")),
    )
    for baslik, anahtarlar in gruplar:
        parca = [f"{a.split('_', 1)[1]}={say[a]}" for a in anahtarlar if say[a]]
        if parca:
            print(f"  {baslik}: " + ", ".join(parca))


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    p = argparse.ArgumentParser(prog="python -m app.eski_aktar", description=__doc__.split("\n\n")[0], add_help=True)
    p.add_argument("--kaynak", required=True, help="eski panel veritabani klasoru (panel.db, ham_veri.db) ya da panel.db yolu")
    p.add_argument("--uygula", action="store_true", help="yazar (varsayilan: kuru deneme, hicbir sey yazilmaz)")
    p.add_argument("--yalniz", default=",".join(ADIMLAR), help="virgulle: " + ", ".join(ADIMLAR))
    p.add_argument("--ad-hepsi", action="store_true", help="tasinan tum kullanicilari AD kullanicisi yap (varsayilan: eski kayittaki bayrak)")
    p.add_argument("--yedek-yok", action="store_true", help="uygulamadan once SQLite yedegi alma")
    try:
        a = p.parse_args(argv)
    except SystemExit as cikis:
        return 0 if cikis.code in (0, None) else 2
    adimlar = {x.strip() for x in a.yalniz.split(",") if x.strip()}
    if not adimlar or not adimlar <= set(ADIMLAR):
        print("--yalniz degerleri: " + ", ".join(ADIMLAR))
        return 2
    env_dosyasi_yukle()
    panel_yolu, ham_yolu = _yollar(a.kaynak)
    if not panel_yolu.exists():
        print(f"panel.db bulunamadi: {panel_yolu}")
        return 1

    url = engine().url
    print(("UYGULAMA" if a.uygula else "KURU DENEME (hicbir sey yazilmaz)") + f" | hedef: {url.get_backend_name()} {url.database or ''} | adimlar: {', '.join(x for x in ADIMLAR if x in adimlar)}")
    say: Counter = Counter()
    yedek = None
    if a.uygula and not a.yedek_yok:
        yedek = _yedek_al()
        print(f"  yedek: {yedek}" if yedek else "  yedek: SQLite degil, panel veritabaninin yedegini kendiniz alin.")

    eski = Kaynak(panel_yolu)
    try:
        with oturum() as db:
            try:
                kisiler = kullanicilari_aktar(db, eski, say, yaz="kullanici" in adimlar, ad_hepsi=a.ad_hepsi)
                unvanlar: dict[str, int] = {}
                if adimlar & {"musteri", "iletisim"}:
                    if "musteri" in adimlar:
                        _, unvanlar = musterileri_aktar(db, eski, kisiler, say)
                    else:
                        unvanlar = {eslestirme_anahtari(c.name or ""): c.id for c in db.scalars(select(Customer))}
                if "iletisim" in adimlar:
                    iletisimi_aktar(db, eski, unvanlar, say)
                if a.uygula:
                    db.add(AuditEvent(at=simdi(), actor="eski_aktar", action="eski_panel.aktar", outcome="allow", module_key="yonetim", detail=json.dumps(dict(say))[:500]))
                    db.commit()
                else:
                    db.rollback()
            except Exception:
                db.rollback()
                raise
    finally:
        eski.kapat()
    if "tampon" in adimlar:
        tamponu_aktar(ham_yolu, a.uygula, say)
    _yazdir(say)
    print("Bitti." if a.uygula else "Kuru deneme bitti: hicbir sey yazilmadi. Sayilar uygun ise ayni komutu --uygula ile calistirin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
