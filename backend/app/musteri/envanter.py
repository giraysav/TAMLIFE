"""Musteri envanteri / Kritik CI: ONENT NEMS_CMDB -> panel (customer_ci) -> musteri kartinin Kritik CI alani.

2026-11-20 kullanici: "onent'ten gelen NEMS_CMDB verilerinde musteri no ile eslesen CI'lari, yani o musteriye ait cmdb verilerini
musteri karti altindaki KRITIK CI alanina ekle; burada envanteri gorelim" + "kritik ci artik excel ile degil onent db'den dinamik
beslenecek" (eski Excel matrisi 'ci' artik okunmaz).

Eslesme: ONENT'te CI_CUSTOMER bos; Musteri No her servis sinifinda CRM_MUSTERI_NO ozelligindedir (CI_ATTRIBUTE / okuma yetkili
MTRL_CI_ATTRIBUTE_INFO). Anahtar = rakamlar, bastaki sifirsiz (tampon.eslestirme.anahtar).
Cekim (isci; panel sureci ONENT'e baglanmaz): 1) panel Musteri No'larina esit CRM_MUSTERI_NO satirlari -> CI no, ad, servis, durum
2) bu CI'larin yalniz OZELLIKLER listesindeki ozellikleri (iletisim e-postasi, SNMP, IP gibi alanlar ALINMAZ). ~166 bin CI, ~20 sn.
Ekranda kaynak adi yazilmaz (2026-11-20 kullanici).
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.dil import m
from app.models import AppSetting, Customer, CustomerCi, CustomerCiFlag
from app.ortak import simdi
from app.tampon.eslestirme import anahtar, musteri_anahtarlari

KAYNAK = "pg_onent"
DURUM_ANAHTARI = "musteri.envanter_durum"
YENILEME_SAAT = 4
HATA_BEKLEME_DK = 60
PARCA = 20_000
SORGU_SN = 600
# (ONENT ozellik adi, kisa ad): yalniz bunlar alinir
OZELLIKLER = (
    ("BANDWIDTH", "bw"),
    ("IMT_ID", "imt"),
    ("DEVRE_NO", "devre"),
    ("KURUMSAL_LOKASYON_ADI", "lokasyon"),
    ("ALTYAPI_TIPI", "altyapi"),
    ("ERISIM_ALTYAPISI", "erisim"),
    ("IZLEME_SAATI", "saat"),
    ("DEVRE_KURULUM_TARIHI", "kurulum"),
    # TopoMaker (2026-11-24 kullanici: "CI'in alanlarini oku, acik adrese gore filtrele; il / ilce / lokasyona gore spesifik ciz").
    # Yalniz adres / saha / devre / cihaz tanimi; IP, VAN/LAN adresi, e-posta, SNMP, kullanici adi ALINMAZ.
    ("MUSTERI_ADDRESS", "adres"),
    ("LOKASYON_ADI", "lok_adi"),
    ("HATBASI_LOKASYON", "hatbasi"),
    ("HATSONU_LOKASYON", "hatsonu"),
    ("BB_ROUTER_HOSTNAME", "bb"),
    ("DEVRE_ALTYAPISI", "devre_alt"),
    ("DEVRE_TIPI", "devre_tipi"),
    ("URUN_BILGISI", "urun"),
    ("YEDEKLILIK_KATEGORISI", "yedeklilik"),
    ("MUSTERI_ROUTER_HOSTNAME", "cpe"),
    ("CIHAZ_MODEL", "model"),
    ("ALTYAPI_SAHIPLIGI", "sahiplik"),
    ("KARSI_UC_DEVRE_NO", "karsi_devre"),
    ("ANA_HAT_SERVICE_ID", "ana_hat"),
    ("YEDEK_HAT_SERVICE_ID", "yedek_hat"),
)
DURUMLAR = {
    "ACTIVE": ("Aktif", "Active"), "INACTIVE": ("Pasif", "Inactive"), "CANCELLED": ("İptal", "Cancelled"),
    "REMOVED": ("Kaldırıldı", "Removed"), "PLANNED": ("Planlandı", "Planned"), "SUSPEND": ("Askıda", "Suspended"),
}  # fmt: skip
SIRA = {"ACTIVE": 0, "SUSPEND": 1, "PLANNED": 2, "INACTIVE": 3, "CANCELLED": 4, "REMOVED": 5}

_CI_SORGU = (
    'SELECT DISTINCT "CI_NO", "CI_NAME", "SERVICE_NAME", "CI_STATUS_NAME", "CLASS_ITEM_VALUE" '
    'FROM "NEMS_CMDB"."MTRL_CI_ATTRIBUTE_INFO" WHERE "CI_CLASS_SPEC_NAME" = \'CRM_MUSTERI_NO\' AND "CLASS_ITEM_VALUE" = ANY(%s)'
)
_OZELLIK_SORGU = (
    'SELECT "CI_NO", "CI_CLASS_SPEC_NAME", "CLASS_ITEM_VALUE" FROM "NEMS_CMDB"."MTRL_CI_ATTRIBUTE_INFO" '
    'WHERE "CI_NO" = ANY(%s) AND "CI_CLASS_SPEC_NAME" = ANY(%s)'
)


# --- Durum ---------------------------------------------------------------------------------------------------------------------
def durum_oku(db: Session) -> dict[str, Any]:
    k = db.get(AppSetting, DURUM_ANAHTARI)
    return dict(k.value) if k is not None and isinstance(k.value, dict) else {}


def _durum_yaz(db: Session, **alanlar: Any) -> None:
    k = db.get(AppSetting, DURUM_ANAHTARI)
    deger = {**(dict(k.value) if k is not None and isinstance(k.value, dict) else {}), **alanlar}
    if k is None:
        db.add(AppSetting(key=DURUM_ANAHTARI, value=deger, updated_by="isci", updated_at=simdi()))
    else:
        k.value, k.updated_by, k.updated_at = deger, "isci", simdi()
    db.commit()


def _zaman(v: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(v)) if v else None
    except ValueError:
        return None


def gerekli_mi(db: Session) -> bool:
    d, an = durum_oku(db), simdi()
    son_basari, son_deneme = _zaman(d.get("son_basari")), _zaman(d.get("son_deneme"))
    if d.get("hata") and son_deneme and an - son_deneme < timedelta(minutes=HATA_BEKLEME_DK):
        return False
    return son_basari is None or an - son_basari >= timedelta(hours=YENILEME_SAAT)


# --- Cekim (isci) ----------------------------------------------------------------------------------------------------------------
def _panel_numaralari(db: Session) -> list[str]:
    """Kartlardaki Musteri No'lar: hem yazildigi hali hem bastaki sifirsiz anahtari (ONENT degeri ikisinden biri olabilir)."""
    sonuc: set[str] = set()
    for (no,) in db.execute(select(Customer.customer_no).where(Customer.customer_no.is_not(None))):
        for k in musteri_anahtarlari(no):
            sonuc.update({k, k.zfill(8)})
    return sorted(sonuc)


