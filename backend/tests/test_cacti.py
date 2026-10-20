"""Cacti: ag yerine sentetik PNG; uretim kimligi/verisi kullanilmaz."""

import base64
import struct
import zlib
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.db import engine
from app.models import AppUser, Customer
from app.rapor import cacti, cacti_kimlik
from tests.conftest import login_ok


def png():
    def chunk(t, data):
        return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 120, 60, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\0" + b"\xff" * 360) * 60))
        + chunk(b"IEND", b"")
    )


@pytest.fixture(autouse=True)
def ayar(monkeypatch, tmp_path):
    for key in ("USERNAME", "PASSWORD", "USERNAME_DPAPI", "PASSWORD_DPAPI", "REALM", "PATH", "MODE"):
        monkeypatch.delenv("TAMLIFE_CACTI_" + key, raising=False)
    monkeypatch.delenv("TAMLIFE_LOOKOUTEYES_URL", raising=False)
    monkeypatch.setenv("TAMLIFE_REPORT_DIR", str(tmp_path / "reports"))


@pytest.mark.parametrize("deger", ["4", "0004", "https://trafik.superonline.net/graph.php?local_graph_id=4&rra_id=all"])
def test_grafik_id(deger):
    assert cacti.grafik_id(deger) == "4"


@pytest.mark.parametrize(
    "deger",
    [
        "0",
        "-1",
        "2147483648",
        "https://evil.test/graph.php?local_graph_id=4",
        "https://trafik.superonline.net@evil.test/graph.php?local_graph_id=4",
        "http://trafik.superonline.net/graph.php?local_graph_id=4",
        "https://trafik.superonline.net/graph.php?local_graph_id=4&local_graph_id=5",
        "https://trafik.superonline.net/graph.php?local_graph_id=4#secret",
    ],
)
def test_ssrf_ve_gecersiz_id(deger):
    with pytest.raises(cacti.CactiHata):
        cacti.grafik_id(deger)


def test_takvim_ayi():
    bas, son = cacti.ay_araligi(2024, 2)
    assert son - bas + 1 == 29 * 86400
    assert datetime.fromtimestamp(bas, cacti.timezone(cacti.timedelta(hours=3))).day == 1
    assert cacti.ay_araligi(2025, 12)[1] + 1 == cacti.ay_araligi(2026, 1)[0]


def test_png():
    cacti.png_dogrula(png())
    for veri in (b"<html>login</html>", png()[:-4], png()[:45] + b"bad" + png()[48:]):
        with pytest.raises(cacti.CactiHata):
            cacti.png_dogrula(veri)


def test_cache_donem_ve_id_izolasyonu(monkeypatch, tmp_path):
    calls = []

    def indir(ids, yil, ay):
        calls.append((ids, yil, ay))
        return [{"anahtar": "cacti-" + i, "baslik": i, "gorsel": "data:image/png;base64," + base64.b64encode(png()).decode()} for i in ids]

    monkeypatch.setattr(cacti, "indir", indir)
    assert cacti.grafikler(["1"], 2026, 9, tmp_path)
    assert cacti.grafikler(["1"], 2026, 9, tmp_path, kilitli=True)
    assert len(calls) == 1
    cacti.grafikler(["2"], 2026, 9, tmp_path)
    cacti.grafikler(["1"], 2026, 8, tmp_path)
    assert len(calls) == 3
    with pytest.raises(cacti.CactiHata, match="Gönderilen"):
        cacti.grafikler(["3"], 2026, 9, tmp_path, kilitli=True)
    assert not list(tmp_path.glob("*.tmp"))


def test_basarisizlik_cache_yazmaz(monkeypatch, tmp_path):
    def indir(*args):
        raise cacti.CactiHata(502, "sentetik hata")

    monkeypatch.setattr(cacti, "indir", indir)
    with pytest.raises(cacti.CactiHata):
        cacti.grafikler(["1"], 2026, 9, tmp_path)
    assert not list(tmp_path.iterdir())


def test_eksik_hesap_ve_limit():
    assert cacti.hazir() is False
    with pytest.raises(cacti.CactiHata, match="tanımlanmamış"):
        cacti.indir(["1"], 2026, 9)
    assert cacti.baglantilar(["1", "01"]) == ["1"]
    with pytest.raises(cacti.CactiHata):
        cacti.baglantilar([str(x) for x in range(1, 8)])


