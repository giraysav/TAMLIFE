"""Ham Musteri Verisi partisi -> musteri kartlari: ONIZLEME, onayli UYGULAMA ve GERI ALMA.

Uretim karsiligi: kutucuklar/veri/musteri_aktar.py. Kurallar (uretimde kullanici onayli):
  * Bos hucre karta DOKUNMAZ, dolu hucre karttaki degeri gunceller.
  * Eslesme: 1) Musteri No (kartta ayni numara varsa o kart) 2) unvan (harf/bosluk/I-İ farksiz).
  * Ayni unvanli satirlar TEK satira birlesir; farkli Musteri No'lar ayni karta virgulle eklenir. Musteri No birikir, silinmez.
  * Kartta olmayan musteri yalniz "yeni olustur" secilirse (cati/istirak listesinde kendiliginden) olusturulur.
  * Hatali satir tamamen atlanir; digerleri uygulanir.
Guvenlik: onizleme salt okur; uygulama tek islemde yazar ve onizlemenin ozeti (plan_ozeti) ile ayni olmalidir (dosya ya da
kartlar arada degistiyse 409). Her uygulama onceki/sonraki degerleri customer_import_run'a yazar; geri alma yalniz hala
aktarimin yazdigi degerde duran alanlari eski haline getirir (sonradan elle degistirilen korunur).
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import threading
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import musteri_alani
from app.dil import m
from app.models import (
    AppUser,
    Customer,
    CustomerTeam,
    IngestBatch,
    ProjectCustomerWork,
    Report,
    ReportDispatch,
    ReportDraft,
    ReportRecipient,
    ScoreDetail,
    ScoreHistory,
    UrunTutarOzet,
)
from app.musteri.servis import _EPOSTA, _GSM, ILETISIM_ALANLARI, SEGMENTLER, VARSAYILAN_TUTAR
from app.ortak import UygulamaHatasi, eslestirme_anahtari, simdi
from app.tampon import depo
from app.tampon import musteri_ham as H
from app.tampon.models import CustomerImportRun

GOSTERILEN_SATIR = 1000  # onizlemede listelenen en fazla satir ('degisiklik yok' satirlari listelenmez)
_kilit = threading.Lock()

# Segment acik adlari ve liste dosyalarinda gorulen yazim hatalari (en yakin ada cekilir; esik 0.85).
_SEGMENT_ADLARI = {
    "strategicaccount": "SA",
    "majoraccount": "MA",
    "smallmediumbusiness": "SMB",
    "smallmediumbussiness": "SMB",
    "wholesale": "WHOLESALE",
    "connectedcar": "CONNCAR",
}


class _Hata(ValueError):
    """Tek hucrenin gecersizligi (satir hatasi olarak toplanir)."""


def _kisalt(v: object, n: int = 120) -> str:
    s = str(v if v is not None else "")
    return s if len(s) <= n else s[: n - 1] + "…"


def _metin(ham: object, azami: int, etiket: str, satir_sonu: bool = False) -> str:
    if isinstance(ham, bool):
        raise _Hata(m(f"{etiket}: geçersiz değer", f"{etiket}: invalid value"))
    if isinstance(ham, float) and ham.is_integer():
        ham = int(ham)
    s = str(ham).strip()
    if not satir_sonu:
        s = " ".join(s.split())
    if len(s) > azami:
        raise _Hata(m(f"{etiket}: en fazla {azami} karakter olabilir", f"{etiket}: at most {azami} characters"))
    return s


def _tamsayi(ham: object, etiket: str) -> int:
    hata = _Hata(m(f"{etiket}: 0 ile 1.000.000.000 arası tam sayı olmalı", f"{etiket}: must be a whole number between 0 and 1,000,000,000"))
    if isinstance(ham, bool):
        raise hata
    if isinstance(ham, float):
        if not ham.is_integer():
            raise hata
        ham = int(ham)
    if isinstance(ham, str):
        s = ham.strip().replace(" ", "")
        if not re.fullmatch(r"\d{1,3}(\.\d{3})+|\d+", s):
            raise hata
        ham = int(s.replace(".", ""))
    if not isinstance(ham, int) or not 0 <= ham <= H.AZAMI_TAMSAYI:
        raise hata
    return ham


def _tutar(ham: object, azami: int, etiket: str) -> str:
    if isinstance(ham, bool):
        raise _Hata(m(f"{etiket}: geçersiz değer", f"{etiket}: invalid value"))
    if isinstance(ham, int | float):
        if ham < 0:
            raise _Hata(m(f"{etiket}: negatif olamaz", f"{etiket}: cannot be negative"))
        return f"{float(ham):,.2f}".replace(",", "\0").replace(".", ",").replace("\0", ".") + " ₺"  # kart gosterimi 1.234,56 ₺
    return _metin(ham, azami, etiket)


def _evet_hayir(ham: object, etiket: str) -> bool:
    s = eslestirme_anahtari(str(ham))
    if s in ("evet", "e", "true", "1", "yes", "var"):
        return True
    if s in ("hayir", "hayır", "h", "false", "0", "no", "yok"):
        return False
    raise _Hata(m(f"{etiket}: Evet ya da Hayır olmalı", f"{etiket}: must be Evet (yes) or Hayır (no)"))


def _segment_kodu(metin: str) -> str | None:
    s = metin.strip()
    for x in SEGMENTLER:
        if s.upper() == x:
            return x
    anahtar = re.sub(r"[^a-z]", "", s.lower().replace("ı", "i"))
    if anahtar in _SEGMENT_ADLARI:
        return _SEGMENT_ADLARI[anahtar]
    yakin = difflib.get_close_matches(anahtar, list(_SEGMENT_ADLARI), n=1, cutoff=0.85) if anahtar else []
    return _SEGMENT_ADLARI[yakin[0]] if yakin else None


def _kisi_sozlugu(db: Session) -> dict[str, set[int]]:
    """{ad / kullanici adi anahtari: {kullanici id}} yalniz aktif personel."""
    sozluk: dict[str, set[int]] = {}
    for k in db.scalars(select(AppUser)):
        if k.active is False:
            continue
        for ad in (k.display_name, k.username):
            anahtar = eslestirme_anahtari(ad or "")
            if anahtar:
                sozluk.setdefault(anahtar, set()).add(k.id)
    return sozluk


def _alan_coz(
    alan: H.Alan, ham: object, mevcut_segment: str | None, kisiler: dict[str, set[int]], adlar: dict[int, str]
) -> tuple[Any, Any]:
    """Dolu bir hucre -> (gosterim, nesne). 'cati' burada yalniz metin; cozumu ikinci turda."""
    a, b = alan.anahtar, alan.baslik
    if a == "customer_no":
        s = _metin(ham, 200, b)
        parcalar = H.no_parcalar(s)
        if not parcalar or any(not re.fullmatch(r"\d+", p) for p in parcalar):
            raise _Hata(
                m(
                    "Müşteri No yalnızca rakamlardan oluşmalı (birden çok numara virgülle ayrılır)",
                    "Customer No must contain digits only (separate several numbers with commas)",
                )
            )
        liste = H.numaralar(s)
        return ", ".join(liste), liste
    if a == "segment":
        s = _metin(ham, 100, b)
        kod = _segment_kodu(s)
        if kod:
            return kod, kod
        if mevcut_segment and s == mevcut_segment.strip():
            return s, s
        raise _Hata(m("Segment şunlardan biri olmalı: ", "Segment must be one of: ") + ", ".join(SEGMENTLER))
    if alan.tip == "tamsayi":
        n = _tamsayi(ham, b)
        return n, n
    if alan.tip == "tutar":
        s = _tutar(ham, alan.azami or 100, b)
        return s, s
    if alan.tip == "evet_hayir":
        v = _evet_hayir(ham, b)
        return ("Evet" if v else "Hayır"), v
    if alan.grup == "iletisim":
        _, azami = ILETISIM_ALANLARI[a]
        s = _metin(ham, azami, b, satir_sonu=(a == "mobil_kmt_detail"))
        if a.endswith("_email") and not _EPOSTA.match(s):
            raise _Hata(m(f"{b}: geçerli bir e-posta adresi olmalı", f"{b}: must be a valid e-mail address"))
        if a.endswith("_gsm") and not _GSM.match(s):
            raise _Hata(
                m(
                    f"{b}: yalnızca rakam, +, boşluk, - ve parantez içerebilir",
                    f"{b}: may contain only digits, +, spaces, - and parentheses",
                )
            )
        return s, s
    if a == "tam":
        s = _metin(ham, 120, b)
        adaylar = kisiler.get(eslestirme_anahtari(s), set())
        if not adaylar:
            raise _Hata(m(f'{b}: "{_kisalt(s, 40)}" adlı aktif personel bulunamadı', f'{b}: no active staff named "{_kisalt(s, 40)}"'))
        if len(adaylar) > 1:
            raise _Hata(
                m(f'{b}: "{_kisalt(s, 40)}" birden çok personelle eşleşiyor', f'{b}: "{_kisalt(s, 40)}" matches more than one staff member')
            )
        kid = next(iter(adaylar))
        return adlar.get(kid, s), kid
    if a == "cati":
        s = _metin(ham, 150, b)
        return s, eslestirme_anahtari(s)
    s = _metin(ham, alan.azami or 200, b)
    return s, s


def _birlestir(satirlar: list[list[Any]], harita: dict[str, int]) -> list[dict[str, Any]]:
    """Ayni unvanli satirlari tek satira indirir: Musteri No'lar birlesir, diger alanlarda ILK dolu deger (farklar uyari olur)."""
    i_unvan, i_no = harita.get("unvan"), harita.get("customer_no")
    cikti: list[dict[str, Any]] = []
    gruplar: dict[str, dict[str, Any]] = {}

    def norm(v: object) -> str:
        return " ".join(str(v).split()).casefold()

    for sira, r in enumerate(satirlar, 1):
        r = list(r)
        ham = r[i_unvan] if i_unvan is not None and i_unvan < len(r) else None
        if H._bos(ham):
            cikti.append({"sira": sira, "satir": r, "siralar": [sira], "farklar": [], "unvanlar": []})
            continue
        unvan = " ".join(str(ham).split())
        g = gruplar.get(eslestirme_anahtari(unvan))
        if g is None:
            g = {
                "sira": sira,
                "satir": r,
                "siralar": [sira],
                "farklar": [],
                "unvanlar": [unvan],
                "_no": H.no_parcalar(r[i_no]) if i_no is not None and i_no < len(r) else [],
            }
            gruplar[eslestirme_anahtari(unvan)] = g
            cikti.append(g)
            continue
        g["siralar"].append(sira)
        for alan, i in harita.items():
            if alan in ("unvan", "customer_no") or i >= len(r) or H._bos(r[i]):
                continue
            if i >= len(g["satir"]) or H._bos(g["satir"][i]):
                g["satir"] += [None] * (i + 1 - len(g["satir"]))
                g["satir"][i] = r[i]
            elif norm(g["satir"][i]) != norm(r[i]) and alan not in g["farklar"]:
                g["farklar"].append(alan)
        if i_no is not None and i_no < len(r):
            g["_no"] += H.no_parcalar(r[i_no])
    for g in cikti:
        parcalar = g.pop("_no", None)
        if parcalar and i_no is not None:
            tekil, gorulen = [], set()
            for p in parcalar:
                k = H.no_anahtar(p) or p
                if k not in gorulen:
                    gorulen.add(k)
                    tekil.append(p)
            g["satir"][i_no] = ", ".join(tekil)
    return cikti


