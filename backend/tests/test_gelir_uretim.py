"""Gelir Faydasi Saglanan Isler: CRUD, yetki matrisi, kisi kurali, suzgec + ozet, Excel ice/disa aktarim, sunum ozeti, sema ve silme baglari.

Test verisi uydurmadir (Alfa/Beta/Gama, Ali/Veli gibi adlar); gercek musteri ya da kisi verisi yoktur.
"""

from __future__ import annotations

import io
from datetime import UTC, date, datetime

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import catalog, kullanicilar
from app.db import engine
from app.gelir_uretim import excel, ice_al, servis
from app.gelir_uretim.models import RevenueBenefit, RevenueBenefitPerson
from app.models import TABLE_OWNER, AppUser, AuditEvent
from app.session import Principal
from app.takvim.servis import TakvimHata
from app.yonetim.kalici_yazici import yazici
from tests.conftest import login_ok
from tests.test_musteri import _cikis

URL = "/api/v1/gelir-uretim"
SIMDI = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


# --- yardimcilar -------------------------------------------------------------------------------------------------------
def _giris(client, monkeypatch, kullanici: str, rol: str) -> dict[str, str]:
    client.post("/api/v1/session/logout")
    monkeypatch.setenv("TAMLIFE_LOCAL_USER", kullanici)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", rol)
    r = client.post("/api/v1/session/login", json={"username": kullanici, "password": "test-parola-1"})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": client.cookies.get("tamlife_csrf") or ""}


def _kisi(kullanici: str, ad: str, rol: str = "TeamMember", aktif: bool = True, admin: bool = False) -> int:
    with Session(engine()) as db:
        satir = AppUser(username=kullanici, display_name=ad, role=rol, is_admin=admin, active=aktif)
        db.add(satir)
        db.commit()
        return satir.id


# Yeni giriste tum zorunlu alanlar dolu olmali (servis.ZORUNLU); testler yalniz konu ettikleri alanlari degistirir.
ZORUNLU_VARSAYILAN = {
    "status_note": "Sürüyor", "roadmap": "Faz 1", "description": "Açıklama", "customers": "Alfa", "revenue_amount": 0, "year_revenue": 0,
    "hours_per_month": 0, "hours_per_year": 0, "extra_note": "-", "start_date": "2026-01-01", "end_date": "2026-12-31", "other_people": "Dış Kişi",
}  # fmt: skip


def _govde(**alanlar) -> dict:
    temel = {"kind": "proje", "benefit_type": "gelir", "title": "Alfa devre yedekleme", "status": "devam", **ZORUNLU_VARSAYILAN}
    return {**temel, **alanlar}


