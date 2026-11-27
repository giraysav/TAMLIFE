"""Veri iscisi: Oracle cekimleri panel (web) surecinin DISINDA (uretim isletim/reportdb_senkron.py + kutucuklar/veri/db_al.py).

  cd backend; ..\\.venv\\Scripts\\python.exe -m app.isci reportdb [--client <Instant Client>]
      30 dk'lik tur: TEMIP alarm kayitlari (tampon/temip_kayit: karta ya da TAM Radar'a; gunde bir mutabakat), ardindan LOE
      devre grafikleri, CI envanteri ve OneDesk sikayet / talep kayitlari. Eski alarm ozet sorgusu 2026-11-23 kaldirildi.
      Servis dongusu her 30 dk: kurulum\\canli_gorev_kur.ps1 (Oracle giris tetikleyicisinin izin verdigi kimlikle).
  ..\\.venv\\Scripts\\python.exe -m app.isci temip-kayit --kip tam|artimli|mutabakat [--kuru] [--csv]
      TEMIP alarm kayitlari elle; 'tam' REPORTDB_KAYIT_BASLANGIC'tan (vars. 2026-01-01) bugune ilk yukleme (dakikalar surer).
      --kuru: ayni sorgular, yazmaz; Musteri No -> unvan -> kart -> sorumlu personel -> acik kayit eslesmesini gosterir.
  ..\\.venv\\Scripts\\python.exe -m app.isci reportdb-katalog [--sema TEMIP ...] [--ornek 200]
      Ham katalog (Veri Girisi agaci): izinli semalarin nesne -> alt nesne -> sutun yapisi + ornek satirlar (tampon/katalog).
      Paneldeki "Yenile" ayni komutu ayri surecte baslatir.
  ..\\.venv\\Scripts\\python.exe -m app.isci pg-katalog --kaynak pg_onent|pg_onedesk [--ornek 20]
      PostgreSQL katalogu (ONENTDB / ONEDESKDB, salt okunur): sema -> tablo -> sutun + ornek satirlar (tampon/postgres).
  ..\\.venv\\Scripts\\python.exe -m app.isci temip-eslesme [--csv]
      Oracle'a baglanmaz: paneldeki TEMIP kayitlarinin eslesmesi (kart / TAM Radar / belirsiz / personelsiz kart, personel basina acik).
      --csv: backend/var/kesif/temip-eslesme-<zaman>-{musteri,personel}.csv (git disi; musteri unvani icerir).
  ..\\.venv\\Scripts\\python.exe -m app.isci rapor-devre [--zorla] [--client <Instant Client>]
      Aylik rapor devre grafikleri (rapor/loe.py, LOE sorgusu): CMDB kopyasi (gunde bir) + secili devrelerin onceki / bu ay saatlik
      olcumleri. 'reportdb' turu her calismada bunu da (ayri kilitle, alarm senkronundan bagimsiz) calistirir. --zorla: hepsini yenile.
  ..\\.venv\\Scripts\\python.exe -m app.isci envanter [--zorla]
      Musteri envanteri / Kritik CI (musteri/envanter.py): ONENT CMDB'den panel Musteri No'larinin CI'lari (4 saatte bir; --zorla:
      hemen). 'reportdb' turu her calismada bunu da (ayri kilitle) cagirir; Oracle istemcisi gerekmez.
  ..\\.venv\\Scripts\\python.exe -m app.isci onedesk-kayit [--kip tam|artimli|mutabakat]
      OneDesk sikayet / talep kayitlari (onedesk/canli.py; alarm kurallariyla ayni: 01.01.2026'dan acilanlar, Musteri No ile karta).
      'reportdb' turu her calismada bunu da (ayri kilitle) cagirir: ilk calisma tam, gunde bir mutabakat, digerleri artimli.
  ..\\.venv\\Scripts\\python.exe -m app.isci utilizasyon [--kuru]
      Gunluk utilizasyon turu (skor/gunluk.py): Kayit Hacmi (panel kayitlarindan bu yil kapanan + acik alarm / talep / sikayet), aktif CI /
      lokasyon (ONENT envanteri) -> util_source_summary; cati skorlari yeniden hesaplanip degisenlere yazilir. Zamanlanmis gorev her
      sabah 06:00 (kurulum\\canli_gorev_kur.ps1). --kuru: ozeti yazar, skora dokunmaz.
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
from app.ortak import UygulamaHatasi
from app.tampon import katalog, oracle, postgres, reportdb, temip_kayit

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


def reportdb_senkron() -> int:
    """30 dk'lik tur: TEMIP alarm kayitlari (karta ya da TAM Radar'a; gunde bir mutabakat). Kart alarm sayaclari yalniz bunlardan.
    2026-11-23: eski alarm ozet sorgusu kaldirildi. Sonuc reportdb.durum_yaz ile Veri Ozeti / Veri Akisi'nda gorunur."""
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
            with oturum() as db:
                kayit = temip_kayit.calistir(db, temip_kayit.otomatik_kip(db))
                reportdb.durum_yaz(db)
        except Exception as e:  # noqa: BLE001 - yazilan parcalar kalir (idempotent); sonraki tur tamamlar
            mesaj = _mesaj(e, a)
            try:
                with oturum() as db:
                    reportdb.durum_yaz(db, mesaj)
            except Exception as yazilamadi:  # noqa: BLE001 - panel DB'sine de yazilamiyorsa gunluk yeter
                gunluge_yaz(f"reportdb durum yazilamadi: {type(yazilamadi).__name__}")
            ariza.kaydet("TL-TAM-01", f"alarm kayit turu: {mesaj}", kaynak="isci.reportdb", kullanici=reportdb.ISCI)
            return _hata("reportdb", f"Alarm kayit turu basarisiz: {mesaj}")
        satir = f"{time.time() - t0:.1f} sn; {_kayit_ozeti(kayit)}"
        print(f"[OK] {satir}")
        gunluge_yaz(f"reportdb OK {satir}")
        return 0
    finally:
        try:
            kilit.unlink()
        except OSError:
            pass


