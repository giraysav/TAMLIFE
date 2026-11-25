"""TopoMaker - musteri envanterinden topoloji.

2026-11-24 kullanici (1): "lokasyon ismi ve ci name alanindaki verileri kullanarak onent'ten gelen ci bilgileri ile basit bir topo ciz".
2026-11-24 kullanici (2): "CI'in alanlarini oku; topolojiyi cizerken acik adrese gore filtrele. Musterinin hangi lokasyonda, hangi il
ilcede servisi varsa ona gore cizimleri daha spesifik olustur; tum envanter cizilince cok buyuk ve anlamsiz veri cikiyor."

Kaynak: customer_ci (kart + istiraklerinin AKTIF CI'lari; isci 4 saatte bir yeniler; adres / devre alanlari musteri.envanter.OZELLIKLER).
  SAHA     = CI'in acik adresi (MUSTERI_ADDRESS; bosluk / noktalama katlanir). Adresi olmayan CI kurumsal lokasyon adiyla gruplanir.
  IL/ILCE  = acik adresin sonundaki "<Ilce> <Il> [TURKIYE]" (adreste gecen SON il adi; ilce ondan onceki kelime). Adres yoksa kurumsal
             lokasyon adi ("Ankara Cankaya") ayni kuralla okunur. Bulunamayan 'Belirsiz'.
  SECIM    = il > ilce > saha. Il secilmemisse en cok CI'li il cizilir; ekranda il / ilce / saha listesi (CI sayilariyla) gelir.
Cizim dosya analiziyle (servis.analiz) AYNI bicimde doner, istemcideki SVG cizimi kullanilir:
  katman 0  Turkcell BB (bulut)
  katman 1  devre (DEVRE_NO; ayni devre no'lu hat / servis CI'lari birlesir) - tur 'switch'
  katman 2  CI (servis kisaltmasi; ipucunda CI adi, urun, cihaz, bant genisligi) - tur 'router'. Devresiz CI dogrudan BB'ye baglanir.
  Kenar etiketi = BB_ROUTER_HOSTNAME, yoksa CI adindaki PE router. Altyapi = DEVRE_TIPI (+ ALTYAPI_SAHIPLIGI) > erisim > CI adi.
  Yedek = Mobile Backup servisi / urunu ya da YEDEKLILIK_KATEGORISI dolu.
  SPoF (tahmin): tek ana devreli ve yedeksiz saha.
Kaynak adi ekranda yazilmaz ("envanter").

2026-11-24 kullanici (3) "cizme kural seti":
  KURAL     = CI adi oneki (topoloji/kurallar.py; 'nw_li', 'nw_mbl'...). Yalniz secili kurallardaki CI'lar cizilir; sayilar ekranda.
  URUN-TUTAR= CI DEVRE_NO'su ailenin Urun-Tutar aktif devre no'lariyla eslesir (skor.urun_tutar.devre_anahtari). Adressiz CI'in
              sahasi Urun-Tutar acik adresinden; iki adres farkli ildeyse CI ipucunda uyari. Eslesme sayilari 'urun_tutar'da.
  LOKASYON  = Kartta elle duzeltilen lokasyon adi (customer_ci_flag.location_name) en yuksek onceliklidir: ayni ilde ayni adli
              CI'lar tek saha, baslik bu ad.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.skor.urun_tutar import devre_anahtari
from app.topoloji import kurallar
from app.topoloji.servis import _KOORDINAT, BULUT, KABLO_RENKLERI, _katla

EN_FAZLA_SAHA = 25
AZAMI_SAHA = 100
AZAMI_CI = 600  # cizilen CI dugumu siniri
SAHA_BASI_CI = 40  # tek saha cizimi doldurmasin
BELIRSIZ = "Belirsiz"
# CI adindaki PE / BB router adi: 'nw_rt_ne40_01.34mslk', 'asr9_01.06sogz' -> 'ne40_01.34mslk', 'asr9_01.06sogz'
_PE = re.compile(r"(?<![a-z0-9])([a-z]+[0-9]+[a-z0-9]*_\d{2}\.\d{2}[a-z]{2,8})", re.IGNORECASE)
# Servis adi -> (etiket, dugumdeki kisaltma). Sira onemli; eslesmeyen servis ilk iki kelimesiyle yazilir, kisaltmasi CI.
KISA_SERVIS = (
    ("MOBILE BACKUP", "Mobil Yedek", "MBB"), ("CPE DATA", "CPE", "CPE"), ("MPLS", "MPLS VPN", "MPLS"), ("SDH", "SDH", "SDH"),
    ("WIFI", "WiFi", "WIFI"), ("INTERNET", "İnternet", "INT"), ("RESELL", "TT Resell", "TT"), ("UYDU", "Uydu", "UYDU"),
    ("SES", "Ses", "SES"), ("VOIP", "Ses", "SES"), ("BEYAZ ALAN", "NDC", "NDC"), ("DDOS", "DDoS", "DDOS"),
    ("GUVENLIK DUVARI", "Firewall", "FW"), ("FIREWALL", "Firewall", "FW"), ("SDWAN", "SD-WAN", "SDWN"), ("WDM", "WDM", "WDM"),
    ("DBS MS", "Yönetilen", "YÖN"), ("MSSP", "Güvenlik", "GÜV"),
)  # fmt: skip
# Adreste il yerine gecen kisaltmalar
IL_KISALTMA = {"IST": "İSTANBUL", "ISTANBUL": "İSTANBUL", "AFYON": "AFYONKARAHİSAR", "MARAS": "KAHRAMANMARAŞ", "URFA": "ŞANLIURFA",
               "ANTEP": "GAZİANTEP", "IZMIT": "KOCAELİ"}  # fmt: skip
_ILCE_DISI = {"TURKIYE", "TR", "MAH", "MAHALLESI", "NO", "CAD", "SK", "SOKAK", "MERKEZI"}
YURT_DISI = "Yurt Dışı"
# Adresin sonundaki ulke adi (katlanmis) -> ekranda ulke. Il 'Yurt Disi', ilce ulke olur (2026-11-24 kullanici onayi).
ULKELER = {
    "ALMANYA": "Almanya", "ITALYA": "İtalya", "INGILTERE": "İngiltere", "FRANSA": "Fransa", "ROMANYA": "Romanya", "FAS": "Fas",
    "SUDAN": "Sudan", "BOSNAHERSEK": "Bosna-Hersek", "HOLLANDA": "Hollanda", "BELCIKA": "Belçika", "AVUSTURYA": "Avusturya",
    "ISVICRE": "İsviçre", "IRAK": "Irak", "IRAN": "İran", "AZERBAYCAN": "Azerbaycan", "GURCISTAN": "Gürcistan", "ABD": "ABD",
    "AMERIKA": "ABD", "OZBEKISTAN": "Özbekistan", "KAZAKISTAN": "Kazakistan", "TURKMENISTAN": "Türkmenistan", "KIRGIZISTAN": "Kırgızistan",
    "KKTC": "KKTC", "KIBRIS": "KKTC", "YUNANISTAN": "Yunanistan", "BULGARISTAN": "Bulgaristan", "RUSYA": "Rusya", "UKRAYNA": "Ukrayna",
    "ISPANYA": "İspanya", "POLONYA": "Polonya", "MACARISTAN": "Macaristan", "SIRBISTAN": "Sırbistan", "KOSOVA": "Kosova",
    "ARNAVUTLUK": "Arnavutluk", "MAKEDONYA": "Makedonya", "LIBYA": "Libya", "MISIR": "Mısır", "CEZAYIR": "Cezayir", "TUNUS": "Tunus",
    "KATAR": "Katar", "BAE": "BAE", "SUUDIARABISTAN": "Suudi Arabistan", "KUVEYT": "Kuveyt", "GURCUSTAN": "Gürcistan",
}  # fmt: skip
# Veri merkezleri: adres girilmemis DC CI'lari lokasyon adindan ile baglanir. Il / ilce, ayni adi tasiyan ADRESLI CI'lardan cikarildi
# (2026-11-24 envanter: Gebze DC 783 CI Kocaeli/Gebze, Temelli DC 357 Ankara/Sincan, Kartal DC Istanbul/Kartal, Sekerpinar Kocaeli/Cayirova).
VERI_MERKEZLERI = (
    ("TURKCELLGEBZEDC", "Gebze DC", "Kocaeli", "Gebze"), ("GEBZEDC", "Gebze DC", "Kocaeli", "Gebze"),
    ("GEBZEDATACENTER", "Gebze DC", "Kocaeli", "Gebze"), ("DCGOSB", "Gebze DC", "Kocaeli", "Gebze"),
    ("TEMELLIDC", "Temelli DC", "Ankara", "Sincan"), ("KARTALDC", "Kartal DC", "İstanbul", "Kartal"),
    ("IZMIRDC", "İzmir DC", "İzmir", "Menderes"), ("BASAKSEHIRVERIMERKEZI", "Başakşehir Veri Merkezi", "İstanbul", "Başakşehir"),
    ("SEKERPINAR", "Şekerpınar", "Kocaeli", "Çayırova"),
)  # fmt: skip


def pe_router(ci_adi: str) -> str:
    m = _PE.search(ci_adi or "")
    return m.group(1).lower() if m else ""


def bb_adi(a: dict, ci_adi: str) -> str:
    bb = (a.get("bb") or "").strip().lower()
    if bb:
        return re.sub(r"^nw_(rt|ra)_", "", bb)
    return pe_router(ci_adi)


def kisa_servis(servis: str) -> tuple[str, str]:
    """(etiket, dugumdeki kisaltma)."""
    s = _katla(servis or "")
    return next(((k, kod) for anahtar, k, kod in KISA_SERVIS if anahtar in s), (" ".join((servis or "CI").split()[:2]), "CI"))


def altyapi(servis: str, a: dict, ci_adi: str = "") -> tuple[str, bool]:
    """(cizgi altyapisi, yedek mi) - KABLO_RENKLERI anahtarlari. Oncelik DEVRE_TIPI (FO / 4.5G / Bakir / MetroEthernet) +
    ALTYAPI_SAHIPLIGI (TT ise TT), sonra erisim / altyapi ozelligi, en son CI adindaki parcalar."""
    s = _katla(servis or "")
    urun = _katla(f"{a.get('urun', '')} {a.get('devre_alt', '')}")
    yedek = "MOBILE BACKUP" in s or "MOBILEBACKUP" in urun.replace(" ", "") or bool(a.get("yedeklilik"))
    tt = _katla(a.get("sahiplik", "")) == "TT" or "TTME" in urun or "RESELL" in s
    tip = _katla(a.get("devre_tipi", ""))
    e = _katla(f"{a.get('erisim', '')} {a.get('altyapi', '')}")
    parca = set(re.split(r"[^a-z0-9]+", (ci_adi or "").lower()))
    if any(k in tip for k in ("4.5G", "4G", "3G", "LTE", "MOBIL")) or "MOBIL" in e or "MOBILE" in s or parca & {"4g", "lte", "mbb"}:
        return "4.5G", True
    if "BAKIR" in tip or "DSL" in tip or "DSL" in e or parca & {"dsl", "adsl", "vdsl", "xdsl", "gshdsl"}:
        return "xDSL", yedek
    if "R/L" in tip or "RADYO" in tip or "R/L" in e or "LEASEDLINE" in e or "RADIOLINK" in urun.replace(" ", ""):
        return "RL", yedek
    if tip in ("FO", "FIBER") or "METROETHERNET" in tip or "METROETHERNET" in e or "FIBER" in e or "SOLME" in urun or parca & {"me", "tsol", "solme", "ttme"}:
        return ("TT Fiber" if tt or "ttme" in parca else "SOL Fiber"), yedek
    if "SDH" in s:
        return "Fiber/RL", yedek
    return "Bilinmiyor", yedek


_IL_ADLARI = {_katla(ad): ad for ad, _ in _KOORDINAT.values()}


def tr_baslik(metin: str) -> str:
    """Turkce bas harf buyuk: 'ÇANKAYA' -> 'Çankaya', 'IĞDIR' -> 'Iğdır', 'istanbul' -> 'İstanbul'."""
    def kelime(k: str) -> str:
        if not k:
            return k
        bas = "İ" if k[0] == "i" else k[0].upper()
        return bas + k[1:].replace("I", "ı").replace("İ", "i").lower()
    return " ".join(kelime(k) for k in metin.split())


def il_ilce(adres: str) -> tuple[str, str]:
    """Acik adres / kurumsal lokasyon adi -> (il, ilce). Adreste gecen SON il adi il, ondan onceki kelime ilce ('Esenler/IST',
    'CAN / CANAKKALE' de okunur); il ilk kelimeyse ('Ankara Cankaya') ilce sonraki kelimedir. Il bulunamazsa ('', '').
    Ilce adresteki yazilisiyla (Turkce harfler korunur) doner; bulunamazsa '' (ekranda 'Belirsiz')."""
    ham = [k for k in re.split(r"[\s,;/\-().:]+", adres or "") if k]
    kelimeler = [_katla(k) for k in ham]

    def ilce_mi(j: int) -> bool:
        aday = kelimeler[j]
        return aday not in _ILCE_DISI and not any(ch.isdigit() for ch in aday) and len(aday) > 1 and \
            _katla(IL_KISALTMA.get(aday, aday)) not in _IL_ADLARI

    for i in range(len(kelimeler) - 1, -1, -1):
        k = _katla(IL_KISALTMA.get(kelimeler[i], kelimeler[i]))
        if k in _IL_ADLARI:
            once = [j for j in range(i - 1, max(-1, i - 3), -1) if ilce_mi(j)]
            sonra = [j for j in range(i + 1, min(len(kelimeler), i + 2)) if ilce_mi(j) and kelimeler[j] != "TURKIYE"]
            j = once[0] if once and i > 0 else (sonra[0] if sonra else (once[0] if once else None))
            return tr_baslik(_IL_ADLARI[k]), (tr_baslik(ham[j]) if j is not None else "")
    return "", ""


def _saha_anahtari(adres: str) -> str:
    return " ".join(re.split(r"[^0-9A-Z]+", _katla(adres or ""))).strip()


def _kisa_adres(adres: str) -> str:
    """Ekranda saha basligi: bos / '.' / '-' parcalar atilir, ilk anlamli parcalar."""
    parcalar = [p.strip() for p in (adres or "").split(",") if p.strip() and p.strip() not in (".", "-", "*", "..", "...")]
    metin = ", ".join(parcalar[:3])
    return metin[:70] + ("…" if len(metin) > 70 else "")


def ulke(metin: str) -> str:
    """Adresin son kelimelerinde ulke adi varsa ulke (yurt disi adres), yoksa ''. Turkiye ili gecen adres yurt disi sayilmaz."""
    kelimeler = [k for k in re.split(r"[^A-Z]+", _katla(metin or "")) if k]
    for n in (2, 1):
        if len(kelimeler) >= n and (u := ULKELER.get("".join(kelimeler[-n:]))):
            return u
    return ""


def veri_merkezi(*adlar: str) -> tuple[str, str, str] | None:
    """Lokasyon adlarindan veri merkezi -> (ad, il, ilce)."""
    for ad in adlar:
        sik = re.sub(r"[^A-Z0-9]", "", _katla(ad or ""))
        for anahtar, dc, il, ilce in VERI_MERKEZLERI:
            if sik and anahtar in sik:
                return dc, il, ilce
    return None


def _saha(r: Any, ut: dict | None = None) -> dict:
    """CI -> saha. Oncelik: acik adres (yurt disi adres -> il 'Yurt Disi', ilce ulke) > Urun-Tutar'da ayni devre no'nun acik
    adresi (ut) > veri merkezi adi > kurumsal lokasyon adi > lokasyon adi. Bulunamayan il / ilce 'Belirsiz' (ciz() ayni devre /
    IMT / saha kodlu kardes CI'dan tamamlar)."""
    a = r.attrs or {}
    adres = a.get("adres", "")
    turetilen = ""
    if not adres and ut and ut.get("adres"):
        adres, turetilen = ut["adres"], "urun_tutar"
    kurumsal = " ".join(str(a.get("lokasyon") or "").split())
    lok_adi = " ".join(str(a.get("lok_adi") or "").split())
    anahtar = _saha_anahtari(adres)
    il, ilce = il_ilce(adres) if adres else ("", "")
    if adres and not il and (u := ulke(adres)):
        il, ilce = YURT_DISI, u
    if not il and not adres and (dc := veri_merkezi(lok_adi, kurumsal)):
        il, ilce, anahtar = dc[1], dc[2], "DC " + _katla(dc[0])
        return {"anahtar": anahtar, "il": il, "ilce": ilce, "adres": "", "kurumsal": dc[0], "turetilen": ""}
    for ad in (kurumsal, lok_adi):
        if il:
            break
        if ad:
            il, ilce = il_ilce(ad)
            if not il and (u := ulke(ad)):
                il, ilce = YURT_DISI, u
    anahtar = anahtar or ("L " + _katla(kurumsal) if kurumsal else "")
    return {"anahtar": anahtar or "YOK", "il": il or BELIRSIZ, "ilce": ilce or BELIRSIZ, "adres": adres, "kurumsal": kurumsal,
            "turetilen": turetilen}  # fmt: skip


def duzeltmeyi_uygula(bilgi: dict, ad: str) -> dict:
    """Kartta elle verilen lokasyon adi: ayni ilde ayni adi tasiyan CI'lar TEK saha olur, baslik bu addir. Adda il gecerse il / ilce
    addan ('Ankara Cankaya Sube'), gecmezse CI'in adres / kardes bilgisinden gelir."""
    il, ilce = il_ilce(ad)
    if not il:
        il, ilce = bilgi["il"], bilgi["ilce"]
    ilce = ilce or BELIRSIZ
    return {**bilgi, "il": il, "ilce": ilce, "anahtar": f"E {_katla(il)}|{_katla(ad)}", "duzeltme": ad}


def ut_karsilastir(r: Any, ut: dict | None) -> str:
    """Urun-Tutar eslesmesi: '' (devre Urun-Tutar'da yok), 'adres' (CI adressiz, adres Urun-Tutar'dan), 'uyumlu' (iki adresin ili
    ayni ya da il okunamadi), 'farkli' (iki adres farkli ilde)."""
    if not ut:
        return ""
    adres = (r.attrs or {}).get("adres", "")
    if not adres:
        return "adres" if ut.get("adres") else "uyumlu"
    il1, il2 = il_ilce(adres)[0], il_ilce(ut.get("adres", ""))[0]
    return "farkli" if il1 and il2 and il1 != il2 else "uyumlu"


KARDES_ALANLARI = ("devre", "imt", "hatbasi")


def kardesten_tamamla(satirlar: list[Any], bilgiler: dict[str, dict]) -> int:
    """Ili belirsiz CI, ayni musteride ayni DEVRE_NO / IMT_ID / hat basi saha kodunu tasiyan ve ili bilinen CI'in sahasina katilir
    (ornek: adresi bos CPE / Mobile Backup CI'i, adresli ana hat CI'i ile ayni devrede). Doner: tamamlanan CI sayisi."""
    bilinen: dict[tuple[str, str, str], dict] = {}
    for r in satirlar:
        b = bilgiler[r.ci_no]
        if b["il"] != BELIRSIZ:
            for alan in KARDES_ALANLARI:
                if deger := (r.attrs or {}).get(alan):
                    bilinen.setdefault((r.customer_key, alan, deger), b)
    n = 0
    for r in satirlar:
        if bilgiler[r.ci_no]["il"] != BELIRSIZ:
            continue
        for alan in KARDES_ALANLARI:
            deger = (r.attrs or {}).get(alan)
            if deger and (k := bilinen.get((r.customer_key, alan, deger))):
                bilgiler[r.ci_no] = {**k, "turetilen": alan}
                n += 1
                break
    return n


def ciz(satirlar: list[Any], baglam: dict | None = None, ara: str = "", en_fazla: int = EN_FAZLA_SAHA, il: str = "", ilce: str = "",
        saha: str = "", kural_seti: list[dict] | None = None, kural: str = "", kural_duzenler: bool = False) -> dict:  # fmt: skip
    """satirlar: CustomerCi (aktif). baglam: musteri.servis.envanter_cileri ('kritik', 'lokasyon', 'ut_devre', 'ut_yuklu').
    kural_seti / kural: CI adi oneki kurallari ve istekteki secim (kurallar.secim_coz). Donus servis.analiz bicimi + 'adres_agaci',
    'secim', 'gosterilen', 'eslesen', 'kurallar', 'urun_tutar'."""
    baglam = baglam or {}
    kritik: set[str] = baglam.get("kritik") or set()
    duzeltme: dict[str, str] = baglam.get("lokasyon") or {}
    ut_devre: dict[str, dict] = baglam.get("ut_devre") or {}
    kural_seti = kural_seti if kural_seti is not None else kurallar.varsayilan()
    onekler = sorted((k["onek"] for k in kural_seti), key=len, reverse=True)
    secili = kurallar.secim_coz(kural, kural_seti)

    # Urun-Tutar devre eslesmesi (devre no anahtari) ve saha bilgisi TUM CI'lar icin (kardes tamamlama filtreden once)
    ut_ci = {r.ci_no: ut_devre.get(devre_anahtari((r.attrs or {}).get("devre"))) for r in satirlar} if ut_devre else {}
    bilgiler = {r.ci_no: _saha(r, ut_ci.get(r.ci_no)) for r in satirlar}
    tamamlanan = kardesten_tamamla(satirlar, bilgiler)
    for ci_no, ad in duzeltme.items():
        if ci_no in bilgiler:
            bilgiler[ci_no] = duzeltmeyi_uygula(bilgiler[ci_no], ad)
    ut_durum = {r.ci_no: ut_karsilastir(r, ut_ci.get(r.ci_no)) for r in satirlar} if ut_devre else {}
    eslesen_ut = {devre_anahtari((r.attrs or {}).get("devre")) for r in satirlar if ut_ci.get(r.ci_no)}

    # Kural filtresi: CI adi oneki
    sinif = {r.ci_no: kurallar.sinifla(r.ci_name, onekler) for r in satirlar}
    kural_sayilari = Counter(sinif.values())
    tum_satirlar = satirlar
    satirlar = [r for r in satirlar if sinif[r.ci_no] in secili]

    sahalar: dict[str, dict] = {}
    for r in satirlar:
        bilgi = bilgiler[r.ci_no]
        s = sahalar.setdefault(bilgi["anahtar"], {**bilgi, "ciler": [], "lok_adlari": Counter()})
        s["ciler"].append(r)
        if lok := (bilgi.get("duzeltme") or (r.attrs or {}).get("lok_adi")):
            s["lok_adlari"][lok] += 1
    # Ilce yazilisi tek: ayni ilce ('PENDIK' -> 'Pendık', 'Pendik') katlanmis anahtarla birlesir, en sik yazilis gosterilir
    yazilis: dict[tuple[str, str], Counter] = {}
    for s in sahalar.values():
        yazilis.setdefault((_katla(s["il"]), _katla(s["ilce"])), Counter())[s["ilce"]] += len(s["ciler"])
    for s in sahalar.values():
        s["ilce"] = yazilis[(_katla(s["il"]), _katla(s["ilce"]))].most_common(1)[0][0]
        s["baslik"] = (s["lok_adlari"].most_common(1)[0][0] if s["lok_adlari"] else "") or _kisa_adres(s["adres"]) or s["kurumsal"] or "Adressiz"

    # Il > ilce > saha agaci (tum envanter; secim listesi)
    agac: dict[str, dict] = {}
    for s in sahalar.values():
        i = agac.setdefault(s["il"], {"il": s["il"], "ci": 0, "ilceler": {}})
        i["ci"] += len(s["ciler"])
        c = i["ilceler"].setdefault(s["ilce"], {"ilce": s["ilce"], "ci": 0, "sahalar": []})
        c["ci"] += len(s["ciler"])
        c["sahalar"].append({"anahtar": s["anahtar"], "baslik": s["baslik"], "adres": _kisa_adres(s["adres"]), "ci": len(s["ciler"])})
    adres_agaci = []
    for i in sorted(agac.values(), key=lambda x: (x["il"] == BELIRSIZ, -x["ci"], x["il"])):
        ilceler = []
        for c in sorted(i["ilceler"].values(), key=lambda x: (x["ilce"] == BELIRSIZ, -x["ci"], x["ilce"])):
            ilceler.append({**c, "sahalar": sorted(c["sahalar"], key=lambda x: (-x["ci"], x["baslik"]))[:AZAMI_SAHA]})
        adres_agaci.append({"il": i["il"], "ci": i["ci"], "ilceler": ilceler})

    # Secim: il verilmemisse (ya da kural degisince secili il kalmadiysa) en cok CI'li il (Belirsiz haric, varsa)
    if il and not any(_katla(x["il"]) == _katla(il) for x in adres_agaci):
        il = ilce = saha = ""
    if not il and adres_agaci:
        il = next((x["il"] for x in adres_agaci if x["il"] != BELIRSIZ), adres_agaci[0]["il"])
    parcalar = [_katla(p) for p in (ara or "").split() if p][:10]

    def uyar(s: dict) -> bool:
        if il and _katla(s["il"]) != _katla(il):
            return False
        if ilce and _katla(s["ilce"]) != _katla(ilce):
            return False
        if saha and s["anahtar"] != saha:
            return False
        if not parcalar:
            return True
        metin = _katla(" ".join([s["baslik"], s["adres"], s["kurumsal"]] + [
            f"{r.ci_name} {r.service} {(r.attrs or {}).get('devre', '')} {(ut_ci.get(r.ci_no) or {}).get('adres', '')}" for r in s["ciler"]]))
        return all(p in metin for p in parcalar)

    eslesen = sorted((s for s in sahalar.values() if uyar(s)), key=lambda s: (-len(s["ciler"]), s["baslik"]))
    secilen = eslesen[: max(1, min(en_fazla, AZAMI_SAHA))]

    dugumler: dict[str, dict] = {BULUT: {"id": BULUT, "tur": "bulut", "etiket": "Turkcell BB", "lokasyon": "", "il": ""}}
    kenarlar: list[dict] = []
    spof: list[dict] = []
    ci_sayisi = gizlenen = 0

    def kenar(kimlik: str, a: str, b: str, alt: str, etiket: str, yedek: bool, devre: str) -> None:
        kenarlar.append({"id": kimlik, "kaynak": a, "hedef": b, "altyapi": alt, "etiket": etiket, "yedek": yedek, "devre": devre,
                         "renk": KABLO_RENKLERI.get(alt, "#7F8C8D")})  # fmt: skip

    for s in secilen:
        lok = f"{s['ilce']} · {s['baslik']}" if s["ilce"] != BELIRSIZ else s["baslik"]
        il_adi = s["il"] if s["il"] != BELIRSIZ else ""
        devreler: dict[str, dict] = {}
        for sira, r in enumerate(sorted(s["ciler"], key=lambda r: (r.service, r.ci_name))):
            if ci_sayisi >= AZAMI_CI or sira >= SAHA_BASI_CI:
                gizlenen += 1
                continue
            a = r.attrs or {}
            alt, yedek = altyapi(r.service, a, r.ci_name)
            bb = bb_adi(a, r.ci_name)
            ci_id = f"CI_{r.ci_no}"
            etiket, kod = kisa_servis(r.service)
            ayrinti = " · ".join(x for x in (r.ci_name, a.get("urun", ""), a.get("model", ""), a.get("bw", "")) if x and x != "CIHAZ_MODEL")
            if ut := ut_ci.get(r.ci_no):
                ayrinti += "\nÜrün-Tutar: " + " · ".join(x for x in (ut.get("grup", ""), ut.get("adres", "")) if x)
                if ut_durum.get(r.ci_no) == "farkli":
                    ayrinti += "\n⚠ Envanter adresi ile Ürün-Tutar adresi farklı ilde"
            dugumler[ci_id] = {"id": ci_id, "tur": "router", "kisa": kod, "etiket": etiket, "lokasyon": lok, "il": il_adi,
                               "ci": ayrinti, "kritik": r.ci_no in kritik}  # fmt: skip
            ci_sayisi += 1
            devre = str(a.get("devre") or "").strip()
            if not devre:
                kenar(f"K{r.ci_no}", BULUT, ci_id, alt, bb, yedek, r.ci_name)
                continue
            d_id = f"D_{s['anahtar']}_{devre}"
            d = devreler.get(d_id)
            if d is None:
                d = devreler[d_id] = {"bb": bb, "alt": alt, "yedek": yedek, "ad": devre}
                dugumler[d_id] = {"id": d_id, "tur": "switch", "kisa": "DEVRE", "etiket": devre, "lokasyon": lok, "il": il_adi}
            d["bb"] = d["bb"] or bb
            if d["alt"] == "Bilinmiyor":
                d["alt"] = alt
            d["yedek"] = d["yedek"] or yedek
            kenar(f"L{r.ci_no}", d_id, ci_id, "LAN", "LAN", False, devre)
        for d_id, d in devreler.items():
            kenar(f"W{d_id}", BULUT, d_id, d["alt"], d["bb"], d["yedek"], d["ad"])
        ana = [d for d in devreler.values() if not d["yedek"]]
        yedekli = any(d["yedek"] for d in devreler.values()) or any("MOBILE" in _katla(x.service) for x in s["ciler"])
        if len(ana) == 1 and not yedekli:
            spof.append({"lokasyon": lok, "bb": ana[0]["bb"] or "—", "altyapilar": [ana[0]["alt"]], "neden": "tek_devre",
                         "devreler": [ana[0]["ad"]]})  # fmt: skip

    sehirler = [
        {"il": x["il"], "adet": x["ci"], "enlem": _KOORDINAT[_katla(x["il"])][1][0], "boylam": _KOORDINAT[_katla(x["il"])][1][1]}
        for x in adres_agaci if _katla(x["il"]) in _KOORDINAT
    ]  # fmt: skip
    uyarilar = []
    if len(eslesen) > len(secilen):
        uyarilar.append(f"{len(eslesen)} sahadan CI sayısı en çok olan {len(secilen)} saha çizildi; ilçe / adres seçerek daraltın.")
    if gizlenen:
        uyarilar.append(f"Çizim sınırı (saha başına {SAHA_BASI_CI}, toplam {AZAMI_CI} CI) nedeniyle {gizlenen} CI gösterilmedi.")
    if spof:
        uyarilar.append("Tek devre (SPoF) tespiti açık adres ve devre no ile yapılan bir tahmindir.")
    ut_ozet = {
        "yuklu": bool(baglam.get("ut_yuklu")),
        "devre": len(ut_devre),
        "eslesen_devre": len(eslesen_ut),
        "eslesen_ci": sum(1 for v in ut_ci.values() if v),
        "adres_tamamlanan": sum(1 for v in ut_durum.values() if v == "adres"),
        "il_farkli": sum(1 for v in ut_durum.values() if v == "farkli"),
    }
    ut_ozet["envanterde_yok"] = ut_ozet["devre"] - ut_ozet["eslesen_devre"]
    if baglam.get("ut_yuklu") and not ut_devre:
        uyarilar.append("Ürün-Tutar dosyası devre listesi saklanmadan önce yüklenmiş; devre no / açık adres eşleşmesi için dosyayı yeniden yükleyin.")
    elif ut_ozet["il_farkli"]:
        uyarilar.append(f"{ut_ozet['il_farkli']} CI'da envanter adresi ile Ürün-Tutar adresi farklı ilde (CI ipucunda gösterilir).")
    kural_listesi = [{**k, "ci": kural_sayilari.get(k["onek"], 0), "secili": k["onek"] in secili, "varsayilan": k["ciz"]} for k in kural_seti]
    kural_listesi.append({"onek": kurallar.DIGER, "ad": "Diğer", "ciz": True, "ci": kural_sayilari.get(kurallar.DIGER, 0),
                          "secili": kurallar.DIGER in secili, "varsayilan": True, "sabit": True})  # fmt: skip
    return {
        "kaynak": "envanter",
        "spof": bool(spof),
        "spof_noktalari": spof,
        "dugumler": list(dugumler.values()),
        "kenarlar": kenarlar,
        "sehirler": sehirler,
        "konumsuz_iller": [],
        "kolonlar": {"loc": "Açık adres", "il": "İl / İlçe", "ci": "CI adı", "c_no_primary": "Devre No", "bb_host": "BB router",
                     "devre_alt": "Devre tipi"},
        "satir": len(tum_satirlar),
        "cizime_giren": len(satirlar),
        "lokasyon": len(sahalar),
        "belirsiz_ci": sum(1 for r in satirlar if bilgiler[r.ci_no]["il"] == BELIRSIZ),
        "tamamlanan_ci": tamamlanan,
        "duzeltilen_ci": sum(1 for r in tum_satirlar if r.ci_no in duzeltme),
        "adres_agaci": adres_agaci,
        "secim": {"il": il, "ilce": ilce, "saha": saha, "kural": ",".join(sorted(secili)) or "-"},
        "kurallar": kural_listesi,
        "kural_duzenler": kural_duzenler,
        "urun_tutar": ut_ozet,
        "gosterilen": len(secilen),
        "eslesen": len(eslesen),
        "degerlendirme": "riskli" if spof else "sinirli",
        "uyarilar": uyarilar,
        "renkler": KABLO_RENKLERI,
    }
