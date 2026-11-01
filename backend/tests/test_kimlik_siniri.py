"""Kimlik ust siniri: cok buyuk/gecersiz int yol ve govde kimlikleri SQLite'a ulasmadan 422 olur (500/OverflowError degil)."""

import pytest
from sqlalchemy.orm import Session

from app.db import engine
from app.models import AppUser, Customer
from app.ortak import EN_BUYUK_KIMLIK
from tests.conftest import login_ok

DEVASA = 10**20  # SQLite INTEGER (64 bit) disinda: sinir olmasa OverflowError -> yakalanmayan 500
SINIR = 2_147_483_647  # PostgreSQL INTEGER ile uyumlu en buyuk kimlik

KURAL = {"name": "k", "source_key": "alarm", "key_column": "Musteri No", "target": "alarm_count", "operation": "set", "value_column": "Adet"}

# (yontem, yol sablonu, govde): {i} yerine denenen kimlik gelir
YOL_UCLARI = [
    ("GET", "/api/v1/musteri/{i}", None),
    ("PUT", "/api/v1/musteri/{i}/kimlik", {}),
    ("PUT", "/api/v1/musteri/{i}/iletisim", {}),
    ("PUT", "/api/v1/musteri/{i}/sorumlu", {"owner_id": 1}),
    ("DELETE", "/api/v1/musteri/{i}", None),
    ("POST", "/api/v1/musteri/{i}/silme-talebi", None),
    ("PUT", "/api/v1/musteri/{i}/ayri-rapor", {"ayri_rapor": True}),
    ("PUT", "/api/v1/musteri/{i}/rapor-muaf", {"rapor_muaf": True}),
    ("GET", "/api/v1/musteri/{i}/rapor/taslak", None),
    ("PUT", "/api/v1/musteri/{i}/rapor/taslak", {"alanlar": {}}),
    ("PUT", "/api/v1/musteri/{i}/rapor/alicilar", {}),
    ("POST", "/api/v1/musteri/{i}/rapor/gonder", {}),
    ("GET", "/api/v1/musteri/{i}/rapor/gecmis", None),
    ("POST", "/api/v1/rapor/gonderim/{i}/geri-al", None),
    ("GET", "/api/v1/rapor/gonderim/{i}/dosya", None),
    ("PUT", "/api/v1/skor/musteri/{i}", {"tam_id": 1, "score": 50}),
    ("POST", "/api/v1/skor/talepler/{i}/karar", {"action": "approve"}),
    ("PUT", "/api/v1/skor/istirak/{i}/final-dahil", {"dahil": True}),
    ("GET", "/api/v1/tampon/partiler/{i}", None),
    ("GET", "/api/v1/tampon/partiler/{i}/satirlar", None),
    ("POST", "/api/v1/tampon/partiler/{i}/analiz", None),
    ("POST", "/api/v1/tampon/partiler/{i}/kabul", None),
    ("DELETE", "/api/v1/tampon/partiler/{i}", None),
    ("PUT", "/api/v1/tampon/kurallar/{i}", KURAL),
    ("POST", "/api/v1/tampon/kurallar/{i}/etkin", {"etkin": True}),
    ("DELETE", "/api/v1/tampon/kurallar/{i}", None),
    ("POST", "/api/v1/tampon/kurallar/{i}/onizle", {"parti_id": 1}),
    ("POST", "/api/v1/tampon/kurallar/{i}/uygula", {"parti_id": 1, "onay": True}),
    ("POST", "/api/v1/yonetim/arizalar/{i}/durum", {"durum": "ack"}),
]