def test_api_csrf_musteri_ve_sirlar(client, monkeypatch):
    with Session(engine()) as db:
        db.add(AppUser(id=1, username="admin", display_name="Test Admin", role="admin", is_admin=True))
        db.add(Customer(id=1, external_key="cacti-test", name="Test", owner_id=1))
        db.commit()
    yol = "/api/v1/musteri/1/rapor/cacti"
    assert client.get(yol).status_code == 401
    hdr = login_ok(client)
    monkeypatch.setenv(cacti_kimlik.KULLANICI_ANAHTARI, cacti_kimlik.koru("synthetic-user"))
    monkeypatch.setenv(cacti_kimlik.PAROLA_ANAHTARI, cacti_kimlik.koru("synthetic-password"))
    result = client.get(yol)
    assert result.status_code == 200
    assert result.json()["data"]["hazir"] is True
    assert "synthetic-user" not in result.text and "synthetic-password" not in result.text
    assert client.put(yol, json={"baglantilar": ["7"]}).status_code == 403
    r = client.put(yol, headers=hdr, json={"baglantilar": ["https://trafik.superonline.net/graph.php?local_graph_id=7"]})
    assert r.status_code == 200 and r.json()["data"]["baglantilar"] == ["7"]
    assert client.put(yol, headers=hdr, json={"baglantilar": ["https://evil.test/"]}).status_code == 400
    assert client.get("/api/v1/musteri/999/rapor/cacti/grafikler").status_code == 404
    monkeypatch.setattr(
        cacti,
        "indir",
        lambda ids, y, a: [{"anahtar": "cacti-7", "baslik": "Test", "gorsel": "data:image/png;base64," + base64.b64encode(png()).decode()}],
    )
    r = client.get(yol + "/grafikler")
    assert r.status_code == 200 and r.json()["data"]["grafikler"][0]["anahtar"] == "cacti-7"
    assert "synthetic-password" not in r.text
    client.post("/api/v1/session/logout", headers=hdr)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "TeamMember")
    hdr = login_ok(client)
    # Standart (2026-10-17): sorumlu personel kendi musterisinin grafik baglantisini tanimlar; admin olmasi gerekmez.
    assert client.get(yol).json()["data"]["duzenleyebilir"] is True
    r = client.put(yol, headers=hdr, json={"baglantilar": ["8"]})
    assert r.status_code == 200 and r.json()["data"]["baglantilar"] == ["8"]
    with Session(engine()) as db:
        db.add(AppUser(id=2, username="other", display_name="Other", role="TeamMember"))
        db.add(Customer(id=2, external_key="cacti-other", name="Other", owner_id=2))
        db.add(Customer(id=3, external_key="cacti-ist", name="Ist", owner_id=2, parent_id=1))  # catisi bende, sorumlusu baskasi
        db.commit()
    # 2026-10-20: baskasinin karti okunur (salt okunur), grafik alimi ve degistirme 403
    o = client.get("/api/v1/musteri/2/rapor/cacti")
    assert o.status_code == 200 and o.json()["data"]["duzenleyebilir"] is False
    assert client.get("/api/v1/musteri/2/rapor/cacti/grafikler").status_code == 403
    assert client.put("/api/v1/musteri/2/rapor/cacti", headers=hdr, json={"baglantilar": ["9"]}).status_code == 403  # baskasinin musterisi
    assert client.put("/api/v1/musteri/3/rapor/cacti", headers=hdr, json={"baglantilar": ["9"]}).status_code == 200  # catinin sorumlusu


def test_tarayi_ci_kimligi_stdin_ile_alir(monkeypatch):
    import json
    import os
    import shutil
    import subprocess

    monkeypatch.setenv(cacti_kimlik.KULLANICI_ANAHTARI, cacti_kimlik.koru("synthetic-user"))
    monkeypatch.setenv(cacti_kimlik.PAROLA_ANAHTARI, cacti_kimlik.koru("synthetic-password"))
    monkeypatch.setenv("REPORTDB_DB_PASSWORD", "synthetic-other-password")
    monkeypatch.setattr(shutil, "which", lambda _: "node")
    encoded = base64.b64encode(png()).decode()

    class Process:
        returncode = 0

        def __init__(self, args, **kwargs):
            assert "synthetic-password" not in str(args)
            assert "TAMLIFE_CACTI_PASSWORD" not in kwargs["env"]
            assert "REPORTDB_DB_PASSWORD" not in kwargs["env"]

        def communicate(self, data=None, **kwargs):
            assert json.loads(data)["password"] == "synthetic-password"
            return json.dumps({"images": [encoded]}), None

    monkeypatch.setattr(subprocess, "Popen", Process)
    result = cacti.indir(["7"], 2026, 9)
    assert result[0]["anahtar"] == "cacti-7"
    assert "synthetic-password" not in json.dumps(result)
    assert cacti_kimlik.coz(os.environ[cacti_kimlik.PAROLA_ANAHTARI]) == "synthetic-password"