def rapor_devre(zorla: bool = False) -> int:
    """Aylik rapor devre grafikleri verisi (rapor/loe.py). Alarm senkronundan bagimsiz kilit; hata durumu panelde gorunur."""
    from app.rapor import loe

    a = oracle.ayar(loe.KAYNAK)
    if not a.ENABLED:
        return _hata("rapor-devre", f"{a.kaynak.enabled_key}=true degil; Oracle'a baglanilmadi.")
    kilit = _klasor() / "isci_loe.kilit"
    if not kilit_al(kilit):
        gunluge_yaz("rapor-devre ATLANDI baska calisma suruyor")
        return 2
    t0 = time.time()
    try:
        with oturum() as db:
            sonuc = loe.senkron(db, zorla)
        parcalar = ([f"cmdb {sonuc['cmdb']}"] if sonuc["cmdb"] else []) + [f"olcum {o}" for o in sonuc["olcum"]]
        if parcalar:
            hata = any("HATA" in p for p in parcalar)
            gunluge_yaz(f"rapor-devre {'HATA' if hata else 'OK'} {'; '.join(parcalar)} ({time.time() - t0:.1f} sn)")
            print(("[!] " if hata else "[OK] ") + "; ".join(parcalar))
            return 1 if hata else 0
        print("[-] rapor-devre: yenilenecek veri yok")
        return 0
    except Exception as e:  # noqa: BLE001
        return _hata("rapor-devre", f"basarisiz: {_mesaj(e, a)}")
    finally:
        try:
            kilit.unlink()
        except OSError:
            pass