# (yontem, yol, govde): govdedeki kimlik alani devasa
GOVDE_UCLARI = [
    ("POST", "/api/v1/musteri", {"name": "Yeni A.S.", "parent_id": DEVASA}),
    ("POST", "/api/v1/musteri", {"name": "Yeni A.S.", "owner_id": DEVASA}),
    ("PUT", "/api/v1/musteri/1/sorumlu", {"owner_id": DEVASA}),
    ("PUT", "/api/v1/skor/musteri/1", {"tam_id": DEVASA, "score": 50}),
    ("POST", "/api/v1/skor/toplu/onizleme", {"tam_id": DEVASA}),
    ("POST", "/api/v1/skor/toplu/uygula", {"customer_ids": [1, DEVASA]}),
    ("POST", "/api/v1/skor/talepler", {"customer_id": DEVASA}),
    ("PUT", "/api/v1/skor/puanlama-disi", {"disi": [1, DEVASA]}),
    ("POST", "/api/v1/tampon/kurallar/1/onizle", {"parti_id": DEVASA}),
    ("POST", "/api/v1/tampon/kurallar/1/uygula", {"parti_id": DEVASA, "onay": True}),
]

# Kimlik olmayan sayisal alanlar: aralik servis katmaninda 400 ile denetlenir (dagitim.dogrula, skor_servis._gecerli_skor)
SINIRSIZ_ALAN_ISTISNALARI = {"KuralGovde.max_age_minutes", "MusteriSkoru.score"}


@pytest.fixture
def veri(client):
    with Session(engine()) as db:
        db.add_all([AppUser(id=1, username="admin", display_name="Admin Kisi", role="admin", is_admin=True), AppUser(id=2, username="ayse", display_name="Ayse Test", role="TeamMember")])
        db.flush()
        db.add_all([Customer(id=1, external_key="k-a", name="Alfa Test A.S.", segment="MA", owner_id=1), Customer(id=2, external_key="k-b", name="Beta Test Ltd", segment="SMB", owner_id=2)])
        db.commit()
    return client


def _cagri(client, hdr, yontem, yol, govde):
    return client.request(yontem, yol, json=govde, headers=hdr)


def _ad(uc):
    return f"{uc[0]} {uc[1]}"


@pytest.mark.parametrize("kimlik", [DEVASA, 2**63, SINIR + 1, 0], ids=["devasa", "2^63", "sinir+1", "sifir"])
@pytest.mark.parametrize("uc", YOL_UCLARI, ids=_ad)
def test_gecersiz_yol_kimligi_422(veri, uc, kimlik):
    hdr = login_ok(veri)
    yontem, yol, govde = uc
    r = _cagri(veri, hdr, yontem, yol.format(i=kimlik), govde)
    assert r.status_code == 422, r.text
    assert r.json()["detail"][0]["loc"][0] == "path"


@pytest.mark.parametrize("uc", YOL_UCLARI, ids=_ad)
def test_sinir_degeri_dogrulamayi_gecer(veri, uc):
    """En buyuk gecerli kimlik 422 degil: kayit yoksa servis 404/409 verir, sunucu hatasi (500) olmaz."""
    hdr = login_ok(veri)
    yontem, yol, govde = uc
    for kimlik in (1, SINIR):
        r = _cagri(veri, hdr, yontem, yol.format(i=kimlik), govde)
        assert r.status_code != 422, (kimlik, r.text)
        assert r.status_code < 500, (kimlik, r.text)


@pytest.mark.parametrize("uc", GOVDE_UCLARI, ids=lambda u: f"{u[0]} {u[1]} {sorted(u[2])}")
def test_devasa_govde_kimligi_422(veri, uc):
    hdr = login_ok(veri)
    yontem, yol, govde = uc
    r = _cagri(veri, hdr, yontem, yol, govde)
    assert r.status_code == 422, r.text
    assert r.json()["detail"][0]["loc"][0] == "body"


def test_sifir_ve_negatif_govde_kimligi_422(veri):
    hdr = login_ok(veri)
    assert veri.put("/api/v1/musteri/1/sorumlu", json={"owner_id": 0}, headers=hdr).status_code == 422
    assert veri.put("/api/v1/skor/puanlama-disi", json={"disi": [-1]}, headers=hdr).status_code == 422
    assert veri.post("/api/v1/skor/talepler", json={"customer_id": -5}, headers=hdr).status_code == 422


