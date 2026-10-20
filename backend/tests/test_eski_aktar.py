"""Eski panel aktarimi (app.eski_aktar): SAHTE eski sema (gecici SQLite) ile kuru deneme, uygulama, tekrar calistirma ve Musteri Radar.

Hicbir gercek unvan / kisi / satir yok; eski dosyalar yalniz test klasorunde uretilir.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import eski_aktar, musteri_alani
from app.db import dispose_engines, engine
from app.models import AffiliateFinalFlag, AppUser, AuditEvent, Base, Customer, CustomerTeam, IngestBatch
from app.radar import servis as radar
from app.tampon import reportdb


@pytest.fixture
def hedef(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Bos yeni panel veritabani; donen yol = tmp_path (yedek klasoru yanina acilir)."""
    monkeypatch.setenv("TAMLIFE_DATABASE_URL", f"sqlite:///{(tmp_path / 'yeni.db').as_posix()}")
    monkeypatch.setenv("TAMLIFE_LOG_DIR", str(tmp_path / "log"))
    dispose_engines()
    Base.metadata.create_all(engine())
    yield tmp_path
    dispose_engines()


def _eski_panel(klasor: Path) -> Path:
    """Eski Flask paneli semasinin test icin gereken kismi (ek sutunlar da var: PIN / TOTP / yetki JSON'u tasinmamali)."""
    klasor.mkdir(parents=True, exist_ok=True)
    b = sqlite3.connect(klasor / "panel.db")
    b.executescript(
        """
        CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, is_admin INTEGER, role TEXT, is_active INTEGER,
                            ad_domain TEXT, is_ad_user INTEGER, pin_hash TEXT, totp_secret TEXT, modules TEXT);
        CREATE TABLE sistem_loglari (id INTEGER PRIMARY KEY, kullanici_adi TEXT, eylem TEXT, olusturuldu TEXT);
        CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, user_id INTEGER, parent_customer_id INTEGER, customer_no TEXT, segment TEXT,
                                sector TEXT, score REAL, envanter_count INTEGER, ft_hacim TEXT, tam_ft TEXT, alarm_count INTEGER,
                                sikayet_count INTEGER, talep_count INTEGER, alarm_closed_count INTEGER, sikayet_closed_count INTEGER,
                                talep_closed_count INTEGER, report_count INTEGER, cacti_urls TEXT, pinned_entries TEXT);
        CREATE TABLE destech_contacts (id INTEGER PRIMARY KEY, customer_name TEXT, sales_manager TEXT, presales_manager TEXT, tac_name TEXT,
                                       tac_gsm TEXT, tac_email TEXT, sol_kmt_name TEXT, sol_kmt_gsm TEXT, sol_kmt_email TEXT,
                                       mobil_kmt_name TEXT, mobil_kmt_gsm TEXT, mobil_kmt_email TEXT, mobil_kmt_detail TEXT);
        """
    )
    kullanicilar = [
        (1, "Ornek.Admin", "Ornek Yonetici", 1, "admin", 1, "ORNEK", 1, "pin", "totp", "[]"),
        (2, "ornek.tam", "Ornek Tam Kisi", 0, "TeamMember", 1, "ORNEK", 1, "pin", "totp", "[]"),
        (3, "ornek.yerel", "Ornek Yerel", 0, "TeamMngr", 1, "", 0, "pin", "totp", "[]"),
        (4, "mevcut.kisi", "Mevcut Kisi Gercek", 0, "TeamMember", 1, "ORNEK", 1, "pin", "totp", "[]"),
        (5, "pasif.kisi", "", 0, "TeamMember", 0, "ORNEK", 1, "pin", "totp", "[]"),
        (6, "", "Kullanici Adsiz", 0, "TeamMember", 1, "", 0, "", "", "[]"),
    ]
    b.executemany("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?,?)", kullanicilar)
    b.executemany(
        "INSERT INTO sistem_loglari (kullanici_adi, eylem, olusturuldu) VALUES (?,?,?)",
        [
            ("ornek.tam", "giris", "2026-09-01 10:00:00"),
            ("ORNEK.TAM", "giris", "2026-10-05 08:00:00"),
            ("ornek.tam", "cikis", "2026-10-06 09:00:00"),
            ("ornek.yerel", "cikis", "2026-10-06 09:00:00"),
        ],
    )
    cacti = json.dumps(["http://cacti.ornek.invalid/a", "javascript:alert(1)", "http://cacti.ornek.invalid/a", "http://cacti.ornek.invalid/b c"])
    musteriler = [
        # id, ad, sorumlu, ust, no, segment, sektor, puan, env, ft, tam_ft, alarm, sikayet, talep, a_k, s_k, t_k, rapor, cacti, pin
        (1, "Ornek Holding A.S.", 2, None, "10000001", "Strategic Account", "Finans", 77.5, 12, "1.234,00 ₺", "0,00 ₺", 5, 2, 1, 3, 1, 0, 4, cacti, '{"ncst": "NC-1"}'),
        (2, "Ornek Istirak Ltd.", None, 1, "", "", "", 40.0, 0, "0,00 ₺", "0,00 ₺", 0, 0, 0, 0, 0, 0, 0, None, '{"ayri_rapor": true, "final_dahil": true}'),
        (3, "Ornek Torun Ltd.", None, 2, "", "", "", None, 0, "", "", 0, 0, 0, 0, 0, 0, 0, "bozuk json", None),
        (4, "  ORNEK   holding a.s. ", 3, None, "", "", "", None, 0, "", "", 0, 0, 0, 0, 0, 0, 0, None, None),
        (5, "Mevcut Panel Musterisi", 4, None, "10000005", "Wholesale", "Eski Sektor", None, 3, "", "", 0, 0, 0, 0, 0, 0, 0, None, None),
        (6, "Segmentsiz Ornek", 99, None, "", "Bilinmeyen Seg", "", None, 0, "", "", 0, 0, 0, 0, 0, 0, 0, None, None),
        (7, "", 2, None, "", "", "", None, 0, "", "", 0, 0, 0, 0, 0, 0, 0, None, None),
    ]  # fmt: skip
    b.executemany("INSERT INTO customers VALUES (" + ",".join("?" * 20) + ")", musteriler)
    temas = [
        (1, "Ornek Holding A.S.", "Satis Ornek", None, "Tac Ornek", "0 555 000 00 00", None, None, None, None, None, None, None, "Not satiri\nikinci"),
        (2, "ORNEK HOLDING A.S.", "Ikinci Kayit", None, None, None, None, None, None, None, None, None, None, None),
        (3, "Tanimsiz Unvan A.S.", "Kimse", None, None, None, None, None, None, None, None, None, None, None),
        (4, "Mevcut Panel Musterisi", "Eskiden Gelen", None, "Tac Mevcut", None, None, None, None, None, None, None, None, None),
    ]  # fmt: skip
    b.executemany("INSERT INTO destech_contacts VALUES (" + ",".join("?" * 14) + ")", temas)
    b.commit()
    b.close()

    h = sqlite3.connect(klasor / "ham_veri.db")
    h.executescript(
        """
        CREATE TABLE reportdb_tampon (musteri_no TEXT, unvan TEXT, aktif INTEGER, biletli_aktif INTEGER, kapanan INTEGER, biletli_kapanan INTEGER,
                                      en_eski TEXT, son_kapanis TEXT);
        CREATE TABLE reportdb_durum (id INTEGER PRIMARY KEY, son_basari TEXT, veri_zamani TEXT);
        """
    )
    h.executemany(
        "INSERT INTO reportdb_tampon VALUES (?,?,?,?,?,?,?,?)",
        [
            ("10000001", "ORNEK HOLDING", 9, 9, 1, 1, "2026-02-01 10:00:00", "2026-10-01 10:00:00"),  # kartin numarasi: radarda cikmaz
            ("30000003", "RADAR ORNEK A.S.", 7, 4, 3, 1, "2026-03-01 10:00:00", "2026-10-02 10:00:00"),
            ("30000004", "BASKA ORNEK", 2, 0, 0, 0, "2026-04-01 10:00:00", None),
            ("30000005", "SIFIR ORNEK", 0, 0, 0, 0, None, None),
        ],
    )
    h.execute("INSERT INTO reportdb_durum VALUES (1, '2026-10-06 12:30:00', '2026-10-06 12:30:00')")
    h.commit()
    h.close()
    return klasor


