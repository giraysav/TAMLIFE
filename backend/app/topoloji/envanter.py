"""TopoMaker - musteri envanterinden basit topoloji (2026-11-24 kullanici: "lokasyon ismi ve ci name alanindaki verileri kullanarak
onent'ten gelen ci bilgileri ile basit bir topo ciz; once neler yapabildigimizi gorelim sonra gelistirelim").

Ilk surum (deneme). Kaynak: customer_ci (kart + istiraklerinin AKTIF CI'lari; isci 4 saatte bir yeniler). Cizim dosya analiziyle
(servis.analiz) AYNI bicimde doner, istemcideki SVG cizimi degismeden kullanilir:
  katman 0  Turkcell BB (bulut)
  katman 1  devre (CI'in DEVRE_NO ozelligi; ayni devre no'lu hat / servis CI'lari tek devrede birlesir) - tur 'switch'
  katman 2  CI (servis basina; kisa servis adi) - tur 'router'. Devresi olmayan CI dogrudan BB'ye baglanir.
  Lokasyon = CI'in KURUMSAL_LOKASYON_ADI ozelligi (buyuk harf / Turkce katlanarak gruplanir; bos ise 'Lokasyonsuz').
  Kenar etiketi = CI adindaki PE router adi (orn. 'ne40_01.34mslk'); altyapi = erisim / servis adindan.
  Il = lokasyon adinin ilk kelimesi il ise (harita sekmesi).
  SPoF (ilk kural): tek devreli ve yedeksiz (Mobile Backup yok) lokasyon.
Buyuk musteride (binlerce CI) cizim okunmaz: arama + en fazla N lokasyon (CI sayisi en cok olanlar) gosterilir.
Kaynak adi ekranda yazilmaz ("envanter").
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.topoloji.servis import _KOORDINAT, BULUT, KABLO_RENKLERI, _katla

EN_FAZLA_LOKASYON = 25
AZAMI_LOKASYON = 100
AZAMI_CI = 600  # cizilen CI dugumu siniri
LOKASYON_BASI_CI = 40  # tek lokasyon cizimi doldurmasin
LOKASYONSUZ = "Lokasyonsuz"
# CI adindaki PE / BB router adi: 'nw_rt_ne40_01.34mslk', 'asr9_01.06sogz' -> 'ne40_01.34mslk', 'asr9_01.06sogz'
_PE = re.compile(r"(?<![a-z0-9])([a-z]+[0-9]+[a-z0-9]*_\d{2}\.\d{2}[a-z]{2,8})", re.I)
# Servis adi -> (etiket, dugumdeki kisaltma). Sira onemli; eslesmeyen servis ilk iki kelimesiyle yazilir, kisaltmasi CI.
KISA_SERVIS = (
    ("MOBILE BACKUP", "Mobil Yedek", "MBB"), ("CPE DATA", "CPE", "CPE"), ("MPLS", "MPLS VPN", "MPLS"), ("SDH", "SDH", "SDH"),
    ("WIFI", "WiFi", "WIFI"), ("INTERNET", "İnternet", "INT"), ("RESELL", "TT Resell", "TT"), ("UYDU", "Uydu", "UYDU"),
    ("SES", "Ses", "SES"), ("VOIP", "Ses", "SES"), ("BEYAZ ALAN", "NDC", "NDC"), ("DDOS", "DDoS", "DDOS"),
    ("GUVENLIK DUVARI", "Firewall", "FW"), ("FIREWALL", "Firewall", "FW"), ("SDWAN", "SD-WAN", "SDWN"), ("WDM", "WDM", "WDM"),
    ("DBS MS", "Yönetilen", "YÖN"), ("MSSP", "Güvenlik", "GÜV"),
)  # fmt: skip


def pe_router(ci_adi: str) -> str:
    m = _PE.search(ci_adi or "")
    return m.group(1).lower() if m else ""


def kisa_servis(servis: str) -> tuple[str, str]:
    """(etiket, dugumdeki kisaltma)."""
    s = _katla(servis or "")
    return next(((k, kod) for anahtar, k, kod in KISA_SERVIS if anahtar in s), (" ".join((servis or "CI").split()[:2]), "CI"))


def altyapi(servis: str, erisim: str, altyapi_tipi: str, ci_adi: str = "") -> tuple[str, bool]:
    """(cizgi altyapisi, yedek mi) - KABLO_RENKLERI anahtarlari. Erisim ozelligi bossa CI adindaki parcalardan
    ('_me_', 'tsol' -> SOL Fiber; 'ttme' -> TT; 'dsl' -> xDSL; '4g' / 'lte' -> 4.5G)."""
    s, e = _katla(servis or ""), _katla(f"{erisim or ''} {altyapi_tipi or ''}")
    parca = set(re.split(r"[^a-z0-9]+", (ci_adi or "").lower()))
    if not e.strip():
        if parca & {"dsl", "adsl", "vdsl", "xdsl", "gshdsl"}:
            e = "DSL"
        elif parca & {"4g", "lte", "mbb", "45g"}:
            e = "MOBIL"
        elif parca & {"ttme", "tt"}:
            e = "TT"
        elif parca & {"me", "tsol", "solme", "fiber"}:
            e = "METROETHERNET"
    if "MOBILE" in s or "MOBIL" in e:
        return "4.5G", True
    if "DSL" in e:
        return "xDSL", True
    if "RESELL" in s or "TT" in e.split():
        return "TT Fiber", False
    if "METROETHERNET" in e or "FIBER" in e:
        return "SOL Fiber", False
    if "R/L" in e or "LEASEDLINE" in e or "SDH" in s:
        return "Fiber/RL", False
    return "Bilinmiyor", False


def _il(lokasyon: str) -> str:
    ilk = _katla(lokasyon).split(" ")[0] if lokasyon else ""
    return _KOORDINAT[ilk][0] if ilk in _KOORDINAT else ""


def ciz(satirlar: list[Any], kritik: set[str], ara: str = "", en_fazla: int = EN_FAZLA_LOKASYON) -> dict:
    """satirlar: CustomerCi (aktif). Donus servis.analiz bicimi + 'kaynak', 'lokasyon_listesi', 'gosterilen', 'gizlenen_ci'."""
    gruplar: dict[str, dict] = {}
    for r in satirlar:
        a = r.attrs or {}
        ad = " ".join(str(a.get("lokasyon") or "").split()) or LOKASYONSUZ
        g = gruplar.setdefault(_katla(ad), {"ad": ad, "ciler": []})
        g["ciler"].append(r)
    parcalar = [_katla(p) for p in (ara or "").split() if p][:10]

    def uyar(g: dict) -> bool:
        if not parcalar:
            return True
        metin = _katla(g["ad"] + " " + " ".join(f"{r.ci_name} {r.service} {(r.attrs or {}).get('devre', '')}" for r in g["ciler"]))
        return all(p in metin for p in parcalar)

    liste = sorted(gruplar.values(), key=lambda g: (-len(g["ciler"]), _katla(g["ad"])))
    eslesen = [g for g in liste if uyar(g)]
    secilen = eslesen[: max(1, min(en_fazla, AZAMI_LOKASYON))]

    dugumler: dict[str, dict] = {BULUT: {"id": BULUT, "tur": "bulut", "etiket": "Turkcell BB", "lokasyon": "", "il": ""}}
    kenarlar: list[dict] = []
    spof: list[dict] = []
    ci_sayisi = gizlenen = 0

    def kenar(kimlik: str, a: str, b: str, alt: str, etiket: str, yedek: bool, devre: str) -> None:
        kenarlar.append({"id": kimlik, "kaynak": a, "hedef": b, "altyapi": alt, "etiket": etiket, "yedek": yedek, "devre": devre,
                         "renk": KABLO_RENKLERI.get(alt, "#7F8C8D")})  # fmt: skip

    for g in secilen:
        lok, il = g["ad"], _il(g["ad"])
        devreler: dict[str, dict] = {}
        for sira, r in enumerate(sorted(g["ciler"], key=lambda r: (r.service, r.ci_name))):
            if ci_sayisi >= AZAMI_CI or sira >= LOKASYON_BASI_CI:
                gizlenen += 1
                continue
            a = r.attrs or {}
            alt, yedek = altyapi(r.service, a.get("erisim", ""), a.get("altyapi", ""), r.ci_name)
            pe = pe_router(r.ci_name)
            ci_id = f"CI_{r.ci_no}"
            etiket, kod = kisa_servis(r.service)
            dugumler[ci_id] = {"id": ci_id, "tur": "router", "kisa": kod, "etiket": etiket,
                               "lokasyon": lok, "il": il, "ci": r.ci_name, "servis": r.service, "bw": a.get("bw", ""),
                               "kritik": r.ci_no in kritik}  # fmt: skip
            ci_sayisi += 1
            devre = str(a.get("devre") or "").strip()
            if not devre:
                kenar(f"K{r.ci_no}", BULUT, ci_id, alt, pe, yedek, r.ci_name)
                continue
            d_id = f"D_{_katla(lok)}_{devre}"
            d = devreler.get(d_id)
            if d is None:
                d = devreler[d_id] = {"pe": pe, "alt": alt, "yedek": yedek, "ciler": []}
                dugumler[d_id] = {"id": d_id, "tur": "switch", "kisa": "DEVRE", "etiket": devre, "lokasyon": lok, "il": il}
            # Devrenin altyapisi / PE'si: bilinen ilk deger (hat CI'inda olur; servis CI'inda bos olabilir)
            d["pe"] = d["pe"] or pe
            if d["alt"] == "Bilinmiyor":
                d["alt"], d["yedek"] = alt, yedek
            d["ciler"].append(ci_id)
            kenar(f"L{r.ci_no}", d_id, ci_id, "LAN", "LAN", False, devre)
        for d_id, d in devreler.items():
            kenar(f"W{d_id}", BULUT, d_id, d["alt"], d["pe"], d["yedek"], dugumler[d_id]["etiket"])
        ana = [d for d in devreler.values() if not d["yedek"]]
        if len(ana) == 1 and not any(d["yedek"] for d in devreler.values()) and not any(
            "MOBILE" in _katla(x.service) for x in g["ciler"]
        ):
            spof.append({"lokasyon": lok, "bb": ana[0]["pe"] or "—", "altyapilar": [ana[0]["alt"]], "neden": "tek_devre",
                         "devreler": [next(dugumler[k]["etiket"] for k, v in devreler.items() if v is ana[0])]})  # fmt: skip

    sayac: dict[str, int] = defaultdict(int)
    for d in dugumler.values():
        if d["tur"] == "router" and d["il"]:
            sayac[d["il"]] += 1
    sehirler = [{"il": il, "adet": n, "enlem": _KOORDINAT[_katla(il)][1][0], "boylam": _KOORDINAT[_katla(il)][1][1]}
                for il, n in sorted(sayac.items(), key=lambda x: (-x[1], x[0]))]  # fmt: skip
    uyarilar = []
    if len(eslesen) > len(secilen):
        uyarilar.append(f"{len(eslesen)} lokasyondan CI sayısı en çok olan {len(secilen)} lokasyon çizildi; aramayla daraltın.")
    if gizlenen:
        uyarilar.append(f"Çizim sınırı (lokasyon başına {LOKASYON_BASI_CI}, toplam {AZAMI_CI} CI) nedeniyle {gizlenen} CI gösterilmedi.")
    if spof:
        uyarilar.append("Tek devre (SPoF) tespiti yalnız lokasyon adı ve devre no ile yapılan bir tahmindir; lokasyon adları tutarsız olabilir.")
    if LOKASYONSUZ.upper() in {_katla(g["ad"]) for g in secilen}:
        uyarilar.append("Lokasyon bilgisi olmayan CI'lar 'Lokasyonsuz' altında toplandı.")
    return {
        "kaynak": "envanter",
        "spof": bool(spof),
        "spof_noktalari": spof,
        "dugumler": list(dugumler.values()),
        "kenarlar": kenarlar,
        "sehirler": sehirler,
        "konumsuz_iller": [],
        "kolonlar": {"loc": "Lokasyon", "ci": "CI adı", "c_no_primary": "Devre No", "bb_host": "CI adındaki PE router"},
        "satir": len(satirlar),
        "lokasyon": len(gruplar),
        "lokasyon_listesi": [{"ad": g["ad"], "ci": len(g["ciler"])} for g in liste[:AZAMI_LOKASYON * 3]],
        "gosterilen": len(secilen),
        "eslesen": len(eslesen),
        "degerlendirme": "riskli" if spof else "sinirli",
        "uyarilar": uyarilar,
        "renkler": KABLO_RENKLERI,
    }