def test_gecerli_kimlikler_aynen_calisir(veri):
    hdr = login_ok(veri)
    assert veri.get("/api/v1/musteri/1").status_code == 200
    assert veri.get("/api/v1/musteri/1/rapor/gecmis").status_code == 200
    assert veri.put("/api/v1/skor/musteri/1", json={"tam_id": 1, "score": 50}, headers=hdr).status_code == 200
    assert veri.put("/api/v1/musteri/1/sorumlu", json={"owner_id": 2}, headers=hdr).status_code == 200
    assert veri.put("/api/v1/musteri/1/sorumlu", json={"owner_id": 99}, headers=hdr).status_code == 404  # sinir icinde ama kayit yok
    assert veri.get("/api/v1/musteri/99").status_code == 404
    assert veri.get(f"/api/v1/musteri/{SINIR}").status_code == 404
    csv = "Müşteri No;Kayıt Türü\n1;Alarm\n".encode()
    parti = veri.put("/api/v1/tampon/yukle?kaynak=kimlik&dosya=k.csv", content=csv, headers={**hdr, "Content-Type": "text/csv"}).json()["data"]
    assert veri.get(f"/api/v1/tampon/partiler/{parti['id']}").status_code == 200


def test_buyuk_sayfa_numarasi_422(veri):
    """Sayfa ofseti de SQLite'a gidiyordu: ust sinir olmadan OverflowError."""
    login_ok(veri)
    assert veri.get(f"/api/v1/musteri?page={DEVASA}").status_code == 422
    assert veri.get("/api/v1/musteri?page=2").status_code == 200


def _sinirsiz_tamsayilar(dugum, yol, bulunan):
    """OpenAPI semasinda 'maximum' tasimayan tum integer alanlari toplar (anyOf/items/allOf dahil)."""
    if isinstance(dugum, list):
        for oge in dugum:
            _sinirsiz_tamsayilar(oge, yol, bulunan)
    elif isinstance(dugum, dict):
        if dugum.get("type") == "integer" and "maximum" not in dugum:
            bulunan.append(yol)
        for anahtar in ("anyOf", "allOf", "oneOf", "items"):
            if anahtar in dugum:
                _sinirsiz_tamsayilar(dugum[anahtar], yol, bulunan)


def test_sozlesme_butun_int_kimlikleri_sinirli(client):
    """Yeni uc eklenip sinir unutulursa burasi kirilir: yol parametreleri ve govde alanlari OpenAPI'de maximum tasir."""
    sema = client.app.openapi()
    sinirsiz: list[str] = []
    for yol, islemler in sema["paths"].items():
        for yontem, islem in islemler.items():
            for p in islem.get("parameters", []):
                if p["in"] == "path":
                    bulunan: list[str] = []
                    _sinirsiz_tamsayilar(p["schema"], f"{yontem.upper()} {yol} {p['name']}", bulunan)
                    sinirsiz += bulunan
                    assert p["schema"].get("type") != "integer" or p["schema"].get("minimum") == 1, (yol, p["name"])
    for ad, govde in sema["components"]["schemas"].items():
        if ad in ("HTTPValidationError", "ValidationError"):  # FastAPI'nin kendi hata semalari (loc: str | int)
            continue
        for alan, alan_sema in govde.get("properties", {}).items():
            bulunan = []
            _sinirsiz_tamsayilar(alan_sema, f"{ad}.{alan}", bulunan)
            sinirsiz += [b for b in bulunan if b not in SINIRSIZ_ALAN_ISTISNALARI]
    assert not sinirsiz, f"Ust siniri olmayan int alanlar (KimlikTipi kullanin): {sinirsiz}"


def test_ortak_sinir_sabiti():
    assert EN_BUYUK_KIMLIK == SINIR