def yenile(db: Session) -> dict[str, Any]:
    """ONENT'ten panel musterilerinin envanterini ceker ve customer_ci'yi bastan yazar. Hata durumu kaydina yazilir."""
    from app.tampon import postgres

    t0 = time.time()
    a = postgres.ayar(KAYNAK)
    try:
        numaralar = _panel_numaralari(db)
        with a.baglan(SORGU_SN) as conn, conn.cursor() as cur:
            cur.execute(_CI_SORGU, (numaralar,))
            cis: dict[str, dict[str, Any]] = {}
            for ci_no, ad, servis, durum, mno in cur.fetchall():
                k = anahtar(mno)
                if not k or ci_no is None:
                    continue
                cis[f"{k}|{ci_no}"] = {"customer_key": k, "ci_no": str(ci_no)[:40], "ci_name": (ad or "")[:300],
                                       "service": (servis or "")[:200], "status": (durum or "")[:40], "attrs": {}}  # fmt: skip
            ozellik = defaultdict(dict)
            adlar = dict(OZELLIKLER)
            ci_nolar = sorted({v["ci_no"] for v in cis.values()})
            for i in range(0, len(ci_nolar), PARCA):
                cur.execute(_OZELLIK_SORGU, (ci_nolar[i : i + PARCA], list(adlar)))
                for ci_no, ad, deger in cur.fetchall():
                    if deger not in (None, ""):
                        ozellik[str(ci_no)][adlar[ad]] = " ".join(str(deger).split())[:300]
        an = simdi()
        satirlar = [{**v, "attrs": ozellik.get(v["ci_no"], {}), "refreshed_at": an} for v in cis.values()]
        db.execute(delete(CustomerCi))
        for i in range(0, len(satirlar), 5000):
            db.execute(insert(CustomerCi), satirlar[i : i + 5000])
        db.commit()
        sure = round(time.time() - t0, 1)
        _durum_yaz(db, son_deneme=an.isoformat(), son_basari=an.isoformat(), hata="", satir=len(satirlar), sure_sn=sure)
        return {"satir": len(satirlar), "sure_sn": sure}
    except Exception as e:  # noqa: BLE001 - durum ekrana (yalniz yonetimde), onceki envanter korunur
        db.rollback()
        mesaj = postgres.hata_metni(e, a.gizliler())
        _durum_yaz(db, son_deneme=simdi().isoformat(), hata=mesaj)
        return {"hata": mesaj}


