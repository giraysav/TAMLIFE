"""RCA icin LLM cozum yorumu (istege bagli). Varsayilan KAPALI.

Acik olmasi icin ucu de gerekir:
  TAMLIFE_YZ_SAGLAYICI=anthropic, TAMLIFE_YZ_VERI_PAYLASIMI=izinli, ANTHROPIC_API_KEY (ortam degiskeni; koda/DB'ye yazilmaz).
Modele YALNIZ kok sebep metinleri (kirpilmis) ve sayilar gider; musteri ve lokasyon adi gonderilmez.
Kurumsal veri politikasi onayi olmadan VERI_PAYLASIMI acilmamali. Yeni bagimlilik yok (standart kutuphane).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from app.ortak import UygulamaHatasi

ADRES = "https://api.anthropic.com/v1/messages"
VARSAYILAN_MODEL = "claude-opus-5-5"
ZAMAN_ASIMI = 40
EN_COK_GRUP = 8


def _ortam(ad: str) -> str:
    return (os.environ.get(ad) or "").strip()


def durum() -> dict[str, object]:
    """Arayuze: saglayici ve hazir olup olmadigi (anahtar degeri ASLA donmez)."""
    saglayici = _ortam("TAMLIFE_YZ_SAGLAYICI").lower() or "yerlesik"
    paylasim = _ortam("TAMLIFE_YZ_VERI_PAYLASIMI").lower() == "izinli"
    anahtar = bool(_ortam("ANTHROPIC_API_KEY"))
    hazir = saglayici == "anthropic" and paylasim and anahtar
    eksik = []
    if saglayici != "anthropic":
        eksik.append("TAMLIFE_YZ_SAGLAYICI=anthropic")
    if not paylasim:
        eksik.append("TAMLIFE_YZ_VERI_PAYLASIMI=izinli")
    if not anahtar:
        eksik.append("ANTHROPIC_API_KEY")
    return {
        "saglayici": "anthropic" if saglayici == "anthropic" else "yerlesik",
        "hazir": hazir,
        "model": (_ortam("TAMLIFE_YZ_MODEL") or VARSAYILAN_MODEL) if hazir else None,
        "eksik": [] if hazir else eksik,
    }


def istem(gruplar: list[dict]) -> str:
    satirlar = [
        f"{i}. ({g['adet']} kayıt, %{g['oran']}) {str(g['kok_sebep'])[:300]}" for i, g in enumerate(gruplar[:EN_COK_GRUP], start=1)
    ]
    return (
        "Bir telekom hizmet yönetimi ekibinin kapatılmış alarm/talep/şikayet kayıtlarından çıkarılan en sık kök neden (RCA) grupları aşağıda.\n"
        "Bu gruplar için önceliklendirilmiş, uygulanabilir ve kalıcı çözüm önerileri yaz. Her grup için: olası ortak neden, kalıcı önlem, "
        "izleme/ölçüm önerisi. Kısa ve madde madde, Türkçe yaz. Müşteri veya lokasyon adı uydurma.\n\n" + "\n".join(satirlar)
    )


def yorumla(gruplar: list[dict]) -> str:
    d = durum()
    if not d["hazir"]:
        raise UygulamaHatasi(503, "YZ yorumu kapalı: " + ", ".join(str(e) for e in d["eksik"]) + " gerekli.")
    if not gruplar:
        raise UygulamaHatasi(400, "Yorumlanacak kök neden kaydı yok.")
    govde = json.dumps(
        {"model": d["model"], "max_tokens": 1200, "messages": [{"role": "user", "content": istem(gruplar)}]},
        ensure_ascii=False,
    ).encode("utf-8")
    istek = urllib.request.Request(
        ADRES,
        data=govde,
        method="POST",
        headers={"content-type": "application/json", "x-api-key": _ortam("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"},
    )
    try:
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as yanit:
            veri = json.loads(yanit.read().decode("utf-8"))
        metin = "".join(b.get("text", "") for b in veri.get("content", []) if isinstance(b, dict) and b.get("type") == "text").strip()
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        raise UygulamaHatasi(502, "YZ servisine ulaşılamadı; daha sonra tekrar deneyin.") from None
    if not metin:
        raise UygulamaHatasi(502, "YZ servisi boş yanıt döndürdü.")
    return metin[:6000]