def test_tarayi_ci_hata_mesajini_sizdirmaz(monkeypatch):
    import shutil
    import subprocess

    monkeypatch.setenv(cacti_kimlik.KULLANICI_ANAHTARI, cacti_kimlik.koru("synthetic-user"))
    monkeypatch.setenv(cacti_kimlik.PAROLA_ANAHTARI, cacti_kimlik.koru("synthetic-password"))
    monkeypatch.setattr(shutil, "which", lambda _: "node")

    class Process:
        returncode = 1

        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, *args, **kwargs):
            return '{"error":"synthetic-password"}', None

    monkeypatch.setattr(subprocess, "Popen", Process)
    with pytest.raises(cacti.CactiHata) as exc:
        cacti.indir(["7"], 2026, 9)
    assert exc.value.kod == 502
    assert "synthetic-password" not in str(exc.value)


def test_bozuk_onbellek_yeniden_alinir(monkeypatch, tmp_path):
    calls = []

    def indir(ids, yil, ay):
        calls.append(1)
        return [{"anahtar": "cacti-7", "baslik": "Test", "gorsel": "data:image/png;base64," + base64.b64encode(png()).decode()}]

    monkeypatch.setattr(cacti, "indir", indir)
    cacti.grafikler(["7"], 2026, 9, tmp_path)
    next(tmp_path.glob("*.json")).write_text('[{"anahtar":"cacti-7","baslik":"Test","gorsel":"https://evil.test/x.png"}]', encoding="utf-8")
    cacti.grafikler(["7"], 2026, 9, tmp_path)
    assert len(calls) == 2


LOE = "http://lookouteyes/lookouteyes/Modules/Graph.aspx?ct=Stock&miid=741942&fn=AVG&val=val_delay"  # personelin bildigi ic adres


@pytest.mark.parametrize(
    "deger",
    [
        "http://lookouteyes/lookouteyes/Modules/Graph.aspx?ct=Stock&miid=741942&fn=AVG&val=val_delay",
        "https://TRAFIK.superonline.net/lookouteyes/modules/graph.aspx?val=val_delay&miid=0741942",
        "http://lookouteyes/lookouteyes/Modules/Graph.ashx?ct=Stock&miid=741942&fn=AVG&val=val_delay&e=1&s=0&r0=5",
    ],
)
def test_lookouteyes_baglantisi_kanonik(deger):
    assert cacti.grafik_id(deger) == LOE
    assert cacti.anahtar(LOE) == "loe-741942-avg-val_delay"


@pytest.mark.parametrize(
    "deger",
    [
        "http://evil.test/lookouteyes/Modules/Graph.aspx?miid=1&val=val_delay",
        "http://lookouteyes:8080/lookouteyes/Modules/Graph.aspx?miid=1&val=val_delay",
        "http://u:p@lookouteyes/lookouteyes/Modules/Graph.aspx?miid=1&val=val_delay",
        "http://lookouteyes/lookouteyes/Modules/Graph.aspx?miid=1",
        "http://lookouteyes/lookouteyes/Modules/Graph.aspx?miid=1&miid=2&val=v",
        "http://lookouteyes/lookouteyes/Modules/Graph.aspx?miid=0&val=v",
        "http://lookouteyes/lookouteyes/Modules/Graph.aspx?miid=1&val=a%27b",
        "http://lookouteyes/lookouteyes/Modules/Graph.aspx?miid=1&val=v#x",
    ],
)
def test_lookouteyes_gecersiz(deger):
    with pytest.raises(cacti.CactiHata):
        cacti.grafik_id(deger)


