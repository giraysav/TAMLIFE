"""Locust ile yuk / spike (istege bagli; cevrimdisi sunucuda pip gerekmeyen esdegeri araclar.yuk.yuk_testi).

YALNIZ ayri test ornegine (araclar.yuk.ornek, kopya DB, ayri port) karsi:
  set TAMLIFE_YUK_KULLANICI=yuk.admin & set TAMLIFE_YUK_PAROLA=<ornegin yazdigi parola>
  locust -f araclar\\yuk\\locustfile.py --host http://127.0.0.1:8199 --headless -u 300 -r 50 -t 2m --csv var\\yuk\\sonuc
  TAMLIFE_YUK_SEKIL=spike ile 5 -> 300 -> 5 kullanici sekli (LoadTestShape) kullanilir.
Cevrimdisi kurulum (internetli makinede): pip download locust -d tekerlek ; sunucuda: pip install --no-index -f tekerlek locust
"""

from __future__ import annotations

import os
import random
from datetime import date, timedelta
from urllib.parse import urlsplit

from locust import HttpUser, LoadTestShape, between, events, task

KULLANICI = os.environ.get("TAMLIFE_YUK_KULLANICI", "yuk.admin")
PAROLA = os.environ.get("TAMLIFE_YUK_PAROLA", "")


@events.test_start.add_listener
def _canli_degil(environment, **_):  # type: ignore[no-untyped-def]
    p = urlsplit(environment.host or "")
    if p.scheme == "https" or p.port in (8117, 443, None):
        raise SystemExit("canli panele (https/8117/443) karsi calistirilmaz; araclar.yuk.ornek ile ayri ornek acin")


class PanelKullanicisi(HttpUser):
    wait_time = between(0, 0.2)

    def on_start(self) -> None:
        r = self.client.post("/api/v1/session/login", json={"username": KULLANICI, "password": PAROLA}, name="giris")
        if r.status_code != 200:
            raise RuntimeError(f"giris {r.status_code}")
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get("tamlife_csrf", "")

    @task(4)
    def musteri_listesi(self) -> None:
        self.client.get("/api/v1/musteri", name="GET musteri")

    @task(2)
    def ekip_ozeti(self) -> None:
        self.client.get("/api/v1/ekip/ozet", name="GET ekip/ozet")

    @task(2)
    def oturum(self) -> None:
        self.client.get("/api/v1/session/me", name="GET session/me")

    @task(2)
    def takvim_yaz(self) -> None:  # kisinin kendi SQLite dosyasi; ayni gune eszamanli yazma yarisi (db.yazma_kilidi)
        gun = date(2026, 1, 1) + timedelta(days=random.randrange(0, 30))
        self.client.put("/api/v1/takvim/gun", json={"tarih": gun.isoformat(), "durum": "calisiyor", "online": random.randint(1, 4), "yuzyuze": 0}, name="PUT takvim/gun")

    @task(1)
    def profil_yaz(self) -> None:  # panel DB'si (dev.db): tek yazici kilidi
        self.client.put("/api/v1/session/profile", json={"phone": f"+90 532 {random.randrange(1000000, 9999999)}"}, name="PUT session/profile")


if os.environ.get("TAMLIFE_YUK_SEKIL") == "spike":

    class Spike(LoadTestShape):
        """30 sn 5 kullanici, 30 sn 300 (ani), 30 sn 5 (toparlanma)."""

        def tick(self):  # type: ignore[no-untyped-def]
            t = self.get_run_time()
            if t < 30:
                return 5, 5
            if t < 60:
                return 300, 300
            if t < 90:
                return 5, 50
            return None