def _mevcut_kayitlar() -> None:
    """Yeni panelde onceden elle girilmis veri: aktarim bunu ezmemeli."""
    with Session(engine()) as db:
        db.add(AppUser(username="mevcut.kisi", display_name="Mevcut Kisi", role="TeamMngr", is_admin=False, active=True))
        musteri = Customer(external_key="k-mevcut", name="Mevcut Panel Musterisi", segment="MA", sector="Elle")
        db.add(musteri)
        db.flush()
        db.add(CustomerTeam(customer_id=musteri.id, sales_manager="Elle Girilen"))
        db.commit()


def _kos(capsys: pytest.CaptureFixture[str], *arg: str) -> tuple[int, str]:
    kod = eski_aktar.main(list(arg))
    return kod, capsys.readouterr().out


@musteri_alani.tum_alanlarda  # WHOLESALE eski musteri Toptan alanina gecer; sayim tum modullerde
def _say(model) -> int:
    with Session(engine()) as db:
        return db.scalar(select(func.count()).select_from(model)) or 0


def test_kuru_deneme_hicbir_sey_yazmaz(hedef, capsys):
    eski = _eski_panel(hedef / "eski")
    _mevcut_kayitlar()
    kod, cikti = _kos(capsys, "--kaynak", str(eski))
    assert kod == 0 and "KURU DENEME" in cikti and "hicbir sey yazilmadi" in cikti
    assert _say(AppUser) == 1 and _say(Customer) == 1 and _say(CustomerTeam) == 1
    assert _say(IngestBatch) == 0 and _say(AuditEvent) == 0 and _say(AffiliateFinalFlag) == 0
    assert not (hedef / "yedek").exists()  # kuru denemede yedek de alinmaz
    with Session(engine()) as db:
        assert db.scalars(select(AppUser.display_name)).all() == ["Mevcut Kisi"]  # mevcutlara kuru denemede de dokunulmaz
    assert "tampon: satir=4" not in cikti and "Tampon: satir=4, yazilacak=1" in cikti


