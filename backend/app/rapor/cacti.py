"""Cacti LDAP oturumu ve aylik PNG grafikleri. Kimlik bilgileri yalniz sunucuda kalir."""

from __future__ import annotations

import base64
import hashlib
import http.cookiejar
import json
import os
import re
import struct
import threading
import zlib
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

from app.ortak import UygulamaHatasi
from app.rapor import cacti_kimlik

ORIGIN = "https://trafik.superonline.net"
AZAMI_GRAFIK = 6
AZAMI_BAYT = 3 * 1024 * 1024
TARAYICI_SURESI = 110  # sn; cacti-grafik.mjs toplam siniri (aylik grafik cizimi gunlukten yavas), surec bundan 15 sn sonra oldurulur
_KILIT = threading.BoundedSemaphore(2)
# Lookouteyes (personelin actigi grafik): Graph.aspx sayfasi tek <img> icerir, resmi Graph.ashx s/e (Unix sn) araligiyla cizer.
LOE_ADRES = ORIGIN + "/lookouteyes/Modules/Graph.aspx"
LOE_SAYFALAR = ("/lookouteyes/modules/graph.aspx", "/lookouteyes/modules/graph.ashx")
LOE_SUNUCULAR = ("lookouteyes", "trafik.superonline.net")
LOE_ALANLAR = (  # (parametre, kalip, varsayilan); s/e/r0 gibi zaman alanlari yok sayilir, donem rapordan gelir
    ("ct", r"[A-Za-z]{1,20}", "Stock"),
    ("miid", r"[0-9]{1,10}", ""),
    ("fn", r"[A-Za-z]{1,10}", "AVG"),
    ("val", r"[A-Za-z0-9_]{1,40}", ""),
)


class CactiHata(UygulamaHatasi):
    pass


def kok() -> str:
    yol = os.environ.get("TAMLIFE_CACTI_PATH", "/").strip()
    if not re.fullmatch(r"/(?:[a-zA-Z0-9_-]+/)*", yol):
        raise CactiHata(503, "Cacti dizin ayarı geçersiz.")
    return ORIGIN + yol


def _lookouteyes(u) -> str | None:
    """Lookouteyes Graph.aspx/Graph.ashx baglantisi ise kanonik Graph.aspx adresi (istek her zaman ORIGIN'e gider), degilse None.
    Ic ad (http://lookouteyes) bu sunucudan erisilemez; ayni yol ag gecidinde /lookouteyes/ altinda acilir (2026-10-17 kontrolu)."""
    if u.path.lower() not in LOE_SAYFALAR:
        return None
    if u.scheme not in ("http", "https") or (u.hostname or "").lower() not in LOE_SUNUCULAR or u.port or u.username or u.password or u.fragment:
        raise CactiHata(400, "Yalnız lookouteyes / trafik.superonline.net grafik bağlantıları kabul edilir.")
    q = parse_qs(u.query)
    alanlar = {}
    for ad, kalip, varsayilan in LOE_ALANLAR:
        degerler = q.get(ad, [varsayilan] if varsayilan else [])
        if len(degerler) != 1 or not re.fullmatch(kalip, degerler[0]):
            raise CactiHata(400, f"Lookouteyes bağlantısında geçerli tek bir '{ad}' olmalı.")
        alanlar[ad] = degerler[0]
    if not 1 <= int(alanlar["miid"]) <= 2147483647:
        raise CactiHata(400, "Lookouteyes miid pozitif bir tam sayı olmalı.")
    alanlar["miid"] = str(int(alanlar["miid"]))
    return LOE_ADRES + "?" + urlencode(alanlar)


def lookouteyes_mu(kimlik: str) -> bool:
    return kimlik.startswith(LOE_ADRES + "?")


def lookouteyes_alanlari(kimlik: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(kimlik).query).items()}


def anahtar(kimlik: str) -> str:
    if lookouteyes_mu(kimlik):
        a = lookouteyes_alanlari(kimlik)
        return f"loe-{a['miid']}-{a['fn']}-{a['val']}".lower()
    return f"cacti-{kimlik}"


