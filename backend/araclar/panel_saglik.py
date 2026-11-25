"""Canli panel saglik denetimi (yalniz OKUR; hicbir sey yazmaz). kurulum\\panel_testi.ps1 (PANELI_TEST_ET.bat) cagirir.

  cd backend; ..\\.venv\\Scripts\\python.exe araclar\\panel_saglik.py

Her denetim tek satir: DURUM|baslik|ayrinti. DURUM: TAMAM | UYARI (dis sistem / izlenecek durum; panel hatasi degil) | HATA
(panelin kendisinde sorun). Cikis kodu: HATA sayisi (0 = sorun yok). Gizli deger (parola, adres) yazilmaz.

Denetimler: veritabani butunlugu (quick_check), sema surumu (alembic head), son 24 saatin ve acik ariza kayitlari, aylik rapor
gonderim hatalari (TL-RAP-01), ReportDB iscisinin son basarili calismasi, dis baglantilar (AD/LDAPS, ReportDB, ONEDESKDB, ONENTDB;
yalniz erisim adimlari: DNS -> TCP -> oturum, veri okunmaz).
"""

from __future__ import annotations

import re
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
ISCI_BAYAT_DK = 30  # 6 dk'lik isci 5 tur kacirdiysa

sonuclar: list[tuple[str, str, str]] = []


def yaz(durum: str, baslik: str, ayrinti: str = "") -> None:
    ayrinti = " ".join(str(ayrinti).split())[:300]
    sonuclar.append((durum, baslik, ayrinti))
    print(f"{durum}|{baslik}|{ayrinti}", flush=True)


def _db_yolu() -> Path | None:
    from app.config import get_settings

    url = get_settings().database_url
    if not url.startswith("sqlite"):
        return None
    yol = url.split("///", 1)[-1]
    return (KOK / yol).resolve() if not Path(yol).is_absolute() else Path(yol)


def veritabani() -> None:
    yol = _db_yolu()
    if yol is None:
        yaz("UYARI", "Veritabani", "SQLite degil; butunluk denetimi atlandi")
        return
    if not yol.is_file():
        yaz("HATA", "Veritabani", f"dosya yok: {yol.name}")
        return
    try:
        c = sqlite3.connect(f"{yol.as_uri()}?mode=ro", uri=True, timeout=30)
        sonuc = c.execute("PRAGMA quick_check").fetchone()[0]
        surum = c.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        acik = c.execute("SELECT count(*) FROM fault_event WHERE status <> 'closed'").fetchone()[0]
        esik = (datetime.now(UTC) - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")  # fault_event.at UTC
        son24 = c.execute("SELECT count(*) FROM fault_event WHERE at >= ? AND severity = 'error'", (esik,)).fetchone()[0]
        rapor = c.execute("SELECT count(*) FROM fault_event WHERE code = 'TL-RAP-01' AND status <> 'closed'").fetchone()[0]
        c.close()
    except sqlite3.Error as e:
        yaz("HATA", "Veritabani", f"okunamadi: {type(e).__name__}: {e}")
        return
    boyut = yol.stat().st_size // (1024 * 1024)
    yaz("TAMAM" if sonuc == "ok" else "HATA", "Veritabani butunlugu", f"quick_check={sonuc}, {boyut} MB")
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    bas = ScriptDirectory.from_config(Config(str(KOK / "alembic.ini"))).get_current_head()
    yaz("TAMAM" if surum == bas else "HATA", "Veritabani semasi", f"veritabani {surum}, kod {bas}" + ("" if surum == bas else " (panel yeniden baslatilinca guncellenir)"))
    yaz("TAMAM" if son24 == 0 else "UYARI", "Ariza kayitlari", f"son 24 saatte {son24} hata, toplam {acik} kapanmamis kayit (Yonetim > Arizalar)")
    yaz("TAMAM" if rapor == 0 else "UYARI", "Aylik rapor gonderimi", f"{rapor} kapanmamis gonderim hatasi (TL-RAP-01)")


def isci() -> None:
    from app.config import get_settings

    klasor = Path(get_settings().log_dir.strip()) if get_settings().log_dir.strip() else KOK / "var" / "logs"
    gunluk = klasor / "isci.log"
    if not gunluk.is_file():
        yaz("UYARI", "ReportDB iscisi", "isci.log yok")
        return
    son_ok = son_hata = None
    with open(gunluk, encoding="utf-8", errors="replace") as f:
        satirlar = f.readlines()[-400:]
    for satir in satirlar:
        m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) reportdb (OK|HATA)", satir)
        if m:
            an = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            if m.group(2) == "OK":
                son_ok = an
            else:
                son_hata = (an, satir.strip()[20:200])
    if son_ok is None:
        yaz("HATA", "ReportDB iscisi", "son 400 satirda basarili calisma yok" + (f"; son hata: {son_hata[1]}" if son_hata else ""))
        return
    yas = int((datetime.now() - son_ok).total_seconds() // 60)
    if yas > ISCI_BAYAT_DK:
        yaz("HATA", "ReportDB iscisi", f"son basarili calisma {yas} dk once (6 dk'da bir olmali)")
    elif son_hata and son_hata[0] > son_ok:
        yaz("UYARI", "ReportDB iscisi", f"son calisma hatali: {son_hata[1]}")
    else:
        yaz("TAMAM", "ReportDB iscisi", f"son basarili calisma {yas} dk once")


def _adimlar(baslik: str, adimlar: list[dict], dis: bool = True) -> None:
    hatali = [a for a in adimlar if a.get("durum") == "hata"]
    if not hatali:
        yaz("TAMAM", baslik, " > ".join(a.get("baslik", "") for a in adimlar)[:200])
    else:
        a = hatali[0]
        yaz("UYARI" if dis else "HATA", baslik, f"{a.get('baslik', '')}: {a.get('ayrinti', '')}")


def baglantilar() -> None:
    from app import ad
    from app.tampon import oracle, postgres

    denetimler = (
        ("Baglanti: AD / LDAPS (giris)", lambda: ad.erisim_adimlari(), False),  # giris AD'ye bagli: koparsa panel hatasi sayilir
        ("Baglanti: ReportDB (Oracle)", lambda: oracle.erisim_adimlari("oracle_reportdb"), True),
        ("Baglanti: ONEDESKDB (PostgreSQL)", lambda: postgres.erisim_adimlari("pg_onedesk"), True),
        ("Baglanti: ONENTDB (PostgreSQL)", lambda: postgres.erisim_adimlari("pg_onent"), True),
    )
    for baslik, cagri, dis in denetimler:
        try:
            _adimlar(baslik, cagri(), dis)
        except Exception as e:  # noqa: BLE001 - tek denetimin hatasi digerlerini durdurmasin
            yaz("UYARI" if dis else "HATA", baslik, f"denetlenemedi: {type(e).__name__}")


def main() -> int:
    for akim in (sys.stdout, sys.stderr):
        if hasattr(akim, "reconfigure"):
            akim.reconfigure(encoding="utf-8", errors="replace")
    from app.config import env_dosyasi_yukle

    env_dosyasi_yukle()
    for denetim in (veritabani, isci, baglantilar):
        try:
            denetim()
        except Exception as e:  # noqa: BLE001
            yaz("HATA", denetim.__name__, f"denetim calismadi: {type(e).__name__}: {e}")
    return sum(1 for d, _, _ in sonuclar if d == "HATA")


if __name__ == "__main__":
    sys.exit(main())
