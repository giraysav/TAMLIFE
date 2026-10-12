"""Aylik rapor: personelin YAZDIGI metnin TR -> EN cevirisi (uretim ceviri.py'den tasindi).

Sira: 1) cevrimdisi model (CTranslate2 + SentencePiece; Argos tr_en paketinin icindeki model, ~126 MB), sunucu internete
kapali oldugu icin asil yol budur. 2) Model/kutuphane yoksa ve YZ acik ise (onedesk/yz.py ayari) YZ ile ceviri.
Ikisi de yoksa 503 + ne gerektigini soyleyen mesaj; panel calismaya devam eder.

Model dosyalari git'te DEGIL: TAMLIFE_v3.5/ceviri_modeli/tr_en (ya da TAMLIFE_CEVIRI_MODEL_DIZINI).
Kurulum: kurulum\\ceviri_kur.ps1 (eski panelin model klasorunden kopyalar ya da argos-net.com'dan indirir, SHA256 dogrular,
ctranslate2/sentencepiece kurar, deneme cevirisi yapar; surumler requirements.txt ile ayni).

SUREC YALITIMI (uretim 2026-09-26): sentencepiece'in Windows paketi bazi sunucularda import aninda erisim ihlaliyle
(0xC0000005) cokuyor; web surecinde olursa API tamamen duser. Ceviri AYRI python surecinde yapilir (-m app.rapor.ceviri
--isci); cokme yalniz alt sureci oldurur, kullaniciya 503 doner ve ceviri KAPALI_SURE boyunca denenmez.
Ceviri MAKINE cevirisidir: personel gondermeden once gozden gecirir.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from app.dil import m
from app.ortak import UygulamaHatasi

BACKEND = Path(__file__).resolve().parents[2]
ZAMAN_ASIMI = 120
KAPALI_SURE = 600  # alt surec coktugunde ceviri bu kadar sn denenmez
ISCI_HATA_KODU = 3  # iscinin "kutuphane/model yok" cikis kodu (cokme degil)
AZAMI_KARAKTER = 60000
CRT_ASGARI = (14, 40)
_CUMLE = re.compile(r"(?<=[.!?:])\s+")
_log = logging.getLogger("tamlife.ceviri")

_sira = threading.BoundedSemaphore(1)  # ayni anda tek alt surec (model 126 MB)
_kapali_kadar = 0.0
_kapali_neden = ""
_kilit = threading.Lock()
_motor: tuple | None = None
_hata: str | None = None


class CeviriYok(RuntimeError):
    """Kutuphane ya da model yok / alt surec coktu."""


def model_dizini() -> Path:
    ayar = (os.environ.get("TAMLIFE_CEVIRI_MODEL_DIZINI") or "").strip()
    return Path(ayar) if ayar else BACKEND.parent / "ceviri_modeli" / "tr_en"


def model_yerinde() -> bool:
    kok = model_dizini()
    return (kok / "model" / "model.bin").is_file() and (kok / "sentencepiece.model").is_file()


def durum() -> dict:
    """Arayuze: hangi yolun hazir oldugu. Kutuphaneyi web surecinde YUKLEMEZ (cokebilen yerel modul)."""
    from app.onedesk import yz

    model = model_yerinde() and time.monotonic() >= _kapali_kadar
    yz_hazir = bool(yz.durum()["hazir"])
    return {"hazir": model or yz_hazir, "kaynak": "model" if model else ("yz" if yz_hazir else None)}


# --- C++ calisma zamani (uretim LADIN01 kok neden) ------------------------------------------------
# ctranslate2/sentencepiece msvcp140.dll >= 14.40 ile derlenmis; eski Visual C++ Redistributable ile std::mutex cagrisi
# cokuyor. Iscide sistemdekinden YENI bir msvcp140 varsa (numpy.libs vb.) 'msvcp140.dll' adiyla ONCEDEN yuklenir.
def _dosya_surumu(yol: Path) -> tuple[int, int, int, int] | None:
    import ctypes
    from ctypes import wintypes

    try:
        surum = ctypes.WinDLL("version")  # type: ignore[attr-defined]
        boyut = surum.GetFileVersionInfoSizeW(str(yol), None)
        if not boyut:
            return None
        tampon = ctypes.create_string_buffer(boyut)
        if not surum.GetFileVersionInfoW(str(yol), 0, boyut, tampon):
            return None
        isaret, uzunluk = ctypes.c_void_p(), wintypes.UINT()
        if not surum.VerQueryValueW(tampon, "\\", ctypes.byref(isaret), ctypes.byref(uzunluk)):
            return None
        bilgi = ctypes.cast(isaret, ctypes.POINTER(wintypes.DWORD * 13)).contents
        ms, ls = bilgi[2], bilgi[3]
        return (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)
    except (OSError, AttributeError, ValueError):
        return None


def crt_hazirla() -> tuple | None:
    if os.name != "nt":
        return None
    import ctypes
    import shutil
    import tempfile

    sistem = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "msvcp140.dll"
    if (_dosya_surumu(sistem) or (0, 0, 0, 0))[:2] >= CRT_ASGARI:
        return None
    adaylar = [Path(p) for p in (os.environ.get("TAMLIFE_CEVIRI_CRT_DLL") or "").split(os.pathsep) if p]
    site = Path(sys.prefix) / "Lib" / "site-packages"
    for klasor in ("numpy.libs", "pandas.libs", "scipy.libs", "ctranslate2"):
        adaylar += sorted((site / klasor).glob("msvcp140*.dll"))
    surumlu = [(s, a) for a in adaylar if a.is_file() and (s := _dosya_surumu(a)) and s[:2] >= CRT_ASGARI]
    if not surumlu:
        return None
    surum, kaynak = max(surumlu)
    hedef = Path(tempfile.gettempdir()) / "tamlife_crt" / ".".join(map(str, surum)) / "msvcp140.dll"
    if not hedef.is_file():
        hedef.parent.mkdir(parents=True, exist_ok=True)
        gecici = hedef.with_suffix(".tmp")
        shutil.copyfile(kaynak, gecici)
        os.replace(gecici, hedef)
    ctypes.WinDLL(str(hedef))  # type: ignore[attr-defined]
    return surum


# --- alt surecte calisan kisim --------------------------------------------------------------------
def _yukle() -> tuple:
    global _motor, _hata
    if _motor is not None:
        return _motor
    with _kilit:
        if _motor is not None:
            return _motor
        if _hata is not None:
            raise CeviriYok(_hata)
        try:
            crt_hazirla()
        except Exception:  # noqa: BLE001 - on yukleme yapilamazsa normal yola devam
            _log.debug("msvcp140 on yuklemesi yapilamadi", exc_info=True)
        try:
            import ctranslate2  # type: ignore[import-not-found]
            import sentencepiece  # type: ignore[import-not-found]
        except ImportError as exc:
            _hata = "kutuphane"
            raise CeviriYok(_hata) from exc
        kok = model_dizini()
        if not model_yerinde():
            _hata = "model"
            raise CeviriYok(_hata)
        try:
            cevirici = ctranslate2.Translator(str(kok / "model"), device="cpu", inter_threads=1, intra_threads=2)
            parcalayici = sentencepiece.SentencePieceProcessor(str(kok / "sentencepiece.model"))
        except Exception as exc:  # bozuk model paneli dusurmesin
            _hata = "model"
            raise CeviriYok(_hata) from exc
        _motor = (cevirici, parcalayici)
        return _motor


def cevir(metin: str) -> str:
    """Turkce metni Ingilizceye cevirir; satir duzeni ve madde isaretleri korunur. Tum cumleler TEK toplu istekte."""
    if not (metin or "").strip():
        return metin or ""
    cevirici, parcalayici = _yukle()
    satirlar = str(metin).replace("\r\n", "\n").split("\n")
    parcali: list[tuple[str, list[str]]] = []
    for satir in satirlar:
        onek = re.match(r"^\s*(?:[•\-*–]|\d+[.)])?\s*", satir)
        bas = onek.group(0) if onek else ""
        parcali.append((bas, [c.strip() for c in _CUMLE.split(satir[len(bas) :]) if c.strip()]))
    duz = [c for _, cumleler in parcali for c in cumleler]
    if not duz:
        return metin
    sonuc = cevirici.translate_batch([parcalayici.encode(c, out_type=str) for c in duz], beam_size=4, max_decoding_length=512)
    cevrilmis = [parcalayici.decode(s.hypotheses[0]) for s in sonuc]
    cikti, sira = [], 0
    for bas, cumleler in parcali:
        cikti.append(bas + " ".join(cevrilmis[sira : sira + len(cumleler)]) if cumleler else bas.rstrip())
        sira += len(cumleler)
    return "\n".join(cikti)


def _isci() -> int:
    """Alt surec girisi: stdin JSON {alan: metin} -> stdout JSON; 'kutuphane/model yok' cikis kodu 3."""
    for akis in (sys.stdin, sys.stdout):
        try:
            akis.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    try:
        metinler = json.loads(sys.stdin.read() or "{}")
        print(json.dumps({"metinler": {ad: cevir(str(deger)) for ad, deger in metinler.items()}}, ensure_ascii=False))
        return 0
    except CeviriYok as exc:
        print(json.dumps({"hata": str(exc)}))
        return ISCI_HATA_KODU
    except Exception as exc:  # noqa: BLE001 - beklenmeyen hata da duzgun mesajla donsun
        print(json.dumps({"hata": type(exc).__name__}))
        return ISCI_HATA_KODU


# --- web sureci ------------------------------------------------------------------------------------
def _isci_komutu() -> list[str]:
    return [sys.executable, "-m", "app.rapor.ceviri", "--isci"]


def _modelle(dolu: dict[str, str]) -> dict[str, str]:
    global _kapali_kadar, _kapali_neden
    if time.monotonic() < _kapali_kadar:
        raise CeviriYok(_kapali_neden)
    if not _sira.acquire(timeout=ZAMAN_ASIMI):
        raise CeviriYok(m("Çeviri şu an meşgul; birkaç saniye sonra tekrar deneyin.", "Translation is busy; try again in a few seconds."))
    try:
        sonuc = subprocess.run(
            _isci_komutu(),
            input=json.dumps(dolu, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=ZAMAN_ASIMI,
            cwd=str(BACKEND),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CeviriYok(
            m("Çeviri zaman aşımına uğradı; metni kısaltıp tekrar deneyin.", "Translation timed out; shorten the text and try again.")
        ) from exc
    except OSError as exc:
        raise CeviriYok(m("Çeviri süreci başlatılamadı.", "The translation process could not be started.")) from exc
    finally:
        _sira.release()
    if sonuc.returncode in (0, ISCI_HATA_KODU):
        try:
            veri = json.loads((sonuc.stdout or "").strip().splitlines()[-1])
        except (ValueError, IndexError):
            veri = {}
        if sonuc.returncode == 0 and isinstance(veri.get("metinler"), dict):
            return {ad: str(v) for ad, v in veri["metinler"].items() if ad in dolu}
        raise CeviriYok(str(veri.get("hata") or "okunamadi"))
    kod = sonuc.returncode & 0xFFFFFFFF
    _kapali_kadar = time.monotonic() + KAPALI_SURE
    _kapali_neden = m(
        f"Çeviri kütüphanesi bu sunucuda çöktü (kod 0x{kod:08X}); panel etkilenmedi. Çeviri {KAPALI_SURE // 60} dakika kapalı.",
        f"The translation library crashed on this server (code 0x{kod:08X}); the panel was not affected. Translation is off for {KAPALI_SURE // 60} minutes.",
    )
    _log.error("Ceviri alt sureci coktu: cikis=0x%08X stderr=%s", kod, (sonuc.stderr or "")[-400:])
    raise CeviriYok(_kapali_neden)


_YZ_ISTEM = (
    "Translate the Turkish values of the following JSON object into English for a monthly technical report sent to a corporate "
    "customer. Keep the keys, line breaks, bullet characters, numbers, names, circuit/CI identifiers and e-mail addresses exactly "
    "as they are. Values that are already English stay unchanged. Reply with ONLY the JSON object, no explanation.\n\n"
)


def _yz_ile(dolu: dict[str, str]) -> dict[str, str]:
    from app.onedesk import yz

    yanit = yz.tamamla(_YZ_ISTEM + json.dumps(dolu, ensure_ascii=False), max_tokens=8000, zaman_asimi=120, sinir=AZAMI_KARAKTER * 2)
    eslesme = re.search(r"\{.*\}", yanit, re.DOTALL)
    try:
        veri = json.loads(eslesme.group(0)) if eslesme else None
    except ValueError:
        veri = None
    if not isinstance(veri, dict):
        raise UygulamaHatasi(502, m("YZ çevirisi okunamadı; tekrar deneyin.", "The AI translation could not be read; try again."))
    return {ad: str(veri.get(ad, deger)) for ad, deger in dolu.items()}


def sozlugu_cevir(metinler: dict[str, str]) -> dict:
    """{alan: turkce} -> {'alanlar': {alan: ingilizce}, 'kaynak': 'model'|'yz'}. Bos alanlar oldugu gibi doner."""
    from app.onedesk import yz

    temiz = {str(ad): str(deger or "") for ad, deger in (metinler or {}).items()}
    dolu = {ad: deger for ad, deger in temiz.items() if deger.strip()}
    if sum(len(d) for d in dolu.values()) > AZAMI_KARAKTER:
        raise UygulamaHatasi(400, m("Çevrilecek metin çok uzun.", "The text to translate is too long."))
    if not dolu:
        return {"alanlar": temiz, "kaynak": None}
    neden = ""
    if model_yerinde():
        try:
            return {"alanlar": {**temiz, **_modelle(dolu)}, "kaynak": "model"}
        except CeviriYok as exc:
            neden = str(exc)
    if yz.durum()["hazir"]:
        return {"alanlar": {**temiz, **_yz_ile(dolu)}, "kaynak": "yz"}
    if neden in ("kutuphane", ""):
        neden = (
            m(
                "Çeviri kütüphanesi kurulu değil; sunucuda kurulum\\ceviri_kur.ps1 betiğini çalıştırın.",
                "The translation library is not installed; run kurulum\\ceviri_kur.ps1 on the server.",
            )
            if model_yerinde()
            else m(
                f"Çeviri modeli bulunamadı: {model_dizini()}. Sunucuda kurulum\\ceviri_kur.ps1 betiğini çalıştırın.",
                f"Translation model not found: {model_dizini()}. Run kurulum\\ceviri_kur.ps1 on the server.",
            )
        )
    elif neden == "model":
        neden = m(f"Çeviri modeli yüklenemedi: {model_dizini()}", f"The translation model could not be loaded: {model_dizini()}")
    raise UygulamaHatasi(503, neden)


if __name__ == "__main__" and "--isci" in sys.argv:
    sys.exit(_isci())