def _parti(db: Session, parti_id: int) -> IngestBatch:
    parti = db.get(IngestBatch, parti_id)
    if parti is None:
        raise UygulamaHatasi(404, m("Parti bulunamadı.", "Batch not found."))
    if parti.source_key != H.KAYNAK:
        raise UygulamaHatasi(
            400, m("Yalnız Ham Müşteri Verisi partileri kartlara aktarılabilir.", "Only raw customer data batches can be applied to cards.")
        )
    if parti.status not in ("ready", "rejected"):
        raise UygulamaHatasi(409, m("Bu parti henüz hazır değil.", "This batch is not ready yet."))
    return parti


@musteri_alani.tum_alanlarda  # kart eslesmesi tum modullerde (WHOLESALE kart Toptan'da)
def plan_olustur(db: Session, parti_id: int, yeni_olustur: bool = False) -> dict[str, Any]:
    """Partiyi kartlarla karsilastirir; HICBIR SEY YAZMAZ. Satir durumlari: guncelle | degisiklik_yok | yeni | hata."""
    parti = _parti(db, parti_id)
    ham_basliklar = list(parti.columns or [])
    genis = H.genis_bicim_mi(ham_basliklar)
    yeni_olustur = yeni_olustur or genis  # cati/istirak listesinde olmayan cati ve istirakler olusturulur (uretim karari)
    basliklar, ham_satirlar, kaynak_sira = H.genis_donustur(ham_basliklar, depo.satirlari_oku(db, parti_id))
    harita = H.sutun_haritasi(basliklar)
    if "unvan" not in harita:
        raise UygulamaHatasi(
            400,
            m(
                'Dosyada "Çatı Müşteri Ünvanı" / "İştirak Müşteri Ünvanı" (ya da "Müşteri Ünvanı") sütunu yok.',
                'The file has no "Çatı Müşteri Ünvanı" / "İştirak Müşteri Ünvanı" (or "Müşteri Ünvanı") column.',
            ),
        )

    musteriler = list(db.scalars(select(Customer)))
    anahtar_musteri = {eslestirme_anahtari(c.name or ""): c for c in musteriler}
    adlar = {c.id: c.name for c in musteriler}
    kisi_kayitlari = {u.id: u for u in db.scalars(select(AppUser))}
    kisi_adlari = {i: H.kisi_adi(u) for i, u in kisi_kayitlari.items()}
    iletisim = H.iletisim_kayitlari(db)
    kisiler = _kisi_sozlugu(db)
    db_ebeveyn = {
        eslestirme_anahtari(c.name or ""): (eslestirme_anahtari(adlar.get(c.parent_id, "")) or None) if c.parent_id else None
        for c in musteriler
    }
    kart_numaralari: dict[str, Customer] = {}
    for c in musteriler:
        for k in H.no_anahtarlari(c.customer_no):
            kart_numaralari.setdefault(k, c)
    dosya_numaralari: dict[str, int] = {}

    satirlar: list[dict[str, Any]] = []
    ilk_gorulen: dict[str, int] = {}
    ad_takma: dict[str, str] = {}
    birlesen = _birlestir(ham_satirlar, harita)
    for g in birlesen:  # satir numarasi DOSYADAKI veri satirini gostersin
        g["sira"], g["siralar"] = kaynak_sira[g["sira"] - 1], [kaynak_sira[x - 1] for x in g["siralar"]]
    for g in birlesen:
        sira, ham_satir = g["sira"], g["satir"]

        def hucre(alan: str, ham_satir: list[Any] = ham_satir) -> Any:
            i = harita.get(alan)
            v = ham_satir[i] if i is not None and i < len(ham_satir) else None
            return None if H._bos(v) else v

        satir: dict[str, Any] = {
            "sira": sira,
            "unvan": "",
            "anahtar": "",
            "durum": "",
            "degisiklikler": [],
            "hatalar": [],
            "uyarilar": [],
            "_deger": {},
            "_uygula": {},
            "_mevcut": None,
            "_cati": None,
            "_cati_metin": "",
        }
        satirlar.append(satir)
        ham_unvan = hucre("unvan")
        if ham_unvan is None:
            satir["hatalar"].append(m("Müşteri Ünvanı boş", "Customer name is empty"))
            continue
        try:
            satir["unvan"] = _metin(ham_unvan, 150, H.ALAN["unvan"].baslik)
        except _Hata as e:
            satir["unvan"] = _kisalt(ham_unvan, 60)
            satir["hatalar"].append(str(e))
            continue
        satir["anahtar"] = eslestirme_anahtari(satir["unvan"])
        if len(g["siralar"]) > 1:
            liste = ", ".join(str(x) for x in g["siralar"])
            satir["uyarilar"].append(
                m(
                    f"Aynı ünvanlı {len(g['siralar'])} satır birleştirildi (satır {liste}); farklı Müşteri No'lar tek karta bağlanır",
                    f"{len(g['siralar'])} rows with the same name were merged (rows {liste}); different Customer Nos go to one card",
                )
            )
        for fark in g["farklar"]:
            satir["uyarilar"].append(
                m(
                    f"Birleşen satırlarda farklı {H.ALAN[fark].baslik}: ilk satırdaki değer alındı",
                    f"Merged rows differ in {H.ALAN[fark].baslik}: the first row's value is used",
                )
            )
        kartlar: list[Customer] = []
        for k in H.no_anahtarlari(hucre("customer_no")):
            c = kart_numaralari.get(k)
            if c is not None and c not in kartlar:
                kartlar.append(c)
        if len(kartlar) > 1:
            satir["hatalar"].append(
                m("Satırdaki Müşteri No'lar farklı kartlarda kayıtlı: ", "The row's Customer Nos belong to different cards: ")
                + ", ".join(f'"{_kisalt(c.name, 40)}"' for c in kartlar)
            )
            continue
        musteri = kartlar[0] if kartlar else None
        if musteri is not None:
            if eslestirme_anahtari(musteri.name or "") != satir["anahtar"]:
                satir["uyarilar"].append(
                    m(
                        f'Müşteri No ile eşleşti (ünvan farklı): kart "{_kisalt(musteri.name, 60)}"',
                        f'Matched by Customer No (different name): card "{_kisalt(musteri.name, 60)}"',
                    )
                )
            satir["anahtar"] = eslestirme_anahtari(musteri.name or "")
        else:
            musteri = anahtar_musteri.get(satir["anahtar"])
        for u in g["unvanlar"] or [satir["unvan"]]:
            ad_takma.setdefault(eslestirme_anahtari(u), satir["anahtar"])
        if satir["anahtar"] in ilk_gorulen:
            satir["hatalar"].append(
                m(
                    f"Bu kart dosyada {ilk_gorulen[satir['anahtar']]}. satırda da var",
                    f"This card also appears in row {ilk_gorulen[satir['anahtar']]}",
                )
            )
            continue
        ilk_gorulen[satir["anahtar"]] = sira
        mevcut = H.kart_degerleri(musteri, iletisim.get(musteri.id), adlar, kisi_kayitlari) if musteri else None
        satir["_mevcut"], satir["_id"] = mevcut, musteri.id if musteri else None
        yeni = musteri is None
        for alan in H.ALANLAR:
            if alan.anahtar == "unvan":
                continue
            ham = hucre(alan.anahtar)
            if ham is None:
                continue
            try:
                gosterim, nesne = _alan_coz(alan, ham, mevcut["segment"] if mevcut else None, kisiler, kisi_adlari)
            except _Hata as e:
                satir["hatalar"].append(str(e))
                continue
            if alan.anahtar == "customer_no":
                eski_metin = (mevcut["customer_no"] if mevcut else "") or ""
                birlesik, eklenen = H.no_ekle(eski_metin, nesne)
                hata_no = None
                for n in nesne:
                    k = H.no_anahtar(n)
                    baska = kart_numaralari.get(k)
                    if k in dosya_numaralari:
                        hata_no = m(
                            f"Aynı Müşteri No dosyada {dosya_numaralari[k]}. satırda da var: {n}",
                            f"The same Customer No is also in row {dosya_numaralari[k]}: {n}",
                        )
                    elif baska is not None and (musteri is None or baska.id != musteri.id):
                        hata_no = m(
                            f"Bu Müşteri No başka bir kartta kayıtlı: {n} ({_kisalt(baska.name, 50)})",
                            f"This Customer No belongs to another card: {n} ({_kisalt(baska.name, 50)})",
                        )
                    if hata_no:
                        break
                if hata_no:
                    satir["hatalar"].append(hata_no)
                    continue
                for n in nesne:
                    dosya_numaralari[H.no_anahtar(n)] = sira
                if eklenen and H.numaralar(eski_metin):
                    satir["uyarilar"].append(
                        m(
                            f"Karttaki Müşteri No korunur; eklenen: {', '.join(eklenen)}",
                            f"The card's Customer No is kept; added: {', '.join(eklenen)}",
                        )
                    )
                gosterim = nesne = ", ".join(birlesik) if eklenen or not eski_metin else eski_metin
                if len(gosterim) > 200:
                    satir["hatalar"].append(m("Müşteri No alanı 200 karakteri aşıyor", "The Customer No field exceeds 200 characters"))
                    continue
            satir["_deger"][alan.anahtar] = nesne
            if alan.anahtar == "cati":
                satir["_cati"], satir["_cati_metin"] = nesne, gosterim
                continue
            if alan.anahtar == "tam":
                degisti = yeni or musteri.owner_id != nesne
                eski = mevcut["tam"] if mevcut else ""
            else:
                eski = mevcut[alan.anahtar] if mevcut else ""
                degisti = yeni or str(eski if eski is not None else "") != str(gosterim)
            if degisti:
                satir["degisiklikler"].append(
                    {"alan": alan.anahtar, "baslik": alan.baslik, "eski": _kisalt(eski), "yeni": _kisalt(gosterim)}
                )
                satir["_uygula"][alan.anahtar] = nesne

    # --- hiyerarsi (cati) ve yeni musteri on kosullari ---
    yeni_anahtarlar = {r["anahtar"] for r in satirlar if r["anahtar"] and r["_mevcut"] is None and not r["hatalar"]}
    bilinen = set(db_ebeveyn) | (yeni_anahtarlar if yeni_olustur else set())
    gorunen_ad = {k: c.name for k, c in anahtar_musteri.items()}
    gorunen_ad.update({r["anahtar"]: r["unvan"] for r in satirlar if r["anahtar"] in yeni_anahtarlar})
    ebeveyn = {k: db_ebeveyn.get(k) for k in bilinen}
    for r in satirlar:
        if r["hatalar"] or r["_cati"] is None:
            continue
        k, p = r["anahtar"], ad_takma.get(r["_cati"], r["_cati"])
        mevcut_cati = (r["_mevcut"] or {}).get("cati") or ""
        if p == k:
            r["hatalar"].append(m("Çatı müşteri: müşteri kendisinin çatısı olamaz", "Parent customer: a customer cannot be its own parent"))
        elif p not in bilinen:
            neden = m(" (yeni müşteri oluşturma kapalı)", " (creating new customers is off)") if p in yeni_anahtarlar else ""
            r["hatalar"].append(
                m(
                    f'Çatı müşteri "{_kisalt(r["_cati_metin"], 40)}" kartlarda yok',
                    f'Parent customer "{_kisalt(r["_cati_metin"], 40)}" is not in the cards',
                )
                + neden
            )
        elif ebeveyn.get(p):
            r["hatalar"].append(
                m(
                    "Çatı müşteri: seçilen müşteri bir iştirak; iştirakin altına iştirak eklenemez",
                    "Parent customer: the selected customer is a subsidiary; subsidiaries cannot be nested",
                )
            )
        elif any(v == k for v in ebeveyn.values()):
            r["hatalar"].append(
                m(
                    "Çatı müşteri: bu müşterinin kendi iştirakleri var; önce onlar taşınmalı",
                    "Parent customer: this customer has its own subsidiaries; move them first",
                )
            )
        else:
            ebeveyn[k] = p
            if r["_mevcut"] is None or eslestirme_anahtari(mevcut_cati) != p:
                r["degisiklikler"].append(
                    {"alan": "cati", "baslik": H.ALAN["cati"].baslik, "eski": _kisalt(mevcut_cati), "yeni": _kisalt(gorunen_ad.get(p, p))}
                )
                r["_uygula"]["cati"] = p

    for r in satirlar:
        if r["hatalar"]:
            r["durum"] = "hata"
            continue
        son_cati = ebeveyn.get(r["anahtar"]) if r["anahtar"] in ebeveyn else r["_cati"]
        if r["_mevcut"] is None:
            if not r["_deger"].get("tam") and not r["_cati"]:
                r["hatalar"].append(
                    m(
                        "Yeni müşteri için Sorumlu TAM (ya da çatı müşteri) gerekli",
                        "A new customer needs a responsible TAM (or a parent customer)",
                    )
                )
                r["durum"] = "hata"
                continue
            r["durum"] = "yeni"
        else:
            r["durum"] = "guncelle" if r["degisiklikler"] else "degisiklik_yok"
        if "ayri_rapor" in r["_deger"] and not son_cati:
            r["uyarilar"].append(
                m(
                    "Ayrı Aylık Rapor yalnız iştirak içindir; çatı müşteride yok sayıldı",
                    "Separate monthly report applies only to subsidiaries; ignored for a parent customer",
                )
            )
            r["_uygula"].pop("ayri_rapor", None)
            r["degisiklikler"] = [c for c in r["degisiklikler"] if c["alan"] != "ayri_rapor"]
            if r["durum"] == "guncelle" and not r["degisiklikler"]:
                r["durum"] = "degisiklik_yok"

    # Catisi yeni olup sonradan hataya dusen satirin istiraki de hata: uygulamada cati karti olusmaz (2026-10-22 KeyError, 500).
    hatali_yeni = {r["anahtar"] for r in satirlar if r["durum"] == "hata" and r["anahtar"] in yeni_anahtarlar}
    for r in satirlar:
        if r["durum"] != "hata" and r["_uygula"].get("cati") in hatali_yeni:
            r["hatalar"].append(
                m(
                    f'Çatı müşteri "{_kisalt(r["_cati_metin"], 40)}" hatalı olduğu için oluşturulamıyor',
                    f'Parent customer "{_kisalt(r["_cati_metin"], 40)}" has errors and cannot be created',
                )
            )
            r["durum"] = "hata"

    ozet: dict[str, Any] = {"toplam": len(satirlar), "guncelle": 0, "degisiklik_yok": 0, "yeni": 0, "hata": 0, "alan_degisikligi": 0}
    for r in satirlar:
        ozet[r["durum"]] += 1
        if r["durum"] in ("guncelle", "yeni"):
            ozet["alan_degisikligi"] += len(r["degisiklikler"])
    ozet["uyari"] = sum(len(r["uyarilar"]) for r in satirlar)
    ozet["yeni_olustur"] = bool(yeni_olustur)
    ozet["genis_bicim"] = genis
    ozet["uygulanacak"] = ozet["guncelle"] + (ozet["yeni"] if yeni_olustur else 0)
    ozet["tanimsiz_sutunlar"] = [b for b in basliklar if H.baslik_alani(b) is None]
    imza = json.dumps(
        [int(parti_id), bool(yeni_olustur)]
        + [
            [r["anahtar"], r["durum"], sorted((c["alan"], c["yeni"]) for c in r["degisiklikler"])]
            for r in satirlar
            if r["durum"] in ("guncelle", "yeni")
        ],
        ensure_ascii=False,
        sort_keys=True,
    )
    return {
        "ozet": ozet,
        "satirlar": satirlar,
        "hash": hashlib.sha256(imza.encode("utf-8")).hexdigest(),
        "uyum": H.uyum_raporu(ham_basliklar),
    }


