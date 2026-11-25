"""Canli panele karsi YIKICI OLMAYAN sizma testi (yalniz standart kutuphane). Veri yazmaz, hesap kilitlemez (--kilit-testi haric).

  ..\\.venv\\Scripts\\python.exe araclar\\sizma_testi.py https://tamlife
  ..\\.venv\\Scripts\\python.exe araclar\\sizma_testi.py https://tamlife --kullanici tcgsav      (parola sorulur, saklanmaz)
  ..\\.venv\\Scripts\\python.exe araclar\\sizma_testi.py https://tamlife --kilit-testi          (var olmayan adla 6 hatali giris)

Cikis kodu: 0 = hepsi gecti, 1 = en az bir bulgu. Sertifika Windows guven deposundan dogrulanir; --ca ile PEM verilebilir.
"""

from __future__ import annotations

import argparse
import getpass
import http.client
import json
import secrets
import socket
import ssl
import sys
import warnings
from http.cookies import SimpleCookie
from urllib.parse import quote, urlsplit

KORUMALI = ("/api/v1/session/me", "/api/v1/musteri", "/api/v1/ekip/ozet", "/api/v1/yonetim/ozet", "/api/v1/tampon/kaynaklar", "/api/v1/roller")
YONETIM = ("/api/v1/yonetim/ozet", "/api/v1/yonetim/veritabani", "/api/v1/tampon/kaynaklar", "/api/v1/roller", "/api/v1/skor/meta")
GEZINME = ("/..%2f..%2fbackend%2f.env", "/%2e%2e/%2e%2e/backend/.env", "/assets/..%2f..%2f..%2fbackend%2f.env", "/..%5c..%5cbackend%5c.env", "/.env", "/backend/.env")
BASLIKLAR = {"x-content-type-options": "nosniff", "x-frame-options": "DENY", "referrer-policy": "no-referrer", "cache-control": "no-store"}


