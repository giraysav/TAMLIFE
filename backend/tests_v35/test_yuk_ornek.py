# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Gercek uvicorn ornegine karsi yuk/stres/spike/kilit/slowloris/govde testleri (gecici bos DB, ayri port; canliya dokunmaz).

Varsayilan kosuda calismaz (pytest.ini: -m "not yuk"); CI'da ayri asama:  pytest tests -m yuk -q -s -p no:cacheprovider
Olculen (2026-10-14, 8 cekirdek bulut): yama 54 oncesi 100 eszamanlida %61 zaman asimi (90 sn), 10 istek/sn; sonrasi %0, 99 istek/sn.
35 sn yazma kilidinde saglik ucu 29,9 sn -> 36 ms, oturumlu okuma 33 sn -> 6 ms.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

from araclar.yuk import yuk_testi as y
from araclar.yuk.ornek import Ornek, bos_db_kur

pytestmark = pytest.mark.yuk


def _bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def ornek(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Ornek]:
    dizin: Path = tmp_path_factory.mktemp("yuk")
    bos_db_kur(dizin)
    o = Ornek(_bos_port(), dizin).baslat()
    yield o
    o.durdur()


@pytest.fixture(scope="module")
def ist(ornek: Ornek) -> y.Istemci:
    return y.Istemci(f"http://127.0.0.1:{ornek.port}", ornek.kullanici, ornek.parola)


def test_karisik_100_eszamanli_okuma_yazma_hatasiz(ist):
    o = y.karisik(ist, 100, 15)
    print(f"\n100 eszamanli: {o.toplam / 15:.0f} istek/sn {o.ozet()}")
    assert o.hata_orani == 0, o.durumlar
    assert o.yuzdelik(0.95) < 5000


def test_kirilma_noktasi_200_altinda_degil(ist):
    nokta, basamaklar = y.kirilma(ist, (25, 50, 100, 200), sure=8, p95_sinir_ms=5000)
    print(f"\nkirilma noktasi: {nokta}")
    assert nokta is None or nokta > 100, [(n, o.ozet()) for n, o in basamaklar]


def test_spike_sonrasi_toparlanir(ist):
    once, tepe, sonra = y.spike(ist, taban=5, tepe=300, sure=8)
    print(f"\nonce  {once.ozet()}\ntepe  {tepe.ozet()}\nsonra {sonra.ozet()}")
    assert tepe.hata_orani < 0.01, tepe.durumlar  # 300 eszamanlida dahi istek dusmez (kuyrukta bekler)
    assert sonra.hata_orani == 0 and sonra.yuzdelik(0.95) < 3 * max(once.yuzdelik(0.95), 100)


def test_busy_timeout_asilinca_503_saglik_ve_okuma_donmaz(ornek, ist):
    yazma, okuma, saglik = y.kilit(ist, str(ornek.db), tut_sn=35, yazici=60)
    print(f"\nyazma  {yazma.ozet()}\nokuma  {okuma.ozet()}\nsaglik {saglik.ozet()}")
    assert set(yazma.durumlar) <= {200, 503}, yazma.durumlar  # 30 sn asilan yazma 503 (TL-DB-02); 500 ya da kopma yok
    assert 503 in yazma.durumlar, "kilit 35 sn surdu; busy_timeout (30 sn) asilan yazma olmali"
    assert max(yazma.sureler) < 34_000, "503 ariza kaydini beklemeden donmeli (kilit 35 sn)"
    assert okuma.yuzdelik(0.99) < 2000, "WAL: yazma kilidi okumayi bekletmemeli (havuz/is parcacigi aclik)"
    assert saglik.toplam > 50 and saglik.yuzdelik(0.99) < 1000, "saglik ucu dolu is parcacigi havuzunda donmamali"


def test_slowloris_500_baglanti_saglik_ucunu_durdurmaz(ist):
    acik, saglik = y.slowloris(ist, 500, sure=15)
    print(f"\nacik yavas soket {acik}; saglik {saglik.ozet()}")
    assert saglik.hata_orani == 0 and saglik.yuzdelik(0.99) < 1000


def test_sinir_ustu_parcali_govde_413_ve_bellek_sinirli(ornek, ist):
    bas = ornek.rss_mb()
    o, tepe = y.govde(ist, eszamanli=20, mb=12, bellek=ornek.rss_mb)  # topoloji siniri 10 MB, Content-Length yok (chunked)
    print(f"\n20 x 12 MB chunked: {o.ozet()}; RSS {bas:.0f} -> tepe {tepe:.0f} MB")
    assert set(o.durumlar) <= {413, "ConnectionResetError", "BrokenPipeError"} and 413 in o.durumlar, o.durumlar
    assert tepe - bas < 20 * 10 * 2 + 100, "govde_oku siniri asan akisi tamponluyor"  # en cok sinir kadar x2 (bytearray + bytes)
    assert y.Istemci(f"http://127.0.0.1:{ornek.port}", "", "").istek("GET", y.SAGLIK)[0] == 200


def test_yavas_parcali_govde_isci_havuzunu_kilitlemez(ornek, ist):
    dur = __import__("threading").Event()
    saglik = y.saglik_sondasi(ist, dur)
    o, _ = y.govde(ist, eszamanli=50, mb=2, parca_kb=16, gecikme_ms=40)  # 50 yavas yukleyici, her biri ~5 sn
    dur.set()
    print(f"\n50 yavas yukleme: {o.ozet()}; saglik {saglik.ozet()}")
    # yukleme suresince saglik ucu akar; 50 govde ayni anda bitip ayristirilirken GIL paylasimi tek ornekte ~1,5 sn tepe yapabilir
    assert saglik.hata_orani == 0 and saglik.yuzdelik(0.9) < 500 and max(saglik.sureler) < 3000