def envanter_turu(zorla: bool = False) -> int:
    """Musteri envanteri (Kritik CI). Kaynak kapali ya da yenileme zamani gelmediyse sessizce gecer."""
    from app.musteri import envanter
    from app.tampon import postgres

    if not postgres.ayar(envanter.KAYNAK).ENABLED:
        return 0
    kilit = _klasor() / "isci_envanter.kilit"
    if not kilit_al(kilit):
        return 2
    try:
        with oturum() as db:
            if not zorla and not envanter.gerekli_mi(db):
                return 0
            sonuc = envanter.yenile(db)
        if "hata" in sonuc:
            return _hata("envanter", f"basarisiz: {sonuc['hata']}")
        gunluge_yaz(f"envanter OK {sonuc['satir']} CI, {sonuc['sure_sn']} sn")
        print(f"[OK] envanter: {sonuc['satir']} CI, {sonuc['sure_sn']} sn")
        return 0
    finally:
        try:
            kilit.unlink()
        except OSError:
            pass


def onedesk_kayit_turu(kip: str | None = None) -> int:
    """OneDesk sikayet / talep kayitlari -> panel (onedesk/canli.py). Kaynak kapaliysa sessizce gecer; hata durumu Veri Ozeti'nde."""
    from app.onedesk import canli
    from app.tampon import postgres

    if not postgres.ayar(canli.KAYNAK).ENABLED:
        return 0
    kilit = _klasor() / "isci_onedesk_kayit.kilit"
    if not kilit_al(kilit):
        return 2
    try:
        with oturum() as db:
            k = kip or canli.otomatik_kip(db)
            try:
                o = canli.calistir(db, k)
            except Exception as e:  # noqa: BLE001 - alarm senkronunu etkilemez; sonraki tur yeniden dener
                db.rollback()
                mesaj = str(getattr(e, "mesaj", "") or e)[:220]
                canli.durum_yaz(db, son_deneme=datetime.now(UTC).isoformat(), hata=mesaj)
                return _hata("onedesk-kayit", f"basarisiz ({k}): {mesaj}")
        satir = (f"onedesk-kayit OK ({k}) {o['satir']} satir: +{o['eklenen']} yeni, {o['guncellenen']} guncel, {o['silinen']} silinen, "
                 f"{o.get('yeniden_baglanan', 0)} yeniden baglanan, {o.get('etkilenen_kart', 0)} kart, {o.get('sure_sn', 0)} sn")  # fmt: skip
        gunluge_yaz(satir)
        print("[OK] " + satir)
        return 0
    finally:
        try:
            kilit.unlink()
        except OSError:
            pass


def utilizasyon_turu(kuru: bool = False) -> int:
    """Gunluk utilizasyon (06:00). Ayni anda tek calisma; kaynak hatasi ozette gorunur, skor kalan verilerle hesaplanir."""
    from app.skor import gunluk

    kilit = _klasor() / "isci_utilizasyon.kilit"
    if not kilit_al(kilit):
        gunluge_yaz("utilizasyon ATLANDI baska calisma suruyor")
        return 2
    try:
        envanter_turu()  # envanter bayatsa once yenilenir (4 saat kurali)
        with oturum() as db:
            d = gunluk.calistir(db, skor_yaz=not kuru)
    except Exception as e:  # noqa: BLE001
        return _hata("utilizasyon", f"basarisiz: {type(e).__name__}: {str(e)[:200]}")
    finally:
        try:
            kilit.unlink()
        except OSError:
            pass
    k = d["kaynaklar"]
    parca = [f"{ad} {v.get('durum')}" + (f" ({v['hata'][:120]})" if v.get("hata") else "") for ad, v in k.items()]
    sk = d.get("skor")
    satir = (f"utilizasyon {'HATA' if any(v.get('durum') == 'hata' for v in k.values()) else 'OK'} {d['sure_sn']} sn; "
             f"{'; '.join(parca)}" + (f"; skor {sk['uygulanan']} yazildi, {sk['degismeyen']} degismedi, {sk['atlanan']} atlandi, {sk.get('kismi', 0)} ara skor (eksik kriterli)" if sk else "; skor yazilmadi (kuru)"))  # fmt: skip
    print(("[OK] " if " OK " in satir else "[!] ") + satir)
    gunluge_yaz(satir)
    return 0 if " OK " in satir else 1