class Sinayici:
    def __init__(self, taban: str, ca: str | None) -> None:
        p = urlsplit(taban)
        self.sema, self.host, self.port = p.scheme, p.hostname or "", p.port or (443 if p.scheme == "https" else 80)
        self.baglam = ssl.create_default_context(cafile=ca) if self.sema == "https" else None
        self.cerez: dict[str, str] = {}
        self.sonuclar: list[tuple[bool, str, str]] = []

    def baglan(self) -> http.client.HTTPConnection:
        if self.sema == "https":
            return http.client.HTTPSConnection(self.host, self.port, timeout=15, context=self.baglam)
        return http.client.HTTPConnection(self.host, self.port, timeout=15)

    def istek(self, yontem: str, yol: str, govde: object = None, basliklar: dict[str, str] | None = None) -> tuple[int, dict[str, str], str, list[str]]:
        b = {"Accept": "application/json", **(basliklar or {})}
        if self.cerez:
            b.setdefault("Cookie", "; ".join(f"{k}={v}" for k, v in self.cerez.items()))
        veri = json.dumps(govde).encode() if govde is not None else None
        if veri is not None:
            b["Content-Type"] = "application/json"
        c = self.baglan()
        try:
            c.request(yontem, yol, body=veri, headers=b)
            r = c.getresponse()
            metin = r.read(200_000).decode("utf-8", "replace")
            ham = r.headers.get_all("Set-Cookie") or []
            for satir in ham:
                for ad, m in SimpleCookie(satir).items():
                    self.cerez[ad] = m.value
            return r.status, {k.lower(): v for k, v in r.getheaders()}, metin, ham
        finally:
            c.close()

    def ham(self, satirlar: str) -> str:
        s = socket.create_connection((self.host, self.port), timeout=15)
        if self.baglam is not None:
            s = self.baglam.wrap_socket(s, server_hostname=self.host)
        try:
            s.sendall(satirlar.encode())
            return s.recv(512).decode("latin-1", "replace").split("\r\n", 1)[0]
        finally:
            s.close()

    def kaydet(self, gecti: bool, ad: str, ayrinti: str = "") -> None:
        self.sonuclar.append((gecti, ad, ayrinti))
        print(f"[{'GECTI' if gecti else 'BULGU'}] {ad}{(' - ' + ayrinti) if ayrinti else ''}")

    def tls(self) -> None:
        if self.baglam is None:
            self.kaydet(False, "TLS", "sema http: trafik sifresiz")
            return
        with socket.create_connection((self.host, self.port), timeout=15) as s, self.baglam.wrap_socket(s, server_hostname=self.host) as t:
            self.kaydet(t.version() in {"TLSv1.2", "TLSv1.3"}, "TLS surumu", str(t.version()))
        zayif = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        zayif.check_hostname, zayif.verify_mode = False, ssl.CERT_NONE
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            zayif.minimum_version = zayif.maximum_version = ssl.TLSVersion.TLSv1_1
        try:
            with socket.create_connection((self.host, self.port), timeout=15) as s, zayif.wrap_socket(s, server_hostname=self.host):
                self.kaydet(False, "TLS 1.1 kapali", "sunucu TLS 1.1 kabul etti")
        except (ssl.SSLError, OSError):
            self.kaydet(True, "TLS 1.1 kapali")

    def calistir(self, kullanici: str | None, kilit: bool) -> int:
        self.tls()
        kod, bas, _, _ = self.istek("GET", "/api/v1/health")
        self.kaydet(kod == 200, "saglik ucu", str(kod))
        eksik = [k for k, v in BASLIKLAR.items() if bas.get(k, "").lower() != v.lower()]
        self.kaydet(not eksik, "guvenlik basliklari", ", ".join(eksik))
        self.kaydet("frame-ancestors 'none'" in bas.get("content-security-policy", ""), "CSP frame-ancestors")
        self.kaydet("server" not in bas or "uvicorn" not in bas["server"].lower(), "Server basligi sizmaz", bas.get("server", ""))
        for yol in ("/docs", "/openapi.json", "/redoc"):
            kod = self.istek("GET", yol)[0]
            self.kaydet(kod in {401, 404}, f"{yol} kapali", str(kod))
        for yol in KORUMALI:
            kod, _, metin, _ = self.istek("GET", yol)
            self.kaydet(kod == 401 and "success" not in metin, f"kimliksiz {yol}", str(kod))
        kod, _, metin, _ = self.istek("GET", "/api/v1/session/me", basliklar={"Cookie": f"tamlife_session={secrets.token_urlsafe(32)}"})
        self.kaydet(kod == 401, "sahte oturum cerezi", str(kod))
        kod = self.istek("POST", "/api/v1/session/logout", {}, {"Origin": "https://evil.example"})[0]
        self.kaydet(kod == 403, "yabanci Origin", str(kod))
        kod = self.istek("POST", "/api/v1/session/logout", {}, {"Origin": "null"})[0]
        self.kaydet(kod == 403, "Origin null", str(kod))
        kod = self.istek("GET", "/api/v1/health", basliklar={"Host": "evil.example"})[0]
        self.kaydet(kod == 400, "izinsiz Host basligi", str(kod))
        for yol in GEZINME:
            kod, _, metin, _ = self.istek("GET", yol)
            self.kaydet(not (kod == 200 and ("TAMLIFE_" in metin or "PASSWORD" in metin)), f"yol gezinme {yol}", str(kod))
        satir = self.ham(f"TRACE / HTTP/1.1\r\nHost: {self.host}\r\nX-Sizma: 1\r\nConnection: close\r\n\r\n")
        self.kaydet(" 200 " not in satir, "TRACE kapali", satir)
        satir = self.ham(f"GET http://169.254.169.254/latest/meta-data/ HTTP/1.1\r\nHost: {self.host}\r\nConnection: close\r\n\r\n")
        self.kaydet(" 200 " not in satir, "mutlak URI ile SSRF (vekil)", satir)
        satir = self.ham(f"GET //evil.example/ HTTP/1.1\r\nHost: {self.host}\r\nConnection: close\r\n\r\n")
        self.kaydet(" 200 " not in satir or "evil" not in satir, "cift egik cizgi yolu", satir)
        kod = self.istek("POST", "/api/v1/session/login", {"username": "a" * 65, "password": "x"})[0]
        self.kaydet(kod == 422, "giris girdi siniri", str(kod))
        if kilit:
            ad = "sizma_" + secrets.token_hex(4)
            yerel = self.host in {"127.0.0.1", "localhost", "::1"}  # uvicorn 127.0.0.1'e XFF ile guvenir: sahte XFF yalniz vekil uzerinden anlamli
            kodlar = [self.istek("POST", "/api/v1/session/login", {"username": ad, "password": "x"}, {} if yerel else {"X-Forwarded-For": f"10.{i}.0.1"})[0] for i in range(6)]
            self.kaydet(kodlar[-1] == 429, "kaba kuvvet kilidi (sahte XFF ile)", ",".join(map(str, kodlar)))
        if kullanici:
            self.oturumlu(kullanici)
        bulgu = sum(1 for g, _, _ in self.sonuclar if not g)
        print(f"\n{len(self.sonuclar)} kontrol, {bulgu} bulgu")
        return 1 if bulgu else 0

    def oturumlu(self, kullanici: str) -> None:
        kod, _, _, ham = self.istek("POST", "/api/v1/session/login", {"username": kullanici, "password": getpass.getpass(f"{kullanici} parolasi: ")})
        if kod != 200:
            self.kaydet(False, "giris", str(kod))
            return
        oturum = next((s.lower() for s in ham if s.lower().startswith("tamlife_session=")), "")
        self.kaydet(all(x in oturum for x in ("httponly", "samesite=strict", "secure")), "oturum cerezi bayraklari", oturum.split(";", 1)[-1])
        csrf = self.cerez.get("tamlife_csrf", "")
        kod = self.istek("POST", "/api/v1/session/logout", {})[0]
        self.kaydet(kod == 403, "CSRF basligi olmadan yazma", str(kod))
        kod = self.istek("POST", "/api/v1/session/logout", {}, {"X-CSRF-Token": self.cerez.get("tamlife_session", "")})[0]
        self.kaydet(kod == 403, "CSRF yerine oturum cerezi", str(kod))
        me = json.loads(self.istek("GET", "/api/v1/session/me")[2] or "{}").get("data", {})
        if not me.get("is_admin"):
            for yol in YONETIM:
                kod = self.istek("GET", yol)[0]
                self.kaydet(kod == 403, f"yetki yukseltme {yol}", str(kod))
            kod = self.istek("POST", "/api/v1/musteri", {"name": "sizma"}, {"X-CSRF-Token": csrf})[0]
            self.kaydet(kod in {403, 422}, "admin disi veri yazma", str(kod))
        for yuk in ("' OR '1'='1", "%' OR 1=1 --", "x' UNION SELECT username FROM app_user --"):
            kod, _, metin, _ = self.istek("GET", "/api/v1/musteri?q=" + quote(yuk, safe=""))
            self.kaydet(kod == 200 and '"total":0' in metin.replace(" ", ""), f"SQLi arama {yuk!r}", str(kod))
        self.istek("POST", "/api/v1/session/logout", {}, {"X-CSRF-Token": csrf})
        self.kaydet(self.istek("GET", "/api/v1/session/me")[0] == 401, "cikistan sonra oturum kapali")


def main() -> int:
    a = argparse.ArgumentParser(description="TAMLIFE yikici olmayan sizma testi")
    a.add_argument("taban", help="ornek: https://tamlife")
    a.add_argument("--kullanici", help="oturumlu testler icin kullanici adi (parola sorulur)")
    a.add_argument("--kilit-testi", action="store_true", help="var olmayan adla 6 hatali giris (o ad 5 dk kilitlenir)")
    a.add_argument("--ca", help="kurum CA sertifikasi (PEM); verilmezse sistem deposu")
    g = a.parse_args()
    return Sinayici(g.taban.rstrip("/"), g.ca).calistir(g.kullanici, g.kilit_testi)


if __name__ == "__main__":
    sys.exit(main())