# --- Kart (panel) ------------------------------------------------------------------------------------------------------------------
def _durum_adi(kod: str) -> str:
    tr, en = DURUMLAR.get((kod or "").upper(), (kod or "", kod or ""))
    return m(tr, en)


def _altyapi(a: dict[str, str]) -> str:
    return " / ".join(x for x in (a.get("altyapi"), a.get("erisim")) if x)


TR = timezone(timedelta(hours=3))
EN_COK_SATIR = 500


def _anahtarlar(musteriler: list[Customer]) -> list[str]:
    sonuc: list[str] = []
    for c in musteriler:
        for k in musteri_anahtarlari(c.customer_no):
            if k not in sonuc:
                sonuc.append(k)
    return sonuc


def _basliklar(coklu: bool) -> list[str]:
    return ([m("Müşteri No", "Customer No")] if coklu else []) + [
        m("CI adı", "CI name"), m("Devre No", "Circuit No"), m("Servis", "Service"), m("Durum", "Status"), m("Bant genişliği", "Bandwidth"), "IMT ID",
        m("Lokasyon", "Location"), m("Lokasyon adı", "Location name"), m("Altyapı", "Infrastructure"), m("Hizmet saati", "Service hours"),
        m("Kurulum tarihi", "Installed"),
    ]  # fmt: skip


LOKASYON_ADI_SUTUNU = 7  # _basliklar(False) icinde 'Lokasyon adi' sirasi (coklu kartta +1)


def _kritikler(db: Session, musteri_id: int) -> set[str]:
    return set(db.scalars(select(CustomerCiFlag.ci_no).where(CustomerCiFlag.customer_id == musteri_id, CustomerCiFlag.critical.is_(True))))


def lokasyon_duzeltmeleri(db: Session, musteri_id: int) -> dict[str, str]:
    """Kartta elle duzeltilmis CI lokasyon adlari {ci_no: ad} (TopoMaker sahasi ve CI listesi bunu kullanir)."""
    return dict(db.execute(select(CustomerCiFlag.ci_no, CustomerCiFlag.location_name).where(
        CustomerCiFlag.customer_id == musteri_id, CustomerCiFlag.location_name.is_not(None), CustomerCiFlag.location_name != "")).all())


def _ozet(db: Session, anahtarlar: list[str], kritik: int = 0) -> tuple[int, str]:
    toplam = db.scalar(select(func.count()).select_from(CustomerCi).where(CustomerCi.customer_key.in_(anahtarlar))) or 0
    aktif = db.scalar(select(func.count()).select_from(CustomerCi).where(CustomerCi.customer_key.in_(anahtarlar), CustomerCi.status == "ACTIVE")) or 0
    son = db.scalar(select(func.max(CustomerCi.refreshed_at)))
    if son is not None:
        son = (son if son.tzinfo else son.replace(tzinfo=UTC)).astimezone(TR)
    tarih = son.strftime("%d.%m.%Y %H:%M") if son else "—"
    return toplam, m(f"{toplam} CI · {aktif} aktif · {kritik} kritik · güncelleme {tarih}",
                     f"{toplam} CIs · {aktif} active · {kritik} critical · updated {tarih}")