def erken_uyari_bildir() -> int:
    """Kayit turundan sonra: kritik musterinin sorumlu TAM'ina panel bildirimi (tekrar siniri app.musteri.erken_uyari.bildir)."""
    from app.musteri import erken_uyari

    t0 = time.time()
    try:
        with oturum() as db:
            d = erken_uyari.bildir(db)
            db.commit()
    except Exception as e:  # noqa: BLE001
        return _hata("erken-uyari-bildir", f"basarisiz: {type(e).__name__}: {str(e)[:200]}")
    if d["gonderilen"]:  # sessiz turlar gunlugu doldurmasin
        gunluge_yaz(f"erken-uyari-bildir OK {d['kritik']} kritik, {d['gonderilen']} bildirim, {d['atlanan']} atlandi ({time.time() - t0:.1f} sn)")
    return 0


def erken_uyari_dogrula(hafta: int) -> int:
    """Musteri Erken Uyari geriye donuk dogrulamasi (yalniz panel verisi, kaynaga baglanmaz): seviye -> sonraki 14 gunde sikayet orani."""
    from app.musteri import erken_uyari

    t0 = time.time()
    try:
        with oturum() as db:
            d = erken_uyari.dogrula(db, hafta=hafta)
    except Exception as e:  # noqa: BLE001
        return _hata("erken-uyari-dogrula", f"basarisiz: {type(e).__name__}: {str(e)[:200]}")
    print(f"Referans gunleri {d['bas']} .. {d['bit']} ({d['hafta']} hafta); sonuc: sonraki 14 gunde yeni sikayet")
    for kume, baslik in (("tum", "Tum musteriler"), ("temiz", "Onceki 14 gunde sikayeti OLMAYANLAR")):
        print(f"  {baslik}:")
        for sev, v in d[kume].items():
            print(f"    {sev:<7} {v['gozlem']:>6} gozlem  {v['sikayet']:>5} sikayet  " + (f"%{100 * v['oran']:.1f}" if v["oran"] is not None else "-"))
    t, n = d["temiz"]["yuksek"], d["temiz"]["normal"]
    kat = f"{t['oran'] / n['oran']:.1f}x" if t["oran"] and n["oran"] else "-"
    satir = (f"erken-uyari-dogrula OK {d['hafta']} hafta, {time.time() - t0:.0f} sn; kritik %{100 * (d['tum']['kritik']['oran'] or 0):.1f} / "
             f"normal %{100 * (d['tum']['normal']['oran'] or 0):.1f}; temiz yuksek/normal {kat}; sikayetlerin %{100 * (d['onceden_gorulen'] or 0):.1f}'i onceden kritik+yuksek")  # fmt: skip
    print(f"[OK] {satir}")
    gunluge_yaz(satir)
    return 0


def _kayit_ozeti(k: dict) -> str:
    return (f"alarm kayitlari ({k['kip']}): +{k['eklenen']} yeni, {k['guncellenen']} guncel, {k['acik_satir']} acik, "
            f"{k['dusen_acik']} dusen ({k.get('aranan_dusen', k['dusen_acik'])} arandi)/{k['kapanan_sorgu']} kapanan,{k['yeniden_baglanan']} yeniden baglanan, {k['etkilenen_kart']} kart")  # fmt: skip


ESLESME_DURUMLARI = (("kart", "karta (sorumlu TAM)"), ("kart_personelsiz", "karta, sorumlusu TAM degil"),
                     ("radar", "TAM Radar (kart yok)"), ("belirsiz", "belirsiz (numara birden cok kartta) -> Radar"))  # fmt: skip


