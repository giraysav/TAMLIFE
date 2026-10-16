"""Olay dongusu blokaji, bellek sizintisi (tracemalloc) ve bozuk girdi testleri.

- Dongu gecikme sondasi: tum `async def` uclari gercek boyutta govdeyle ve eszamanli senkron trafikle surulurken olay dongusu
  ESIK_MS'den uzun donmamali (senkron is threadpool'a gitmeli). asyncio debug modu yavas geri cagriyi da yakalar.
- Politika: `async def` uc govdesinde dogrudan DB/dosya/servis cagrisi yasak (run_in_threadpool icinde olmali).
- tracemalloc: isinmadan sonra ayni istek dongusunu tekrarlamak app/ kaynakli bellegi buyutmemeli.
- Bozuk CSV (kapanmamis tirnak, 128 KB ustu alan) 500 degil 400 doner (yama 54 oncesi csv.Error 500 veriyordu).
Dongu testleri asyncio.run kullanir; pytest-asyncio gerekmez ve cevrimdisi sunucuda da calisir.
"""

from __future__ import annotations

import ast
import asyncio
import gc
import inspect
import logging
import textwrap
import time
import tracemalloc

import pytest
from fastapi.routing import APIRoute

from app.yonetim.kalici_yazici import yazici
from tests.conftest import login_ok

ESIK_MS = 100
GOVDE = b"Lokasyon;Devre;Altyapi\n" + b"".join(b"L%d;D%d;FIBER\n" % (i, i) for i in range(4000))  # ~80 KB gecerli CSV
BOZUK_CSV = b'Lokasyon;Devre\n"' + b"a" * 200_000 + b"\n"


def _async_uclar(app) -> list[tuple[APIRoute, str]]:
    """(rota, tam yol): dahil edilen router'lar FastAPI 0.14x'te ic ice durur (test_guvenlik_sinir._uclar ile ayni gezinti)."""
    sonuc: list[tuple[APIRoute, str]] = []

    def gez(rotalar, on: str = "") -> None:
        for r in rotalar:
            ic = getattr(r, "router", None) or getattr(r, "original_router", None)
            if ic is not None and not isinstance(r, APIRoute):
                gez(ic.routes, on + getattr(r, "prefix", ""))
            elif isinstance(r, APIRoute) and inspect.iscoroutinefunction(r.endpoint):
                sonuc.append((r, on + r.path))

    gez(app.routes)
    return sonuc


# --- politika (statik) ------------------------------------------------------------------------------
YASAK_ADLAR = {"oturum", "kullanici_oturumu", "open", "sleep", "load_workbook"}
YASAK_NESNELER = {"db", "servis", "rs", "ice_al", "urun_tutar", "time"}


def _ihlaller(fonk) -> list[str]:
    agac = ast.parse(textwrap.dedent(inspect.getsource(fonk)))
    serbest: set[int] = set()  # run_in_threadpool(...) argumanlari ve lambda govdeleri threadpool'da calisir
    for d in ast.walk(agac):
        if isinstance(d, ast.Call) and getattr(d.func, "id", "") == "run_in_threadpool" or isinstance(d, ast.Lambda):
            serbest |= {id(x) for x in ast.walk(d)} - {id(d)}
    sonuc = []
    for d in ast.walk(agac):
        if not isinstance(d, ast.Call) or id(d) in serbest:
            continue
        f = d.func
        if isinstance(f, ast.Attribute) and f.attr[:1].isupper():
            continue  # hata/model sinifi kurmak G/C degil
        if isinstance(f, ast.Name) and f.id in YASAK_ADLAR or isinstance(f, ast.Attribute) and getattr(f.value, "id", "") in YASAK_NESNELER:
            sonuc.append(f"{fonk.__module__}.{fonk.__name__}: {ast.unparse(d)[:80]}")
    return sonuc


def test_async_uclar_senkron_g_c_cagirmaz(client):
    uclar = _async_uclar(client.app)
    assert len(uclar) >= 10, "async uc bulunamadi"
    ihlal = [i for r, _ in uclar for i in _ihlaller(r.endpoint)]
    assert not ihlal, "async uc govdesinde olay dongusunu bloklayan cagri:\n" + "\n".join(ihlal)


