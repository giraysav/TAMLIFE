# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Takvim uctan uca senkron (2026-10-15 kullanici bildirimi: "19 kisi veri giriyor, admin panelde gorunmuyor; herkesin veri girdigi
ve senkron oldugu yapiyi teyit et"). Her kisi kendi oturumuyla HTTP uzerinden yazar; admin ayni anda TAM Takvim, kisi gunleri ve
Genel Bakis ozetinde hepsini, ikinci yazmayi da hemen (onbelleksiz) gorur. Teshis araci her kisinin dosyasini sayar."""

from __future__ import annotations

from datetime import datetime

from app.takvim import teshis

KISI = 19
YIL = 2026


def _giris(client, monkeypatch, kullanici: str, rol: str) -> dict[str, str]:
    client.post("/api/v1/session/logout")
    monkeypatch.setenv("TAMLIFE_LOCAL_USER", kullanici)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", rol)
    r = client.post("/api/v1/session/login", json={"username": kullanici, "password": "test-parola-1"})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": client.cookies.get("tamlife_csrf") or ""}


def test_herkesin_girdigi_takvim_admine_aninda_gorunur(client, monkeypatch):
    kisiler = [f"tam.kisi{i:02d}" for i in range(1, KISI + 1)]
    bugun = datetime.now().date().isoformat()
    for i, ad in enumerate(kisiler, start=1):
        hdr = _giris(client, monkeypatch, ad, "TeamMember")
        gunler = (
            {"tarih": "2026-10-05", "durum": "calisiyor", "online": i, "yuzyuze": 1, "toplanti_ozeti": f"{ad} toplanti", "yapilan_isler": f"{ad} is"},
            {"tarih": "2026-10-06", "durum": "yillik_izin"},
            {"tarih": bugun, "durum": "raporlu"},
        )
        for g in gunler:
            r = client.put("/api/v1/takvim/gun", json=g, headers=hdr)
            assert r.status_code == 200, r.text

    _giris(client, monkeypatch, "yonetici", "admin")
    ekip = client.get("/api/v1/takvim/ekip", params={"yil": YIL, "ceyrek": 0}).json()["data"]
    uyeler = {u["kullanici"]: u for u in ekip["uyeler"]}
    assert sorted(uyeler) == kisiler  # admin satir acmaz, 19 kisinin hepsi var
    for i, ad in enumerate(kisiler, start=1):
        u = uyeler[ad]
        assert (u["online"], u["yuzyuze"], u["is_gunu"], u["ozet_gunu"], u["kayitli_gun"]) == (i, 1, 1, 1, 3 if bugun[:4] == "2026" else 2)
        assert u["durumlar"]["yillik_izin"] == 1
        # kisinin kendi ekranindaki yil sayilariyla ayni (kayitsiz is gunu Calisiyor sayilir)
        _giris(client, monkeypatch, ad, "TeamMember")
        kendi = client.get("/api/v1/takvim/ben", params={"yil": YIL, "ay": 10}).json()["data"]["yil_ozet"]["gorunen"]
        assert u["durumlar"] == kendi
        _giris(client, monkeypatch, "yonetici", "admin")
    # 2026-10-20: ekip satiri yalniz toplantilari toplar; gun kirilimlari takvimden (kisiye ozel izin kisi satirlarinda)
    assert ekip["genel"]["online"] == sum(range(1, KISI + 1)) and ekip["genel"]["durumlar"]["yillik_izin"] == 0
    assert sum(u["durumlar"]["yillik_izin"] for u in ekip["uyeler"]) == KISI

    # admin kisinin gunlerini metinleriyle gorur
    u1 = uyeler[kisiler[0]]
    gunler = client.get(f"/api/v1/takvim/ekip/{u1['id']}", params={"yil": YIL, "ceyrek": 4}).json()["data"]["gunler"]
    g = next(g for g in gunler if g["tarih"] == "2026-10-05")
    assert (g["online"], g["toplanti_ozeti"], g["yapilan_isler"]) == (1, "tam.kisi01 toplanti", "tam.kisi01 is")

    # Genel Bakis ozeti de 19 kisiyi ve bugunku durumu gorur
    ozet = client.get("/api/v1/ekip/ozet").json()["data"]
    satirlar = {s["id"]: s for s in ozet["satirlar"]}
    assert all(uyeler[ad]["id"] in satirlar for ad in kisiler)
    if bugun[:4] == "2026":
        assert {satirlar[uyeler[ad]["id"]]["bugun"] for ad in kisiler} == {"raporlu"}

    # ikinci yazma admin'e hemen yansir (onbellek yok)
    hdr = _giris(client, monkeypatch, kisiler[0], "TeamMember")
    assert client.put("/api/v1/takvim/gun", json={"tarih": "2026-10-05", "durum": "calisiyor", "online": 9}, headers=hdr).status_code == 200
    _giris(client, monkeypatch, "yonetici", "admin")
    yeni = {u["kullanici"]: u for u in client.get("/api/v1/takvim/ekip", params={"yil": YIL, "ceyrek": 0}).json()["data"]["uyeler"]}
    assert yeni[kisiler[0]]["online"] == 9

    # admin olmayan yonetici metni gormez, sayilari gorur
    _giris(client, monkeypatch, "mudur", "TeamMngr")
    gunler = client.get(f"/api/v1/takvim/ekip/{u1['id']}", params={"yil": YIL, "ceyrek": 4}).json()["data"]["gunler"]
    g = next(g for g in gunler if g["tarih"] == "2026-10-05")
    assert g["online"] == 9 and "toplanti_ozeti" not in g

    # teshis: her hesabin dosyasi ve kayit sayisi, hesapsiz dosya yok
    rapor = "\n".join(teshis.rapor())
    for ad in kisiler:
        satir = next(s for s in rapor.splitlines() if s.startswith(f"{ad} |"))
        assert "| evet | " in satir and f"{ad}.db" in satir
    assert "Hesabi olmayan takvim dosyalari: 0" in rapor