def onizleme(db: Session, parti_id: int, yeni_olustur: bool = False) -> dict[str, Any]:
    plan = plan_olustur(db, parti_id, yeni_olustur)
    gosterilecek = [r for r in plan["satirlar"] if r["durum"] != "degisiklik_yok"]
    return {
        "parti_id": parti_id,
        "ozet": plan["ozet"],
        "uyum": plan["uyum"],
        "satirlar": [
            {k: r[k] for k in ("sira", "unvan", "durum", "degisiklikler", "hatalar", "uyarilar")} for r in gosterilecek[:GOSTERILEN_SATIR]
        ],
        "kesildi": max(0, len(gosterilecek) - GOSTERILEN_SATIR),
        "plan_ozeti": plan["hash"],
    }


def _ham_deger(v: Any) -> Any:
    """Kayit icin JSON'a sigan ham deger."""
    return list(v) if isinstance(v, list) else v


@musteri_alani.tum_alanlarda  # kart eslesmesi tum modullerde (WHOLESALE kart Toptan'da)
def uygula(db: Session, parti_id: int, yeni_olustur: bool, plan_ozeti: str, kullanici: str) -> dict[str, Any]:
    """Onizlenen plani kartlara tek islemde yazar. plan_ozeti onizlemeden gelen deger; farkliysa 409."""
    with _kilit:
        plan = plan_olustur(db, parti_id, yeni_olustur)
        yeni_olustur = plan["ozet"]["yeni_olustur"]
        if not plan_ozeti or plan["hash"] != plan_ozeti:
            raise UygulamaHatasi(
                409,
                m(
                    "Dosya ya da kartlar önizlemeden sonra değişti; önizlemeyi yenileyip tekrar deneyin.",
                    "The file or the cards changed after the preview; refresh the preview and try again.",
                ),
            )
        satirlar = [r for r in plan["satirlar"] if r["durum"] == "guncelle" or (r["durum"] == "yeni" and yeni_olustur)]
        if not satirlar:
            raise UygulamaHatasi(400, m("Uygulanacak değişiklik yok.", "There are no changes to apply."))
        anahtar_musteri = {eslestirme_anahtari(c.name or ""): c for c in db.scalars(select(Customer))}
        kayit: dict[str, list[Any]] = {"guncellenen": [], "olusturulan": [], "iletisim_olusturulan": []}
        # 1) yeni musteriler: once catilar, sonra istirakler
        for r in sorted((r for r in satirlar if r["durum"] == "yeni"), key=lambda r: 1 if r["_uygula"].get("cati") else 0):
            u = r["_uygula"]
            cati = anahtar_musteri[u["cati"]] if u.get("cati") else None
            segment = u.get("segment") or (cati.segment if cati and cati.segment in SEGMENTLER else "")
            dis_anahtar = f"panel-{r['anahtar']}"[:80]
            n = 1
            while db.scalar(select(func.count()).select_from(Customer).where(Customer.external_key == dis_anahtar)):
                n += 1
                dis_anahtar = f"panel-{r['anahtar']}"[:76] + f"-{n}"
            c = Customer(
                name=r["unvan"],
                external_key=dis_anahtar,
                status="",
                segment=segment,
                owner_id=u.get("tam") or (cati.owner_id if cati else None),
                parent_id=cati.id if cati else None,
                ft_volume=VARSAYILAN_TUTAR,
                tam_ft=VARSAYILAN_TUTAR,
            )
            db.add(c)
            db.flush()
            anahtar_musteri[r["anahtar"]] = c
            kayit["olusturulan"].append({"id": c.id, "unvan": c.name})
        olusan = {o["id"] for o in kayit["olusturulan"]}
        # 2) alan yazimi
        for r in satirlar:
            c = anahtar_musteri[r["anahtar"]]
            uygula_ = dict(r["_uygula"])
            if r["durum"] == "yeni":
                for a in ("tam", "cati", "segment"):
                    uygula_.pop(a, None)
            onceki: dict[str, Any] = {}
            sonraki: dict[str, Any] = {}
            for alan, nesne in uygula_.items():
                if alan in ILETISIM_ALANLARI:
                    continue
                kolon = H.KOLON[alan]
                onceki.setdefault(kolon, _ham_deger(getattr(c, kolon)))
                if alan == "cati":
                    nesne = anahtar_musteri[nesne].id
                setattr(c, kolon, nesne)
                sonraki[kolon] = _ham_deger(getattr(c, kolon))
            iletisim = {a: v for a, v in uygula_.items() if a in ILETISIM_ALANLARI}
            iletisim_onceki = None
            if iletisim:
                k = db.get(CustomerTeam, c.id)
                if k is None:
                    k = CustomerTeam(customer_id=c.id)
                    db.add(k)
                    if c.id not in olusan:
                        kayit["iletisim_olusturulan"].append(c.id)
                else:
                    iletisim_onceki = {a: getattr(k, a) for a in iletisim}
                for a, v in iletisim.items():
                    setattr(k, a, v or None)
            if c.id not in olusan:
                kayit["guncellenen"].append(
                    {
                        "id": c.id,
                        "unvan": c.name,
                        "onceki": onceki,
                        "sonraki": sonraki,
                        "iletisim_onceki": iletisim_onceki,
                        "iletisim_sonraki": {a: v or None for a, v in iletisim.items()},
                    }
                )
        ozet = {
            "guncellenen": len(kayit["guncellenen"]),
            "olusturulan": len(kayit["olusturulan"]),
            "hatali_atlanan": plan["ozet"]["hata"],
            "degisiklik_yok": plan["ozet"]["degisiklik_yok"],
        }
        run = CustomerImportRun(batch_id=parti_id, at=simdi(), actor=kullanici[:120], summary=ozet, record=kayit, reverted_by="")
        db.add(run)
        db.flush()
        return {"kayit_id": run.id, "ozet": ozet}