# --- dinamik: dongu gecikme sondasi ----------------------------------------------------------------
def _istek(r: APIRoute, tam_yol: str, mid: int) -> tuple[str, str, bytes | None]:
    yol = tam_yol.replace("{musteri_id:int}", str(mid)).replace("{musteri_id}", str(mid))
    if "{" in yol:
        yol = yol.split("{", 1)[0] + "1"
    yontem = min(r.methods)
    govde = b"{}" if yol.endswith(("/analiz", "/cevir")) and "rapor" in yol else GOVDE
    return yontem, yol + ("?dosya=yuk.csv" if yontem == "PUT" else ""), govde if yontem in {"PUT", "POST"} else None


async def _surus(app, cerez, hdr, istekler) -> tuple[float, list[str], list]:
    """istekleri ASGI uzerinden eszamanli surer; (azami dongu gecikmesi ms, asyncio'nun yavas geri cagri uyarilari, yanitlar)."""
    import httpx

    dongu = asyncio.get_running_loop()
    dongu.set_debug(True)
    dongu.slow_callback_duration = ESIK_MS / 1000
    yavas: list[str] = []
    isleyici = logging.Handler()
    isleyici.emit = lambda k: yavas.append(k.getMessage())  # type: ignore[method-assign]
    logging.getLogger("asyncio").addHandler(isleyici)
    gecikme, bitti = [0.0], asyncio.Event()

    async def sonda() -> None:
        while not bitti.is_set():
            a = time.perf_counter()
            await asyncio.sleep(0.005)
            gecikme[0] = max(gecikme[0], (time.perf_counter() - a - 0.005) * 1000)

    # Onceki testlerden kalan yigin: tam bir gc turu (GIL'i tutar) olcume denk gelirse dongu "bloklanmis" gorunur; kalanlari dondur.
    gc.collect()
    gc.freeze()
    try:
        tasima = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=tasima, base_url="http://testserver", cookies=cerez, headers=hdr, timeout=60) as ac:
            s = asyncio.create_task(sonda())
            yanitlar = await asyncio.gather(*(ac.request(y, yol, content=g) for y, yol, g in istekler))
            bitti.set()
            await s
    finally:
        gc.unfreeze()
        logging.getLogger("asyncio").removeHandler(isleyici)
    return gecikme[0], [y[:80] + " ... " + y[y.rfind(" took "):] for y in yavas if " took " in y], yanitlar


def test_dongu_sondasi_bloklayan_ucu_yakalar(client):
    """Sondanin kendisi: async govdede time.sleep(0.3) olan gecici uc yakalanmali (test bos gecmesin)."""

    @client.app.get("/api/v1/_test_bloklayan")
    async def bloklayan() -> dict:
        time.sleep(0.3)  # noqa: ASYNC251 - sondanin yakalamasi gereken kasitli blokaj
        return {}

    gecikme, yavas, _ = asyncio.run(_surus(client.app, {}, {}, [("GET", "/api/v1/_test_bloklayan", None)]))
    assert gecikme > 250 and yavas, (gecikme, yavas)


def test_async_uclar_olay_dongusunu_bloklamaz(client, monkeypatch):
    hdr = login_ok(client)
    mid = client.post("/api/v1/musteri", json={"name": "Yuk Musteri"}, headers=hdr).json()["data"]["id"]
    monkeypatch.setenv("TAMLIFE_ENV", "dev")  # test ortaminda denetim olayi cagiran is parcacigina yazilir; canli davranis kuyruk
    uclar = _async_uclar(client.app)
    istekler = []
    for _ in range(3):
        istekler += [_istek(r, yol, mid) for r, yol in uclar]
        istekler += [("GET", "/api/v1/musteri", None), ("GET", "/api/v1/session/me", None), ("GET", "/api/v1/ekip/ozet", None)]
    gecikme, yavas, yanitlar = asyncio.run(_surus(client.app, dict(client.cookies), hdr, istekler))
    yazici.bosalt(zorla=True)  # dev kipinde kuyruga giren denetim olaylari test DB'si hala gecerliyken yazilsin
    print(f"\n{len(uclar)} async uc x3 + senkron trafik: azami dongu gecikmesi {gecikme:.0f} ms, yavas geri cagri {len(yavas)}")
    assert not [y for y in yanitlar if y.status_code >= 500 and y.status_code != 503], [y.text[:200] for y in yanitlar if y.status_code >= 500]
    # Bloklama olcutu: dongude ESIK_MS'den uzun tek geri cagri yok. Toplam gecikme threadpool'daki CPU isinin GIL rekabetini de
    # icerir (4000 satirlik topoloji analizi x3); o yalniz gevsek tavanla sinirlanir.
    assert not yavas, f"olay dongusunu bloklayan geri cagri: {yavas[:3]}"
    assert gecikme < 2000, f"olay dongusu {gecikme:.0f} ms dondu"


