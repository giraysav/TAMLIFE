"""SLA Excel'inin TUM verisinin analizi ve ozet rapor metni (aylik rapor).

Uretim karsiliklari: ats_analizi.py (CI bazli analiz, kural tabanli oneriler, LLM yorumu), blueprints/customer_bp.py
(_ats_kayitlari, _ci_ticket_pivotu, _hat_availability_ozeti, _excel_rapor_metinleri).

Iki katman:
  1) Yerlesik analiz (her zaman, cevrimdisi): Detay sayfalarindaki kapanan Alarm/Sikayet/Talep kayitlari CI Adi bazinda;
     tur basina adet, Kategori ve Cagri Servisi dagilimi, en cok tekrar edenin kok sebebi / yapilan cozum ve kural
     tabanli kalici onlem onerileri; 'Hat Availability' ozeti ve donem sayilari. Hicbir veri disari cikmaz.
  2) YZ yorumu (istege bagli): onedesk/yz.py ile AYNI ayar (TAMLIFE_YZ_SAGLAYICI=anthropic, TAMLIFE_YZ_VERI_PAYLASIMI=izinli,
     ANTHROPIC_API_KEY). Modele yalniz OZET gider (en cok 10 CI, kirpilmis metinler); musteri adi gonderilmez.
Ozet metin rapor dilinde uretilir (tr/en); personel rapora eklemeden once gozden gecirir. Iki parca (kullanici karari
2026-10-11): 'bilgi' (SLA Excel verileri + donem ozeti; maddeler arasinda bos satir) ve 'devam' (Devam Eden Calismalar:
acik kayitlar numarasiyla ve tekrar eden sorunlarin takibi). Musteriye ONERI yazilmaz; rapor takip belgesidir.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections import Counter
from typing import Any

from app.ortak import normal
from app.rapor.sla import AZAMI_ACIK, KATEGORILER, SlaHata, ay_kodu, sayi

EN_COK_CI = 10
EN_COK_TEKRAR = 3
EN_COK_COZUM = 3
EN_COK_KIRILIM = 8
METIN_SINIRI = 300
AZAMI_SATIR = 20000
HUCRE_SINIRI = 500
TURLER = tuple(k for k, _ in KATEGORILER)

# Sutun eslemesi: baslik metni (Turkce harf/buyuk-kucuk duyarsiz) bu adlardan biriyle BIREBIR, yoksa ICEREREK eslesir.
SUTUN_ADLARI = {
    "ci": ("ci adi", "ci name", "ci", "lokasyon", "konfigurasyon ogesi"),
    "kategori": ("kategori", "alarm adi", "alarm", "ozet", "ozeti", "summary", "kisa aciklama"),
    "urun": ("cagri urun adi", "urun adi", "urun"),
    "servis": ("cagri servisi", "servis"),
    "kok": ("kok sebep", "kok neden", "root cause"),
    "cozum": ("cozum aciklamasi", "cozum", "resolution", "yapilan islem", "kapanis notu"),
    "kapanis": ("kapanis ayi",),
    "no": ("cagri no", "inc id", "kayit no", "ticket no", "no"),
}
EN_COK_ACIK = 30
YOK = {
    "tr": {"ci": "(CI adı yok)", "kategori": "(kategori yok)", "servis": "(servis yok)"},
    "en": {"ci": "(no CI name)", "kategori": "(no category)", "servis": "(no service)"},
}
TUR_ADI = {
    "tr": {"alarm": "alarm", "sikayet": "şikayet", "talep": "talep"},
    "en": {"alarm": "alarm", "sikayet": "complaint", "talep": "request"},
}

# (anahtar kelimeler, {dil: kalici onlem onerisi}). Kok sebep + kategori + cozum metninde aranir.
_KURALLAR: tuple[tuple[tuple[str, ...], dict[str, str]], ...] = (
    (
        ("enerji", "elektrik", "guc", "power", "ups", "jenerator"),
        {
            "tr": "Lokasyonun enerji altyapısını (UPS/akü, jeneratör, pano) kontrol ettirin; kesinti tekrarlıyorsa enerji yedekliliği için müşteriyle aksiyon planı yapın.",
            "en": "Have the site's power infrastructure (UPS/battery, generator, panel) checked; if outages recur, agree a power redundancy action plan with the customer.",
        },
    ),
    (
        ("fiber", "kablo", "kesik", "hat", "devre", "link", "down", "flap", "bakir"),
        {
            "tr": "Hattın fiziksel katmanını (fiber/bakır, ek noktaları, taşıyıcı) saha ekibiyle ortak inceleyin; tekrar eden kesintide yedek hat/alternatif güzergâh önerin.",
            "en": "Review the physical layer of the line (fiber/copper, splice points, carrier) with the field team; propose a backup line or alternative route for recurring outages.",
        },
    ),
    (
        ("crc", "interface error", "hata sayaci", "sfp", "port"),
        {
            "tr": "Port hata sayaçlarını izleyin; kablo, patch ve SFP değişimini planlayın.",
            "en": "Monitor port error counters; plan cable, patch and SFP replacement.",
        },
    ),
    (
        ("cpu", "bellek", "memory", "kaynak", "kapasite", "utilization", "doluluk"),
        {
            "tr": "Cihaz kaynak kullanımını trend olarak izleyin; eşikleri gözden geçirip kapasite artırımı/yük dağıtımı önerin.",
            "en": "Track device resource usage as a trend; review thresholds and propose a capacity upgrade or load balancing.",
        },
    ),
    (
        ("sicaklik", "temperature", "fan", "isinma", "klima", "sogutma"),
        {
            "tr": "Kabin/oda soğutmasını ve fanları kontrol ettirin; sıcaklık alarmı için çevresel izleme ekleyin.",
            "en": "Have cabinet/room cooling and fans checked; add environmental monitoring for temperature alarms.",
        },
    ),
    (
        ("paket kaybi", "packet loss", "gecikme", "latency", "jitter", "yavas"),
        {
            "tr": "Hat kalitesini (paket kaybı/gecikme) ölçün; bant genişliği ve QoS yapılandırmasını gözden geçirin.",
            "en": "Measure line quality (packet loss/latency); review bandwidth and QoS configuration.",
        },
    ),
    (
        ("bgp", "ospf", "routing", "yonlendirme", "konfigurasyon", "config"),
        {
            "tr": "Yönlendirme/konfigürasyon değişikliklerini değişiklik kaydıyla ilişkilendirin; standart yapılandırma ve değişiklik öncesi kontrol listesi uygulayın.",
            "en": "Link routing/configuration changes to change records; apply a standard configuration and a pre-change checklist.",
        },
    ),
    (
        ("yazilim", "firmware", "bug", "reboot", "yeniden basla", "restart", "surum"),
        {
            "tr": "Cihaz yazılım sürümünü üretici önerisiyle karşılaştırın; bilinen hata varsa planlı sürüm yükseltmesi yapın.",
            "en": "Compare the device software version with the vendor recommendation; schedule an upgrade if there is a known bug.",
        },
    ),
    (
        ("musteri kaynakli", "musteri tarafi", "kullanici hatasi", "musteri lokasyonu"),
        {
            "tr": "Müşteri kaynaklı tekrarları müşteriyle paylaşın; lokasyon tarafında alınacak önlemi birlikte planlayın.",
            "en": "Share customer-caused recurrences with the customer and plan the on-site measures together.",
        },
    ),
)
_VARSAYILAN_ONERI = {
    "tr": "Tekrar eden kayıt için problem kaydı açıp kök neden analizi (RCA) yapın; kalıcı çözüm uygulanana kadar CI'yi yakın izlemeye alın.",
    "en": "Open a problem record for the recurring issue and run a root cause analysis (RCA); keep the CI under close watch until a permanent fix is in place.",
}


# --- okuma -----------------------------------------------------------------------------------------
def sutunlari_bul(basliklar: list[str]) -> dict[str, int | None]:
    """{'ci': indeks|None, ...}. Birebir eslesme icerene tercih edilir; 4 harften kisa ad icererek eslesmez."""
    adlar = [normal(b) for b in basliklar]
    sonuc: dict[str, int | None] = {}
    for alan, adaylar in SUTUN_ADLARI.items():
        bulunan = next((adlar.index(a) for a in adaylar if a in adlar), None)
        if bulunan is None:
            for aday in (a for a in adaylar if len(a) >= 4):
                bulunan = next((i for i, ad in enumerate(adlar) if aday in ad), None)
                if bulunan is not None:
                    break
        sonuc[alan] = bulunan
    return sonuc


def _metin(deger: object) -> str:
    if deger is None:
        return ""
    if hasattr(deger, "strftime"):
        return deger.strftime("%Y-%m-%d")  # type: ignore[union-attr]
    return str(deger).strip()[:HUCRE_SINIRI]


def _ws_satirlari(ws: Any, sinir: int) -> list[tuple]:
    satirlar = []
    for i, satir in enumerate(ws.iter_rows(values_only=True)):
        if i >= sinir:
            break
        satirlar.append(tuple(satir))
    return satirlar


def _detay(satirlar: list[tuple]) -> dict | None:
    """Baslik satiri (ilk 5 satirda 'Kapanis Ayi' gecen), KAPANAN kayitlar (Kapanis Ayi dolu) ve ACIK kayitlar (bos, satir dolu)."""
    for b, dizi in enumerate(satirlar[:5]):
        basliklar = [_metin(h) for h in dizi]
        sutunlar = sutunlari_bul(basliklar)
        kapanis = sutunlar["kapanis"]
        if kapanis is None:
            continue
        kayitlar, acik = [], []
        for s in satirlar[b + 1 :]:
            if len(s) > kapanis and s[kapanis] not in (None, ""):
                kayitlar.append([_metin(v) for v in s])
            elif any(v not in (None, "") for v in s):
                acik.append([_metin(v) for v in s])
        return {"basliklar": basliklar, "sutunlar": sutunlar, "satirlar": kayitlar, "acik": acik}
    return None


def _ci_pivotu(satirlar: list[tuple]) -> dict | None:
    """'CI Ticket Analiz': CI Adi x ay (YYYY-MM) kapanan kayit sayisi."""
    for b, dizi in enumerate(satirlar[:5]):
        ci = next((i for i, h in enumerate(dizi) if h and normal(h) == "ci adi"), None)
        if ci is None:
            continue
        aylar = [(i, ay_kodu(h)) for i, h in enumerate(dizi) if h is not None and re.fullmatch(r"\d{4}-\d{2}", ay_kodu(h))]
        if not aylar:
            return None
        kayit = []
        for s in satirlar[b + 1 :]:
            ad = _metin(s[ci] if len(s) > ci else None)
            if not ad or normal(ad) in ("genel toplam", "toplam", "grand total"):
                continue
            kayit.append([ad[:200]] + [int(sayi(s[i]) or 0) if len(s) > i else 0 for i, _ in aylar])
        return {"aylar": [a for _, a in aylar], "satirlar": kayit}
    return None


def _availability(satirlar: list[tuple]) -> dict | None:
    """'Hat Availability': devre bazli erisilebilirlik. Deger oran (0.995) ya da yuzde (99.5) gelebilir."""
    for b, dizi in enumerate(satirlar[:6]):
        sutun = next((i for i, h in enumerate(dizi) if h and "availability" in normal(h)), None)
        if sutun is None:
            continue
        devreler = []
        for s in satirlar[b + 1 :]:
            deger = sayi(s[sutun]) if len(s) > sutun else None
            if not s or s[0] is None or deger is None or deger < 0:
                continue
            devreler.append((str(s[0]).strip()[:120], deger))
        if any(d > 1.0 for _, d in devreler):
            devreler = [(a, d / 100) for a, d in devreler if d <= 100]
        if not devreler:
            return None
        en_dusuk = min(devreler, key=lambda x: x[1])
        return {
            "devre_sayisi": len(devreler),
            "ortalama": sum(d for _, d in devreler) / len(devreler),
            "en_dusuk_devre": en_dusuk[0],
            "en_dusuk_deger": en_dusuk[1],
            "tam_erisim_sayisi": sum(1 for _, d in devreler if d >= 1.0),
        }
    return None


def dosyayi_oku(veri: bytes) -> dict:
    """{'kaynaklar': {tur: detay}, 'pivot', 'availability'}. Okunamayan dosyada 400."""
    import openpyxl
    from openpyxl.utils.exceptions import InvalidFileException

    from app.dil import m
    from app.ortak import eslestirme_anahtari

    try:
        if sum(b.file_size for b in zipfile.ZipFile(io.BytesIO(veri)).infolist()) > AZAMI_ACIK:
            raise ValueError("boyut")
        wb = openpyxl.load_workbook(io.BytesIO(veri), read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as exc:
        raise SlaHata(400, m("SLA dosyası okunamadı.", "The SLA file could not be read.")) from exc
    try:
        anahtar = {eslestirme_anahtari(s): s for s in wb.sheetnames}
        kaynaklar = {}
        for tur, ad in KATEGORILER:
            sayfa = anahtar.get(eslestirme_anahtari(f"{ad} Detay"))
            detay = _detay(_ws_satirlari(wb[sayfa], AZAMI_SATIR)) if sayfa else None
            if detay:
                kaynaklar[tur] = detay
        pivot_sayfa = anahtar.get(eslestirme_anahtari("CI Ticket Analiz"))
        hat_sayfa = anahtar.get(eslestirme_anahtari("Hat Availability"))
        return {
            "kaynaklar": kaynaklar,
            "pivot": _ci_pivotu(_ws_satirlari(wb[pivot_sayfa], AZAMI_SATIR)) if pivot_sayfa else None,
            "availability": _availability(_ws_satirlari(wb[hat_sayfa], AZAMI_SATIR)) if hat_sayfa else None,
        }
    finally:
        wb.close()


# --- yerlesik analiz -------------------------------------------------------------------------------
def _grup_anahtari(metin: str) -> str:
    """Benzer kayitlari tek grupta toplar: sayi/IP/tarih farklari yok sayilir."""
    return re.sub(r"\d+", "#", normal(metin))


def _en_sik(metinler: list[str], adet: int) -> list[tuple[str, int]]:
    gruplar: Counter[str] = Counter()
    ornekler: dict[str, Counter[str]] = {}
    for metin in metinler:
        if not metin:
            continue
        a = _grup_anahtari(metin)
        gruplar[a] += 1
        ornekler.setdefault(a, Counter())[metin] += 1
    return [(ornekler[a].most_common(1)[0][0][:METIN_SINIRI], n) for a, n in gruplar.most_common(adet)]


def onleyici_oneriler(*metinler: str, dil: str = "tr", adet: int = 2) -> list[str]:
    """Metinler ONCELIK sirasiyla verilir (en sik kok sebep once): ilk metnin eslestigi kural basa gelir."""
    oneriler: list[str] = []
    for metin in metinler:
        n = normal(metin)
        if not n:
            continue
        for anahtarlar, oneri in _KURALLAR:
            if oneri[dil] not in oneriler and any(k in n for k in anahtarlar):
                oneriler.append(oneri[dil])
    return (oneriler or [_VARSAYILAN_ONERI[dil]])[:adet]


def _kayitlar(kaynaklar: dict, dil: str, liste: str = "satirlar") -> list[dict]:
    """liste: 'satirlar' (kapanan) ya da 'acik'."""
    yok = YOK[dil]
    sonuc = []
    for tur in TURLER:
        kaynak = kaynaklar.get(tur)
        if not kaynak:
            continue
        s = kaynak["sutunlar"]

        def deger(satir: list[str], alan: str, s: dict = s) -> str:
            i = s.get(alan)
            return satir[i] if i is not None and i < len(satir) else ""

        for satir in kaynak.get(liste) or []:
            sonuc.append(
                {
                    "tur": tur,
                    "no": deger(satir, "no")[:60],
                    "ci": deger(satir, "ci") or yok["ci"],
                    "kategori": deger(satir, "kategori") or yok["kategori"],
                    "servis": deger(satir, "servis") or yok["servis"],
                    "urun": deger(satir, "urun"),
                    "kok": deger(satir, "kok"),
                    "cozum": deger(satir, "cozum"),
                    "ay": ay_kodu(deger(satir, "kapanis")),
                }
            )
    return sonuc


def _kirilim(kayitlar: list[dict], alan: str, adet: int) -> list[dict]:
    sayac = Counter(k[alan] for k in kayitlar)
    tur_sayac: dict[str, Counter[str]] = {}
    for k in kayitlar:
        tur_sayac.setdefault(k[alan], Counter())[k["tur"]] += 1
    return [
        {"ad": ad[:METIN_SINIRI], "adet": n, "turler": dict(tur_sayac[ad])}
        for ad, n in sorted(sayac.items(), key=lambda x: (-x[1], normal(x[0])))[:adet]
    ]


def _tekrarlar(kayitlar: list[dict], dil: str) -> list[dict]:
    """En cok tekrar eden kategori(+urun): kok sebep, yapilan cozum, kalici aksiyon."""
    icerik = [" / ".join(x for x in (k["kategori"], k["urun"]) if x) for k in kayitlar]
    sonuc = []
    for ornek, n in _en_sik(icerik, EN_COK_TEKRAR):
        anahtar = _grup_anahtari(ornek)
        ilgili = [k for k, metin in zip(kayitlar, icerik, strict=True) if _grup_anahtari(metin) == anahtar]
        koklar = _en_sik([k["kok"] for k in ilgili], 2)
        cozumler = _en_sik([k["cozum"] for k in ilgili], EN_COK_COZUM)
        sonuc.append(
            {
                "icerik": ornek,
                "adet": n,
                "kok_sebepler": [{"metin": t, "adet": a} for t, a in koklar],
                "cozumler": [{"metin": t, "adet": a} for t, a in cozumler],
                "oneriler": onleyici_oneriler(*(t for t, _ in koklar), ornek, *(t for t, _ in cozumler), dil=dil),
            }
        )
    return sonuc


def donem_sla(grafikler: list[dict] | None, donem: str) -> dict[str, dict]:
    """SLA Excel pivotlarindan (rapor/sla.py grafikleri) donemin kapanan adedi ve sure ortalamalari (dk)."""
    sonuc: dict[str, dict] = {}
    for g in grafikler or []:
        aylar = g.get("aylar") or []
        if donem not in aylar:
            continue
        i = aylar.index(donem)
        hedef = sonuc.setdefault(g.get("kategori") or "", {})
        for ad, seri in (g.get("seriler") or {}).items():
            if i < len(seri) and seri[i] is not None:
                hedef[ad] = seri[i]
    return {k: v for k, v in sonuc.items() if k and v}


def analiz(okunan: dict, donem: str, dil: str = "tr", grafikler: list[dict] | None = None) -> dict:
    """Dosyadaki tum kapanan kayitlarin CI bazinda analizi + donem sayilari + acik kayitlar + availability."""
    kayitlar = _kayitlar(okunan.get("kaynaklar") or {}, dil)
    acik = _kayitlar(okunan.get("kaynaklar") or {}, dil, "acik")
    ci_grup: dict[str, list[dict]] = {}
    for k in kayitlar:
        ci_grup.setdefault(k["ci"], []).append(k)
    sirali = sorted(ci_grup.items(), key=lambda x: (-len(x[1]), normal(x[0])))
    pivot = okunan.get("pivot") or {}
    trend = {normal(p[0]): list(zip(pivot.get("aylar") or [], p[1:], strict=False)) for p in pivot.get("satirlar") or [] if p}
    ciler = [
        {
            "ci": ci[:METIN_SINIRI],
            "adet": len(ks),
            "turler": dict(Counter(k["tur"] for k in ks)),
            "trend": [{"ay": a, "adet": n} for a, n in trend.get(normal(ci), []) if n],
            "kategoriler": _kirilim(ks, "kategori", EN_COK_KIRILIM),
            "servisler": _kirilim(ks, "servis", EN_COK_KIRILIM),
            "tekrarlar": _tekrarlar(ks, dil),
        }
        for ci, ks in sirali[:EN_COK_CI]
    ]
    donemde = [k for k in kayitlar if k["ay"] == donem]
    return {
        "dil": dil,
        "donem": donem,
        "turler_mevcut": [t for t in TURLER if t in (okunan.get("kaynaklar") or {})],
        "toplam": len(kayitlar),
        "tur_toplam": dict(Counter(k["tur"] for k in kayitlar)),
        "donem_toplam": dict(Counter(k["tur"] for k in donemde)),
        "aylar": sorted({k["ay"] for k in kayitlar if re.fullmatch(r"\d{4}-\d{2}", k["ay"])}),
        "ci_sayisi": len(ci_grup),
        "tekrarlayan_ci": sum(1 for ks in ci_grup.values() if len(ks) >= 2),
        "kategori_dagilimi": _kirilim(kayitlar, "kategori", 10),
        "servis_dagilimi": _kirilim(kayitlar, "servis", 10),
        "donem_ciler": _kirilim(donemde, "ci", 5),
        "donem_sla": donem_sla(grafikler, donem),
        "acik_toplam": dict(Counter(k["tur"] for k in acik)),
        "acik": [{a: k[a][:METIN_SINIRI] for a in ("tur", "no", "ci", "kategori")} for k in acik[:EN_COK_ACIK]],
        "ciler": ciler,
        "availability": okunan.get("availability"),
    }


def _yuzde(oran: float, dil: str) -> str:
    return f"{oran * 100:.3f}%" if dil == "en" else f"%{oran * 100:.3f}".replace(".", ",")


def _sayi_yaz(deger: float, dil: str) -> str:
    metin = f"{deger:.0f}" if float(deger).is_integer() else f"{deger:.1f}"
    return metin if dil == "en" else metin.replace(".", ",")


def ozet_metni(sonuc: dict, donem_adi: str, dil: str = "tr") -> dict[str, str]:
    """Rapor alanlarina eklenebilecek yerlesik ozet (rapor dilinde, madde isaretli, maddeler arasi bos satir):
    'bilgi' -> Bilgilendirmeler (SLA Excel verileri + donem ozeti), 'devam' -> Devam Eden Calismalar (acik kayitlar, takip)."""
    en = dil == "en"
    ad = TUR_ADI["en" if en else "tr"]
    dt = sonuc.get("donem_toplam") or {}
    tt = sonuc.get("tur_toplam") or {}
    mevcut = sonuc.get("turler_mevcut") or []
    bilgi: list[str] = []
    # SLA Excel'inin kendi verileri (pivotlar): kategori basina donemde kapanan, ilk mudahale ve cozum ortalamasi.
    for tur, deger in (sonuc.get("donem_sla") or {}).items():
        if tur not in ad:
            continue
        parca = []
        if "adet" in deger:
            parca.append(f"{_sayi_yaz(deger['adet'], dil)} closed" if en else f"{_sayi_yaz(deger['adet'], dil)} kayıt kapatılmış")
        if "ilk" in deger:
            parca.append(
                f"average first response {_sayi_yaz(deger['ilk'], dil)} min"
                if en
                else f"ortalama ilk müdahale süresi {_sayi_yaz(deger['ilk'], dil)} dk"
            )
        if "cozum" in deger:
            parca.append(
                f"average resolution {_sayi_yaz(deger['cozum'], dil)} min"
                if en
                else f"ortalama çözüm süresi {_sayi_yaz(deger['cozum'], dil)} dk"
            )
        if parca:
            baslik = ad[tur].capitalize()
            bilgi.append(
                f"• {baslik} (SLA report, {donem_adi}): " + ", ".join(parca) + "."
                if en
                else f"• {baslik} (SLA raporu, {donem_adi}): " + ", ".join(parca) + "."
            )
    if mevcut:
        parcalar = ", ".join(f"{dt.get(t, 0)} {ad[t]}" for t in mevcut)
        bilgi.append(
            f"• In the {donem_adi} period, {parcalar} records were closed."
            if en
            else f"• {donem_adi} döneminde {parcalar} kaydı kapatılmıştır."
        )
        aylar = sonuc.get("aylar") or []
        kapsam = f" ({aylar[0]} – {aylar[-1]})" if len(aylar) > 1 else ""
        toplam = ", ".join(f"{tt.get(t, 0)} {ad[t]}" for t in mevcut)
        bilgi.append(
            f"• The SLA file covers {sonuc['toplam']} closed records in total{kapsam}: {toplam}; {sonuc['ci_sayisi']} CIs, "
            f"{sonuc['tekrarlayan_ci']} of them with more than one record."
            if en
            else f"• SLA dosyasında toplam {sonuc['toplam']} kapanan kayıt{kapsam} incelenmiştir: {toplam}; "
            f"{sonuc['ci_sayisi']} CI, bunlardan {sonuc['tekrarlayan_ci']} tanesinde birden fazla kayıt bulunmaktadır."
        )
    donem_ci = [c for c in sonuc.get("donem_ciler") or [] if c["adet"] >= 2]
    if donem_ci:
        liste = ", ".join(f"{c['ad']} ({c['adet']})" for c in donem_ci[:3])
        bilgi.append(f"• Most records in the period: {liste}." if en else f"• Dönemde en çok kayıt açılan CI'lar: {liste}.")
    kat = (sonuc.get("kategori_dagilimi") or [])[:3]
    if kat:
        liste = ", ".join(f"{k['ad']} ({k['adet']})" for k in kat)
        bilgi.append(f"• Most frequent categories: {liste}." if en else f"• En sık kategoriler: {liste}.")
    av = sonuc.get("availability")
    if av:
        bilgi.append(
            f"• Availability: {av['devre_sayisi']} circuits were monitored; average availability was {_yuzde(av['ortalama'], dil)}, "
            f"lowest {_yuzde(av['en_dusuk_deger'], dil)} ({av['en_dusuk_devre']})."
            if en
            else f"• Erişilebilirlik: {av['devre_sayisi']} devre izlenmiş, ortalama erişilebilirlik {_yuzde(av['ortalama'], dil)}, "
            f"en düşük {_yuzde(av['en_dusuk_deger'], dil)} ({av['en_dusuk_devre']}) olarak ölçülmüştür."
        )
    devam: list[str] = []
    for k in sonuc.get("acik") or []:
        no = k["no"] or "-"
        devam.append(
            f"• {ad[k['tur']].capitalize()} record no. {no} ({k['ci']}, {k['kategori']}) is still open; work on it continues."
            if en
            else f"• {no} numaralı {ad[k['tur']]} kaydı ({k['ci']}, {k['kategori']}) açık durumdadır; çalışmalar devam etmektedir."
        )
    acik_toplam = sum((sonuc.get("acik_toplam") or {}).values())
    if acik_toplam > len(sonuc.get("acik") or []):
        devam.append(
            f"• {acik_toplam} records are open in total; the list above shows the first {len(sonuc['acik'])}."
            if en
            else f"• Toplam {acik_toplam} kayıt açıktır; yukarıda ilk {len(sonuc['acik'])} kayıt listelenmiştir."
        )
    for c in (sonuc.get("ciler") or [])[:3]:
        if c["adet"] < 2 or not c["tekrarlar"] or c["tekrarlar"][0]["adet"] < 2:
            continue
        t = c["tekrarlar"][0]
        devam.append(
            f'• {c["ci"]}: "{t["icerik"]}" recurred {t["adet"]} times; the root cause is being followed up.'
            if en
            else f'• {c["ci"]}: "{t["icerik"]}" {t["adet"]} kez tekrarlamıştır; kök neden takibi devam etmektedir.'
        )
    return {"bilgi": "\n\n".join(bilgi), "devam": "\n\n".join(devam)}


# --- YZ yorumu -------------------------------------------------------------------------------------
_YZ_SISTEM = {
    "tr": (
        "Sen Turkcell Teknik Müşteri Yöneticisi (TAM) için çalışan bir ağ operasyon analistisin. Sana bir müşterinin SLA raporundaki "
        "KAPANAN alarm/şikayet/talep kayıtlarının özeti JSON olarak verilecek: dönem ve toplam sayılar, CI Adı (lokasyon/cihaz) bazında "
        "tür adetleri, Kategori ve Çağrı Servisi kırılımı, en çok tekrar edenlerin kök sebebi ve yapılan çözüm, erişilebilirlik. "
        "Ayrıca dönemin SLA pivot değerleri (kapanan adet, ortalama ilk müdahale ve çözüm süresi, dk) ve AÇIK kayıtlar (kayıt "
        "numarasıyla) verilir. Müşteriye gidecek aylık rapora BİLGİLENDİRME yaz; müşteriye öneri ya da tavsiye YAZMA. İki bölüm: "
        "'Bilgilendirme:' altında dönemin SLA verileri ve genel değerlendirmesi; 'Devam eden çalışmalar:' altında her açık kayıt "
        "için '<numara> numaralı kayıt açık durumdadır; çalışmalar devam etmektedir' biçiminde birer madde ve tekrar eden sorunların "
        "takibi. Yalnızca verideki bilgiye dayan; veride olmayan cihaz modeli, tarih ya da sayı uydurma. Türkçe, kısa maddeler (• ile "
        "başlayan), maddeler arasında bir boş satır, düz metin; Markdown başlık ya da tablo kullanma."
    ),
    "en": (
        "You are a network operations analyst working for a Turkcell Technical Account Manager (TAM). You will receive, as JSON, a "
        "summary of the CLOSED alarm/complaint/request records in a customer's SLA report: period and total counts, per-CI (site/device) "
        "type counts, category and call service breakdown, root cause and resolution of the most recurring ones, and availability. "
        "You also receive the period's SLA pivot values (closed count, average first response and resolution time in minutes) and "
        "the OPEN records (with record numbers). Write INFORMATION for the monthly report sent to the customer; do NOT give the "
        "customer recommendations or advice. Two sections: under 'Information:' the period's SLA figures and overall assessment; "
        "under 'Ongoing work:' one bullet per open record in the form 'Record no. <number> is still open; work on it continues', "
        "plus follow-up of recurring issues. Rely only on the data; do not invent device models, dates or numbers. English, short "
        "bullets starting with •, one blank line between bullets, plain text; no Markdown headings or tables."
    ),
}


def yz_girdisi(sonuc: dict) -> str:
    """Modele giden ozet: musteri adi YOK; metinler kirpilir."""
    ozet = {
        "donem": sonuc["donem"],
        "donemde_kapanan": sonuc["donem_toplam"],
        "toplam_kapanan": sonuc["tur_toplam"],
        "ci_sayisi": sonuc["ci_sayisi"],
        "tekrarlayan_ci": sonuc["tekrarlayan_ci"],
        "kategoriler": [{"ad": k["ad"][:120], "adet": k["adet"]} for k in sonuc["kategori_dagilimi"]],
        "erisilebilirlik": sonuc.get("availability"),
        "donem_sla": sonuc.get("donem_sla"),
        "acik_kayitlar": [{a: str(k[a])[:120] for a in ("tur", "no", "ci", "kategori")} for k in sonuc.get("acik") or []],
        "ciler": [
            {
                "ci": c["ci"][:120],
                "kapanan": c["adet"],
                "turler": c["turler"],
                "aylik": c["trend"][-6:],
                "kategoriler": [{"ad": k["ad"][:120], "adet": k["adet"]} for k in c["kategoriler"]],
                "cagri_servisleri": [{"ad": k["ad"][:120], "adet": k["adet"]} for k in c["servisler"]],
                "tekrar_edenler": [
                    {
                        "icerik": a["icerik"][:200],
                        "adet": a["adet"],
                        "kok_sebep": [k["metin"][:150] for k in a["kok_sebepler"]],
                        "yapilan_cozum": [z["metin"][:200] for z in a["cozumler"]],
                    }
                    for a in c["tekrarlar"]
                ],
            }
            for c in sonuc["ciler"]
        ],
    }
    return json.dumps(ozet, ensure_ascii=False)


def yz_yorumu(sonuc: dict, dil: str = "tr") -> str:
    from app.onedesk import yz

    return yz.tamamla(yz_girdisi(sonuc), sistem=_YZ_SISTEM["en" if dil == "en" else "tr"], max_tokens=3000, zaman_asimi=120, sinir=12000)