def kart_ozeti(db: Session, musteriler: list[Customer], musteri_id: int) -> dict[str, Any]:
    """Kart verisi icin yalniz sayi ve ozet; satirlar Kritik CI penceresi acilinca ayri istekle gelir (buyuk musteride ~22 bin CI)."""
    anahtarlar = _anahtarlar(musteriler)
    if not anahtarlar:
        return {"basliklar": _basliklar(False), "satirlar": [], "toplam": 0, "ozet": m("Kartta Müşteri No yok.", "The card has no Customer No."), "ara": "", "adres": None}
    toplam, ozet = _ozet(db, anahtarlar, len(_kritikler(db, musteri_id)))
    return {"basliklar": _basliklar(len(anahtarlar) > 1), "satirlar": [], "toplam": toplam, "ozet": ozet,
            "ara": m("CI adı, servis, IMT ID, lokasyon ara…", "Search CI name, service, IMT ID, location…"),
            "adres": f"/api/v1/musteri/{musteri_id}/kritik-ci"}  # fmt: skip


def kritik_ci(db: Session, musteriler: list[Customer], musteri_id: int, metin: str = "", duzenleyebilir: bool = False,
              kural: str = "") -> dict[str, Any]:  # fmt: skip
    """CI listesi: kart (ve istirakleri) Musteri No'larinin envanteri; kritik isaretli once, sonra aktif, servis ve ad. Arama sunucuda
    (tum sutunlarda parca eslesmesi, kelimeler VE; "evet"/"hayir" kritik durumunu da arar); en fazla EN_COK_SATIR satir.
    kural: CI adi oneki filtresi (TopoMaker kural seti; 'nw_li,nw_mbl,diger'; bos = tumu) - 2026-11-24 kullanici: "musteri
    kartindaki bu alanda nw_li gibi olanlari secebilecegimiz filtreleme yapalim". Kural sayilari arama metninden bagimsizdir."""
    from app.topoloji import kurallar as ci_kurallari

    anahtarlar = _anahtarlar(musteriler)
    coklu = len(anahtarlar) > 1
    etiket = {"kritik_baslik": m("Kritik CI", "Critical CI"), "evet": m("Evet", "Yes"), "hayir": m("Hayır", "No"), "duzenleyebilir": duzenleyebilir}
    if not anahtarlar:
        return {"basliklar": _basliklar(False), "satirlar": [], "kayitlar": [], "toplam": 0, "eslesen": 0,
                "ozet": m("Kartta Müşteri No yok.", "The card has no Customer No."), **etiket}  # fmt: skip
    kritik = _kritikler(db, musteri_id)
    duzeltme = lokasyon_duzeltmeleri(db, musteri_id)
    kayitlar = db.scalars(select(CustomerCi).where(CustomerCi.customer_key.in_(anahtarlar))).all()
    kayitlar = sorted(kayitlar, key=lambda r: (r.ci_no not in kritik, SIRA.get(r.status.upper(), 9), r.service, r.ci_name))
    parcalar = [p for p in " ".join((metin or "").split())[:200].casefold().split(" ") if p]
    kural_seti = ci_kurallari.oku(db)
    onekler = sorted((k["onek"] for k in kural_seti), key=len, reverse=True)
    sinif = {r.ci_no: ci_kurallari.sinifla(r.ci_name, onekler) for r in kayitlar}
    sayilar = Counter(sinif.values())
    secili = {ci_kurallari.onek_normal(p) for p in (kural or "").split(",") if ci_kurallari.onek_normal(p)}
    kural_listesi = [{"onek": k["onek"], "ad": k["ad"], "ci": sayilar.get(k["onek"], 0), "secili": k["onek"] in secili} for k in kural_seti]
    kural_listesi.append({"onek": ci_kurallari.DIGER, "ad": m("Diğer", "Other"), "ci": sayilar.get(ci_kurallari.DIGER, 0),
                          "secili": ci_kurallari.DIGER in secili})  # fmt: skip
    kural_listesi = [k for k in kural_listesi if k["ci"]]
    sonuc = []
    eslesen = 0
    for r in kayitlar:
        if secili and sinif[r.ci_no] not in secili:
            continue
        a = r.attrs or {}
        hucreler = ([r.customer_key] if coklu else []) + [
            r.ci_name, a.get("devre", ""), r.service, _durum_adi(r.status), a.get("bw", ""), a.get("imt", ""), a.get("lokasyon", ""),
            duzeltme.get(r.ci_no) or a.get("lok_adi", ""), _altyapi(a), a.get("saat", ""), (a.get("kurulum", "") or "")[:10],
        ]  # fmt: skip
        k = r.ci_no in kritik
        if parcalar:
            metin_ = (" ".join(hucreler) + " " + (etiket["evet"] if k else etiket["hayir"])).casefold()
            if not all(p in metin_ for p in parcalar):
                continue
        eslesen += 1
        if len(sonuc) < EN_COK_SATIR:
            sonuc.append({"ci": r.ci_no, "kritik": k, "hucreler": hucreler, "lokasyon_duzeltildi": r.ci_no in duzeltme,
                          "lokasyon_ilk": a.get("lok_adi", "")})  # fmt: skip
    toplam, ozet = _ozet(db, anahtarlar, len(kritik))
    return {"basliklar": _basliklar(coklu), "satirlar": [x["hucreler"] for x in sonuc], "kayitlar": sonuc, "toplam": toplam,
            "eslesen": eslesen, "ozet": ozet, "lokasyon_sutun": LOKASYON_ADI_SUTUNU + (1 if coklu else 0),
            "kurallar": kural_listesi, "kural_baslik": m("CI adı filtresi", "CI name filter"), "kural_tumu": m("Tümü", "All"),
            "lokasyon_ipucu": m("Lokasyon adını düzeltin (boş bırakılırsa envanterdeki ad kullanılır). TopoMaker aynı adlı CI'ları tek sahada çizer.",
                                "Correct the location name (empty = inventory name). TopoMaker draws CIs with the same name as one site."),
            **etiket}  # fmt: skip