def _eslesme_yaz(r: dict, csv: bool) -> None:
    """Eslesme ozetini yazar; csv ise musteri ve personel tablolarini var/kesif/'e (git disi) yazar."""
    print("Eslesme (Musteri No -> kart -> sorumlu personel):")
    for d, ad in ESLESME_DURUMLARI:
        o = r["ozet"][d]
        print(f"  {ad:<46} {o['musteri']:>6} musteri {o['acik']:>7} acik {o['kapali']:>8} kapali")
    print("Personel basina (ilk 15, acik kayda gore):")
    for p in r["personel"][:15]:
        etiket = p["personel"] + ("" if p["tam"] else " (TAM degil)")
        print(f"  {etiket[:40]:<40} {p['kart']:>4} kart {p['acik']:>6} acik ({p['acik_ticketli']} ticketli) {p['kapali']:>7} kapali")
    u = r["uyari"]
    if u["belirsiz_numara"]:
        print(f"[!] Birden cok kartta yazili Musteri No ({len(u['belirsiz_numara'])}): {', '.join(u['belirsiz_numara'][:20])}")
    if u["personelsiz_kart"]:
        print(f"[!] Sorumlusu TAM olmayan eslesen kart ({len(u['personelsiz_kart'])}): {', '.join(u['personelsiz_kart'][:10])}")
    if u["bicimsiz_kart_no"]:
        print(f"[!] Musteri No'su TEMIP bicimine (8 hane) uymayan kart ({len(u['bicimsiz_kart_no'])}): {', '.join(u['bicimsiz_kart_no'][:10])}")
    print(f"  Numarasi olup TEMIP kaydi eslesmeyen kart: {u['kayitsiz_numarali_kart']}")
    if "bagli_olmayan" in r:
        print(f"  Kart baglantisi guncel olmayan kayit (sonraki turda baglanir): {r['bagli_olmayan']}")
    if not csv:
        return
    import csv as csvmod

    klasor = Path(__file__).resolve().parents[1] / "var" / "kesif"
    klasor.mkdir(parents=True, exist_ok=True)
    zaman = f"{datetime.now(UTC).astimezone():%Y%m%d-%H%M}"
    tablolar = (
        ("musteri", r["musteriler"], ("musteri_no", "temip_unvan", "durum", "kart_id", "panel_unvan", "cati", "personel",
                                      "personel_kullanici", "acik", "acik_ticketli", "kapali", "toplam", "aday_kartlar")),
        ("personel", r["personel"], ("personel", "personel_kullanici", "tam", "kart", "musteri_no", "acik", "acik_ticketli", "kapali")),
    )  # fmt: skip
    for ad, satirlar, sutunlar in tablolar:
        yol = klasor / f"temip-eslesme-{zaman}-{ad}.csv"
        with open(yol, "w", encoding="utf-8-sig", newline="") as f:
            w = csvmod.DictWriter(f, fieldnames=sutunlar, delimiter=";", extrasaction="ignore")
            w.writeheader()
            w.writerows(satirlar)
        print(f"  CSV: {yol}")


def temip_eslesme(csv: bool) -> int:
    """Oracle'siz: paneldeki TEMIP kayitlarinin su anki kart numaralarina gore eslesmesi."""
    try:
        with oturum() as db:
            r = temip_kayit.eslesme_raporu(db)
    except Exception as e:  # noqa: BLE001
        return _hata("temip-eslesme", f"basarisiz: {type(e).__name__}: {e}")
    if not r["musteriler"]:
        print("[-] Panelde TEMIP kaydi yok (once: temip-kayit --kip tam).")
        return 0
    _eslesme_yaz(r, csv)
    return 0