def kayitlar(db: Session, adet: int = 20) -> list[dict[str, Any]]:
    return [
        {
            "id": k.id,
            "parti_id": k.batch_id,
            "zaman": k.at.isoformat() if k.at else None,
            "kullanici": k.actor,
            "guncellenen": int((k.summary or {}).get("guncellenen", 0)),
            "olusturulan": int((k.summary or {}).get("olusturulan", 0)),
            "geri_alinan": {"zaman": k.reverted_at.isoformat(), "kullanici": k.reverted_by} if k.reverted_at else None,
        }
        for k in db.scalars(select(CustomerImportRun).order_by(CustomerImportRun.id.desc()).limit(adet))
    ]


_BAGLI = (Report, ReportDispatch, ReportDraft, ReportRecipient, ScoreDetail, ScoreHistory, UrunTutarOzet, ProjectCustomerWork)


@musteri_alani.tum_alanlarda  # kart eslesmesi tum modullerde (WHOLESALE kart Toptan'da)
def geri_al(db: Session, kayit_id: int, kullanici: str) -> dict[str, Any]:
    """Aktarimi geri alir: yalniz hala aktarimin yazdigi degerde duran alanlar eski haline doner; aktarimin olusturdugu musteriler
    rapor/skor/istirak gibi baska bir kayda baglanmamissa silinir."""
    with _kilit:
        k = db.get(CustomerImportRun, kayit_id)
        if k is None:
            raise UygulamaHatasi(404, m("Aktarım kaydı bulunamadı.", "Import record not found."))
        if k.reverted_at is not None:
            raise UygulamaHatasi(409, m("Bu aktarım zaten geri alınmış.", "This import has already been undone."))
        kayit = k.record or {}
        geri = korunan = 0
        for g in kayit.get("guncellenen") or []:
            c = db.get(Customer, g["id"])
            if c is None:
                continue
            for kolon, eski in (g.get("onceki") or {}).items():
                if _ham_deger(getattr(c, kolon)) == (g.get("sonraki") or {}).get(kolon):
                    setattr(c, kolon, eski)
                    geri += 1
                else:
                    korunan += 1
            ekip = db.get(CustomerTeam, c.id)
            if ekip is not None and g.get("iletisim_onceki"):
                for a, eski in g["iletisim_onceki"].items():
                    if getattr(ekip, a) == (g.get("iletisim_sonraki") or {}).get(a):
                        setattr(ekip, a, eski)
                        geri += 1
                    else:
                        korunan += 1
        for cid in kayit.get("iletisim_olusturulan") or []:
            db.execute(delete(CustomerTeam).where(CustomerTeam.customer_id == cid))
        olusan = {o["id"] for o in kayit.get("olusturulan") or []}
        silinen: list[str] = []
        silinemeyen: list[str] = []
        kalan: set[int] = set()
        for c in sorted((c for c in (db.get(Customer, i) for i in olusan) if c is not None), key=lambda c: 0 if c.parent_id else 1):
            altlar = [s for s in db.scalars(select(Customer.id).where(Customer.parent_id == c.id)) if s not in olusan or s in kalan]
            bagli = any(db.scalar(select(func.count()).select_from(t).where(t.customer_id == c.id)) for t in _BAGLI)
            if altlar or bagli:
                silinemeyen.append(c.name)
                kalan.add(c.id)
                continue
            db.execute(delete(CustomerTeam).where(CustomerTeam.customer_id == c.id))
            db.delete(c)
            db.flush()
            silinen.append(c.name)
        k.reverted_at, k.reverted_by = simdi(), kullanici[:120]
        db.flush()
        return {"geri_alinan_alan": geri, "korunan_alan": korunan, "silinen_musteri": len(silinen), "silinemeyen_musteri": silinemeyen}
