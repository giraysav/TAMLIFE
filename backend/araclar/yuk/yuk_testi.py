"""Yuk, stres, spike, SQLite kilit, slowloris ve buyuk govde testleri (yalniz standart kutuphane; cevrimdisi sunucuda pip gerekmez).

YALNIZ ayri test ornegine karsi calistirin (araclar.yuk.ornek; canli DB'nin kopyasi, ayri port). 8117/443 reddedilir.

  ..\\.venv\\Scripts\\python.exe -m araclar.yuk.yuk_testi http://127.0.0.1:8199 --kullanici yuk.admin --parola <p> kirilma
  ... karisik --eszamanli 40 --sure 60        okuma/yazma karisimi (takvim + profil yazar, musteri/ekip okur)
  ... spike --tepe 300                        5 -> 300 -> 5 eszamanli; toparlanma suresi
  ... kilit --db <kopya>\\yuk.db --tut 35      kopya DB'de 35 sn yazma kilidi + 60 yazici + saglik sondasi (busy_timeout 30 sn asilir)
  ... slowloris --baglanti 500                yavas baslik; bu sirada saglik ucu yanit vermeli
  ... govde --eszamanli 20 --mb 12            ayni anda sinir ustu (10 MB) parcali govde; 413 ve bellek (--pid ile)

Cikis kodu: 0 = beklenti tuttu, 1 = kirildi (ayrinti ciktida).
"""

from __future__ import annotations

import argparse
import http.client
import json
import random
import socket
import sqlite3
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from http.cookies import SimpleCookie
from urllib.parse import urlsplit

OKUMA = ("/api/v1/session/me", "/api/v1/musteri", "/api/v1/ekip/ozet", "/api/v1/modules")
SAGLIK = "/api/v1/health"


@dataclass
class Olcum:
    sureler: list[float] = field(default_factory=list)  # ms
    durumlar: Counter = field(default_factory=Counter)
    kilit: threading.Lock = field(default_factory=threading.Lock)

    def ekle(self, ms: float, durum: int | str) -> None:
        with self.kilit:
            self.sureler.append(ms)
            self.durumlar[durum] += 1

    def yuzdelik(self, p: float) -> float:
        s = sorted(self.sureler)
        return s[min(len(s) - 1, int(len(s) * p))] if s else 0.0

    @property
    def toplam(self) -> int:
        return sum(self.durumlar.values())

    @property
    def hata_orani(self) -> float:
        hatali = sum(n for d, n in self.durumlar.items() if not (isinstance(d, int) and d < 400))
        return hatali / self.toplam if self.toplam else 0.0

    def ozet(self) -> str:
        if not self.sureler:
            return "istek yok"
        return (f"istek={self.toplam} p50={self.yuzdelik(.5):.0f}ms p95={self.yuzdelik(.95):.0f}ms p99={self.yuzdelik(.99):.0f}ms "
                f"azami={max(self.sureler):.0f}ms hata=%{self.hata_orani * 100:.2f} durumlar={dict(self.durumlar)}")  # fmt: skip