def test_cikti_yalniz_sayi_icerir(hedef, capsys):
    eski = _eski_panel(hedef / "eski")
    _, cikti = _kos(capsys, "--kaynak", str(eski), "--uygula")
    govde = "\n".join(s for s in cikti.splitlines() if not s.startswith(("UYGULAMA", "  yedek:")))  # yollar hedef klasorden gelir
    for yasak in ("Ornek", "ornek", "ORNEK", "Holding", "10000001", "30000003", "Satis", "cacti"):
        assert yasak not in govde


def test_uygulama_kullanicilar(hedef, capsys):
    eski = _eski_panel(hedef / "eski")
    _mevcut_kayitlar()
    kod, cikti = _kos(capsys, "--kaynak", str(eski), "--uygula")
    assert kod == 0 and "Bitti." in cikti
    with Session(engine()) as db:
        k = {u.username: u for u in db.scalars(select(AppUser))}
    assert set(k) == {"ornek.admin", "ornek.tam", "ornek.yerel", "mevcut.kisi", "pasif.kisi"}  # kullanici adi bos olan atlanir
    assert (k["ornek.admin"].is_admin, k["ornek.admin"].role, k["ornek.admin"].display_name) == (True, "admin", "Ornek Yonetici")
    assert (k["ornek.tam"].role, k["ornek.tam"].is_admin, k["ornek.tam"].is_ad_user, k["ornek.tam"].ad_domain) == ("TeamMember", False, True, "ornek")
    assert k["ornek.tam"].last_login_at.replace(tzinfo=UTC) == datetime(2026, 10, 5, 8, 0, tzinfo=UTC)  # en son 'giris'; 'cikis' sayilmaz
    assert (k["ornek.yerel"].role, k["ornek.yerel"].is_ad_user, k["ornek.yerel"].ad_domain) == ("TeamMngr", False, "")
    assert k["pasif.kisi"].active is False and k["pasif.kisi"].display_name == "Pasif Kisi"  # eski ad bos: kullanici adindan uretilir
    assert all(u.password_hash is None for u in k.values())  # parola / PIN / TOTP tasinmaz
    # panelde zaten olan kisi: rol ve aktiflik sabit, uretilmis ad gercek adla degisir
    assert (k["mevcut.kisi"].role, k["mevcut.kisi"].display_name) == ("TeamMngr", "Mevcut Kisi Gercek")
    assert "kullanici: yeni=4" not in cikti and "Kullanici: yeni=4, guncellenen=1, atlanan=1, ad_degil=1" in cikti