def grafik_id(deger: str) -> str:
    """Cacti grafik ID'si (sayi) ya da kanonik Lookouteyes Graph.aspx adresi."""
    deger = deger.strip()
    if not deger.isascii():
        raise CactiHata(400, "Grafik ID veya Cacti bağlantısı geçersiz.")
    if not deger.isdecimal():
        u = urlsplit(deger)
        loe = _lookouteyes(u)
        if loe is not None:
            return loe
        izinli = {kok() + ad for ad in ("graph.php", "graph_image.php", "graph_view.php")}
        if u.username or u.password or u.fragment or f"{u.scheme}://{u.netloc}{u.path}" not in izinli:
            raise CactiHata(400, "Yalnız trafik.superonline.net grafik bağlantıları kabul edilir.")
        ids = parse_qs(u.query).get("local_graph_id", [])
        if len(ids) != 1:
            raise CactiHata(400, "Bağlantıda tek bir local_graph_id olmalı.")
        deger = ids[0]
    if not re.fullmatch(r"[0-9]{1,10}", deger) or not 1 <= int(deger) <= 2147483647:
        raise CactiHata(400, "Grafik ID pozitif bir tam sayı olmalı.")
    return str(int(deger))


def baglantilar(deger: list[str]) -> list[str]:
    if len(deger) > AZAMI_GRAFIK:
        raise CactiHata(400, f"Bir müşteri için en fazla {AZAMI_GRAFIK} grafik tanımlanabilir.")
    return list(dict.fromkeys(grafik_id(x) for x in deger if x.strip()))


def hazir() -> bool:
    return cacti_kimlik.hazir()


def ay_araligi(yil: int, ay: int) -> tuple[int, int]:
    # Cacti Unix zamanlarini kullanir; rapor takvim ayi Turkiye saatidir.
    tz = timezone(timedelta(hours=3))
    bas = datetime(yil, ay, 1, tzinfo=tz)
    son = datetime(yil + (ay == 12), ay % 12 + 1, 1, tzinfo=tz)
    return int(bas.timestamp()), int(son.timestamp()) - 1


def aralik_metni(yil: int, ay: int) -> str:
    """Grafik basligindaki rapor araligi (Turkiye saati), or. '01.09.2026 00:00 – 30.09.2026 23:59'."""
    tz = timezone(timedelta(hours=3))
    bas, son = (datetime.fromtimestamp(t, tz) for t in ay_araligi(yil, ay))
    return f"{bas:%d.%m.%Y %H:%M} – {son:%d.%m.%Y %H:%M}"