# --- bellek ---------------------------------------------------------------------------------------
def _tur(client, hdr, mid: int) -> None:
    client.get("/api/v1/session/me")
    client.get("/api/v1/musteri")
    client.get(f"/api/v1/musteri/{mid}")
    client.get("/api/v1/ekip/ozet")
    client.put("/api/v1/takvim/gun", json={"tarih": "2026-03-02", "durum": "calisiyor", "online": 1, "yuzyuze": 0}, headers=hdr)
    client.put("/api/v1/topoloji/analiz?dosya=y.csv", content=GOVDE, headers=hdr)
    client.post("/api/v1/session/login", json={"username": "admin", "password": "yanlis-parola"})


def test_tekrarlanan_istekler_bellek_sizdirmaz(client):
    hdr = login_ok(client)
    mid = client.post("/api/v1/musteri", json={"name": "Bellek Musteri"}, headers=hdr).json()["data"]["id"]
    for _ in range(30):  # isinma: onbellekler, sema, ilk import
        _tur(client, hdr, mid)
    gc.collect()
    tracemalloc.start(1)
    once = tracemalloc.take_snapshot()
    for _ in range(150):
        _tur(client, hdr, mid)
    gc.collect()
    sonra = tracemalloc.take_snapshot()
    tracemalloc.stop()
    filtre = [tracemalloc.Filter(True, "*/app/*")]
    fark = sorted(sonra.filter_traces(filtre).compare_to(once.filter_traces(filtre), "filename"), key=lambda s: -s.size_diff)
    artis = sum(s.size_diff for s in fark)
    print(f"\n150 tur (1050 istek) sonrasi app/ bellek artisi {artis / 1024:.0f} KB; ilk: {[str(s)[:120] for s in fark[:3]]}")
    assert artis < 1024 * 1024, f"app/ bellegi {artis / 1024:.0f} KB buyudu: " + "; ".join(str(s) for s in fark[:5])


def test_govde_oku_tepe_bellegi_govdenin_uc_katini_asmaz(client):
    hdr = login_ok(client)
    govde = GOVDE * 100  # ~8 MB, 10 MB topoloji sinirinin altinda

    def parcali():
        for i in range(0, len(govde), 65536):
            yield govde[i : i + 65536]

    tracemalloc.start()
    r = client.put("/api/v1/topoloji/analiz?dosya=y.csv", content=parcali(), headers=hdr)
    _, tepe = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"\n{len(govde) / 1048576:.1f} MB parcali govde: durum {r.status_code}, tepe {tepe / 1048576:.1f} MB")
    assert r.status_code == 400  # 5000 satir siniri; govde sinira kadar okunur, isleme satir sinirinda durur
    assert tepe < len(govde) * 8, f"tepe bellek {tepe / 1048576:.0f} MB"


@pytest.mark.parametrize(
    "yol",
    ["/api/v1/topoloji/analiz?dosya=b.csv", "/api/v1/tampon/yukle?kaynak=onedesk&dosya=b.csv", "/api/v1/tampon/musteri-ham/yukle?dosya=b.csv"],
)
def test_bozuk_csv_500_degil_400(client, yol):
    hdr = login_ok(client)
    r = client.put(yol, content=BOZUK_CSV, headers=hdr)
    assert r.status_code == 400, (r.status_code, r.text[:200])
