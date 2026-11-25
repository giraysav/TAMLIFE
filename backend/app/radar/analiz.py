"""Musteri Radar yonetim sunumu ve musteri analizi (2026-10-25 kullanici istegi: "radardaki atanan musteriler icin ust yonetime sunulacak
satis firsati yaratmaya olanak saglayacak sunum gorseli, grafik; musteriye en cok hangi kok nedenden alarm olusmus, hangi konularda
sikayet / talep olmus ozet; satis direktorleri ve GMY seviyesinde raporlanacak").

Kaynak yalniz Radar'a atanan kartsiz numaralarin TEMIP alarm kayitlari (radar.servis._radar_numaralari).

Kok neden (2026-10-25 veri denetimi): kurumsal devre alarmlari IP SLA olcum alarmidir; ADDITIONALTEXT her zaman "AVAILABILITY / ProbeHost
/ CIName / DEVRE KAPASITESI / MUSTERI SEGMENTI" tasir, PROBABLECAUSE "Unknown". TEMIP'te ariza kok nedeni YOKTUR (OneDesk bilet cozum
kaydindadir). Bu yuzden "ariza profili" verinin gercekten tasidigi uc boyuttan cikarilir: kesinti suresi (anlik < 5 dk: hat kararsizligi;
uzun > 1 sa: fiziksel / enerji / saha arizasi), etki turu (ALARMHEADER: erisilemezlik, gecikme, paket kaybi, jitter) ve hizmet / devre
turu (CI adindan: SD-WAN, MPLS, VPLS, P2P, Internet). Sikayet / talep (2026-11-23 kullanici karari A): Radar numaralarinin OneDesk
kayitlari onedesk.canli isci turuyla kartsiz gelir; musteri basina sayi, acik adet ve en sik konular (kategori) ozetlenir.

Analiz iki katmanli: (1) kural tabanli (her zaman; sayilar, profil -> satis onerisi, firsat skoru) ve (2) istege bagli YZ yorumu
(onedesk.yz; kapaliysa 503). YZ'ye YALNIZ toplu sayilar ve oranlar gider; musteri ve lokasyon adi gonderilmez. Uretilen YZ yorumu
AppSetting YZ_AYARI'nda saklanir (sunumda yeniden ucret odenmeden gosterilir).
"""

from __future__ import annotations

import math
import statistics
import threading
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import musteri_alani
from app.models import AppSetting, OnedeskRecord
from app.ortak import UygulamaHatasi, iso, simdi

YZ_AYARI = "radar.yz_analizleri"
LOKASYON_ADET = 5
AY_ADET = 12
KONU_ADET = 5
# (anahtar, ad, ust sinir dakika) - sabit sira
SURELER = (("anlik", "Anlık (< 5 dk)", 5), ("kisa", "Kısa (5–60 dk)", 60), ("uzun", "Uzun (1–8 sa)", 480), ("cok_uzun", "Çok uzun (> 8 sa)", None))
ETKILER = {"AVAILABILITY": "Erişilemezlik (devre kesintisi)", "DELAY": "Gecikme", "PACKETLOSS": "Paket kaybı", "JITTER": "Jitter"}
KALITE = ("DELAY", "PACKETLOSS", "JITTER")
# CI adi (nw_li_cust_<hizmet>_<musteri lokasyon>[_yedek][_nw_<cihaz>]) -> hizmet turu, ilk eslesen. "_" ile ayrilmis BELIRTEC (tam esleme)
# ya da ICERIK (bitisik yazilabilir: "anasolmempls"). Canli CI ornekleri: _3g_..._yedek_ssr, _tsol_me_int_, _va_sdsl_, _adsl_int_, _sdwan.
HIZMETLER: tuple[tuple[str, frozenset[str], tuple[str, ...]], ...] = (
    ("SD-WAN", frozenset(), ("sdwan",)),
    ("Mobil erişim (3G/4.5G)", frozenset({"3g", "4g", "lte", "m2m", "5g"}), ("3gyedek",)),
    ("VPLS", frozenset(), ("vpls",)),
    ("MPLS", frozenset(), ("mpls",)),
    ("Noktadan noktaya (P2P)", frozenset(), ("p2p",)),
    ("DSL", frozenset({"adsl", "vdsl", "sdsl", "shdsl", "xdsl", "ndsl"}), ()),
    ("İnternet", frozenset({"int", "inet", "internet", "dia"}), ()),
    ("VPN", frozenset({"vpn"}), ()),
    ("Radyolink", frozenset({"rl"}), ()),
)
YEDEK = frozenset({"yedek", "backup"})
VARSAYILAN_ONERI = "7/24 proaktif izleme ve TAM (teknik müşteri yönetimi) hizmeti"