def temip_kayit_calistir(kip: str, kuru: bool = False, csv: bool = False) -> int:
    """Elle: 'tam' ilk yukleme (REPORTDB_KAYIT_BASLANGIC'tan bugune, ay ay), 'mutabakat', 'artimli'. 30 dk'lik turla ayni kilit.
    kuru: ayni sorgular, panel DB'sine yazmaz (kilit almaz); eslesmeyi gosterir."""
    a = oracle.ayar(reportdb.KAYNAK)
    if not a.ENABLED:
        return _hata("temip-kayit", f"{a.kaynak.enabled_key}=true degil; Oracle'a baglanilmadi.")
    if kuru:
        t0 = time.time()
        try:
            with oturum() as db:
                k = temip_kayit.onizle(db, kip)
        except Exception as e:  # noqa: BLE001
            return _hata("temip-kayit", f"kuru {kip} basarisiz: {_mesaj(e, a)}")
        aylar = ", ".join(f"{x['ay']}={x['satir']}" for x in k["aylar"])
        print(f"[KURU] {kip}, baslangic {k['baslangic']}: {k['kapali_satir']} kapali + {k['acik_satir']} acik satir, "
              f"{time.time() - t0:.1f} sn; hicbir sey yazilmadi" + (f"; aylar: {aylar}" if aylar else ""))  # fmt: skip
        _eslesme_yaz(k, csv)
        return 0
    kilit = _klasor() / "isci_reportdb.kilit"
    if not kilit_al(kilit):
        print("[-] Baska bir senkron suruyor; atlandi.")
        gunluge_yaz("temip-kayit ATLANDI baska calisma suruyor")
        return 2
    t0 = time.time()
    try:
        with oturum() as db:
            k = temip_kayit.calistir(db, kip)
    except Exception as e:  # noqa: BLE001 - yazilan parcalar kalir (idempotent); sonraki calisma tamamlar
        return _hata("temip-kayit", f"{kip} basarisiz: {_mesaj(e, a)}")
    finally:
        try:
            kilit.unlink()
        except OSError:
            pass
    satir = f"temip-kayit OK {time.time() - t0:.1f} sn; {_kayit_ozeti(k)}"
    if k.get("aylar"):
        satir += "; aylar: " + ", ".join(f"{x['ay']}={x['satir']}" for x in k["aylar"])
    print(f"[OK] {satir}")
    gunluge_yaz(satir)
    return temip_eslesme(csv) if csv else 0


def katalog_calistir(semalar: list[str] | None, adet: int, kullanici: str, parametre: dict | None = None) -> int:
    """Ham katalog taramasi (yalniz SELECT: veri sozlugu + ornek satir). Ayni anda tek calisma."""
    a = oracle.ayar(katalog.KAYNAK)
    if not a.ENABLED:
        return _hata("reportdb-katalog", f"{a.kaynak.enabled_key}=true degil; Oracle'a baglanilmadi.")
    kilit = _klasor() / "isci_katalog.kilit"
    if not kilit_al(kilit):
        print("[-] Baska bir katalog taramasi suruyor; atlandi.")
        return 2
    t0 = time.time()
    try:
        with oturum() as db:
            k = katalog.tara(
                db, kullanici, semalar, adet, parametre=parametre, kalp=lambda: os.utime(kilit)
            )  # uzun tarama: kilit bayatlamasin
            ozet = dict(k.summary or {})
    except Exception as e:  # noqa: BLE001 - katalog 'failed' olarak yazildi
        return _hata("reportdb-katalog", f"basarisiz: {_mesaj(e, a)}")
    finally:
        try:
            kilit.unlink()
        except OSError:
            pass
    satir = (f"reportdb-katalog OK {time.time() - t0:.1f} sn; semalar {', '.join(ozet.get('semalar', []))}: "
             f"{ozet.get('nesne', 0)} nesne, {ozet.get('sutun', 0)} sutun")  # fmt: skip
    print(f"[OK] {satir}")
    gunluge_yaz(satir)
    return _katalogdan_kayitlar()


def _katalogdan_kayitlar() -> int:
    """2026-10-19 kullanici: "reportdb verileri guncellemiyor": katalog taramasi bitince alarm kayitlari ham dosyadan kartlara / TAM
    Radar'a aktarilir (eskiden ayri 'temip-kayit --kip katalogdan' gerekiyordu). Ayni kilit: 30 dk'lik tur suruyorsa atlanir."""
    kilit = _klasor() / "isci_reportdb.kilit"
    if not kilit_al(kilit):
        gunluge_yaz("temip-kayit (katalogdan) atlandi: baska senkron suruyor")
        return 0
    t0 = time.time()
    try:
        with oturum() as db:
            k = temip_kayit.calistir(db, "katalogdan")
    except Exception as e:  # noqa: BLE001 - katalog yazildi; aktarim elle yeniden denenir
        ariza.kaydet("TL-TAM-01", f"katalogdan kayit aktarimi: {type(e).__name__}", kaynak="isci.reportdb-katalog", kullanici=reportdb.ISCI)
        return _hata("temip-kayit", f"katalogdan aktarim basarisiz: {type(e).__name__}: {str(e)[:200]}")
    finally:
        try:
            kilit.unlink()
        except OSError:
            pass
    satir = f"temip-kayit OK {time.time() - t0:.1f} sn; katalog sonrasi: {_kayit_ozeti(k)}"
    print(f"[OK] {satir}")
    gunluge_yaz(satir)
    return 0


