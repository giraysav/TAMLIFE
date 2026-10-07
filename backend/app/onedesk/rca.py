"""RCA (kok neden) ortak nokta analizi: saf, cevrimdisi, kural tabanli. Uretim ats_analizi.py kurallarindan uyarlandi.

Girdi: kayit sozlukleri {root_cause, customer, location, kind, category}. Hicbir veri disari cikmaz.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence

from app.ortak import normal

METIN_SINIRI = 300
_SAYI = re.compile(r"\d+")
_SOZCUK = re.compile(r"[a-z0-9]{4,}")

# Bilgi tasimayan sozcukler (normal() sonrasi, ASCII). Ortak nokta cikarirken elenir.
_DURAK = frozenset(
    ["icin", "ile", "veya", "olarak", "olan", "olduguna", "oldugu", "nedeniyle", "sebebiyle", "kaynakli", "sonucu", "sonra", "gore", "daha", "cok", "kadar", "uzerine", "uzerinde", "tarafindan", "tarafinda", "yapilan", "yapildi", "yapilmasi", "edildi", "edilen", "edilmesi", "gerekli", "gerekiyor", "tespit", "alinan", "alindi", "oldu", "olmustur", "olmasi", "bulunan", "bulundu", "sorun", "sorunu", "problem", "sorunlu", "hatasi", "hata", "ariza", "arizasi", "kayit", "kaydi", "musteri", "musteriye", "musterinin", "lokasyon", "lokasyonda", "lokasyonu", "cihaz", "cihazi", "cihazin", "that", "with", "from", "this", "have", "were", "been"]
)

# (anahtar kelimeler, kalici onlem onerisi). Kok sebep + kategori + cozum metninde aranir.
KURALLAR: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("enerji", "elektrik", "guc", "power", "ups", "jenerator"),
        "Lokasyonun enerji altyapısını (UPS/akü, jeneratör, pano) kontrol ettirin; kesinti tekrarlıyorsa enerji yedekliliği için müşteriyle aksiyon planı yapın.",
    ),
    (
        ("fiber", "kablo", "kesik", "hat", "devre", "link", "down", "flap", "bakir"),
        "Hattın fiziksel katmanını (fiber/bakır, ek noktaları, taşıyıcı) saha ekibiyle ortak inceleyin; tekrar eden kesintide yedek hat/alternatif güzergâh önerin.",
    ),
    (
        ("crc", "interface error", "hata sayaci", "sfp", "port"),
        "Port hata sayaçlarını izleyin; kablo, patch ve SFP değişimini planlayın.",
    ),
    (
        ("cpu", "bellek", "memory", "kaynak", "kapasite", "utilization", "doluluk"),
        "Cihaz kaynak kullanımını trend olarak izleyin; eşikleri gözden geçirip kapasite artırımı/yük dağıtımı önerin.",
    ),
    (
        ("sicaklik", "temperature", "fan", "isinma", "klima", "sogutma"),
        "Kabin/oda soğutmasını ve fanları kontrol ettirin; sıcaklık alarmı için çevresel izleme ekleyin.",
    ),
    (
        ("paket kaybi", "packet loss", "gecikme", "latency", "jitter", "yavas"),
        "Hat kalitesini (paket kaybı/gecikme) ölçün; bant genişliği ve QoS yapılandırmasını gözden geçirin.",
    ),
    (
        ("bgp", "ospf", "routing", "yonlendirme", "konfigurasyon", "config"),
        "Yönlendirme/konfigürasyon değişikliklerini değişiklik kaydıyla ilişkilendirin; standart yapılandırma ve değişiklik öncesi kontrol listesi uygulayın.",
    ),
    (
        ("yazilim", "firmware", "bug", "reboot", "yeniden basla", "restart", "surum"),
        "Cihaz yazılım sürümünü üretici önerisiyle karşılaştırın; bilinen hata varsa planlı sürüm yükseltmesi yapın.",
    ),
    (
        ("musteri kaynakli", "musteri tarafi", "kullanici hatasi", "musteri lokasyonu"),
        "Müşteri kaynaklı tekrarları müşteriyle paylaşın; lokasyon tarafında alınacak önlemi birlikte planlayın.",
    ),
)
VARSAYILAN_ONERI = (
    "Tekrar eden kayıt için problem kaydı açıp kök neden analizi (RCA) yapın; kalıcı çözüm uygulanana kadar lokasyonu yakın izlemeye alın."
)


def grup_anahtari(metin: str) -> str:
    """Benzer kok sebepleri tek grupta toplar: sayi/IP/tarih farklari yok sayilir."""
    return _SAYI.sub("#", normal(metin))


def onleyici_oneriler(*metinler: str, adet: int = 2) -> list[str]:
    """Metinler ONCELIK sirasiyla verilir: ilk metnin eslestigi kural listenin basina gelir."""
    oneriler: list[str] = []
    for metin in metinler:
        m = normal(metin)
        if not m:
            continue
        for anahtarlar, oneri in KURALLAR:
            if oneri not in oneriler and any(k in m for k in anahtarlar):
                oneriler.append(oneri)
    return (oneriler or [VARSAYILAN_ONERI])[:adet]


def ortak_noktalar(kayitlar: Sequence[dict], adet: int = 8) -> list[dict]:
    """Kok sebep metinlerini gruplar; en sik gruplari etki alani (musteri/lokasyon sayisi, tur dagilimi) ve onerilerle doner."""
    gruplar: dict[str, dict] = {}
    toplam = 0
    for k in kayitlar:
        metin = str(k.get("root_cause") or "").strip()
        if not metin:
            continue
        toplam += 1
        g = gruplar.setdefault(
            grup_anahtari(metin),
            {"n": 0, "ornek": Counter(), "musteriler": set(), "lokasyonlar": set(), "turler": Counter(), "kategoriler": Counter()},
        )
        g["n"] += 1
        g["ornek"][metin] += 1
        if k.get("customer"):
            g["musteriler"].add(k["customer"])
        if k.get("location"):
            g["lokasyonlar"].add(k["location"])
        g["turler"][str(k.get("kind") or "")] += 1
        if k.get("category"):
            g["kategoriler"][str(k["category"])] += 1
    sonuc = []
    for _, g in sorted(gruplar.items(), key=lambda kv: (-kv[1]["n"], kv[0]))[:adet]:
        ornek = g["ornek"].most_common(1)[0][0][:METIN_SINIRI]
        kategori = g["kategoriler"].most_common(1)[0][0] if g["kategoriler"] else ""
        sonuc.append(
            {
                "kok_sebep": ornek,
                "adet": g["n"],
                "oran": round(100 * g["n"] / toplam, 1) if toplam else 0.0,
                "musteri_sayisi": len(g["musteriler"]),
                "lokasyon_sayisi": len(g["lokasyonlar"]),
                "turler": {t: n for t, n in g["turler"].items() if t},
                "kategori": kategori,
                "oneriler": onleyici_oneriler(ornek, kategori),
            }
        )
    return sonuc


def anahtar_kelimeler(kayitlar: Iterable[dict], adet: int = 12) -> list[dict]:
    """Kok sebep metinlerinde en cok gecen anlamli sozcukler (kayit basina bir kez sayilir)."""
    sayac: Counter[str] = Counter()
    for k in kayitlar:
        sozcukler = {s for s in _SOZCUK.findall(normal(k.get("root_cause") or "")) if s not in _DURAK}
        sayac.update(sozcukler)
    return [{"kelime": kelime, "adet": n} for kelime, n in sayac.most_common(adet) if n > 1]


def tekrar_eden_lokasyonlar(kayitlar: Iterable[dict], adet: int = 8) -> list[dict]:
    """Ayni lokasyonda birden cok kayit: kalici cozum adayi."""
    sayac: Counter[tuple[str, str]] = Counter()
    for k in kayitlar:
        if k.get("location"):
            sayac[(str(k.get("customer") or "—"), str(k["location"]))] += 1
    return [{"musteri": m, "lokasyon": lok, "adet": n} for (m, lok), n in sayac.most_common(adet) if n > 1]