def test_lookouteyes_kisinin_kimligiyle_dogrudan_adrese_gider_ve_baslik_alir(monkeypatch):
    import json
    import shutil
    import subprocess

    monkeypatch.setattr(shutil, "which", lambda _: "node")  # sunucu DPAPI hesabi tanimsiz: Lookouteyes icin gerekmez
    encoded = base64.b64encode(png()).decode()

    class Process:
        returncode = 0

        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, data=None, **kwargs):
            govde = json.loads(data)
            assert (govde["username"], govde["password"], govde["loeOrigin"]) == ("ayse", "kisi-parolasi", "http://lookouteyes")
            assert govde["items"] == [{"tur": "loe", "ct": "Stock", "miid": "741942", "fn": "AVG", "val": "val_delay"}, {"tur": "cacti", "id": "7"}]
            return json.dumps({"images": [encoded, encoded], "titles": ["BR - MERKEZ\x07 - INT", ""]}), None

    monkeypatch.setattr(subprocess, "Popen", Process)
    result = cacti.indir([LOE, "7"], 2026, 9, ("ayse", "kisi-parolasi"))
    assert "kisi-parolasi" not in json.dumps(result)
    assert [g["anahtar"] for g in result] == ["loe-741942-avg-val_delay", "cacti-7"]
    aralik = "01.09.2026 00:00 – 30.09.2026 23:59"  # Eylul raporu: tam takvim ayi, Turkiye saati
    assert [g["baslik"] for g in result] == [f"BR - MERKEZ  - INT · {aralik}", f"Cacti #7 · {aralik}"]
    assert cacti.aralik_metni(2026, 2) == "01.02.2026 00:00 – 28.02.2026 23:59"
    assert cacti.aralik_metni(2025, 12) == "01.12.2025 00:00 – 31.12.2025 23:59"


def test_lookouteyes_http_yonteminde_reddedilir(monkeypatch):
    monkeypatch.setenv(cacti_kimlik.KULLANICI_ANAHTARI, cacti_kimlik.koru("synthetic-user"))
    monkeypatch.setenv(cacti_kimlik.PAROLA_ANAHTARI, cacti_kimlik.koru("synthetic-password"))
    monkeypatch.setenv("TAMLIFE_CACTI_MODE", "http")
    with pytest.raises(cacti.CactiHata) as exc:
        cacti.indir([LOE], 2026, 9, ("ayse", "p"))
    assert exc.value.kod == 503


def test_lookouteyes_eski_kanonik_bicim_ve_adres_ayari(monkeypatch):
    eski = "https://trafik.superonline.net/lookouteyes/Modules/Graph.aspx?ct=Stock&miid=741942&fn=AVG&val=val_delay"
    assert cacti.lookouteyes_mu(eski) and cacti.grafik_id(eski) == LOE
    assert cacti.loe_kok() == "http://lookouteyes"
    monkeypatch.setenv("TAMLIFE_LOOKOUTEYES_URL", "https://trafik.superonline.net/")
    assert cacti.loe_kok() == "https://trafik.superonline.net"
    monkeypatch.setenv("TAMLIFE_LOOKOUTEYES_URL", "http://evil.test")
    with pytest.raises(cacti.CactiHata):
        cacti.loe_kok()


def test_lookouteyes_parolasiz_428_ve_parola_dogrulama(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(cacti, "indir", lambda *a: calls.append(a) or [])
    with pytest.raises(cacti.CactiHata) as exc:
        cacti.grafikler([LOE], 2026, 9, tmp_path)
    assert exc.value.kod == 428 and not calls  # kayit yok, parola yok: ag erisimi yapilmaz
    for kotu in ("", None, 5, "x" * 257):
        with pytest.raises(cacti.CactiHata) as exc:
            cacti.kisi_kimligi("ayse", kotu)
        assert exc.value.kod == 400 and "x" * 20 not in str(exc.value)
    assert cacti.kisi_kimligi("ayse", "p") == ("ayse", "p")


def test_lookouteyes_kayitli_donem_parola_istemez(monkeypatch, tmp_path):
    def indir(ids, yil, ay, kimlik=None):
        assert kimlik == ("ayse", "p")
        return [{"anahtar": cacti.anahtar(LOE), "baslik": "BR", "gorsel": "data:image/png;base64," + base64.b64encode(png()).decode()}]

    monkeypatch.setattr(cacti, "indir", indir)
    assert cacti.grafikler([LOE], 2026, 9, tmp_path, kimlik=("ayse", "p"))
    assert cacti.grafikler([LOE], 2026, 9, tmp_path)[0]["baslik"] == "BR"  # ayni ay ikinci acilis: dosyadan, parolasiz