_ONBELLEK: tuple[tuple, dict[str, Any]] | None = None
_KILIT = threading.Lock()


class AnalizHata(UygulamaHatasi):
    pass


def _belirtecler(ci: str) -> tuple[str, set[str]]:
    ad = (ci or "").casefold().split("_nw_")[0]
    return ad, set(ad.split("_"))


def hizmet_turu(ci: str) -> str:
    ad, b = _belirtecler(ci)
    return next((tur for tur, tam, icerik in HIZMETLER if b & tam or any(x in ad for x in icerik)), "Diğer")


def yedek_hat_mi(ci: str) -> bool:
    ad, b = _belirtecler(ci)
    return bool(b & YEDEK) or "yedek" in ad


def sure_sinifi(dakika: float) -> str:
    return next(a for a, _, ust in SURELER if ust is None or dakika < ust)


def _numaralar(db: Session) -> set[str]:
    from app.radar import servis

    return servis._radar_numaralari(db)


def _kayitlar(db: Session, nolar: set[str]) -> dict[str, list[tuple]]:
    """Musteri No -> [(durum, acilis, kapanis, baslik, lokasyon, ayrinti, unvan)] (yalniz kartsiz TEMIP kayitlari)."""
    from app.tampon import temip_kayit

    grup: dict[str, list[tuple]] = defaultdict(list)
    sutunlar = (OnedeskRecord.customer_no, OnedeskRecord.status, OnedeskRecord.opened_at, OnedeskRecord.closed_at, OnedeskRecord.category,
                OnedeskRecord.location, OnedeskRecord.detail, OnedeskRecord.customer_label)  # fmt: skip
    liste = sorted(nolar)
    for i in range(0, len(liste), 500):
        for no, *geri in db.execute(
            select(*sutunlar).where(
                OnedeskRecord.source == temip_kayit.KAYNAK_ADI, OnedeskRecord.customer_id.is_(None), OnedeskRecord.customer_no.in_(liste[i : i + 500])
            )
        ):
            grup[no].append(tuple(geri))
    return grup


def _biletler(db: Session, nolar: set[str]) -> dict[str, list[tuple[str, str, str]]]:
    """Musteri No -> [(tur, durum, konu)]: Radar numarasinin kartsiz sikayet / talep kayitlari (onedesk.canli)."""
    from app.onedesk import canli

    grup: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    liste = sorted(nolar)
    for i in range(0, len(liste), 500):
        for no, tur, durum, konu in db.execute(
            select(OnedeskRecord.customer_no, OnedeskRecord.kind, OnedeskRecord.status, OnedeskRecord.category).where(
                OnedeskRecord.source == canli.KAYNAK_ADI, OnedeskRecord.customer_id.is_(None), OnedeskRecord.customer_no.in_(liste[i : i + 500])
            )
        ):
            grup[no].append((tur, durum, konu or ""))
    return grup