def pg_katalog_calistir(kaynak: str, adet: int, kullanici: str) -> int:
    """PostgreSQL katalogu (yalniz SELECT, salt okunur oturum). Kaynak basina ayni anda tek calisma."""
    kilit = _klasor() / f"isci_pg_{kaynak}.kilit"
    if not kilit_al(kilit):
        print("[-] Bu kaynakta baska bir katalog taramasi suruyor; atlandi.")
        return 2
    t0 = time.time()
    try:
        with oturum() as db:
            k = postgres.tara(db, kaynak, kullanici, adet)
            ozet = dict(k.summary or {})
    except postgres.PgHata as e:
        return _hata("pg-katalog", f"{kaynak} {e.mesaj}")
    finally:
        try:
            kilit.unlink()
        except OSError:
            pass
    satir = f"pg-katalog OK {kaynak} {time.time() - t0:.1f} sn; {len(ozet.get('semalar', []))} sema, {ozet.get('nesne', 0)} nesne, {ozet.get('sutun', 0)} sutun"
    print(f"[OK] {satir}")
    gunluge_yaz(satir)
    return 0


def main(argv: list[str] | None = None) -> int:
    for akim in (sys.stdout, sys.stderr):
        if hasattr(akim, "reconfigure"):
            akim.reconfigure(errors="replace")  # Windows konsol kod sayfasinda olmayan harf cokertmesin
    p = argparse.ArgumentParser(prog="python -m app.isci", description="Veri iscisi (Oracle cekimleri, panel disi surec)")
    alt = p.add_subparsers(dest="is_", required=True)
    r = alt.add_parser("reportdb", help="30 dk turu: TEMIP alarm kayitlari + LOE + envanter + OneDesk")
    t = alt.add_parser("temip-kayit", help="TEMIP alarm kayitlari: karta / TAM Radar'a (tam = ilk yukleme)")
    t.add_argument(
        "--kip", choices=temip_kayit.KIPLER, default="artimli", help="katalogdan: kapananlar ham katalog dosyasindan (ilk yukleme)"
    )
    t.add_argument("--client", default=None, help="Oracle Instant Client klasoru (vars. ORACLE_CLIENT_DIR)")
    t.add_argument("--kuru", action="store_true", help="yazmadan dene; eslesmeyi goster")
    t.add_argument("--csv", action="store_true", help="eslesmeyi var/kesif/'e CSV yaz")
    kt = alt.add_parser("reportdb-katalog", help="ham katalog: sema -> nesne -> alt nesne -> sutun + ornek satirlar")
    kt.add_argument("--sema", action="append", default=None, help="yalniz bu sema (tekrarlanabilir; vars. tum izinli semalar)")
    kt.add_argument("--ornek", type=int, default=katalog.ORNEK_ADET, help="nesne basina ornek satir (1-1000)")
    kt.add_argument("--kullanici", default="isci", help="kataloga yazilan baslatan")
    kt.add_argument("--ara", default=None, help="sutun degerlerinde aranacak metin (vars. nw_li_cust: kurumsal alarmlar)")
    kt.add_argument("--alan", default=None, help="domain sutunu (vars. NETWORK)")
    kt.add_argument("--deger", action="append", default=None, help="domain degeri (tekrarlanabilir; vars. NOC DESTECH)")
    kt.add_argument("--saat", type=int, default=None, help="bolumlu tabloda pencere (saat, vars. 6)")
    kt.add_argument("--client", default=None, help="Oracle Instant Client klasoru (vars. ORACLE_CLIENT_DIR)")
    pg = alt.add_parser("pg-katalog", help="PostgreSQL katalogu (ONENTDB / ONEDESKDB): sema -> tablo -> sutun + ornek satirlar")
    pg.add_argument("--kaynak", required=True, choices=sorted(postgres.KAYNAKLAR))
    pg.add_argument("--ornek", type=int, default=postgres.ORNEK_ADET, help="nesne basina ornek satir (1-200)")
    pg.add_argument("--kullanici", default="isci", help="kataloga yazilan baslatan")
    rd = alt.add_parser("rapor-devre", help="aylik rapor devre grafikleri: CMDB kopyasi + secili devrelerin olcumleri (LOE)")
    rd.add_argument("--zorla", action="store_true", help="CMDB ve tum olcumleri yenile")
    rd.add_argument("--client", default=None, help="Oracle Instant Client klasoru (vars. ORACLE_CLIENT_DIR)")
    ev = alt.add_parser("envanter", help="musteri envanteri / Kritik CI (ONENT CMDB)")
    ev.add_argument("--zorla", action="store_true", help="yenileme zamanini bekleme")
    ok = alt.add_parser("onedesk-kayit", help="OneDesk sikayet / talep kayitlari -> kartlar (alarm kurallariyla)")
    ok.add_argument("--kip", choices=("tam", "artimli", "mutabakat"), default=None, help="vars. otomatik")
    ut = alt.add_parser("utilizasyon", help="gunluk utilizasyon: kapanan kayitlar + envanter -> ozet ve skor (06:00)")
    ut.add_argument("--kuru", action="store_true", help="ozeti yaz, skora dokunma")
    eu = alt.add_parser("erken-uyari-dogrula", help="Musteri Erken Uyari geriye donuk dogrulama (panel verisiyle, Oracle'siz)")
    eu.add_argument("--hafta", type=int, default=16, help="kac haftalik referans gunu (4-40)")
    e = alt.add_parser("temip-eslesme", help="paneldeki TEMIP kayitlarinin kart / personel eslesmesi (Oracle'siz)")
    e.add_argument("--csv", action="store_true", help="var/kesif/'e CSV yaz")
    for alt_p in (r,):
        alt_p.add_argument("--client", default=None, help="Oracle Instant Client klasoru (vars. ORACLE_CLIENT_DIR)")
    a = p.parse_args(argv)
    env_dosyasi_yukle()
    if a.is_ == "temip-eslesme":
        return temip_eslesme(a.csv)
    if a.is_ == "erken-uyari-dogrula":
        return erken_uyari_dogrula(max(4, min(int(a.hafta), 40)))
    if a.is_ == "pg-katalog":
        return pg_katalog_calistir(a.kaynak, max(1, min(int(a.ornek), 200)), a.kullanici)
    if a.is_ == "envanter":
        return envanter_turu(a.zorla)
    if a.is_ == "utilizasyon":
        return utilizasyon_turu(a.kuru)
    if a.is_ == "onedesk-kayit":
        return onedesk_kayit_turu(a.kip)
    hata = _istemci(a.client)
    if hata:
        return _hata(a.is_, hata)
    if a.is_ == "reportdb-katalog":
        parametre = {"ara": a.ara, "alan": a.alan, "degerler": a.deger, "saat": a.saat}
        return katalog_calistir(a.sema, max(1, min(int(a.ornek), 1000)), a.kullanici, parametre)
    if a.is_ == "temip-kayit":
        return temip_kayit_calistir(a.kip, a.kuru, a.csv)
    if a.is_ == "rapor-devre":
        return rapor_devre(a.zorla)
    if a.is_ == "reportdb":
        kod = reportdb_senkron()
        rapor_devre()  # 2026-11-20: ayni 30 dk'lik turda; sonucu alarm turunun cikis kodunu degistirmez
        envanter_turu()  # 2026-11-20: Kritik CI envanteri (4 saatte bir)
        onedesk_kayit_turu()  # 2026-11-21: OneDesk sikayet / talep kayitlari (alarm kurallariyla)
        erken_uyari_bildir()  # 2026-11-27 (kullanici onayi): yeni kayitlarla kritik olan musterinin TAM'ina panel bildirimi
        return kod
    return _hata(a.is_, "bilinmeyen is")


if __name__ == "__main__":
    sys.exit(main())