def test_uygulama_musteriler(hedef, capsys):
    eski = _eski_panel(hedef / "eski")
    _mevcut_kayitlar()
    _, cikti = _kos(capsys, "--kaynak", str(eski), "--uygula")
    with Session(engine()) as db:
        m = {c.name: c for c in db.scalars(select(Customer))}
        kisi = {u.id: u.username for u in db.scalars(select(AppUser))}
        # ad kuru: bosluk / buyuk-kucuk harf farkli ikinci kayit birlestirilir, 4 yeni + mevcut = 5 musteri (bos adli atlanir)
        assert set(m) == {"Ornek Holding A.S.", "Ornek Istirak Ltd.", "Ornek Torun Ltd.", "Mevcut Panel Musterisi", "Segmentsiz Ornek"}
        h, ist, torun, mev, seg = (m[a] for a in ("Ornek Holding A.S.", "Ornek Istirak Ltd.", "Ornek Torun Ltd.", "Mevcut Panel Musterisi", "Segmentsiz Ornek"))
        assert kisi[h.owner_id] == "ornek.tam" and h.parent_id is None
        assert (h.segment, h.customer_no, h.sector, h.score, h.inventory_count, h.ncst) == ("SA", "10000001", "Finans", 77.5, 12, "NC-1")
        assert (h.alarm_count, h.complaint_count, h.request_count, h.alarm_closed_count, h.complaint_closed_count, h.report_count) == (5, 2, 1, 3, 1, 4)
        assert h.ft_volume == "1.234,00 ₺" and h.tam_ft == "0,00 ₺"
        assert h.cacti_urls == ["http://cacti.ornek.invalid/a"]  # javascript:, bosluklu ve tekrar eden adresler elenir
        # istirak: ust musteriye baglanir, sorumlu ve segment ustten gelir, ayri rapor + final dahil bayragi tasinir, puan yalniz catida
        assert (ist.parent_id, ist.owner_id, ist.segment, ist.separate_report, ist.score) == (h.id, h.owner_id, "SA", True, None)
        flag = db.get(AffiliateFinalFlag, ist.id)
        assert flag is not None and flag.included is True
        # istiragin istiraki en ustteki catiya duzlestirilir (yeni panelde tek seviye)
        assert torun.parent_id == h.id and torun.separate_report is False and db.get(AffiliateFinalFlag, torun.id) is None
        # mevcut musteri: elle girilen korunur, yalniz bos alan dolar; sorumlu eski sorumludan (mevcut.kisi) gelir
        assert (mev.segment, mev.sector, mev.customer_no, mev.inventory_count, kisi[mev.owner_id]) == ("MA", "Elle", "10000005", 3, "mevcut.kisi")
        assert seg.segment == "" and seg.owner_id is None  # tanimsiz segment ve eslesmeyen sorumlu bos kalir
    assert "Musteri: yeni=4, guncellenen=1, ad_cakismasi=1, istirak=2, final_dahil=1, sorumlusuz=" in cikti and "segment_tanimsiz=1" in cikti and "atlanan=1" in cikti


def test_uygulama_iletisim_yalniz_bos_alanlar(hedef, capsys):
    eski = _eski_panel(hedef / "eski")
    _mevcut_kayitlar()
    _, cikti = _kos(capsys, "--kaynak", str(eski), "--uygula")
    with Session(engine()) as db:
        ekip = {c.name: db.get(CustomerTeam, c.id) for c in db.scalars(select(Customer))}
    h = ekip["Ornek Holding A.S."]
    assert (h.sales_manager, h.tac_name, h.tac_gsm, h.mobil_kmt_detail) == ("Satis Ornek", "Tac Ornek", "0 555 000 00 00", "Not satiri\nikinci")  # ikinci kayit yok sayilir
    mev = ekip["Mevcut Panel Musterisi"]
    assert (mev.sales_manager, mev.tac_name) == ("Elle Girilen", "Tac Mevcut")  # elle girilen ezilmez, bos olan dolar
    assert ekip["Ornek Istirak Ltd."] is None
    assert "Iletisim: yeni=1, guncellenen=1, tekrar=1, eslesmeyen=1" in cikti


def test_uygulama_tampon_ve_radar(hedef, capsys):
    eski = _eski_panel(hedef / "eski")
    _, cikti = _kos(capsys, "--kaynak", str(eski), "--uygula")
    assert "Tampon: satir=4, alindi=1" in cikti
    with Session(engine()) as db:
        parti = db.scalars(select(IngestBatch).where(IngestBatch.source_key == reportdb.KAYNAK)).one()
        assert (parti.status, parti.row_count, parti.columns) == ("ready", 4, list(reportdb.BASLIKLAR))
        # veri gercek yasiyla gorunur: 12:30 yerel (UTC+3) = 09:30 UTC
        assert parti.received_at.replace(tzinfo=UTC) == datetime(2026, 10, 6, 9, 30, tzinfo=UTC)
        radar_sonuc = radar.adaylar(db)
        # kartlara yazilmaz: dagitim kurallari kapali, alarm sayilari degismez
        assert db.scalars(select(Customer.alarm_count).where(Customer.name == "Ornek Holding A.S.")).one() == 5
    assert radar_sonuc["var"] is True and radar_sonuc["veri_zamani"] == "2026-10-06 12:30:00"
    # 10000001 kartin numarasi (cikmaz), sifir kayit cikmaz; toplam azalan
    assert [(s["musteri_no"], s["toplam"]) for s in radar_sonuc["satirlar"]] == [("30000003", 10), ("30000004", 2)]