def _bilet_ozeti(biletler: list[tuple[str, str, str]]) -> dict[str, Any]:
    """{sikayet, talep, sikayet_acik, talep_acik, konular: [{ad, adet, sikayet, talep}]} (en sik KONU_ADET konu)."""
    s = {t: sum(1 for k in biletler if k[0] == t) for t in ("sikayet", "talep")}
    s.update({f"{t}_acik": sum(1 for k in biletler if k[0] == t and k[1] == "open") for t in ("sikayet", "talep")})
    konu: dict[str, Counter[str]] = defaultdict(Counter)
    for tur, _, ad in biletler:
        konu[ad or "Konu belirtilmemiş"][tur] += 1
    sirali = sorted(konu.items(), key=lambda x: (-x[1].total(), x[0]))[:KONU_ADET]
    s["konular"] = [{"ad": ad, "adet": c.total(), "sikayet": c["sikayet"], "talep": c["talep"]} for ad, c in sirali]
    return s


def _yuzde(pay: float, payda: float) -> float:
    return round(100 * pay / payda, 1) if payda else 0.0


def _naif(d):
    return d.replace(tzinfo=None) if d is not None and d.tzinfo else d


def _dagilim(sayac: Counter, adlar: dict[str, str], toplam: int, sira: list[str] | None = None) -> list[dict[str, Any]]:
    anahtarlar = sira if sira is not None else [a for a, _ in sorted(sayac.items(), key=lambda x: (-x[1], x[0]))]
    return [{"anahtar": a, "ad": adlar.get(a, a), "adet": sayac[a], "oran": _yuzde(sayac[a], toplam)} for a in anahtarlar]


def _musteri(no: str, kayitlar: list[tuple], bugun) -> dict[str, Any]:
    acilislar = [k[1] for k in kayitlar if k[1] is not None]
    ilk, son = (min(acilislar), max(acilislar)) if acilislar else (None, None)
    aylar = Counter(f"{k[1]:%Y-%m}" for k in kayitlar if k[1] is not None)
    kapali = [k for k in kayitlar if k[0] == "closed"]
    sureler = [(k[2] - k[1]).total_seconds() / 60 for k in kapali if k[1] and k[2] and k[2] >= k[1]]
    sure_sayac = Counter(sure_sinifi(d) for d in sureler)
    etki = Counter((k[3] or "").upper() or "DİĞER" for k in kayitlar)
    lokasyonlar = Counter(k[4] for k in kayitlar if k[4])
    hizmet_alarm: Counter[str] = Counter()
    hizmet_lok: Counter[str] = Counter()
    for ci, n in lokasyonlar.items():
        tur = hizmet_turu(ci)
        hizmet_alarm[tur] += n
        hizmet_lok[tur] += 1
    kendiliginden = sum(1 for k in kapali if (k[5] or "").endswith(("Auto-Clear", "atm")))
    son30 = sum(1 for d in acilislar if _naif(d) >= bugun - timedelta(days=30))
    onceki30 = sum(1 for d in acilislar if bugun - timedelta(days=60) <= _naif(d) < bugun - timedelta(days=30))
    toplam = len(kayitlar)
    return {
        "musteri_no": no,
        "unvan": next((k[6] for k in kayitlar if k[6]), no),
        "toplam": toplam,
        "acik": sum(1 for k in kayitlar if k[0] == "open"),
        "kapanan": len(kapali),
        "ilk_kayit": iso(ilk),
        "son_kayit": iso(son),
        "aylik_ortalama": round(toplam / max(1, len(aylar)), 1),
        "lokasyon_sayisi": len(lokasyonlar),
        "sdwan_oran": _yuzde(hizmet_lok["SD-WAN"], len(lokasyonlar)),
        "yedek_oran": _yuzde(sum(1 for ci in lokasyonlar if yedek_hat_mi(ci)), len(lokasyonlar)),
        "kendiliginden_oran": _yuzde(kendiliginden, len(kapali)),
        "medyan_cozum_dk": round(statistics.median(sureler)) if sureler else None,
        "anlik_oran": _yuzde(sure_sayac["anlik"], len(sureler)),
        "uzun_oran": _yuzde(sure_sayac["uzun"] + sure_sayac["cok_uzun"], len(sureler)),
        "kalite_oran": _yuzde(sum(etki[e] for e in KALITE), toplam),
        "son30": son30,
        "onceki30": onceki30,
        "degisim": _yuzde(son30 - onceki30, onceki30) if onceki30 else None,
        "aylar": [{"ay": a, "toplam": aylar[a]} for a in sorted(aylar)[-AY_ADET:]],
        "sure_profili": _dagilim(sure_sayac, {a: ad for a, ad, _ in SURELER}, len(sureler), [a for a, _, _ in SURELER]),
        "etki": _dagilim(etki, ETKILER, toplam),
        "hizmetler": [{"ad": t, "adet": n, "lokasyon": hizmet_lok[t], "oran": _yuzde(n, toplam)} for t, n in sorted(hizmet_alarm.items(), key=lambda x: (-x[1], x[0]))],
        "lokasyonlar": [{"ad": ad, "adet": n} for ad, n in sorted(lokasyonlar.items(), key=lambda x: (-x[1], x[0]))[:LOKASYON_ADET]],
    }  # fmt: skip