def _ekle(client, hdr, **alanlar) -> int:
    r = client.post(URL, json=_govde(**alanlar), headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _eski(client, hdr, **alanlar) -> int:
    """Zorunlu alan kuralindan onceki (ya da Excel'den ice alinan) onayli kayit: yalniz verilen alanlar dolu (ozet/sunum testleri)."""
    kisiler = alanlar.pop("person_ids", [])
    girdi = {"kind": "proje", "benefit_type": "gelir", "title": "Alfa devre yedekleme", "status": "devam", **alanlar}
    for ad in ("start_date", "end_date"):
        if isinstance(girdi.get(ad), str):
            girdi[ad] = date.fromisoformat(girdi[ad])
    with Session(engine()) as db:
        kimlik = servis.ekle(db, "admin", servis.temizle(girdi), kisiler).id
        db.commit()
        return kimlik


def _liste(client, **sorgu) -> dict:
    r = client.get(URL, params=sorgu)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _say(model=RevenueBenefit) -> int:
    with Session(engine()) as db:
        return db.scalar(select(func.count()).select_from(model)) or 0


def _denetim() -> list[tuple[str, str]]:
    yazici.bosalt(zorla=True)
    with Session(engine()) as db:
        return [(o.action, o.detail) for o in db.scalars(select(AuditEvent).order_by(AuditEvent.id)) if o.action.startswith("gelir_uretim.")]


BASLIKLAR = [
    "İlgili TAM", "İşin özeti", "Güncel durum", "Detaylı açıklaması", "Hangi müşteri/müşterileri etkilediği", "Aylık gelir faydası (TL/ay)",
    "Aylık verimlilik faydası (saat efor kazancı/ay)", "Ek açıklamalar", "Proje/çalışma başlangıç tarihi", "Proje/çalışma bitiş tarihi",
]  # fmt: skip
BOLUM = "Tam Gelir Artırıcı Aldığımız İnsiyatifler"
KULLANICI_BASLIKLARI = [
    "İlgili TAM", "İşin özeti", "Güncel durum", "Yol Haritası", "Detaylı açıklaması", "Hangi müşteri/müşterileri etkilediği", "Aylık gelir faydası (TL/ay)",
    "Yıllık gelir faydası (TL/12 ay)", "Aylık verimlilik faydası (saat efor kazancı/ay)", "Yıllık verimlilik faydası (saat efor kazancı/12 ay)",
    "Ek açıklamalar", "Proje/çalışma başlangıç tarihi", "Proje/çalışma bitiş tarihi",
]  # fmt: skip


def _xlsx(satirlar: list[list], basliklar: list | None = None, sayfa: str = "Liste") -> bytes:
    kitap = Workbook()
    ws = kitap.active
    ws.title = sayfa
    ws.append(BASLIKLAR if basliklar is None else basliklar)
    for s in satirlar:
        ws.append(s)
    cikti = io.BytesIO()
    kitap.save(cikti)
    return cikti.getvalue()


def _ornek_dosya() -> bytes:
    """Alfa/Beta/Gama uydurma verisi: iki proje, bos satirlar, bolum satiri, uc inisiyatif (biri dosyada tekrar)."""
    return _xlsx(
        [
            ["Ali Örnek, Veli Deneme", "Alfa yedek devre projesi", "Devam ediyor.//7.10.2026", "Alfa için yedek devre satışı.", "Tüm kurumsal müşteriler",
             "88,2 KTL/ay (son ölçüm) -düzenli artıyor.", "Çalışma sürüyor", "-", datetime(2026, 4, 1), "devam ediyor", "2026 yılı içi gelir: 1 MTL"],
            ["ALİ ÖRNEK & Zeynep Dışarıda", "Beta otomasyon", "Her ayın ilk günü güncelleniyor", "Rapor otomasyonu", "Beta Ltd.", "yok", "36 Saat / Ay",
             "Diğer irtibatlar: Kişi X", " 15.05.2026", "Ağustos 2026"],
            [],
            [],
            [BOLUM],
            ["Veli Deneme", "Gama hız artışı", "Tamamlandı. //18.8.2026", "Hız artışı", "Gama", "1250,75 $ / ay", None, None, datetime(2026, 3, 1), datetime(2026, 6, 1)],
            ["Veli Deneme", "Gama hız artışı", "Tamamlandı.", "aynı başlık", "Gama", "5K TL / ay", None, None, datetime(2026, 3, 2), datetime(2026, 6, 2)],
            ["Mehmet Yönetici", "Delta tek seferlik satış", "Tamamlandı", "", "Delta", "900 eurox4 adet (tek seferlik)", "yok", None, datetime(2026, 9, 24), datetime(2026, 9, 24)],
        ]
    )


@pytest.fixture
def ekip(client):
    """Personel: Ali Örnek, Veli Deneme (etkin TeamMember); personel olmayanlar: pasif, yonetici, admin."""
    return {
        "ali": _kisi("ali", "Ali Örnek"),
        "veli": _kisi("veli", "Veli Deneme"),
        "pasif": _kisi("pasif", "Pasif Kişi", aktif=False),
        "mudur": _kisi("mudur", "Mehmet Yönetici", rol="TeamMngr"),
        "yonetici_admin": _kisi("yadmin", "Ayşe Admin", rol="admin", admin=True),
    }


# --- CRUD + denetim --------------------------------------------------------------------------------------------------
def test_admin_ekler_gunceller_siler_ve_denetler(client, ekip):
    hdr = login_ok(client)
    kimlik = _ekle(
        client, hdr, title="Alfa yedek devre", customers="Alfa A.Ş.", revenue_amount=88200, revenue_currency="TRY", revenue_period="ay",
        start_date="2026-04-01", person_ids=[ekip["ali"], ekip["veli"], ekip["ali"]], other_people="Dış Kişi",
    )  # fmt: skip
    veri = _liste(client)
    assert veri["yazabilir"] is True and veri["ozet"]["is_sayisi"] == 1 and veri["ozet"]["aylik_gelir"] == {"TRY": 88200.0}
    kayit = veri["items"][0]
    assert kayit["id"] == kimlik and kayit["title"] == "Alfa yedek devre" and kayit["end_date"] == "2026-12-31"
    assert kayit["approval"] == "onayli" and kayit["eksik"] == [] and kayit["roadmap"] == "Faz 1"  # admin girisi dogrudan onayli
    assert [k["name"] for k in kayit["people"]] == ["Ali Örnek", "Veli Deneme"] and kayit["other_people"] == "Dış Kişi"
    assert kayit["created_by"] == "admin" and kayit["updated_at"]
    assert [p["ad"] for p in veri["secenekler"]["personel"]] == ["Ali Örnek", "Veli Deneme"]  # pasif, yonetici ve admin listede yok

    # guncelleme: degisen ALAN ADLARI doner; degisiklik yoksa bos
    yeni = _govde(title="Alfa yedek devre", customers="Alfa A.Ş.", revenue_amount=88200, start_date="2026-04-01", other_people="Dış Kişi", status="tamamlandi", person_ids=[ekip["veli"]])
    r = client.put(f"{URL}/{kimlik}", json=yeni, headers=hdr)
    assert r.status_code == 200 and set(r.json()["data"]["degisen"]) == {"status", "person_ids"}
    assert [k["name"] for k in _liste(client)["items"][0]["people"]] == ["Veli Deneme"]
    assert client.put(f"{URL}/{kimlik}", json=yeni, headers=hdr).json()["data"]["degisen"] == []

    assert client.delete(f"{URL}/{kimlik}", headers=hdr).status_code == 200
    assert _liste(client)["items"] == [] and _say() == 0 and _say(RevenueBenefitPerson) == 0
    assert client.put(f"{URL}/{kimlik}", json=yeni, headers=hdr).status_code == 404
    assert client.delete(f"{URL}/{kimlik}", headers=hdr).status_code == 404

    # denetim: alan adlari var, degerler (baslik, tutar) yok
    olaylar = _denetim()
    assert [o[0] for o in olaylar] == ["gelir_uretim.ekle", "gelir_uretim.guncelle", "gelir_uretim.sil"]
    assert olaylar[1][1] == f"is={kimlik} alanlar=status,person_ids"
    assert not any("Alfa" in d or "88200" in d for _, d in olaylar)


def test_yazilmayan_degisiklik_guncelleme_izi_birakmaz(client, ekip):
    hdr = login_ok(client)
    kimlik = _ekle(client, hdr, title="Alfa")
    with Session(engine()) as db:
        onceki = db.get(RevenueBenefit, kimlik).updated_at
    client.put(f"{URL}/{kimlik}", json=_govde(title="Alfa"), headers=hdr)
    with Session(engine()) as db:
        assert db.get(RevenueBenefit, kimlik).updated_at == onceki
    assert [a for a, _ in _denetim()] == ["gelir_uretim.ekle"]


# --- yetki ---------------------------------------------------------------------------------------------------------------
def test_yetki_matrisi_personel_girer_onayli_kaydi_degistiremez(client, monkeypatch, ekip):
    """2026-10-15: modulu goren herkes yeni is girer (onaya duser); onayli kaydi duzenleme/silme ve ice aktarma sahibin/admin'indir."""
    hdr = login_ok(client)
    kimlik = _ekle(client, hdr, title="Alfa")
    dosya = _ornek_dosya()
    for kullanici, rol in (("uye", "TeamMember"), ("yon", "TeamMngr")):
        h = _giris(client, monkeypatch, kullanici, rol)
        veri = _liste(client)
        assert veri["yazabilir"] is False and veri["onay"]["yonetebilir"] is False and len(veri["items"]) == 1
        assert client.get(f"{URL}/excel").status_code == 200
        yeni = client.post(URL, json=_govde(title=f"Yeni {kullanici}"), headers=h)
        assert yeni.status_code == 200 and yeni.json()["data"]["approval"] == "bekliyor"
        for yanit in (
            client.put(f"{URL}/{kimlik}", json=_govde(title="Degisti"), headers=h),
            client.delete(f"{URL}/{kimlik}", headers=h),
            client.post(f"{URL}/{kimlik}/onay", json={"karar": "geri_al"}, headers=h),
            client.post(f"{URL}/ice-al/onizleme", content=dosya, headers=h),
            client.post(f"{URL}/ice-al/uygula", content=dosya, headers=h),
            client.put(f"{URL}/sahip", json={"user_id": ekip["ali"]}, headers=h),
        ):
            assert yanit.status_code == 403, (kullanici, yanit.text)
    assert _say() == 3  # onayli kayit + iki bekleyen giris
    with Session(engine()) as db:
        assert db.get(RevenueBenefit, kimlik).title == "Alfa"


def test_oturumsuz_istek_reddedilir(client):
    assert client.get(URL).status_code == 401
    assert client.get(f"{URL}/excel").status_code == 401
    assert client.post(URL, json=_govde()).status_code in (401, 403)


def test_rol_kaydi_modulu_gizler_veya_acar(client, monkeypatch, ekip):
    """Admin rol modullerinden gelir_uretim'i cikarirsa 403, eklerse 200."""
    hdr = login_ok(client)
    _ekle(client, hdr)
    # gelir_uretim listede yok:
    assert client.put("/api/v1/roller/TeamMember", json={"modules": ["musteri", "talep"], "landing": "musteri"}, headers=hdr).status_code == 200
    _cikis(client, hdr)
    _giris(client, monkeypatch, "uye", "TeamMember")
    for yol in (URL, f"{URL}/excel"):
        assert client.get(yol).status_code == 403
    assert "gelir_uretim" not in {i["id"] for i in client.get("/api/v1/session/me").json()["data"]["navigation"]}
    # admin gelir_uretim'i geri verirse:
    _cikis(client, {"X-CSRF-Token": client.cookies.get("tamlife_csrf")})
    hdr = _giris(client, monkeypatch, "admin", "admin")
    assert client.put("/api/v1/roller/TeamMember", json={"modules": ["musteri", "talep", "gelir_uretim"], "landing": "ozet"}, headers=hdr).status_code == 200
    _cikis(client, hdr)
    _giris(client, monkeypatch, "uye", "TeamMember")
    for yol in (URL, f"{URL}/excel"):
        assert client.get(yol).status_code == 200
    assert "gelir_uretim" in {i["id"] for i in client.get("/api/v1/session/me").json()["data"]["navigation"]}


def test_katalogda_hazir_ve_tablo_sahipligi():
    modul = catalog.get("gelir_uretim")
    assert modul.ready is True and modul.table == "revenue_benefit" and modul.title == "Gelir Faydası Sağlanan İşler"
    assert TABLE_OWNER["revenue_benefit"] == "gelir_uretim" and TABLE_OWNER["revenue_benefit_person"] == "gelir_uretim"
    assert "income_production" not in TABLE_OWNER


# --- kisi kurali ---------------------------------------------------------------------------------------------------------
def test_kisi_yalniz_etkin_tam_personeli(client, ekip):
    hdr = login_ok(client)
    for yanlis in (ekip["pasif"], ekip["mudur"], ekip["yonetici_admin"], 999_999):
        r = client.post(URL, json=_govde(person_ids=[ekip["ali"], yanlis]), headers=hdr)
        assert r.status_code == 400, (yanlis, r.text)
    assert _say() == 0
    kimlik = _ekle(client, hdr, person_ids=[ekip["ali"]])
    r = client.put(f"{URL}/{kimlik}", json=_govde(person_ids=[ekip["ali"], ekip["mudur"]]), headers=hdr)
    assert r.status_code == 400 and "TAM" in r.json()["detail"]
    assert [k["id"] for k in _liste(client)["items"][0]["people"]] == [ekip["ali"]]  # reddedilen guncelleme hicbir sey degistirmedi


def test_sonradan_pasif_olan_bagli_kisi_guncellemeyi_engellemez(client, ekip):
    hdr = login_ok(client)
    kimlik = _ekle(client, hdr, person_ids=[ekip["ali"], ekip["veli"]])
    with Session(engine()) as db:
        db.get(AppUser, ekip["veli"]).active = False
        db.commit()
    # zaten bagli pasif kisi korunabilir; yeni bir pasif kisi eklenemez
    r = client.put(f"{URL}/{kimlik}", json=_govde(status="tamamlandi", person_ids=[ekip["ali"], ekip["veli"]]), headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["degisen"] == ["status"]
    assert client.put(f"{URL}/{kimlik}", json=_govde(person_ids=[ekip["pasif"]]), headers=hdr).status_code == 400
    # secenekler listesinde pasif kisi yok, ama isin uzerindeki ad gorunur (gecmis)
    veri = _liste(client)
    assert [p["ad"] for p in veri["secenekler"]["personel"]] == ["Ali Örnek"]
    assert {k["name"] for k in veri["items"][0]["people"]} == {"Ali Örnek", "Veli Deneme"}


def test_baglanti_kisi_silinince_kalkar(client, ekip):
    hdr = login_ok(client)
    kimlik = _ekle(client, hdr, person_ids=[ekip["ali"], ekip["veli"]])
    with Session(engine()) as db:
        ozet = kullanicilar.sil(db, Principal("admin", "admin", True), ekip["ali"])
        db.commit()
    assert ozet["silinen"] == 1
    veri = _liste(client)
    assert veri["items"][0]["id"] == kimlik and [k["name"] for k in veri["items"][0]["people"]] == ["Veli Deneme"]
    assert _say(RevenueBenefitPerson) == 1


# --- dogrulama -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "alanlar,kod",
    [
        ({"title": ""}, 422),
        ({"title": "x" * 301}, 422),
        ({"title": "   "}, 400),  # bosluk Pydantic'i gecer, servis reddeder
        ({"status": "bitti"}, 422),
        ({"kind": "baska"}, 422),
        ({"benefit_type": "kar"}, 422),
        ({"revenue_currency": "GBP"}, 422),
        ({"revenue_period": "hafta"}, 422),
        ({"revenue_amount": -1}, 422),
        ({"year_revenue": -0.5}, 422),
        ({"hours_per_month": -2}, 422),
        ({"revenue_amount": 1e20}, 422),
        ({"description": "d" * 8001}, 422),
        ({"status_note": "d" * 4001}, 422),
        ({"extra_note": "d" * 4001}, 422),
        ({"customers": "d" * 501}, 422),
        ({"other_people": "d" * 301}, 422),
        ({"start_date": "2026-13-01"}, 422),
        ({"start_date": "2026-05-01", "end_date": "2026-04-30"}, 400),
        ({"person_ids": [0]}, 422),
        ({"person_ids": ["a"]}, 422),
    ],
)
def test_gecersiz_girdi_reddedilir(client, alanlar, kod):
    hdr = login_ok(client)
    assert client.post(URL, json=_govde(**alanlar), headers=hdr).status_code == kod
    assert _say() == 0


def test_sinir_degerleri_kabul_edilir(client):
    hdr = login_ok(client)
    _ekle(client, hdr, title="x" * 300, description="d" * 8000, status_note="s" * 4000, extra_note="e" * 4000, customers="c" * 500, revenue_note="r" * 500,
          hours_note="h" * 500, other_people="o" * 300, revenue_amount=0, year_revenue=0, hours_per_month=0, start_date="2026-05-01", end_date="2026-05-01")  # fmt: skip
    assert _say() == 1


def test_servis_temizle_dogrudan():
    temiz = servis.temizle({"title": "  Alfa  ", "revenue_amount": 5, "start_date": datetime(2026, 1, 2, 3, 4)})
    assert temiz["title"] == "Alfa" and temiz["revenue_amount"] == 5.0 and temiz["start_date"] == date(2026, 1, 2) and temiz["status"] == "devam"
    for kotu in ({"title": "a", "revenue_amount": float("nan")}, {"title": "a", "revenue_amount": True}, {"title": "a", "revenue_amount": "5"}, {"title": "a", "start_date": "2026-01-01"}):
        with pytest.raises(servis.GelirUretimHata) as hata:
            servis.temizle(kotu)
        assert hata.value.kod == 400


# --- liste, suzgec, ozet ---------------------------------------------------------------------------------------------------
def _cesitli(client, hdr, ekip):
    _eski(client, hdr, title="Çimento hız artışı", customers="Çimsa Örnek", benefit_type="gelir", status="tamamlandi", revenue_amount=100000, revenue_period="ay",
          year_revenue=1_000_000, start_date="2026-03-01", end_date="2026-06-01", person_ids=[ekip["ali"]])  # fmt: skip
    _eski(client, hdr, title="Alfa raporlama otomasyonu", benefit_type="verimlilik", status="devam", hours_per_month=36, start_date="2026-02-15", person_ids=[ekip["veli"]])
    _eski(client, hdr, title="Beta yazılım tasarrufu", benefit_type="tasarruf", status="devam", revenue_amount=2000, revenue_currency="USD", revenue_period="ay", start_date="2025-11-01",
          end_date="2026-01-31")  # fmt: skip
    _eski(client, hdr, kind="inisiyatif", title="Gama tek seferlik satış", status="tamamlandi", revenue_amount=7500, revenue_currency="EUR", revenue_period="tek_sefer",
          start_date="2026-09-24", other_people="Dış Kişi")  # fmt: skip
    _eski(client, hdr, kind="inisiyatif", title="Delta iptal edilen", status="iptal", revenue_amount=999999, revenue_period="ay", hours_per_month=500, start_date="2026-05-01")
    _eski(client, hdr, title="Tarihsiz iş", status="baslamadi", revenue_amount=50, revenue_period="yil")


def test_liste_suzgecleri(client, ekip):
    hdr = login_ok(client)
    _cesitli(client, hdr, ekip)
    basliklar = lambda **s: [k["title"] for k in _liste(client, **s)["items"]]
    tumu = basliklar()
    assert len(tumu) == 6
    assert tumu[:4] == ["Çimento hız artışı", "Alfa raporlama otomasyonu", "Beta yazılım tasarrufu", "Tarihsiz iş"]  # projeler: yeni baslangic ustte, tarihsiz sonda
    assert set(tumu[4:]) == {"Gama tek seferlik satış", "Delta iptal edilen"} and tumu[4] == "Gama tek seferlik satış"
    assert basliklar(tur="inisiyatif") == ["Gama tek seferlik satış", "Delta iptal edilen"]
    assert basliklar(durum="tamamlandi") == ["Çimento hız artışı", "Gama tek seferlik satış"]
    assert basliklar(fayda="verimlilik") == ["Alfa raporlama otomasyonu"]
    assert basliklar(fayda="tasarruf") == ["Beta yazılım tasarrufu"]
    assert basliklar(tam=ekip["ali"]) == ["Çimento hız artışı"]
    assert basliklar(tam=ekip["veli"]) == ["Alfa raporlama otomasyonu"]
    assert basliklar(tur="proje", durum="devam") == ["Alfa raporlama otomasyonu", "Beta yazılım tasarrufu"]
    # metin aramasi: Turkce harf ve buyuk/kucuk farksiz; baslik, musteri, kisi adi (panel kisisi ve diger kisiler)
    assert basliklar(q="CIMENTO") == ["Çimento hız artışı"]
    assert basliklar(q="cimsa") == ["Çimento hız artışı"]
    assert basliklar(q="ali orn") == ["Çimento hız artışı"]
    assert basliklar(q="dis kisi") == ["Gama tek seferlik satış"]
    assert basliklar(q="bulunmaz") == []
    # yil: calisma araligi o yila degen isler; baslangici olmayan elenir; bitis bos = devam ediyor
    assert basliklar(yil=2025) == ["Beta yazılım tasarrufu"]
    assert set(basliklar(yil=2026)) == {"Çimento hız artışı", "Alfa raporlama otomasyonu", "Beta yazılım tasarrufu", "Gama tek seferlik satış", "Delta iptal edilen"}
    assert "Tarihsiz iş" not in basliklar(yil=2026) and basliklar(yil=2030) == ["Alfa raporlama otomasyonu", "Delta iptal edilen"]
    assert client.get(URL, params={"yil": 1999}).status_code == 422
    assert client.get(URL, params={"durum": "bitti"}).status_code == 422
    assert client.get(URL, params={"tam": 0}).status_code == 422


def test_ozet_toplamlari(client, ekip):
    hdr = login_ok(client)
    _cesitli(client, hdr, ekip)
    ozet = _liste(client)["ozet"]
    assert ozet["is_sayisi"] == 6 and ozet["toplam_is"] == 6
    assert ozet["durum_sayilari"] == {"baslamadi": 1, "devam": 2, "tamamlandi": 2, "iptal": 1}
    # iptal edilen is sayida gorunur, toplamlara girmez; para birimleri ayri toplanir (kur cevirisi yok)
    assert ozet["aylik_gelir"] == {"TRY": 100000.0, "USD": 2000.0}
    assert ozet["tek_seferlik_gelir"] == {"EUR": 7500.0} and ozet["yillik_gelir"] == {"TRY": 50.0}
    assert ozet["yil_ici_gelir"] == 1_000_000.0 and ozet["aylik_saat"] == 36.0
    # ozet suzulmus kumeyi ozetler; toplam_is suzulmemis sayidir
    filtreli = _liste(client, durum="devam")["ozet"]
    assert filtreli["is_sayisi"] == 2 and filtreli["toplam_is"] == 6 and filtreli["aylik_gelir"] == {"USD": 2000.0}
    bos = _liste(client, q="yok boyle bir sey")["ozet"]
    assert bos["is_sayisi"] == 0 and bos["aylik_gelir"] == {} and bos["yil_ici_gelir"] == 0 and bos["toplam_is"] == 6


# --- Excel ice aktarma ---------------------------------------------------------------------------------------------------------
def _onizle(client, hdr, veri: bytes, dosya: str = "gelir.xlsx"):
    return client.post(f"{URL}/ice-al/onizleme", params={"dosya": dosya}, content=veri, headers=hdr)


def _uygula(client, hdr, veri: bytes, dosya: str = "gelir.xlsx"):
    return client.post(f"{URL}/ice-al/uygula", params={"dosya": dosya}, content=veri, headers=hdr)


def test_onizleme_hicbir_sey_yazmaz_ve_satirlari_ayristirir(client, ekip):
    hdr = login_ok(client)
    r = _onizle(client, hdr, _ornek_dosya())
    assert r.status_code == 200, r.text
    veri = r.json()["data"]
    assert _say() == 0 and _say(RevenueBenefitPerson) == 0 and _denetim() == []  # onizleme yazmaz, denetim kaydi birakmaz
    assert veri["dosya"] == "gelir.xlsx" and veri["sayfa"] == "Liste" and veri["baslik_satiri"] == 1
    assert veri["plan"] == {"toplam": 5, "yeni": 4, "var": 0, "tekrar": 1, "hatali": 0}
    ilk, ikinci, gama, tekrar, delta = veri["satirlar"]
    assert ilk["satir"] == 2 and ilk["durum"] == "yeni" and ilk["kind"] == "proje" and ilk["status"] == "devam"
    assert ilk["people"] == ["Ali Örnek", "Veli Deneme"] and ilk["other_people"] == ""
    assert (ilk["revenue_amount"], ilk["revenue_currency"], ilk["revenue_period"]) == (88200.0, "TRY", "ay")
    assert ilk["revenue_note"] == "(son ölçüm) -düzenli artıyor." and ilk["year_revenue"] == 1_000_000.0 and ilk["start_date"] == "2026-04-01" and ilk["end_date"] is None
    # 2. satir: durum metni bir durum sozcugu ile baslamiyor; bitis "Ağustos 2026" ay sonu olarak okunur ve gecmiste -> tamamlandi; harf farkli ad eslesir
    assert ikinci["people"] == ["Ali Örnek"] and ikinci["other_people"] == "Zeynep Dışarıda" and ikinci["status"] == "tamamlandi"
    assert ikinci["hours_per_month"] == 36.0 and ikinci["benefit_type"] == "verimlilik" and ikinci["start_date"] == "2026-05-15" and ikinci["end_date"] == "2026-08-31"
    assert any("TAM eşleşmedi" in u for u in ikinci["uyarilar"])
    # bolum satirindan sonrasi inisiyatif
    assert gama["kind"] == "inisiyatif" and gama["status"] == "tamamlandi" and (gama["revenue_amount"], gama["revenue_currency"]) == (1250.75, "USD")
    assert tekrar["durum"] == "tekrar" and tekrar["kind"] == "inisiyatif" and any("daha önce" in u for u in tekrar["uyarilar"])
    # yonetici personel degildir: eslesmez, "diger kisiler"e yazilir; tek seferlik adetli tutar
    assert delta["people"] == [] and delta["other_people"] == "Mehmet Yönetici" and delta["revenue_amount"] == 3600.0 and delta["revenue_period"] == "tek_sefer"


def test_uygula_yalniz_yenileri_ekler_ikinci_yukleme_ekleme_yapmaz(client, ekip):
    hdr = login_ok(client)
    r = _uygula(client, hdr, _ornek_dosya())
    assert r.status_code == 200, r.text
    sonuc = r.json()["data"]
    assert (sonuc["eklendi"], sonuc["tekrar"], sonuc["var"], sonuc["hatali"], sonuc["toplam"]) == (4, 1, 0, 0, 5)
    assert _say() == 4 and _say(RevenueBenefitPerson) == 4
    veri = _liste(client)
    kayitlar = {k["title"]: k for k in veri["items"]}
    assert set(kayitlar) == {"Alfa yedek devre projesi", "Beta otomasyon", "Gama hız artışı", "Delta tek seferlik satış"}
    alfa = kayitlar["Alfa yedek devre projesi"]
    assert [p["name"] for p in alfa["people"]] == ["Ali Örnek", "Veli Deneme"] and alfa["revenue_amount"] == 88200.0 and alfa["year_revenue"] == 1_000_000.0
    assert alfa["status_note"] == "Devam ediyor.//7.10.2026" and alfa["created_by"] == "admin" and alfa["customers"] == "Tüm kurumsal müşteriler"
    beta = kayitlar["Beta otomasyon"]
    assert beta["extra_note"] == "Diğer irtibatlar: Kişi X" and beta["hours_note"] == ""
    assert beta["status"] == "tamamlandi"  # durum metni durum sozcugu ile baslamiyor, bitis (Agustos 2026 sonu) gecmiste
    gama = kayitlar["Gama hız artışı"]  # dosyadaki ilk satir eklenir, ayni baslikli ikincisi eklenmez
    assert gama["kind"] == "inisiyatif" and gama["revenue_amount"] == 1250.75 and gama["start_date"] == "2026-03-01" and gama["status"] == "tamamlandi"

    # idempotent: ayni dosya tekrar yuklenince hicbir sey eklenmez
    ikinci = _uygula(client, hdr, _ornek_dosya()).json()["data"]
    assert (ikinci["eklendi"], ikinci["var"], ikinci["yeni"]) == (0, 4, 0) and ikinci["tekrar"] == 1
    assert _say() == 4 and _say(RevenueBenefitPerson) == 4
    onizleme = _onizle(client, hdr, _ornek_dosya()).json()["data"]
    assert onizleme["plan"] == {"toplam": 5, "yeni": 0, "var": 4, "tekrar": 1, "hatali": 0}
    # denetim: sayilar var, baslik/ad yok
    olaylar = _denetim()
    assert [a for a, _ in olaylar] == ["gelir_uretim.ice_al", "gelir_uretim.ice_al"]
    assert olaylar[0][1] == "satir=5 eklendi=4 var=0 tekrar=1 hatali=0" and "Alfa" not in olaylar[0][1]


def test_ice_al_ayni_baslik_farkli_turde_yeni_sayilir_ve_buyuk_kucuk_farksizdir(client, ekip):
    hdr = login_ok(client)
    _uygula(client, hdr, _xlsx([["", "Alfa  Projesi", "Devam ediyor"]]))
    # ayni baslik (bosluk/harf farki) ayni turde: var; farkli turde (bolum satiri sonrasi): yeni
    veri = _onizle(client, hdr, _xlsx([["", "ALFA projesi", "Devam"], [BOLUM], ["", "alfa projesi", "Devam"]])).json()["data"]
    assert [s["durum"] for s in veri["satirlar"]] == ["var", "yeni"] and veri["satirlar"][1]["kind"] == "inisiyatif"


def test_ice_al_hatali_satir_ve_uyarilar(client, ekip):
    hdr = login_ok(client)
    uzun = "u" * 9000
    veri = _onizle(
        client,
        hdr,
        _xlsx(
            [
                ["Ali Örnek", "", "Devam ediyor", "başlıksız satır"],
                ["Ali Örnek", "Çok sayılı tutar", "Devam", uzun, "", "5,148M TL/ay + 412,7K TL/ay", "98,5K TL/ay elde edildi.", None, "1.1.2026", "1.1.2025"],
                ["Veli Deneme", "Dönemsiz tutar", "Devam", "", "", "15,8 KTL", None, None, None, None, "2026 yılı içi gelir: 190,3 KTL (not)"],
                ["Veli Deneme", "Yıl içi anlaşılmaz", "Devam", "", "", None, None, None, None, None, "belli değil"],
            ]
        ),
    ).json()["data"]
    assert veri["plan"] == {"toplam": 4, "yeni": 3, "var": 0, "tekrar": 0, "hatali": 1}
    bos, sayili, donemsiz, yil = veri["satirlar"]
    assert bos["durum"] == "hatali" and bos["title"] == "" and bos["uyarilar"]
    assert sayili["revenue_amount"] is None and "5,148M TL/ay" in sayili["revenue_note"]  # kaybolmaz, notta durur
    assert sayili["hours_per_month"] is None and sayili["end_date"] is None  # bitis baslangictan once: alinmadi
    assert len(sayili["uyarilar"]) >= 4 and any("kısaltıldı" in u for u in sayili["uyarilar"]) and any("Bitiş tarihi başlangıçtan önce" in u for u in sayili["uyarilar"])
    assert donemsiz["revenue_amount"] is None and donemsiz["revenue_note"] == "15,8 KTL" and donemsiz["year_revenue"] == 190_300.0
    assert any("sayıya çevrilemedi" in u for u in donemsiz["uyarilar"])
    assert yil["year_revenue"] is None and any("Yıl içi gelir" in u for u in yil["uyarilar"])
    # uygulayinca metinler kaybolmaz
    assert _uygula(client, hdr, _xlsx([["", "Metin korunur", "Devam", "", "", "15,8 KTL", "12 saat", None, None, None, "belli değil"]])).status_code == 200
    kayit = _liste(client)["items"][0]
    assert kayit["revenue_note"] == "15,8 KTL" and kayit["hours_note"] == "12 saat" and "Yıl içi gelir (Excel): belli değil" in kayit["extra_note"]


def test_ice_al_yok_isaretleri_bos_sayilir_cumleler_korunur(client, ekip):
    hdr = login_ok(client)
    basliklar = [*BASLIKLAR, "Yıl içi gelir (TL)"]
    dosya = _xlsx(
        [
            ["", "İşaretli", "Devam", "", "", "yok", "-", "Yok.", None, None, "n/a"],
            ["", "Cümle", "Devam", "", "", "ek gelir yok", "yoktur ama izleniyor", "—", None, None, "yok"],
        ],
        basliklar,
    )
    isaretli, cumle = _onizle(client, hdr, dosya).json()["data"]["satirlar"]
    # isaret: hucrenin tamami "deger yok" -> bos; not da uyari da uretmez
    assert (isaretli["revenue_note"], isaretli["year_revenue"], isaretli["hours_per_month"]) == ("", None, None) and isaretli["uyarilar"] == []
    # cumle oldugu gibi nota gider; K'daki "yok" isareti uyari uretmez
    assert cumle["revenue_note"] == "ek gelir yok" and cumle["year_revenue"] is None and cumle["uyarilar"] == []
    assert _uygula(client, hdr, dosya).status_code == 200
    kayitlar = {k["title"]: k for k in _liste(client)["items"]}
    assert (kayitlar["İşaretli"]["revenue_note"], kayitlar["İşaretli"]["hours_note"], kayitlar["İşaretli"]["extra_note"]) == ("", "", "")
    assert (kayitlar["Cümle"]["revenue_note"], kayitlar["Cümle"]["hours_note"], kayitlar["Cümle"]["extra_note"]) == ("ek gelir yok", "yoktur ama izleniyor", "")


def test_ice_al_fayda_turu_sutunu_ve_basliksiz_k_sutunu(client, ekip):
    hdr = login_ok(client)
    baslik = [*BASLIKLAR, None]  # K basliksiz
    veri = _onizle(client, hdr, _xlsx([["", "Tasarruf işi", "Tamamlandı", "", "", "Tasarruf", None, None, None, None, "2026 yılı içi gelir: 5 KTL"]], baslik)).json()["data"]
    assert veri["satirlar"][0]["year_revenue"] == 5000.0 and veri["satirlar"][0]["benefit_type"] == "tasarruf"
    acik = _onizle(client, hdr, _xlsx([["", "Açık tür", "Devam", "", "", "100 TL/ay", None, None, None, None, None, "Verimlilik"]], [*BASLIKLAR, "Yıl içi gelir (TL)", "Fayda türü"])).json()["data"]
    assert acik["satirlar"][0]["benefit_type"] == "verimlilik"


def test_ice_al_eksik_sutun_uyarisi_ve_baslik_arama(client, ekip):
    hdr = login_ok(client)
    # baslik 3. satirda, yalniz "Isin ozeti" zorunlu; olmayan sutunlar uyari verir
    kitap = Workbook()
    ws = kitap.active
    ws.append(["Gelir raporu"])
    ws.append([])
    ws.append(["Kim", "isin ÖZETI", "GÜNCEL DURUM", "Başlangıç"])
    ws.append(["Ali Örnek", "Küçük iş", "Tamamlandı", datetime(2026, 1, 5)])
    cikti = io.BytesIO()
    kitap.save(cikti)
    veri = _onizle(client, hdr, cikti.getvalue()).json()["data"]
    assert veri["baslik_satiri"] == 3 and veri["plan"]["yeni"] == 1 and veri["satirlar"][0]["status"] == "tamamlandi"
    assert veri["satirlar"][0]["people"] == []  # "Kim" basligi taninmadi: kisi okunmadi
    assert veri["uyarilar"] and "Bulunamayan sütunlar" in veri["uyarilar"][0]


def test_ice_al_dosya_hatalari(client, ekip):
    hdr = login_ok(client)
    for veri, kod in (
        (b"", 400),
        (b"bu bir excel degil", 400),
        (b"PK\x03\x04bozuk", 400),
        (_xlsx([["Ali", "Baslik yok"]], ["Foo", "Bar", "Baz"]), 400),  # "Isin ozeti" sutunu yok
        (b"x" * (5 * 1024 * 1024 + 1), 413),
    ):
        for yol in ("onizleme", "uygula"):
            r = client.post(f"{URL}/ice-al/{yol}", content=veri, headers=hdr)
            assert r.status_code == kod, (kod, yol, r.text)
            assert r.json()["detail"]
    assert _say() == 0


def test_ice_al_satir_siniri(client, ekip):
    hdr = login_ok(client)
    satirlar = [["", f"İş {i}", "Devam"] for i in range(ice_al.EN_COK_SATIR + 1)]
    r = _onizle(client, hdr, _xlsx(satirlar))
    assert r.status_code == 413 and str(ice_al.EN_COK_SATIR) in r.json()["detail"]
    assert _onizle(client, hdr, _xlsx(satirlar[: ice_al.EN_COK_SATIR])).json()["data"]["plan"]["yeni"] == ice_al.EN_COK_SATIR


def test_ice_al_dil_ingilizce_uyarilar(client, ekip):
    hdr = login_ok(client)
    veri = _xlsx([["Bilinmeyen Kişi", "Dil denemesi", "Devam", "", "", "15,8 KTL"]])
    r = client.post(f"{URL}/ice-al/onizleme", content=veri, headers={**hdr, "X-Dil": "en"})
    uyarilar = r.json()["data"]["satirlar"][0]["uyarilar"]
    assert any("No TAM account matched" in u for u in uyarilar) and any("could not be converted" in u for u in uyarilar)
    r = client.post(f"{URL}/ice-al/uygula", content=b"bozuk", headers={**hdr, "X-Dil": "en"})
    assert r.status_code == 400 and "could not be read" in r.json()["detail"]


def test_ice_al_tek_islem_ortada_hata_hicbir_sey_birakmaz(client, ekip, monkeypatch):
    sayac = {"n": 0}
    gercek = servis.ekle

    def bozuk(*a, **k):
        sayac["n"] += 1
        if sayac["n"] == 3:
            raise RuntimeError("ortada hata")
        return gercek(*a, **k)

    monkeypatch.setattr(servis, "ekle", bozuk)
    with Session(engine()) as db, pytest.raises(RuntimeError):
        ice_al.uygula(db, Principal("admin", "admin", True), _ornek_dosya(), "x.xlsx")
        db.commit()
    assert _say() == 0 and _say(RevenueBenefitPerson) == 0  # commit'e varilmadi: ilk iki satir da yazilmadi


# --- Excel disa aktarim --------------------------------------------------------------------------------------------------------
def test_excel_disa_aktarim_basliklari_ve_icerigi(client, ekip):
    hdr = login_ok(client)
    _ekle(client, hdr, title="Alfa proje", status="devam", status_note="Güncel not", description="Açıklama", customers="Alfa A.Ş.", revenue_amount=88200, year_revenue=1_000_000,
          hours_per_month=36, start_date="2026-04-01", person_ids=[ekip["ali"]], other_people="Dış Kişi", extra_note="Ek not")  # fmt: skip
    _ekle(client, hdr, kind="inisiyatif", title="Beta inisiyatif", benefit_type="tasarruf", status="tamamlandi", revenue_amount=7500, revenue_currency="EUR", revenue_period="tek_sefer",
          revenue_note="adetli", start_date="2026-09-24", end_date="2026-09-24")  # fmt: skip
    _ekle(client, hdr, title="=1+1", description="=HYPERLINK(\"x\")")
    r = client.get(f"{URL}/excel")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert r.headers["content-disposition"].startswith('attachment; filename="Gelir_Faydasi_') and r.headers["content-disposition"].endswith('.xlsx"')
    ws = load_workbook(io.BytesIO(r.content)).active
    satirlar = [[h.value for h in satir] for satir in ws.iter_rows()]
    assert tuple(satirlar[0]) == excel.BASLIKLAR and list(satirlar[0][:13]) == KULLANICI_BASLIKLARI  # kullanicinin Excel'i, ayni sira
    alfa = next(s for s in satirlar if s[1] == "Alfa proje")
    assert alfa[:7] == ["Ali Örnek, Dış Kişi", "Alfa proje", "Devam ediyor. Güncel not", "Faz 1", "Açıklama", "Alfa A.Ş.", "88200 TL/ay"]
    assert alfa[7:] == [1_000_000, "36 saat/ay", 0, "Ek not", datetime(2026, 4, 1), datetime(2026, 12, 31), "Gelir"]
    sira = [s[1] or s[0] for s in satirlar[1:]]
    assert sira.index(excel.BOLUM_INISIYATIF) < sira.index("Beta inisiyatif") and sira.index("Alfa proje") < sira.index(excel.BOLUM_INISIYATIF)  # projeler, bolum satiri, inisiyatifler
    beta = next(s for s in satirlar if s[1] == "Beta inisiyatif")
    assert beta[2] == "Tamamlandı. Sürüyor" and beta[6] == "7500 EUR (tek seferlik) adetli" and beta[13] == "Tasarruf"
    ozet = load_workbook(io.BytesIO(r.content))[excel.OZET_SAYFASI]
    degerler = {s[0]: s[1] for s in ozet.iter_rows(min_row=3, values_only=True)}
    assert degerler["İş sayısı"] == 3 and degerler["Aylık gelir faydası (iptaller hariç)"] == "88200 TL" and degerler["Yıllık gelir faydası (TL/12 ay)"] == 1_000_000
    # formul gibi gorunen metin formul olarak yazilmaz
    formul = next(h for satir in ws.iter_rows() for h in satir if h.value == "=1+1")
    assert formul.data_type == "s"
    assert [a for a, _ in _denetim()][-1] == "gelir_uretim.excel"


def test_excel_disa_aktarim_bos_veritabani(client):
    login_ok(client)
    ws = load_workbook(io.BytesIO(client.get(f"{URL}/excel").content)).active
    assert [h.value for h in ws[1]] == list(excel.BASLIKLAR) and ws.max_row == 1


def test_disa_aktarim_yeniden_ice_aktarilabilir(client, ekip):
    """Disa aktarilan dosya ice aktarim bicimiyle okunur: bos veritabanina geri yuklenince ayni kayitlar olusur."""
    hdr = login_ok(client)
    _cesitli(client, hdr, ekip)
    onceki = {k["title"]: k for k in _liste(client)["items"]}
    dosya = client.get(f"{URL}/excel").content
    for k in list(onceki.values()):
        client.delete(f"{URL}/{k['id']}", headers=hdr)
    assert _say() == 0
    sonuc = _uygula(client, hdr, dosya).json()["data"]
    assert sonuc["eklendi"] == 6 and sonuc["hatali"] == 0
    sonra = {k["title"]: k for k in _liste(client)["items"]}
    assert set(sonra) == set(onceki)
    for baslik, eski in onceki.items():
        yeni = sonra[baslik]
        for alan in ("kind", "benefit_type", "status", "revenue_amount", "revenue_currency", "revenue_period", "year_revenue", "hours_per_month", "start_date", "end_date", "customers"):
            assert yeni[alan] == eski[alan], (baslik, alan)
        assert [p["name"] for p in yeni["people"]] == [p["name"] for p in eski["people"]] and yeni["other_people"] == eski["other_people"]


# --- sunum ozeti ---------------------------------------------------------------------------------------------------------------
def _ekle_db(db: Session, **alanlar) -> RevenueBenefit:
    temiz = servis.temizle({"title": "İş", **alanlar})
    return servis.ekle(db, "test", temiz, [])


def test_sunum_ozeti_ceyrek_kesisimi_ve_coklu_para(client, ekip):
    login_ok(client)
    with Session(engine()) as db:
        _ekle_db(db, title="Q3 icinde biter", start_date=date(2026, 7, 10), end_date=date(2026, 9, 5), revenue_amount=1000, status="tamamlandi")
        _ekle_db(db, title="Q3'ten Q4'e", start_date=date(2026, 8, 1), end_date=date(2026, 11, 15), revenue_amount=2000, year_revenue=50000, hours_per_month=10)
        _ekle_db(db, title="Q4 basinda baslar", start_date=date(2026, 10, 1), revenue_amount=300, revenue_currency="USD", revenue_period="ay")
        _ekle_db(db, title="Devam eden eski", start_date=date(2025, 1, 1), revenue_amount=400, revenue_currency="EUR", revenue_period="ay")
        _ekle_db(db, title="Q2 sonunda biter", start_date=date(2026, 4, 1), end_date=date(2026, 6, 30), revenue_amount=9999)
        _ekle_db(db, title="Q1 2027 baslar", start_date=date(2027, 1, 1), revenue_amount=8888)
        _ekle_db(db, title="Tek seferlik", start_date=date(2026, 11, 1), revenue_amount=777, revenue_period="tek_sefer")
        _ekle_db(db, title="Iptal edilen", start_date=date(2026, 11, 1), revenue_amount=555, status="iptal")
        _ekle_db(db, title="Tarihsiz", revenue_amount=444)
        _ekle_db(db, title="Bitisiz tamamlanmis", start_date=date(2026, 9, 20), status="tamamlandi", revenue_amount=222)
        db.commit()
        q4 = servis.sunum_ozeti(db, 2026, 4)
        q3 = servis.sunum_ozeti(db, 2026, 3)
        yil = servis.sunum_ozeti(db, 2026, 0)
    basliklar = lambda ozet: [s[0] for s in ozet["tablo"]["satirlar"]]
    # Q4 (1 Ekim-31 Aralik): ceyrekle kesisen, iptal ve tarihsiz haric; tamamlanmis ama bitisi bos is yalniz baslangic gununde sayilir
    assert basliklar(q4) == ["Devam eden eski", "Q3'ten Q4'e", "Q4 basinda baslar", "Tek seferlik"]
    assert basliklar(q3) == ["Devam eden eski", "Q3 icinde biter", "Q3'ten Q4'e", "Bitisiz tamamlanmis"]
    assert basliklar(yil) == ["Devam eden eski", "Q2 sonunda biter", "Q3 icinde biter", "Q3'ten Q4'e", "Bitisiz tamamlanmis", "Q4 basinda baslar", "Tek seferlik"]
    # KPI: sayi, tamamlanan, para birimi basina AYLIK gelir (tek seferlik ve yillik toplanmaz), yil ici gelir, efor
    kpi = {k["ad"]: k for k in q4["kpi"]}
    assert kpi["Fayda sağlanan iş"]["deger"] == 4 and kpi["Tamamlanan"]["deger"] == 0
    assert kpi["Aylık gelir TRY"]["deger"] == 2000.0 and kpi["Aylık gelir TRY"]["birim"] == "TRY"
    assert kpi["Aylık gelir USD"]["deger"] == 300.0 and kpi["Aylık gelir EUR"]["deger"] == 400.0
    assert kpi["Yıl içi gelir"]["deger"] == 50000.0 and kpi["Aylık efor kazancı (saat)"]["deger"] == 10.0
    assert all(k["ad_en"] and "alt" in k and "birim" in k for k in q4["kpi"])
    sutunlar = [s["ad"] for s in q4["tablo"]["sutunlar"]]
    assert sutunlar == ["İş", "TAM", "Başlangıç", "Bitiş", "Aylık gelir TRY", "Aylık gelir USD", "Aylık gelir EUR", "Yıl içi gelir", "Saat/ay"]
    assert all(s["ad_en"] for s in q4["tablo"]["sutunlar"]) and [s["birim"] for s in q4["tablo"]["sutunlar"]][4:8] == ["TRY", "USD", "EUR", "TRY"]
    satir = next(s for s in q4["tablo"]["satirlar"] if s[0] == "Q3'ten Q4'e")
    assert satir[1:] == ["—", "2026-08-01", "2026-11-15", 2000.0, None, None, 50000.0, 10.0]  # dile bagimsiz hucreler (ceyrek dondurulur)
    assert all(len(s) == len(sutunlar) for s in q4["tablo"]["satirlar"])
    assert {k["ad"]: k for k in q3["kpi"]}["Tamamlanan"]["deger"] == 2  # Q3 icinde biter + bitisiz tamamlanmis


def test_sunum_ozeti_bos_donem_ve_gecersiz_girdi(client, ekip):
    login_ok(client)
    with Session(engine()) as db:
        bos = servis.sunum_ozeti(db, 2026, 2)
        assert bos["tablo"]["satirlar"] == [] and bos["kpi"][0]["deger"] == 0
        assert [k["ad"] for k in bos["kpi"]] == ["Fayda sağlanan iş", "Tamamlanan", "Aylık gelir TRY"] and bos["kpi"][2]["deger"] == 0
        for yil, ceyrek in ((1999, 1), (2026, 5), (2026, -1)):
            with pytest.raises(TakvimHata):
                servis.sunum_ozeti(db, yil, ceyrek)


def test_sunum_ozeti_kisi_adlari(client, ekip):
    login_ok(client)
    with Session(engine()) as db:
        satir = servis.ekle(db, "t", servis.temizle({"title": "Kişili iş", "start_date": date(2026, 5, 1), "other_people": "Dış Kişi"}), [ekip["veli"], ekip["ali"]])
        db.commit()
        assert satir.id
        assert servis.sunum_ozeti(db, 2026, 2)["tablo"]["satirlar"][0][1] == "Ali Örnek, Veli Deneme, Dış Kişi"


def test_calisma_araligi_kurallari():
    ekle = lambda **a: RevenueBenefit(**{"kind": "proje", "status": "devam", **a})
    assert servis.calisma_araligi(ekle()) is None
    assert servis.calisma_araligi(ekle(start_date=date(2026, 1, 1))) == (date(2026, 1, 1), None)
    assert servis.calisma_araligi(ekle(start_date=date(2026, 1, 1), end_date=date(2026, 2, 1))) == (date(2026, 1, 1), date(2026, 2, 1))
    assert servis.calisma_araligi(ekle(start_date=date(2026, 1, 1), status="tamamlandi")) == (date(2026, 1, 1), date(2026, 1, 1))
    assert servis.calisma_araligi(ekle(start_date=date(2026, 3, 1), end_date=date(2026, 2, 1))) == (date(2026, 3, 1), date(2026, 3, 1))  # bozuk veri: bitis baslangictan once olamaz


# --- sema ------------------------------------------------------------------------------------------------------------------------
def test_kisi_baglantisi_is_silinince_cascade_ile_gider(client, ekip):
    hdr = login_ok(client)
    kimlik = _ekle(client, hdr, person_ids=[ekip["ali"]])
    assert _say(RevenueBenefitPerson) == 1
    client.delete(f"{URL}/{kimlik}", headers=hdr)
    assert _say(RevenueBenefitPerson) == 0


def test_ice_al_geri_alinir_sonradan_duzenlenen_korunur(client, ekip):
    """2026-11-01: elle yuklenen dosya Import > Ice aktarma gecmisi'nden geri alinir; aktarimdan sonra duzenlenen kayit korunur."""
    hdr = login_ok(client)
    assert _uygula(client, hdr, _ornek_dosya()).json()["data"]["eklendi"] == 4
    kayit = client.get("/api/v1/tampon/ice-aktarmalar").json()["data"][0]
    assert (kayit["tur"], kayit["dosya"], kayit["ozet"]["eklendi"], kayit["geri_alinan"]) == ("gelir_uretim", "gelir.xlsx", 4, None)
    with Session(engine()) as db:
        db.scalar(select(RevenueBenefit).where(RevenueBenefit.title == "Beta otomasyon")).updated_at = datetime(2020, 1, 1, tzinfo=UTC)
        db.commit()
    r = client.post(f"{"/api/v1/tampon/ice-aktarmalar"}/{kayit['id']}/geri-al", headers=hdr)
    assert r.json()["data"] == {"geri_alinan": 3, "korunan": 1}
    with Session(engine()) as db:
        assert [r.title for r in db.scalars(select(RevenueBenefit))] == ["Beta otomasyon"]
        kalan = db.scalar(select(RevenueBenefit.id))
        assert {p.item_id for p in db.scalars(select(RevenueBenefitPerson))} <= {kalan}  # silinenin kisi baglari da gider
    assert client.post(f"{"/api/v1/tampon/ice-aktarmalar"}/{kayit['id']}/geri-al", headers=hdr).status_code == 409
    assert client.get("/api/v1/tampon/ice-aktarmalar").json()["data"][0]["geri_alinan"]["kullanici"] == "admin"
