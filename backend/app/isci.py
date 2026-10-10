"""Veri iscisi: Oracle cekimleri panel (web) surecinin DISINDA (uretim isletim/reportdb_senkron.py + kutucuklar/veri/db_al.py).

  cd backend; ..\\.venv\\Scripts\\python.exe -m app.isci reportdb [--client <Instant Client>] [--kuru]
      ReportDB alarm senkronu: ozet -> tampon partisi; 'Kartlara yaz' (dagitim kurallari) aciksa kartlar + alarm kayitlari (Onedesk).
      Zamanlanmis gorev her 6 dk: kurulum\\reportdb_gorev_kur.ps1 (Oracle giris tetikleyicisinin izin verdigi kimlikle).
  ..\\.venv\\Scripts\\python.exe -m app.isci cek <kaynak> [--client <Instant Client>] [--kuru]
      <ON EK>_IMPORT_QUERY sonucu -> tampon partisi '<kaynak>_import' (analiz / dagitim / geri alma Veri Girisi'nde).
  --kuru: hicbir sey yazmaz; sorguyu calistirip satir sayisini ve ilk satirlari gosterir.
Kaynak <ON EK>_ENABLED=true degilse Oracle'a baglanilmaz, hicbir sey yazilmaz. Ayarlar backend/.env (panelle ayni: TAMLIFE_DATABASE_URL,
ORACLE_*). Cikis: 0 basarili | 1 hata (tampon ve kartlar degismez) | 2 baska calisma suruyor (atlandi).
Gunluk: <TAMLIFE_LOG_DIR ya da backend/var/logs>/isci.log (calisma basina tek satir).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from app import ariza
from app.config import env_dosyasi_yukle, get_settings
from app.db import oturum
from app.onedesk import ice_al
from app.ortak import UygulamaHatasi
from app.tampon import kaynak, oracle, reportdb

KILIT_BAYAT_SN = 600  # bundan eski kilit dosyasi coken calismadan kalmis sayilir


def _klasor() -> Path:
    ayar = get_settings().log_dir.strip()
    yol = Path(ayar) if ayar else Path(__file__).resolve().parents[1] / "var" / "logs"
    yol.mkdir(parents=True, exist_ok=True)
    return yol


def gunluge_yaz(satir: str) -> None:
    try:
        with open(_klasor() / "isci.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(UTC).astimezone():%Y-%m-%d %H:%M:%S} {satir}\n")
    except OSError:
        pass


def kilit_al(yol: Path) -> bool:
    """Ayni anda tek calisma: yoksa olusturur; taze kilit varsa False. Eski kilit (cokme artigi) silinip yeniden alinir."""
    yol.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            os.close(os.open(str(yol), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return True
        except FileExistsError:
            try:
                if time.time() - yol.stat().st_mtime < KILIT_BAYAT_SN:
                    return False
                yol.unlink()
            except OSError:
                return False
    return False


def _istemci(client: str | None) -> str | None:
    """--client ya da ORACLE_CLIENT_DIR verilmisse oci.dll olmali (thick mod); hic verilmemisse thin mod. Donus: hata metni."""
    klasor = (client or os.environ.get("ORACLE_CLIENT_DIR") or "").strip()
    if not klasor:
        return None
    if not (Path(klasor) / "oci.dll").is_file():
        return f"Oracle Instant Client bulunamadi: {klasor}"
    os.environ["ORACLE_CLIENT_DIR"] = klasor
    return None


def _mesaj(hata: BaseException, a: oracle.OracleKaynak) -> str:
    if isinstance(hata, UygulamaHatasi):
        return oracle.maskele(hata.mesaj, a.gizliler())
    return " ".join(oracle.hata_metni(hata, a.gizliler())).strip()


def _hata(is_: str, mesaj: str) -> int:
    print(f"[!] {mesaj}", file=sys.stderr)
    gunluge_yaz(f"{is_} HATA {mesaj}")
    return 1


def reportdb_senkron(kuru: bool = False) -> int:
    a = oracle.ayar(reportdb.KAYNAK)
    if not a.ENABLED:
        return _hata("reportdb", f"{a.kaynak.enabled_key}=true degil; Oracle'a baglanilmadi.")
    kilit = _klasor() / "isci_reportdb.kilit"
    if not kilit_al(kilit):
        print("[-] Baska bir senkron suruyor; atlandi.")
        gunluge_yaz("reportdb ATLANDI baska calisma suruyor")
        return 2
    t0 = time.time()
    try:
        try:
            basliklar, satirlar = reportdb.cek()
            sure = time.time() - t0
            if kuru:
                print(f"[OK] KURU: {len(satirlar)} satir, {sure:.1f} sn. Sutunlar: {basliklar}")
                for s in satirlar[:5]:
                    print("    ", s)
                return 0
            with oturum() as db:
                parti = reportdb.tampona_yaz(db, basliklar, satirlar, sure)
                parti_id, durum, n, red = parti.id, parti.status, parti.row_count, parti.error
        except Exception as e:  # noqa: BLE001 - her hata partiye yazilir, kartlara dokunulmaz
            mesaj = _mesaj(e, a)
            try:
                with oturum() as db:
                    reportdb.hata_yaz(db, mesaj)
            except Exception as yazilamadi:  # noqa: BLE001 - panel DB'sine de yazilamiyorsa gunluk yeter
                gunluge_yaz(f"reportdb hata partisi yazilamadi: {type(yazilamadi).__name__}")
            return _hata("reportdb", f"Senkron basarisiz: {mesaj}")
        if durum != "ready":
            return _hata("reportdb", f"parti #{parti_id} kabul edilmedi: {red}")
        kayit = None
        try:
            with oturum() as db:
                reportdb.kurallari_hazirla(db)
                sonuc = reportdb.kartlara_uygula(db, parti_id)
                if sonuc["uygulandi"]:  # 'Kartlara yaz' acik: sayilarla birlikte alarm kayit listeleri (kapaliyken ek sorgu gitmez)
                    kparti, kayit = reportdb.kayit_partisi(db)
                    if kayit["musteri"]:
                        kayit.update(ice_al.kaynak_yenile(db, kparti.id if kparti else None, reportdb.ONEDESK_KAYNAGI, "alarm"))
                        db.commit()
        except Exception as e:  # noqa: BLE001 - parti yazildi; kart/kayit yazimi sonraki turda yeniden denenir
            mesaj = f"{n} musteri tampona yazildi, kartlar/kayitlar yazilamadi: {_mesaj(e, a)}"
            ariza.kaydet("TL-TAM-01", mesaj, kaynak="isci.reportdb", kullanici=reportdb.ISCI)
            return _hata("reportdb", mesaj)
        ek = (f"kartlara yazildi: {sonuc['guncellenen']} deger, {sonuc['sifirlanan']} sifirlanan"
              if sonuc["uygulandi"] else f"kartlara yazilmadi ({sonuc['neden']})")  # fmt: skip
        if kayit:
            ek += f"; alarm kayitlari: {kayit['musteri']} kart, {kayit['kapanan_satir']} kapanan + {kayit['acik_satir']} acik satir"
        print(f"[OK] parti #{parti_id}: {n} musteri, {time.time() - t0:.1f} sn; {ek}")
        gunluge_yaz(f"reportdb OK parti #{parti_id}: {n} musteri, {time.time() - t0:.1f} sn; {ek}")
        return 0
    finally:
        try:
            kilit.unlink()
        except OSError:
            pass


def oracle_cek(anahtar: str, kuru: bool = False) -> int:
    a = oracle.ayar(anahtar)
    if not a.ENABLED:
        return _hata(anahtar, f"{a.kaynak.enabled_key}=true degil; Oracle'a baglanilmadi.")
    kilit = _klasor() / f"isci_{anahtar}.kilit"
    if not kilit_al(kilit):
        print("[-] Baska bir cekim suruyor; atlandi.")
        gunluge_yaz(f"{anahtar} ATLANDI baska calisma suruyor")
        return 2
    t0 = time.time()
    try:
        if kuru:
            akis = a.akis(oracle.sorgu_temizle(a.IMPORT_QUERY), 5)
            basliklar = next(akis)
            satirlar = [[oracle.deger(v) for v in s] for blok in akis for s in blok]
            print(f"[OK] KURU: ilk {len(satirlar)} satir, {time.time() - t0:.1f} sn. Sutunlar: {basliklar}")
            for s in satirlar:
                print("    ", s)
            return 0
        with oturum() as db:
            parti = kaynak.oracle_parti(db, anahtar, "isci")
            parti_id, durum, n, red = parti.id, parti.status, parti.row_count, parti.error
    except Exception as e:  # noqa: BLE001 - parti 'failed' olarak kalir (oracle_parti), ayrinti kisa mesajla
        return _hata(anahtar, f"Cekim basarisiz: {_mesaj(e, a)}")
    finally:
        try:
            kilit.unlink()
        except OSError:
            pass
    if durum != "ready":
        return _hata(anahtar, f"parti #{parti_id} kabul edilmedi: {red}")
    print(f"[OK] parti #{parti_id}: {n} satir, {time.time() - t0:.1f} sn")
    gunluge_yaz(f"{anahtar} OK parti #{parti_id}: {n} satir, {time.time() - t0:.1f} sn")
    return 0


def main(argv: list[str] | None = None) -> int:
    for akim in (sys.stdout, sys.stderr):
        if hasattr(akim, "reconfigure"):
            akim.reconfigure(errors="replace")  # Windows konsol kod sayfasinda olmayan harf cokertmesin
    p = argparse.ArgumentParser(prog="python -m app.isci", description="Veri iscisi (Oracle cekimleri, panel disi surec)")
    alt = p.add_subparsers(dest="is_", required=True)
    r = alt.add_parser("reportdb", help="ReportDB alarm senkronu")
    c = alt.add_parser("cek", help="<ON EK>_IMPORT_QUERY -> tampon partisi")
    c.add_argument("kaynak", choices=sorted(oracle.KAYNAKLAR))
    for alt_p in (r, c):
        alt_p.add_argument("--client", default=None, help="Oracle Instant Client klasoru (vars. ORACLE_CLIENT_DIR)")
        alt_p.add_argument("--kuru", action="store_true", help="yazmadan dene")
    a = p.parse_args(argv)
    env_dosyasi_yukle()
    hata = _istemci(a.client)
    if hata:
        return _hata(a.is_ if a.is_ == "reportdb" else a.kaynak, hata)
    return reportdb_senkron(a.kuru) if a.is_ == "reportdb" else oracle_cek(a.kaynak, a.kuru)


if __name__ == "__main__":
    sys.exit(main())