def _skorla(musteriler: list[dict[str, Any]]) -> None:
    """Firsat skoru 0-100 (portfoy icinde goreli): aylik alarm hacmi %40 (log), etkilenen lokasyon %20, acik alarm %15, uzun kesinti
    (> 1 sa) orani %15, son 30 gun artis %10. Sinif portfoyun ucte birlik dilimleri: ust 1/3 yuksek, orta 1/3 orta, alt 1/3 dusuk (3'ten az
    musteride skor 70 / 40 esikleri)."""
    if not musteriler:
        return
    en = {k: max(math.log1p(m[a]) for m in musteriler) or 1 for k, a in (("hacim", "aylik_ortalama"), ("lokasyon", "lokasyon_sayisi"), ("acik", "acik"))}
    for m in musteriler:
        bilesen = {
            "hacim": 40 * math.log1p(m["aylik_ortalama"]) / en["hacim"],
            "lokasyon": 20 * math.log1p(m["lokasyon_sayisi"]) / en["lokasyon"],
            "acik": 15 * math.log1p(m["acik"]) / en["acik"],
            "uzun_kesinti": 15 * min(1.0, m["uzun_oran"] / 50),
            "artis": 10 * min(1.0, max(0.0, (m["degisim"] or 0) / 100)),
        }
        m["skor"] = round(sum(bilesen.values()))
        m["skor_bilesen"] = {k: round(v, 1) for k, v in bilesen.items()}
    if len(musteriler) < 3:
        for m in musteriler:
            m["firsat"] = "yuksek" if m["skor"] >= 70 else "orta" if m["skor"] >= 40 else "dusuk"
        return
    sirali = sorted(musteriler, key=lambda m: (-m["skor"], -m["toplam"]))
    ucte = math.ceil(len(sirali) / 3)
    for i, m in enumerate(sirali):
        m["firsat"] = "yuksek" if i < ucte else "orta" if i < 2 * ucte else "dusuk"


def _tr(v: float) -> str:
    if isinstance(v, float) and not v.is_integer():
        return f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{int(v):,}".replace(",", ".")


def _sure_metni(dk: int) -> str:
    return f"{_tr(dk)} dk" if dk < 120 else f"{_tr(round(dk / 60, 1))} saat"