def isaretle(db: Session, musteri: Customer, musteriler: list[Customer], ci_no: str, kritik: bool, kullanici: str) -> dict[str, Any]:
    """CI'yi kartta kritik (EVET) / degil (HAYIR) isaretler. CI kartin (ya da istiraklerinin) envanterinde olmali."""
    from app.musteri.servis import MusteriHata

    ci_no = (ci_no or "").strip()[:40]
    var = db.scalar(select(CustomerCi.id).where(CustomerCi.ci_no == ci_no, CustomerCi.customer_key.in_(_anahtarlar(musteriler))).limit(1))
    if not ci_no or var is None:
        raise MusteriHata(404, m("CI bu müşterinin envanterinde bulunamadı.", "CI not found in this customer's inventory."))
    k = db.get(CustomerCiFlag, (musteri.id, ci_no))
    if k is None:
        k = CustomerCiFlag(customer_id=musteri.id, ci_no=ci_no)
        db.add(k)
    k.critical, k.updated_by, k.updated_at = bool(kritik), kullanici, simdi()
    return {"ci": ci_no, "kritik": bool(kritik)}


def lokasyon_ata(db: Session, musteri: Customer, musteriler: list[Customer], ci_no: str, ad: str, kullanici: str) -> dict[str, Any]:
    """CI'in lokasyon adini kartta duzeltir; bos ya da envanterdeki adla ayni ise duzeltme kalkar (envanter degeri kullanilir)."""
    from app.musteri.servis import MusteriHata

    ci_no = (ci_no or "").strip()[:40]
    ad = " ".join((ad or "").split())[:300]
    r = db.scalar(select(CustomerCi).where(CustomerCi.ci_no == ci_no, CustomerCi.customer_key.in_(_anahtarlar(musteriler))).limit(1))
    if not ci_no or r is None:
        raise MusteriHata(404, m("CI bu müşterinin envanterinde bulunamadı.", "CI not found in this customer's inventory."))
    ilk = (r.attrs or {}).get("lok_adi", "")
    yeni = ad if ad and ad != ilk else None
    k = db.get(CustomerCiFlag, (musteri.id, ci_no))
    if k is None:
        if yeni is None:
            return {"ci": ci_no, "lokasyon": ilk, "duzeltildi": False}
        k = CustomerCiFlag(customer_id=musteri.id, ci_no=ci_no, critical=False)
        db.add(k)
    k.location_name, k.updated_by, k.updated_at = yeni, kullanici, simdi()
    return {"ci": ci_no, "lokasyon": yeni or ilk, "duzeltildi": yeni is not None}