class Istemci:
    """Tek oturum; is parcacigi basina ayri baglanti (keep-alive)."""

    def __init__(self, taban: str, kullanici: str, parola: str, zaman_asimi: float = 90) -> None:
        p = urlsplit(taban)
        if p.port in (8117, 443) or p.scheme == "https":
            raise SystemExit("canli panele (8117/443/https) karsi calistirilmaz; araclar.yuk.ornek ile ayri ornek acin")
        self.host, self.port, self.zaman_asimi = p.hostname or "127.0.0.1", p.port or 80, zaman_asimi
        self.cerez: dict[str, str] = {}
        self._yerel = threading.local()
        if kullanici:
            d, _ = self.istek("POST", "/api/v1/session/login", {"username": kullanici, "password": parola})
            if d != 200:
                raise SystemExit(f"giris basarisiz: {d}")

    def _baglanti(self) -> http.client.HTTPConnection:
        if getattr(self._yerel, "c", None) is None:
            self._yerel.c = http.client.HTTPConnection(self.host, self.port, timeout=self.zaman_asimi)
        return self._yerel.c

    def istek(self, yontem: str, yol: str, govde: object = None) -> tuple[int | str, float]:
        b = {"Accept": "application/json", "Host": self.host}
        if self.cerez:
            b["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cerez.items())
            b["X-CSRF-Token"] = self.cerez.get("tamlife_csrf", "")
        veri = json.dumps(govde).encode() if govde is not None else None
        if veri is not None:
            b["Content-Type"] = "application/json"
        bas = time.perf_counter()
        try:
            c = self._baglanti()
            c.request(yontem, yol, body=veri, headers=b)
            r = c.getresponse()
            r.read()
            for satir in r.headers.get_all("Set-Cookie") or []:
                for ad, m in SimpleCookie(satir).items():
                    self.cerez[ad] = m.value
            durum: int | str = r.status
        except (OSError, http.client.HTTPException) as h:
            self._yerel.c = None
            durum = type(h).__name__
        return durum, (time.perf_counter() - bas) * 1000


def _yazma_govdesi(rnd: random.Random) -> tuple[str, str, dict]:
    if rnd.random() < 0.5:
        gun = date(2026, 1, 1) + timedelta(days=rnd.randrange(0, 365))
        return "PUT", "/api/v1/takvim/gun", {"tarih": gun.isoformat(), "durum": "calisiyor", "online": rnd.randrange(1, 5), "yuzyuze": 0}
    return "PUT", "/api/v1/session/profile", {"phone": f"+90 532 {rnd.randrange(1000000, 9999999)}"}


def karisik(ist: Istemci, eszamanli: int, sure: float, yazma_orani: float = 0.3) -> Olcum:
    """eszamanli is parcacigi `sure` boyunca bekleme olmadan istek atar (kapali dongu: her biri bir oncekinin yanitini bekler)."""
    olcum, bitis = Olcum(), time.monotonic() + sure

    def isci(n: int) -> None:
        rnd = random.Random(n)
        while time.monotonic() < bitis:
            if rnd.random() < yazma_orani:
                yontem, yol, govde = _yazma_govdesi(rnd)
            else:
                yontem, yol, govde = "GET", rnd.choice(OKUMA), None
            olcum.ekle(*reversed(ist.istek(yontem, yol, govde)))

    _kos([threading.Thread(target=isci, args=(n,), daemon=True) for n in range(eszamanli)])
    return olcum


def kirilma(ist: Istemci, basamaklar: tuple[int, ...] = (10, 25, 50, 100, 200, 400), sure: float = 15, p95_sinir_ms: float = 2000,
            hata_siniri: float = 0.01) -> tuple[int | None, list[tuple[int, Olcum]]]:  # fmt: skip
    """Eszamanliligi basamak basamak artirir; hata orani ya da p95 siniri asilan ilk basamak kirilma noktasidir (None: kirilmadi)."""
    sonuc: list[tuple[int, Olcum]] = []
    for n in basamaklar:
        o = karisik(ist, n, sure)
        sonuc.append((n, o))
        print(f"  eszamanli={n:<4} {o.ozet()}", flush=True)
        if o.hata_orani > hata_siniri or o.yuzdelik(0.95) > p95_sinir_ms:
            return n, sonuc
    return None, sonuc


def spike(ist: Istemci, taban: int = 5, tepe: int = 300, sure: float = 10) -> tuple[Olcum, Olcum, Olcum]:
    once = karisik(ist, taban, sure)
    ani = karisik(ist, tepe, sure)
    sonra = karisik(ist, taban, sure)
    return once, ani, sonra


def saglik_sondasi(ist: Istemci, dur: threading.Event, aralik: float = 0.25) -> Olcum:
    olcum = Olcum()
    yalin = Istemci(f"http://{ist.host}:{ist.port}", "", "", zaman_asimi=60)

    def dongu() -> None:
        while not dur.is_set():
            olcum.ekle(*reversed(yalin.istek("GET", SAGLIK)))
            time.sleep(aralik)

    threading.Thread(target=dongu, daemon=True).start()
    return olcum


def kilit(ist: Istemci, db_yolu: str, tut_sn: float = 35, yazici: int = 60) -> tuple[Olcum, Olcum, Olcum]:
    """KOPYA DB'de BEGIN IMMEDIATE ile yazma kilidi tutulur (isci/yedek uzun yazmasinin benzeri). Bu sirada `yazici` adet yazma
    istegi, okuma istekleri ve saglik sondasi gonderilir. Donus: (yazma, okuma, saglik)."""
    hazir, birak = threading.Event(), threading.Event()

    def tut() -> None:
        b = sqlite3.connect(db_yolu, timeout=0, isolation_level=None)
        b.execute("BEGIN IMMEDIATE")
        hazir.set()
        birak.wait(tut_sn)
        b.execute("ROLLBACK")
        b.close()

    threading.Thread(target=tut, daemon=True).start()
    hazir.wait(10)
    dur = threading.Event()
    saglik = saglik_sondasi(ist, dur)
    yazma, okuma = Olcum(), Olcum()

    def yaz(n: int) -> None:
        yazma.ekle(*reversed(ist.istek(*_yazma_govdesi(random.Random(n)))))

    def oku() -> None:
        time.sleep(2)  # yazicilar is parcacigi havuzunu doldursun
        for _ in range(5):
            okuma.ekle(*reversed(ist.istek("GET", "/api/v1/session/me")))

    t0 = time.monotonic()
    _kos([threading.Thread(target=yaz, args=(n,), daemon=True) for n in range(yazici)] + [threading.Thread(target=oku, daemon=True)])
    birak.set()
    dur.set()
    print(f"  kilit {tut_sn:.0f} sn, gecen {time.monotonic() - t0:.1f} sn", flush=True)
    return yazma, okuma, saglik


def slowloris(ist: Istemci, baglanti: int = 500, sure: float = 30) -> tuple[int, Olcum]:
    """Her soket basligi bayt bayt, 5 sn arayla yollar ve hic bitirmez. Bu sirada saglik ucu olculur. Donus: (acik kalan soket, saglik)."""
    soketler: list[socket.socket] = []
    for _ in range(baglanti):
        try:
            s = socket.create_connection((ist.host, ist.port), timeout=5)
            s.sendall(f"GET {SAGLIK} HTTP/1.1\r\nHost: {ist.host}\r\n".encode())
            soketler.append(s)
        except OSError:
            break
    dur = threading.Event()
    saglik = saglik_sondasi(ist, dur)
    bitis = time.monotonic() + sure
    while time.monotonic() < bitis:
        for s in list(soketler):
            try:
                s.sendall(b"X-a: b\r\n")
            except OSError:
                soketler.remove(s)
        time.sleep(5)
    dur.set()
    acik = len(soketler)
    for s in soketler:
        s.close()
    return acik, saglik


def govde(ist: Istemci, eszamanli: int = 20, mb: int = 12, parca_kb: int = 64, gecikme_ms: float = 0, yol: str = "/api/v1/topoloji/analiz?dosya=y.csv",
          bellek=None) -> tuple[Olcum, float]:  # fmt: skip
    """eszamanli istemci Content-Length VERMEDEN (chunked) mb buyuklugunde govde yollar. bellek: surec RSS'ini MB donen cagrilabilir.
    Donus: (olcum, olculen en yuksek RSS MB)."""
    olcum, tepe, dur = Olcum(), [bellek() if bellek else 0.0], threading.Event()
    parca = b"a," * (parca_kb * 512)

    def izle() -> None:
        while not dur.is_set() and bellek:
            tepe[0] = max(tepe[0], bellek())
            time.sleep(0.05)

    def yolla() -> None:
        c = http.client.HTTPConnection(ist.host, ist.port, timeout=120)
        b = {"Host": ist.host, "Cookie": "; ".join(f"{k}={v}" for k, v in ist.cerez.items()), "X-CSRF-Token": ist.cerez.get("tamlife_csrf", ""),
             "Content-Type": "application/octet-stream"}  # fmt: skip

        def akis():
            for _ in range(mb * 1024 // parca_kb):
                if gecikme_ms:
                    time.sleep(gecikme_ms / 1000)
                yield parca

        bas = time.perf_counter()
        try:
            c.request("PUT", yol, body=akis(), headers=b, encode_chunked=True)
            r = c.getresponse()
            r.read()
            durum: int | str = r.status
        except (OSError, http.client.HTTPException) as h:
            durum = type(h).__name__  # sunucu 413'u erken verip baglantiyi kapatirsa yazma tarafinda kopma normaldir
        olcum.ekle((time.perf_counter() - bas) * 1000, durum)

    threading.Thread(target=izle, daemon=True).start()
    _kos([threading.Thread(target=yolla, daemon=True) for _ in range(eszamanli)])
    dur.set()
    return olcum, tepe[0]


def _kos(iplikler: list[threading.Thread]) -> None:
    for t in iplikler:
        t.start()
    for t in iplikler:
        t.join()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("taban")
    p.add_argument("--kullanici", required=True)
    p.add_argument("--parola", required=True)
    alt = p.add_subparsers(dest="senaryo", required=True)
    k = alt.add_parser("karisik")
    k.add_argument("--eszamanli", type=int, default=40)
    k.add_argument("--sure", type=float, default=60)
    alt.add_parser("kirilma")
    s = alt.add_parser("spike")
    s.add_argument("--tepe", type=int, default=300)
    kl = alt.add_parser("kilit")
    kl.add_argument("--db", required=True, help="ornegin KOPYA DB dosyasi (canli dev.db DEGIL)")
    kl.add_argument("--tut", type=float, default=35)
    kl.add_argument("--yazici", type=int, default=60)
    sl = alt.add_parser("slowloris")
    sl.add_argument("--baglanti", type=int, default=500)
    g = alt.add_parser("govde")
    g.add_argument("--eszamanli", type=int, default=20)
    g.add_argument("--mb", type=int, default=12)
    g.add_argument("--pid", type=int)
    a = p.parse_args()
    ist = Istemci(a.taban, a.kullanici, a.parola)
    if a.senaryo == "karisik":
        o = karisik(ist, a.eszamanli, a.sure)
        print(o.ozet())
        return int(o.hata_orani > 0.01)
    if a.senaryo == "kirilma":
        nokta, _ = kirilma(ist)
        print(f"KIRILMA NOKTASI: {nokta if nokta else 'yok (en yuksek basamak gecti)'} eszamanli istemci")
        return 0
    if a.senaryo == "spike":
        once, ani, sonra = spike(ist, tepe=a.tepe)
        for ad, o in (("once", once), ("tepe", ani), ("sonra", sonra)):
            print(f"{ad:<6} {o.ozet()}")
        return int(sonra.hata_orani > 0.01 or sonra.yuzdelik(0.95) > 3 * max(once.yuzdelik(0.95), 50))
    if a.senaryo == "kilit":
        yazma, okuma, saglik = kilit(ist, a.db, a.tut, a.yazici)
        print(f"yazma  {yazma.ozet()}\nokuma  {okuma.ozet()}\nsaglik {saglik.ozet()}")
        return int(any(isinstance(d, str) or d == 500 for d in yazma.durumlar) or saglik.yuzdelik(0.99) > 1000)
    if a.senaryo == "slowloris":
        acik, saglik = slowloris(ist, a.baglanti)
        print(f"acik yavas soket={acik}\nsaglik {saglik.ozet()}")
        return int(saglik.hata_orani > 0 or saglik.yuzdelik(0.99) > 1000)
    if a.senaryo == "govde":
        from araclar.yuk.ornek import rss_mb

        o, tepe = govde(ist, a.eszamanli, a.mb, bellek=(lambda: rss_mb(a.pid)) if a.pid else None)
        print(f"{o.ozet()}\nen yuksek RSS={tepe:.0f} MB")
        return int(any(d not in (413, "ConnectionResetError", "BrokenPipeError") for d in o.durumlar))
    return 2


if __name__ == "__main__":
    sys.exit(main())