def _ozet_cumleleri(m: dict[str, Any], sira: int, adet: int) -> list[str]:
    """Kural tabanli yonetim ozeti (YZ kapaliyken de calisir). Yalniz olculen sayilardan, uydurma yok."""
    c = [f"{_tr(m['toplam'])} ağ alarmı (aylık ortalama {_tr(m['aylik_ortalama'])}); Radar portföyünde alarm hacminde {sira}/{adet}. sırada."]
    if m["etki"]:
        e = m["etki"][0]
        c.append(f"Alarmların %{_tr(e['oran'])}'i {e['ad'].lower()}" + (f"; %{_tr(m['kalite_oran'])}'i hizmet kalitesi (gecikme, paket kaybı)." if m["kalite_oran"] else "."))
    if m["kapanan"]:
        c.append(f"Kesintilerin %{_tr(m['anlik_oran'])}'i 5 dakikadan kısa, %{_tr(m['uzun_oran'])}'i 1 saatten uzun sürdü"
                 + (f"; medyan süre {_sure_metni(m['medyan_cozum_dk'])}." if m["medyan_cozum_dk"] is not None else "."))  # fmt: skip
    if m["lokasyon_sayisi"]:
        h = m["hizmetler"][0]
        c.append(f"{_tr(m['lokasyon_sayisi'])} lokasyon/devre etkilendi; alarmların %{_tr(h['oran'])}'i {h['ad']} devrelerinde.")
    if m["degisim"] is not None:
        yon = "arttı" if m["degisim"] > 0 else "azaldı" if m["degisim"] < 0 else "değişmedi"
        c.append(f"Son 30 günde {_tr(m['son30'])} alarm; önceki 30 güne göre %{_tr(abs(m['degisim']))} {yon}.")
    if m["acik"]:
        c.append(f"Şu an {_tr(m['acik'])} açık alarm var.")
    b = m["sikayet_talep"]
    if b["sikayet"] or b["talep"]:
        acik = b["sikayet_acik"] + b["talep_acik"]
        c.append(f"{_tr(b['sikayet'])} şikayet ve {_tr(b['talep'])} talep kaydı" + (f" ({_tr(acik)} açık)" if acik else "")
                 + (f"; en sık konu: {b['konular'][0]['ad']}." if b["konular"] else "."))  # fmt: skip
    return c


def _oneriler(m: dict[str, Any]) -> list[dict[str, str]]:
    """Satis firsatlari: olculen ariza profilinden (her biri gerekcesiyle). En cok 4."""
    o: list[dict[str, str]] = []
    if m["uzun_oran"] >= 25 and m["yedek_oran"] >= 10:
        o.append({"baslik": "Mevcut yedek hatların 4.5G/5G'ye yükseltilmesi ve otomatik yük devri",
                  "gerekce": f"Lokasyonların %{_tr(m['yedek_oran'])}'inde yedek hat var, yine de kesintilerin %{_tr(m['uzun_oran'])}'i 1 saatten uzun"})  # fmt: skip
    elif m["uzun_oran"] >= 25:
        o.append({"baslik": "Yedekli erişim (ikinci hat ya da 4.5G/5G yedek)", "gerekce": f"Kesintilerin %{_tr(m['uzun_oran'])}'i 1 saatten uzun sürüyor"})
    if m["anlik_oran"] >= 50:
        o.append({"baslik": "Hat sağlığı analizi ve hat yenileme", "gerekce": f"Kesintilerin %{_tr(m['anlik_oran'])}'i 5 dakikadan kısa (kararsız hat)"})
    if m["kalite_oran"] >= 5:
        o.append({"baslik": "Kapasite artışı ve QoS", "gerekce": f"Alarmların %{_tr(m['kalite_oran'])}'i gecikme / paket kaybı / jitter"})
    if m["lokasyon_sayisi"] >= 5 and m["sdwan_oran"] >= 30:
        o.append({"baslik": "Mevcut SD-WAN için yedek erişim ve SLA'lı yönetilen hizmet",
                  "gerekce": f"{_tr(m['lokasyon_sayisi'])} lokasyonun %{_tr(m['sdwan_oran'])}'i SD-WAN ve alarm üretmeye devam ediyor"})  # fmt: skip
    elif m["lokasyon_sayisi"] >= 5:
        o.append({"baslik": "Merkezi yönetimli ağ (SD-WAN / Managed Network)", "gerekce": f"{_tr(m['lokasyon_sayisi'])} lokasyon/devre alarm üretiyor"})
    if len(o) < 4:
        o.append({"baslik": VARSAYILAN_ONERI, "gerekce": f"TAM'a atanmamış müşteri; aylık ortalama {_tr(m['aylik_ortalama'])} alarm"})
    return o[:4]


