"""LOOKOUTEYES grafik kaynagi (MSSQL, salt okunur): aylik rapora serbest metinle grafik getirir.

2026-11-10 kullanici: "aylik rapor modulunde GALAPAGOS GRAFIKLERI ismini LOOKOUTEYES olarak degistir; kullanici serbest
metin yazinca db'den gelen grafik rapora otomatik eklensin; tam aciklama ya da yalniz '100005149106' gibi parca girilince
de bulunsun; MSSQL".

Ayar (.env; deger burada okunur, hicbir yerde yazdirilmaz):
  LOOKOUTEYESDB_MSSQL_ENABLED=true
  LOOKOUTEYESDB_MSSQL_HOST / _PORT (vars. 1433) / _DBNAME / _USER / _PASSWORD
  LOOKOUTEYESDB_MSSQL_TIMEOUT        baglanti ve sorgu suresi sn (vars. 20)
  LOOKOUTEYESDB_MSSQL_DRIVER         ODBC surucu adi (vars. "ODBC Driver 17 for SQL Server"); yalniz pyodbc ile
  LOOKOUTEYESDB_MSSQL_SEARCH_QUERY   TEK SELECT. Kullanicinin yazdigi metin `?` yer tutucusuna (kac tane olursa olsun, hepsine
                                     ayni deger) '%metin%' olarak parametreyle gecer; birlestirme YOK. Sonucun
                                     1. sutunu grafik adi (metin), 2. sutunu gorsel (PNG/JPEG/GIF baytlari ya da base64 metin).
  ornek: SELECT TOP 10 ad, gorsel FROM dbo.grafik WHERE ad LIKE ? OR aciklama LIKE ?

Surucu: pyodbc ya da pymssql (hangisi kuruluysa); ikisi de yoksa net mesajla 503 doner, panel calismaya devam eder.
Guvenlik: salt okunur baglanti, parametreli sorgu, LIKE ozel karakterleri (% _ [) kacirilir (ME_800M_I birebir aranir), hata
metinlerinde parola/adres/kullanici maskelenir, en cok EN_COK_SONUC grafik.
"""

from __future__ import annotations

import base64
import binascii
import os
from typing import Any

from app.dil import m
from app.ortak import UygulamaHatasi
from app.tampon import oracle

EN_COK_SONUC = 10
EN_COK_BAYT = 10 * 1048576
EN_AZ_METIN = 3
EN_COK_METIN = 300


def _ortam(ad: str) -> str:
    return (os.environ.get(f"LOOKOUTEYESDB_MSSQL_{ad}") or "").strip()


def acik_mi() -> bool:
    return _ortam("ENABLED").lower() == "true"


def eksikler() -> list[str]:
    return [f"LOOKOUTEYESDB_MSSQL_{ad}" for ad in ("HOST", "DBNAME", "USER", "PASSWORD", "SEARCH_QUERY") if not (os.environ.get(f"LOOKOUTEYESDB_MSSQL_{ad}") or "").strip()]


def durum() -> dict[str, Any]:
    """Arayuze: kaynak hazir mi (gizli deger ASLA donmez)."""
    acik = acik_mi()
    eksik = eksikler() if acik else ["LOOKOUTEYESDB_MSSQL_ENABLED=true"]
    return {"hazir": acik and not eksik, "eksik": eksik}


def kac(metin: str) -> str:
    """LIKE ozel karakterlerini (% _ [) kacirir: kullanicinin yazdigi metin birebir aranir ('ME_800M_I' '_' joker olmaz)."""
    return "".join("[" + c + "]" if c in "%_[" else c for c in metin)


def _surucu() -> tuple[str, Any]:
    try:
        import pyodbc  # type: ignore[import-not-found]

        return "pyodbc", pyodbc
    except ImportError:
        pass
    try:
        import pymssql  # type: ignore[import-not-found]

        return "pymssql", pymssql
    except ImportError:
        pass
    raise UygulamaHatasi(
        503,
        m(
            "LOOKOUTEYES bağlantısı için sunucuda pyodbc (ya da pymssql) paketi kurulu değil.",
            "The pyodbc (or pymssql) package required for the LOOKOUTEYES connection is not installed on the server.",
        ),
    )