class _Yonlendirme(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urlsplit(newurl)
        if u.scheme != "https" or u.netloc != "trafik.superonline.net" or u.username or u.password:
            raise CactiHata(502, "Cacti farklı bir sunucuya yönlendirdi; erişim durduruldu.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _Form(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms: list[dict] = []
        self.current: dict | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.current = {"action": a.get("action") or "index.php", "fields": {}}
            self.forms.append(self.current)
        elif tag == "input" and self.current is not None and a.get("name"):
            self.current["fields"][a["name"]] = a.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None


def _oku(opener, url: str, data: bytes | None = None) -> bytes:
    # TLS sertifika dogrulamasi aciktir. Cerezler yalniz bu istek grubunun bellegindedir.
    req = Request(url, data=data, headers={"User-Agent": "TAMLIFE-Report/1.0", "Accept": "image/png,text/html"})
    with opener.open(req, timeout=10) as yanit:
        veri = yanit.read(AZAMI_BAYT + 1)
    if len(veri) > AZAMI_BAYT:
        raise CactiHata(502, "Cacti yanıtı boyut sınırını aştı.")
    return veri


def png_dogrula(veri: bytes) -> None:
    # HTML giris/hata sayfasi ya da bozuk PNG rapora girmesin. CRC ve boyut sinirli.
    if not veri.startswith(b"\x89PNG\r\n\x1a\n"):
        raise CactiHata(502, "Cacti grafik yerine giriş veya hata sayfası döndürdü.")
    pos, ihdr, idat, iend = 8, False, False, False
    while pos + 12 <= len(veri):
        boy = struct.unpack(">I", veri[pos : pos + 4])[0]
        tur = veri[pos + 4 : pos + 8]
        son = pos + 8 + boy
        if son + 4 > len(veri) or zlib.crc32(veri[pos + 4 : son]) & 0xFFFFFFFF != struct.unpack(">I", veri[son : son + 4])[0]:
            raise CactiHata(502, "Cacti PNG dosyası bozuk.")
        if not ihdr:
            if tur != b"IHDR" or boy != 13:
                raise CactiHata(502, "Cacti PNG başlığı geçersiz.")
            w, h = struct.unpack(">II", veri[pos + 8 : pos + 16])
            if not 100 <= w <= 2400 or not 50 <= h <= 1600:
                raise CactiHata(502, "Cacti grafik boyutları geçersiz.")
            ihdr = True
        idat |= tur == b"IDAT"
        if tur == b"IEND":
            iend = boy == 0 and son + 4 == len(veri)
            break
        pos = son + 4
    if not (ihdr and idat and iend):
        raise CactiHata(502, "Cacti PNG dosyası tamamlanmamış.")


def indir(ids: list[str], yil: int, ay: int) -> list[dict]:
    if not hazir():
        raise CactiHata(503, "Cacti LDAP hesabı sunucuda tanımlanmamış.")
    if os.environ.get("TAMLIFE_CACTI_MODE", "browser") == "browser":
        return _tarayici(ids, yil, ay)
    if any(lookouteyes_mu(k) for k in ids):
        raise CactiHata(503, "Lookouteyes grafikleri yalnız tarayıcı yöntemiyle alınır (TAMLIFE_CACTI_MODE=browser).")
    kullanici, parola = cacti_kimlik.oku()
    opener = build_opener(_Yonlendirme(), HTTPCookieProcessor(http.cookiejar.CookieJar()))
    try:
        sayfa = _oku(opener, kok() + "index.php").decode("utf-8", errors="replace")
        form = _Form()
        form.feed(sayfa)
        giris = next((f for f in form.forms if "login_username" in f["fields"] and "login_password" in f["fields"]), None)
        if giris is None:
            raise CactiHata(502, "Cacti LDAP giriş formuna ulaşılamadı. Ağ geçidi veya giriş biçimi kontrol edilmeli.")
        hedef = urljoin(kok(), giris["action"])
        if not hedef.startswith(kok()) or urlsplit(hedef).netloc != "trafik.superonline.net":
            raise CactiHata(502, "Cacti giriş formunun adresi geçersiz.")
        alanlar = {
            **giris["fields"],
            "login_username": kullanici,
            "login_password": parola,
            "realm": os.environ.get("TAMLIFE_CACTI_REALM", "2"),
            "action": "login",
        }
        sonuc = _oku(opener, hedef, urlencode(alanlar).encode()).decode("utf-8", errors="replace")
        if re.search(r'name\s*=\s*["\']login_password["\']', sonuc, re.IGNORECASE):
            raise CactiHata(502, "Cacti LDAP oturumu açılamadı; hesap, realm ve erişim izni kontrol edilmeli.")
        bas, son = ay_araligi(yil, ay)
        grafikler = []
        for kimlik in ids:
            query = urlencode(
                {
                    "local_graph_id": kimlik,
                    "graph_start": bas,
                    "graph_end": son,
                    "graph_width": 1000,
                    "graph_height": 300,
                    "image_format": "png",
                }
            )
            veri = _oku(opener, kok() + "graph_image.php?" + query)
            png_dogrula(veri)
            grafikler.append(
                {
                    "anahtar": f"cacti-{kimlik}",
                    "baslik": f"Cacti #{kimlik} · {aralik_metni(yil, ay)}",
                    "gorsel": "data:image/png;base64," + base64.b64encode(veri).decode("ascii"),
                }
            )
        return grafikler
    except (HTTPError, URLError, OSError, ValueError) as from_error:
        raise CactiHata(502, "Cacti erişimi başarısız. Ağ, TLS ve LDAP ayarlarını kontrol edin.") from from_error


def grafikler(ids: list[str], yil: int, ay: int, dizin: Path, *, kilitli: bool = False) -> list[dict]:
    if not ids:
        return []
    iz = hashlib.sha256(json.dumps([kok(), ids]).encode()).hexdigest()[:20]
    dosya = dizin / f"{yil}-{ay:02d}-{iz}.json"

    def oku():
        if dosya.is_file():
            try:
                if dosya.stat().st_size > len(ids) * (4 * AZAMI_BAYT // 3 + 4096):
                    return None
                kayit = json.loads(dosya.read_text(encoding="utf-8"))
                if not isinstance(kayit, list) or len(kayit) != len(ids):
                    return None
                for kimlik, g in zip(ids, kayit, strict=True):
                    if not isinstance(g, dict) or g.get("anahtar") != anahtar(kimlik) or not isinstance(g.get("baslik"), str):
                        return None
                    gorsel = g.get("gorsel")
                    onek = "data:image/png;base64,"
                    if not isinstance(gorsel, str) or not gorsel.startswith(onek):
                        return None
                    png_dogrula(base64.b64decode(gorsel[len(onek) :], validate=True))
                return kayit
            except (OSError, ValueError, CactiHata):
                pass
        return None

    kayit = oku()
    if kayit is not None:
        return kayit
    if kilitli:
        raise CactiHata(409, "Gönderilen dönemin kayıtlı Cacti grafikleri bulunamadı.")
    if not _KILIT.acquire(blocking=False):
        raise CactiHata(429, "Cacti grafik alma işlemi sürüyor; kısa süre sonra tekrar deneyin.")
    try:
        kayit = oku()
        if kayit is not None:
            return kayit
        kayit = indir(ids, yil, ay)
        dizin.mkdir(parents=True, exist_ok=True)
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=dizin, suffix=".tmp", delete=False) as f:
            json.dump(kayit, f, ensure_ascii=False)
            gecici = Path(f.name)
        try:
            os.replace(gecici, dosya)
        finally:
            gecici.unlink(missing_ok=True)
        return kayit
    finally:
        _KILIT.release()


def _baslik(kimlik: str, ad: object) -> str:
    """Grafik basligi: Lookouteyes sayfasindaki ad (kisa ad, yoksa tam metrik adi), yoksa ID. Kontrol karakteri ve uzunluk sinirli."""
    temiz = re.sub(r"[\x00-\x1f\x7f]+", " ", ad).strip()[:160] if isinstance(ad, str) else ""
    if temiz:
        return temiz
    return f"Lookouteyes #{lookouteyes_alanlari(kimlik)['miid']}" if lookouteyes_mu(kimlik) else f"Cacti #{kimlik}"


def _tarayici(ids: list[str], yil: int, ay: int) -> list[dict]:
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        raise CactiHata(503, "Cacti grafik alımı için Node.js bulunamadı.")
    bas, son = ay_araligi(yil, ay)
    kullanici, parola = cacti_kimlik.oku()
    govde = json.dumps(
        {
            "base": kok(),
            "username": kullanici,
            "password": parola,
            "realm": os.environ.get("TAMLIFE_CACTI_REALM", "2"),
            "items": [{"tur": "loe", **lookouteyes_alanlari(k)} if lookouteyes_mu(k) else {"tur": "cacti", "id": k} for k in ids],
            "start": bas,
            "end": son,
        }
    )
    betik = Path(__file__).resolve().parents[2] / "araclar" / "cacti-grafik.mjs"
    # Credentials go through stdin, never command-line args or environment of browser children.
    izinli_ortam = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "LOCALAPPDATA",
        "APPDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PROGRAMDATA",
        "COMSPEC",
        "PATHEXT",
        "HOMEDRIVE",
        "HOMEPATH",
        "HOME",
        "LANG",
    }
    ortam = {k: v for k, v in os.environ.items() if k.upper() in izinli_ortam}
    try:
        p = subprocess.Popen(
            [node, str(betik)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            env=ortam,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except OSError:
        raise CactiHata(503, "Cacti tarayıcı işlemi başlatılamadı.") from None
    try:
        cikti, _ = p.communicate(govde, timeout=TARAYICI_SURESI + 15)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(p.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            p.kill()
        p.communicate()
        raise CactiHata(504, "Cacti grafik alımı zaman aşımına uğradı.") from None
    finally:
        govde = ""
    try:
        sonuc = json.loads(cikti)
        if not isinstance(sonuc, dict):
            raise TypeError
        images = sonuc.get("images")
        basliklar = sonuc.get("titles")
        if p.returncode or not isinstance(images, list) or len(images) != len(ids):
            raise ValueError
        if not isinstance(basliklar, list) or len(basliklar) != len(ids):
            basliklar = [""] * len(ids)
        sonuc = []
        for kimlik, encoded, ad in zip(ids, images, basliklar, strict=True):
            veri = base64.b64decode(encoded, validate=True)
            if len(veri) > AZAMI_BAYT:
                raise ValueError
            png_dogrula(veri)
            sonuc.append(
                {"anahtar": anahtar(kimlik), "baslik": f"{_baslik(kimlik, ad)} · {aralik_metni(yil, ay)}", "gorsel": "data:image/png;base64," + encoded}
            )
        return sonuc
    except (ValueError, TypeError, KeyError):
        raise CactiHata(
            502, "Cacti kurumsal oturumu veya grafik alımı başarısız. LDAP, erişim izni, MFA ve grafik ID bilgilerini kontrol edin."
        ) from None