def _yz_kayitlari(db: Session) -> dict[str, Any]:
    a = db.get(AppSetting, YZ_AYARI)
    return dict(a.value) if a is not None and isinstance(a.value, dict) else {}


def _yz_durumu() -> dict[str, Any]:
    from app.onedesk import yz

    d = yz.durum()
    return {"hazir": d["hazir"], "eksik": d["eksik"]}


def _topla(musteriler: list[dict[str, Any]], alan: str) -> list[dict[str, Any]]:
    sayac: Counter[str] = Counter()
    adlar: dict[str, str] = {}
    for m in musteriler:
        for x in m[alan]:
            sayac[x["anahtar"]] += x["adet"]
            adlar[x["anahtar"]] = x["ad"]
    toplam = sum(sayac.values())
    sira = [a for a, _, _ in SURELER] if alan == "sure_profili" else None
    return _dagilim(sayac, adlar, toplam, sira)


@musteri_alani.tum_alanlarda
def portfoy(db: Session) -> dict[str, Any]:
    """Radar'a atanan tum musterilerin analizi (firsat skoruna gore) ve portfoy toplamlari. Surum + Radar listesi izine gore onbellekte."""
    global _ONBELLEK
    from app.radar import servis
    from app.tampon import temip_kayit

    nolar = _numaralar(db)
    iz = (temip_kayit.surum(db), servis.bilet_surumu(db), frozenset(nolar))
    with _KILIT:
        if _ONBELLEK is not None and _ONBELLEK[0] == iz:
            return _ONBELLEK[1]
    bugun = _naif(simdi())
    biletler = _biletler(db, nolar)
    musteriler = [{**_musteri(no, k, bugun), "sikayet_talep": _bilet_ozeti(biletler.get(no, []))} for no, k in _kayitlar(db, nolar).items() if k]
    _skorla(musteriler)
    hacim_sirasi = {m["musteri_no"]: i for i, m in enumerate(sorted(musteriler, key=lambda m: -m["toplam"]), 1)}
    yz = _yz_kayitlari(db)
    for m in musteriler:
        m["ozet"] = _ozet_cumleleri(m, hacim_sirasi[m["musteri_no"]], len(musteriler))
        m["oneriler"] = _oneriler(m)
        m["yz"] = yz.get(m["musteri_no"])
    musteriler.sort(key=lambda m: (-m["skor"], -m["toplam"]))
    sonuc = {
        "zaman": iso(simdi()),
        "veri_zamani": temip_kayit.surum(db) or None,
        "musteri_sayisi": len(musteriler),
        "toplam_alarm": sum(m["toplam"] for m in musteriler),
        "acik_alarm": sum(m["acik"] for m in musteriler),
        "lokasyon": sum(m["lokasyon_sayisi"] for m in musteriler),
        "firsat": {f: sum(1 for m in musteriler if m["firsat"] == f) for f in ("yuksek", "orta", "dusuk")},
        "sure_profili": _topla(musteriler, "sure_profili"),
        "etki": _topla(musteriler, "etki"),
        "musteriler": musteriler,
        "yz": _yz_durumu(),
    }
    with _KILIT:
        _ONBELLEK = (iz, sonuc)
    return sonuc


def musteri(db: Session, musteri_no: str) -> dict[str, Any]:
    for m in portfoy(db)["musteriler"]:
        if m["musteri_no"] == musteri_no:
            return m
    raise AnalizHata(404, "Bu Müşteri No Müşteri Radar'da değil.")