def _baglan() -> Any:
    ad, mod = _surucu()
    zaman = max(5, min(int(_ortam("TIMEOUT") or 20), 120))
    host, port = _ortam("HOST"), _ortam("PORT") or "1433"
    if ad == "pyodbc":
        surucu = _ortam("DRIVER") or "ODBC Driver 17 for SQL Server"
        cs = f"DRIVER={{{surucu}}};SERVER={host},{port};DATABASE={_ortam('DBNAME')};UID={_ortam('USER')};PWD={os.environ.get('LOOKOUTEYESDB_MSSQL_PASSWORD', '')};ApplicationIntent=ReadOnly;TrustServerCertificate=yes"
        return mod.connect(cs, timeout=zaman, readonly=True)
    return mod.connect(server=host, port=port, user=_ortam("USER"), password=os.environ.get("LOOKOUTEYESDB_MSSQL_PASSWORD", ""), database=_ortam("DBNAME"), login_timeout=zaman, timeout=zaman)


def _gizliler() -> tuple[str, ...]:
    return tuple(v for v in (_ortam("HOST"), _ortam("USER"), os.environ.get("LOOKOUTEYESDB_MSSQL_PASSWORD", ""), _ortam("DBNAME")) if v)


def gorsel_baytlari(deger: Any) -> bytes | None:
    """Sutun degeri -> gorsel baytlari (bytes/memoryview ya da base64 / 'data:' URL metin). Taninmazsa None."""
    if deger is None:
        return None
    if isinstance(deger, (bytes, bytearray, memoryview)):
        veri = bytes(deger)
    elif isinstance(deger, str):
        s = deger.strip()
        if s.startswith("data:") and "," in s:
            s = s.split(",", 1)[1]
        try:
            veri = base64.b64decode(s, validate=False)
        except (binascii.Error, ValueError):
            return None
    else:
        return None
    return veri if 0 < len(veri) <= EN_COK_BAYT else None


def ara(metin: str) -> list[tuple[str, bytes]]:
    """Serbest metin -> [(grafik adi, gorsel baytlari)]. Hata: UygulamaHatasi (kod = HTTP durumu); eslesme yoksa 404."""
    d = durum()
    if not d["hazir"]:
        raise UygulamaHatasi(503, m("LOOKOUTEYES kapalı: ", "LOOKOUTEYES is disabled: ") + ", ".join(d["eksik"]) + m(" gerekli.", " required."))
    aranan = " ".join((metin or "").split())
    if len(aranan) < EN_AZ_METIN:
        raise UygulamaHatasi(400, m(f"En az {EN_AZ_METIN} karakter girin.", f"Enter at least {EN_AZ_METIN} characters."))
    if len(aranan) > EN_COK_METIN:
        raise UygulamaHatasi(400, m("Arama metni çok uzun.", "The search text is too long."))
    try:
        sorgu = oracle.sorgu_temizle(_ortam("SEARCH_QUERY"))
    except UygulamaHatasi:
        raise
    except Exception:
        raise UygulamaHatasi(500, m("LOOKOUTEYES arama sorgusu geçersiz (yalnız tek SELECT).", "The LOOKOUTEYES search query is invalid (single SELECT only).")) from None
    sayi = sorgu.count("?")
    if sayi < 1:
        raise UygulamaHatasi(500, m("LOOKOUTEYES arama sorgusunda '?' yer tutucusu yok.", "The LOOKOUTEYES search query has no '?' placeholder."))
    ad, _ = _surucu()
    parametre = f"%{kac(aranan)}%"
    if ad == "pymssql":
        sorgu = sorgu.replace("%", "%%").replace("?", "%s")
    baglanti = None
    try:
        baglanti = _baglan()
        imlec = baglanti.cursor()
        imlec.execute(sorgu, tuple([parametre] * sayi))
        satirlar = imlec.fetchmany(EN_COK_SONUC * 3)
    except UygulamaHatasi:
        raise
    except Exception as e:
        mesaj = oracle.maskele(f"{type(e).__name__}: {e}", _gizliler())[:200]
        raise UygulamaHatasi(502, m("LOOKOUTEYES sorgusu çalışmadı: ", "The LOOKOUTEYES query failed: ") + mesaj) from None
    finally:
        if baglanti is not None:
            try:
                baglanti.close()
            except Exception:
                pass
    sonuc: list[tuple[str, bytes]] = []
    gorulen: set[str] = set()
    for satir in satirlar:
        if len(satir) < 2:
            continue
        baslik = " ".join(str(satir[0] or "").split())[:200]
        veri = gorsel_baytlari(satir[1])
        if veri is None or not baslik or baslik in gorulen:
            continue
        gorulen.add(baslik)
        sonuc.append((baslik, veri))
        if len(sonuc) >= EN_COK_SONUC:
            break
    if not sonuc:
        raise UygulamaHatasi(404, m("Girilen metinle eşleşen grafik bulunamadı.", "No chart matched the entered text."))
    return sonuc