def test_tekrar_calistirma_cogaltmaz(hedef, capsys):
    eski = _eski_panel(hedef / "eski")
    _mevcut_kayitlar()
    _kos(capsys, "--kaynak", str(eski), "--uygula")
    onceki = [_say(m) for m in (AppUser, Customer, CustomerTeam, AffiliateFinalFlag, IngestBatch)]
    kod, cikti = _kos(capsys, "--kaynak", str(eski), "--uygula")
    assert kod == 0
    assert [_say(m) for m in (AppUser, Customer, CustomerTeam, AffiliateFinalFlag, IngestBatch)] == onceki
    assert "Kullanici: ayni=5, atlanan=1" in cikti and "Musteri: ayni=5, ad_cakismasi=1" in cikti and "Iletisim: ayni=2" in cikti
    assert "Tampon: satir=4, zaten_alinmis=1" in cikti and "yeni=" not in cikti
    assert _say(AuditEvent) == 2  # her uygulama bir denetim kaydi birakir


def test_yedek_ve_denetim_kaydi(hedef, capsys):
    eski = _eski_panel(hedef / "eski")
    _kos(capsys, "--kaynak", str(eski), "--uygula")
    yedekler = list((hedef / "yedek").glob("yeni-eski_aktar-*.db"))
    assert len(yedekler) == 1
    # yedek tutarli bir SQLite: aktarimdan ONCEKI (bos) hali
    k = sqlite3.connect(yedekler[0])
    assert k.execute("SELECT COUNT(*) FROM customer").fetchone()[0] == 0
    k.close()
    with Session(engine()) as db:
        olay = db.scalars(select(AuditEvent)).one()
        assert (olay.actor, olay.action) == ("eski_aktar", "eski_panel.aktar") and "musteri_yeni" in olay.detail and "Ornek" not in olay.detail
    kod, _ = _kos(capsys, "--kaynak", str(eski), "--uygula", "--yedek-yok")
    assert kod == 0 and len(list((hedef / "yedek").glob("yeni-eski_aktar-*.db"))) == 1  # --yedek-yok yeni yedek almaz


def test_yalniz_adimlar_ve_ad_hepsi(hedef, capsys):
    eski = _eski_panel(hedef / "eski")
    kod, _ = _kos(capsys, "--kaynak", str(eski), "--uygula", "--yalniz", "kullanici", "--ad-hepsi", "--yedek-yok")
    assert kod == 0
    assert _say(Customer) == 0 and _say(IngestBatch) == 0
    with Session(engine()) as db:
        assert all(u.is_ad_user for u in db.scalars(select(AppUser))) and _say(AppUser) == 5
    # yalniz musteri adimi: kullanici eslemesi olmadan sorumlu atanmaz ama musteri gelir
    kod, _ = _kos(capsys, "--kaynak", str(eski), "--uygula", "--yalniz", "musteri", "--yedek-yok")
    assert kod == 0 and _say(Customer) == 5


def test_klasor_ya_da_dosya_yolu_ve_hatalar(hedef, capsys):
    eski = _eski_panel(hedef / "eski")
    kod, _ = _kos(capsys, "--kaynak", str(eski / "panel.db"), "--yalniz", "tampon")
    assert kod == 0
    kod, cikti = _kos(capsys, "--kaynak", str(hedef / "yok"))
    assert kod == 1 and "panel.db bulunamadi" in cikti
    kod, cikti = _kos(capsys, "--kaynak", str(eski), "--yalniz", "rapor")
    assert kod == 2 and "--yalniz degerleri" in cikti
    assert eski_aktar.main([]) == 2  # --kaynak zorunlu


def test_eski_dosyalar_degismez(hedef, capsys):
    eski = _eski_panel(hedef / "eski")
    oncesi = {a: (eski / a).read_bytes() for a in ("panel.db", "ham_veri.db")}
    _kos(capsys, "--kaynak", str(eski), "--uygula")
    assert {a: (eski / a).read_bytes() for a in ("panel.db", "ham_veri.db")} == oncesi
    assert sorted(p.name for p in eski.iterdir()) == ["ham_veri.db", "panel.db"]  # yan dosya (wal / kopya) birakmaz


def test_tampon_yoksa_atlanir(hedef, capsys):
    eski = _eski_panel(hedef / "eski")
    (eski / "ham_veri.db").unlink()
    kod, cikti = _kos(capsys, "--kaynak", str(eski), "--uygula", "--yalniz", "tampon")
    assert kod == 0 and "ham_veri.db bulunamadi" in cikti and _say(IngestBatch) == 0