SISTEM = (
    "Bir telekom operatörünün kurumsal satış ve teknik müşteri yönetimi analistisin. Raporunu satış direktörleri ve genel müdür yardımcısı "
    "okuyacak. Yalnız verilen sayılara dayan; sayı, ürün adı ya da müşteri bilgisi uydurma. Türkçe, kısa, karar odaklı yaz."
)


def istem(m: dict[str, Any]) -> str:
    """YZ istemi: YALNIZ toplu sayilar ve oranlar (musteri / lokasyon adi yok)."""
    sure = ", ".join(f"{x['ad']}: %{x['oran']}" for x in m["sure_profili"])
    etki = ", ".join(f"{x['ad']}: {x['adet']}" for x in m["etki"])
    hizmet = ", ".join(f"{x['ad']}: {x['adet']} alarm / {x['lokasyon']} lokasyon" for x in m["hizmetler"]) + f"; yedek hatlı lokasyon %{m['yedek_oran']}"
    aylar = ", ".join(f"{a['ay']}: {a['toplam']}" for a in m["aylar"])
    b = m["sikayet_talep"]
    bilet = (
        f"Müşteri kayıtları: {b['sikayet']} şikayet ({b['sikayet_acik']} açık), {b['talep']} talep ({b['talep_acik']} açık).\n"
        if b["sikayet"] or b["talep"]
        else "Bu dönemde müşterinin şikayet ya da talep kaydı yok.\n"
    )
    return (
        "Panelde hiçbir teknik müşteri yöneticisine (TAM) atanmamış bir kurumsal müşterinin devre izleme (IP SLA) alarm özeti aşağıda. "
        "Alarmlar devreye erişilemediğini ya da kalitenin düştüğünü gösterir; arıza kök nedeni kayıtta yoktur, süre profili kök neden "
        "sınıfına işaret eder (çok sayıda kısa kesinti: hat kararsızlığı; uzun kesinti: fiziksel / enerji / saha arızası).\n"
        f"Toplam alarm {m['toplam']} (açık {m['acik']}), aylık ortalama {m['aylik_ortalama']}, etkilenen lokasyon/devre {m['lokasyon_sayisi']}, "
        f"medyan kesinti süresi {m['medyan_cozum_dk'] if m['medyan_cozum_dk'] is not None else 'bilinmiyor'} dk, son 30 gün {m['son30']} / "
        f"önceki 30 gün {m['onceki30']}.\nKesinti süresi profili: {sure}\nEtki türü: {etki}\nHizmet türü: {hizmet}\nAylık alarm: {aylar}\n"
        f"{bilet}\n"
        "Şu başlıklarla yaz (her biri en çok 2 madde): 1) Durum, 2) İş etkisi ve risk, 3) Satış fırsatı (somut hizmet önerisi ve "
        "gerekçesi), 4) Önerilen ilk aksiyon. Toplam 160 kelimeyi geçme."
    )


def yz_uret(db: Session, musteri_no: str, kullanici: str) -> dict[str, Any]:
    """YZ yorumu uretir ve saklar. YZ kapaliysa onedesk.yz 503 doner (anahtar degeri hata metnine girmez)."""
    global _ONBELLEK
    from app.onedesk import yz

    m = musteri(db, musteri_no)
    metin = yz.tamamla(istem(m), sistem=SISTEM, max_tokens=900)
    kayit = {"metin": metin.strip(), "zaman": iso(simdi()), "kim": kullanici, "model": yz.durum()["model"]}
    hepsi = _yz_kayitlari(db)
    hepsi[musteri_no] = kayit
    a = db.get(AppSetting, YZ_AYARI)
    if a is None:
        db.add(AppSetting(key=YZ_AYARI, value=hepsi, updated_by=kullanici, updated_at=simdi()))
    else:
        a.value, a.updated_by, a.updated_at = hepsi, kullanici, simdi()
    db.commit()
    with _KILIT:
        _ONBELLEK = None
    return kayit
