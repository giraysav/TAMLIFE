"""Dagitim: tampondaki ham veriyi KURAL + SABIT HEDEF ile panel tablolarina yazar.

Akis: onizle (yazmaz) -> uygula (onayli, TEK islem, her degisiklik distribution_log'a eski/yeni ile) -> geri al
(yalniz hala yazilan degerde duranlar; sonradan elle degisen korunur). Hedef kataloğu sabittir: serbest hedef yok;
katalogda olan her hedef bir panel alanina baglidir (uretim veri/hedefler.py ile ayni ilke).

Guvenceler: kural varsayilan KAPALI; bir numara birden cok karta dusuyorsa BELIRSIZ sayilir ve atlanir; eslesmeyen satir
sessizce yutulmaz (sayilir); sayi okunamayan / negatif sonuc yazilmaz; kart verisi tampon yoksa ancak
'eslesmeyeni sifirla' secilmisse 0 yazilir (uretimdeki "alarm bitti" anlami).
"""

from __future__ import annotations

import math
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Customer, IngestBatch
from app.ortak import UygulamaHatasi, iso, simdi
from app.tampon import analiz, depo
from app.tampon.eslestirme import DEGERSIZ_ISLECLER, ISLECLER, alan_anahtarlari, kosul_saglar, sayi
from app.tampon.models import DistributionLog, DistributionRule

# Alarm / sikayet / talep sayaclari hedef DEGIL: tek yazan kayitlar (onedesk/sayac.sayaclari_yenile; 2026-11-23).
HEDEFLER: dict[str, dict[str, str]] = {
    "customer.inventory_count": {"ad": "Envanter / lokasyon", "sutun": "inventory_count", "tip": "sayi"},
    "customer.sector": {"ad": "Sektör", "sutun": "sector", "tip": "metin"},
}
ISLEMLER: dict[str, dict[str, str]] = {
    "say": {"ad": "Say (satır adedi)", "tip": "sayi"},
    "farkli_say": {"ad": "Farklı değer say", "tip": "sayi"},
    "topla": {"ad": "Topla", "tip": "sayi"},
    "ortalama": {"ad": "Ortalama", "tip": "sayi"},
    "en_buyuk": {"ad": "En büyük", "tip": "sayi"},
    "en_kucuk": {"ad": "En küçük", "tip": "sayi"},
    "ilk": {"ad": "İlk dolu değer", "tip": "metin"},
    "en_cok": {"ad": "En sık değer", "tip": "metin"},
}
ESLESME_ALANLARI = {"customer_no": "Müşteri No", "ncst": "NCST", "name": "Müşteri ünvanı"}
AZAMI_KOSUL = 5
ORNEK_ADET = 50


def katalog() -> dict[str, Any]:
    return {
        "hedefler": [{"anahtar": k, **v} for k, v in HEDEFLER.items()],
        "islemler": [{"anahtar": k, **v} for k, v in ISLEMLER.items()],
        "islecler": list(ISLECLER),
        "degersiz_islecler": list(DEGERSIZ_ISLECLER),
        "eslesme_alanlari": [{"anahtar": k, "ad": v} for k, v in ESLESME_ALANLARI.items()],
    }


# --- Kural tanimi ------------------------------------------------------------------------------------------------
def _metin(govde: dict[str, Any], alan: str, ad: str, azami: int, zorunlu: bool = True) -> str:
    deger = str(govde.get(alan) or "").strip()
    if zorunlu and not deger:
        raise UygulamaHatasi(400, f"{ad} zorunlu.")
    if len(deger) > azami:
        raise UygulamaHatasi(400, f"{ad} en fazla {azami} karakter olabilir.")
    return deger


def dogrula(govde: dict[str, Any]) -> dict[str, Any]:
    """Kural govdesini denetler; temiz alanlari doner (UygulamaHatasi 400)."""
    hedef = _metin(govde, "target", "Hedef", 60)
    if hedef not in HEDEFLER:
        raise UygulamaHatasi(400, "Geçersiz hedef.")
    islem = _metin(govde, "operation", "İşlem", 20)
    if islem not in ISLEMLER or ISLEMLER[islem]["tip"] != HEDEFLER[hedef]["tip"]:
        raise UygulamaHatasi(400, "Bu hedef için geçersiz işlem.")
    eslesme = _metin(govde, "match_field", "Eşleşme alanı", 20)
    if eslesme not in ESLESME_ALANLARI:
        raise UygulamaHatasi(400, "Geçersiz eşleşme alanı.")
    deger_sutunu = _metin(govde, "value_column", "Değer sütunu", 160, zorunlu=islem != "say")
    kosullar = govde.get("conditions") or []
    if not isinstance(kosullar, list) or len(kosullar) > AZAMI_KOSUL:
        raise UygulamaHatasi(400, f"En fazla {AZAMI_KOSUL} koşul tanımlanabilir.")
    temiz_kosullar = []
    for k in kosullar:
        if not isinstance(k, dict):
            raise UygulamaHatasi(400, "Koşul biçimi geçersiz.")
        islec = str(k.get("islec") or "")
        kolon = str(k.get("kolon") or "").strip()
        deger = str(k.get("deger") or "").strip()
        if islec not in ISLECLER or not kolon or (islec not in DEGERSIZ_ISLECLER and not deger):
            raise UygulamaHatasi(400, "Koşul eksik ya da geçersiz.")
        temiz_kosullar.append({"kolon": kolon[:160], "islec": islec, "deger": deger[:200]})
    yas = govde.get("max_age_minutes")
    if yas in ("", None):
        yas = None
    elif not isinstance(yas, int) or isinstance(yas, bool) or not 1 <= yas <= 525_600:
        raise UygulamaHatasi(400, "En büyük parti yaşı 1 ile 525600 dakika arasında olmalı.")
    return {
        "name": _metin(govde, "name", "Kural adı", 120),
        "source_key": _metin(govde, "source_key", "Kaynak", 40),
        "match_field": eslesme,
        "key_column": _metin(govde, "key_column", "Anahtar sütunu", 160),
        "target": hedef,
        "operation": islem,
        "value_column": deger_sutunu,
        "conditions": temiz_kosullar,
        "zero_unmatched": bool(govde.get("zero_unmatched", False)),
        "max_age_minutes": yas,
    }


def kural_satiri(k: DistributionRule) -> dict[str, Any]:
    return {
        "id": k.id,
        "ad": k.name,
        "kaynak": k.source_key,
        "eslesme_alani": k.match_field,
        "anahtar_sutunu": k.key_column,
        "hedef": k.target,
        "islem": k.operation,
        "deger_sutunu": k.value_column,
        "kosullar": k.conditions or [],
        "eslesmeyeni_sifirla": k.zero_unmatched,
        "en_buyuk_yas_dk": k.max_age_minutes,
        "etkin": k.enabled,
        "olusturan": k.created_by,
        "guncelleme": iso(k.updated_at),
    }


def kurallar(db: Session) -> list[dict[str, Any]]:
    return [kural_satiri(k) for k in db.scalars(select(DistributionRule).order_by(DistributionRule.id))]


def kural_getir(db: Session, kural_id: int) -> DistributionRule:
    kural = db.get(DistributionRule, kural_id)
    if kural is None:
        raise UygulamaHatasi(404, "Kural yok.")
    return kural


def kural_olustur(db: Session, govde: dict[str, Any], kullanici: str) -> DistributionRule:
    """Yeni kural her zaman KAPALI baslar; etkinlestirmek ayri ve bilincli bir adimdir."""
    kural = DistributionRule(**dogrula(govde), enabled=False, created_by=kullanici[:120], updated_at=simdi())
    db.add(kural)
    db.flush()
    return kural


def kural_guncelle(db: Session, kural_id: int, govde: dict[str, Any]) -> DistributionRule:
    kural = kural_getir(db, kural_id)
    for alan, deger in dogrula(govde).items():
        setattr(kural, alan, deger)
    if "enabled" in govde:
        kural.enabled = bool(govde["enabled"])
    kural.updated_at = simdi()
    db.flush()
    return kural


def kural_sil(db: Session, kural_id: int) -> None:
    kural = kural_getir(db, kural_id)
    if db.scalar(select(func.count()).select_from(DistributionLog).where(DistributionLog.rule_id == kural_id)):
        raise UygulamaHatasi(409, "Bu kuralın uygulama geçmişi var; silmek yerine devre dışı bırakın.")
    db.delete(kural)
    db.flush()


# --- Hesap -------------------------------------------------------------------------------------------------------
@dataclass
class Degisim:
    musteri_id: int
    ad: str
    eski: Any
    yeni: Any
    sifirlama: bool = False


@dataclass
class Hesap:
    degisimler: list[Degisim] = field(default_factory=list)
    eslesen_musteri: int = 0
    degismeyen: int = 0
    toplam_satir: int = 0
    kosul_disi: int = 0
    eslesmeyen_satir: int = 0
    belirsiz_satir: int = 0
    gecersiz: int = 0
    sayilamayan_hucre: int = 0
    uyarilar: list[str] = field(default_factory=list)


class _Birikim:
    """Bir musterinin satirlarindan tek deger uretir (islem turune gore)."""

    def __init__(self, islem: str) -> None:
        self.islem = islem
        self.adet = 0
        self.toplam = 0.0
        self.sayili = 0
        self.en_buyuk: float | None = None
        self.en_kucuk: float | None = None
        self.farkli: set[str] = set()
        self.ilk: str | None = None
        self.sayac: Counter[str] = Counter()

    def ekle(self, deger: object, hesap: Hesap) -> None:
        self.adet += 1
        if self.islem == "say":
            return
        if deger in (None, ""):
            return
        if self.islem == "farkli_say":
            self.farkli.add(str(deger).strip().lower())
        elif self.islem in ("ilk", "en_cok"):
            metin = " ".join(str(deger).split())
            if self.ilk is None:
                self.ilk = metin
            self.sayac[metin] += 1
        else:
            x = sayi(deger)
            if x is None:
                hesap.sayilamayan_hucre += 1
                return
            self.toplam += x
            self.sayili += 1
            self.en_buyuk = x if self.en_buyuk is None else max(self.en_buyuk, x)
            self.en_kucuk = x if self.en_kucuk is None else min(self.en_kucuk, x)

    def sonuc(self) -> float | str | None:
        if self.islem == "say":
            return float(self.adet)
        if self.islem == "farkli_say":
            return float(len(self.farkli))
        if self.islem == "ilk":
            return self.ilk
        if self.islem == "en_cok":
            return self.sayac.most_common(1)[0][0] if self.sayac else None
        if not self.sayili:
            return None
        return {"topla": self.toplam, "ortalama": self.toplam / self.sayili, "en_buyuk": self.en_buyuk, "en_kucuk": self.en_kucuk}[
            self.islem
        ]


def _sutun_no(basliklar: list[str], ad: str) -> int:
    try:
        return basliklar.index(ad)
    except ValueError:
        raise UygulamaHatasi(400, f"Sütun partide yok: {ad}") from None


def _tam_sayi(x: float) -> int:
    return math.floor(x + 0.5)


def hesapla(db: Session, kural: DistributionRule, parti: IngestBatch) -> Hesap:
    """Kuralin bu partiye uygulanmasi halinde olacaklari (YAZMAZ)."""
    hedef = HEDEFLER[kural.target]
    sayisal = hedef["tip"] == "sayi"
    basliklar = list(parti.columns)
    anahtar_no = _sutun_no(basliklar, kural.key_column)
    deger_no = _sutun_no(basliklar, kural.value_column) if kural.value_column else None
    kosullar = [(_sutun_no(basliklar, k["kolon"]), k["islec"], k.get("deger", "")) for k in (kural.conditions or [])]

    dizin = analiz.musteri_dizini(db)[kural.match_field]
    musteriler = {c.id: c for c in db.scalars(select(Customer))}
    hesap = Hesap()
    birikim: dict[int, _Birikim] = defaultdict(lambda: _Birikim(kural.operation))
    belirsiz_anahtarlar: set[str] = set()

    for satir in depo.satirlari_oku(db, parti.id):
        hesap.toplam_satir += 1
        if not all(kosul_saglar(satir[i] if i < len(satir) else None, islec, deger) for i, islec, deger in kosullar):
            hesap.kosul_disi += 1
            continue
        anahtarlar = alan_anahtarlari(kural.match_field, satir[anahtar_no] if anahtar_no < len(satir) else None)
        if not anahtarlar:
            hesap.eslesmeyen_satir += 1
            continue
        eslesenler: set[int] = set()
        belirsiz = False
        for k in anahtarlar:
            kimlikler = dizin.get(k)
            if not kimlikler:
                continue
            if len(kimlikler) > 1:
                belirsiz_anahtarlar.add(k)
                belirsiz = True
                continue
            eslesenler.add(kimlikler[0])
        deger = satir[deger_no] if deger_no is not None and deger_no < len(satir) else None
        for kimlik in eslesenler:
            birikim[kimlik].ekle(deger, hesap)
        if belirsiz:
            hesap.belirsiz_satir += 1
        if not eslesenler and not belirsiz:
            hesap.eslesmeyen_satir += 1

    hesap.eslesen_musteri = len(birikim)
    sutun = hedef["sutun"]

    def kaydet(kimlik: int, yeni: Any, sifirlama: bool = False) -> None:
        musteri = musteriler[kimlik]
        eski = getattr(musteri, sutun)
        if sayisal:
            eski = int(eski or 0)
        if eski == yeni or (eski is None and yeni in (None, "")):
            hesap.degismeyen += 1
            return
        hesap.degisimler.append(Degisim(kimlik, musteri.name or f"#{kimlik}", eski, yeni, sifirlama))

    for kimlik, b in birikim.items():
        ham = b.sonuc()
        if ham is None:
            hesap.gecersiz += 1
            continue
        if sayisal:
            yeni = _tam_sayi(float(ham))
            if yeni < 0:
                hesap.gecersiz += 1
                continue
            kaydet(kimlik, yeni)
        else:
            kaydet(kimlik, str(ham)[:100])

    if kural.zero_unmatched and sayisal:
        belirsiz_musteri = {i for k in belirsiz_anahtarlar for i in dizin.get(k, [])}
        anahtarli = {i for ids in dizin.values() for i in ids}
        for kimlik in sorted(anahtarli - set(birikim) - belirsiz_musteri):
            kaydet(kimlik, 0, sifirlama=True)

    if hesap.belirsiz_satir:
        hesap.uyarilar.append(f"{hesap.belirsiz_satir} satırın numarası birden çok karta düşüyor (belirsiz); atlandı.")
    if hesap.sayilamayan_hucre:
        hesap.uyarilar.append(f"{hesap.sayilamayan_hucre} hücre sayıya çevrilemedi; atlandı.")
    if hesap.gecersiz:
        hesap.uyarilar.append(f"{hesap.gecersiz} müşteri için geçerli değer üretilemedi (boş/negatif); yazılmayacak.")
    return hesap


def _ozet(h: Hesap) -> dict[str, Any]:
    return {
        "toplam_satir": h.toplam_satir,
        "kosul_disi": h.kosul_disi,
        "eslesen_musteri": h.eslesen_musteri,
        "degisecek": len(h.degisimler),
        "sifirlanacak": sum(1 for d in h.degisimler if d.sifirlama),
        "degismeyen": h.degismeyen,
        "eslesmeyen_satir": h.eslesmeyen_satir,
        "belirsiz_satir": h.belirsiz_satir,
        "gecersiz": h.gecersiz,
        "uyarilar": h.uyarilar,
    }


def _parti_ve_kural(db: Session, kural_id: int, parti_id: int) -> tuple[DistributionRule, IngestBatch]:
    kural = kural_getir(db, kural_id)
    parti = db.get(IngestBatch, parti_id)
    if parti is None:
        raise UygulamaHatasi(404, "Parti yok.")
    if parti.status != "ready":
        raise UygulamaHatasi(409, "Parti hazır değil.")
    if parti.source_key != kural.source_key:
        raise UygulamaHatasi(409, "Kural bu kaynağın partisine uygulanır.")
    return kural, parti


def onizle(db: Session, kural_id: int, parti_id: int) -> dict[str, Any]:
    kural, parti = _parti_ve_kural(db, kural_id, parti_id)
    h = hesapla(db, kural, parti)
    ornek = sorted(h.degisimler, key=lambda d: (not d.sifirlama, d.ad.lower()))[:ORNEK_ADET]
    return {
        **_ozet(h),
        "ornek": [{"musteri_id": d.musteri_id, "ad": d.ad, "eski": d.eski, "yeni": d.yeni, "sifirlama": d.sifirlama} for d in ornek],
    }


def uygula(db: Session, kural_id: int, parti_id: int, kullanici: str) -> dict[str, Any]:
    """Tek islemde yazar (commit cagiranda); her degisiklik eski/yeni ile distribution_log'a girer."""
    kural, parti = _parti_ve_kural(db, kural_id, parti_id)
    if not kural.enabled:
        raise UygulamaHatasi(409, "Kural etkin değil; önce etkinleştirin.")
    if kural.max_age_minutes and parti.received_at is not None:
        zaman = parti.received_at if parti.received_at.tzinfo else parti.received_at.replace(tzinfo=simdi().tzinfo)
        if simdi() - zaman > timedelta(minutes=kural.max_age_minutes):
            raise UygulamaHatasi(409, f"Parti çok eski (en fazla {kural.max_age_minutes} dakika).")
    h = hesapla(db, kural, parti)
    run_id, an = uuid.uuid4().hex, simdi()
    sutun = HEDEFLER[kural.target]["sutun"]
    for d in h.degisimler:
        setattr(db.get(Customer, d.musteri_id), sutun, d.yeni)
        db.add(
            DistributionLog(
                run_id=run_id,
                rule_id=kural.id,
                batch_id=parti.id,
                customer_id=d.musteri_id,
                target=kural.target,
                old_value=None if d.eski is None else str(d.eski),
                new_value=str(d.yeni),
                at=an,
                actor=kullanici[:120],
            )
        )
    db.flush()
    return {"run_id": run_id, **_ozet(h), "yazilan": len(h.degisimler)}


def geri_al(db: Session, run_id: str, kullanici: str) -> dict[str, Any]:
    """Yalniz hala bu uygulamanin yazdigi degerde duran kartlari eski degerine dondurur; elle degisen korunur."""
    kayitlar = db.scalars(select(DistributionLog).where(DistributionLog.run_id == run_id, DistributionLog.reverted.is_(False))).all()
    if not kayitlar:
        raise UygulamaHatasi(404, "Geri alınacak kayıt yok (uygulama yok ya da zaten geri alındı).")
    geri, korunan = 0, 0
    for k in kayitlar:
        musteri = db.get(Customer, k.customer_id)
        hedef = HEDEFLER.get(k.target)
        if musteri is None or hedef is None:
            korunan += 1
            continue
        guncel = getattr(musteri, hedef["sutun"])
        if ("" if guncel is None else str(guncel)) != (k.new_value or ""):
            korunan += 1  # sonradan elle degismis: dokunma
            continue
        eski: Any = k.old_value
        if hedef["tip"] == "sayi":
            eski = int(k.old_value) if k.old_value not in (None, "") else 0
        setattr(musteri, hedef["sutun"], eski)
        k.reverted = True
        geri += 1
    db.flush()
    return {"geri_alinan": geri, "korunan": korunan}


def uygulamalar(db: Session, adet: int = 30) -> list[dict[str, Any]]:
    gruplu = db.execute(
        select(
            DistributionLog.run_id,
            DistributionLog.rule_id,
            DistributionLog.batch_id,
            DistributionLog.target,
            DistributionLog.actor,
            func.min(DistributionLog.at),
            func.count(),
            func.sum(case((DistributionLog.reverted.is_(True), 1), else_=0)),
        )
        .group_by(DistributionLog.run_id, DistributionLog.rule_id, DistributionLog.batch_id, DistributionLog.target, DistributionLog.actor)
        .order_by(func.min(DistributionLog.at).desc())
        .limit(adet)
    ).all()
    adlar = {k.id: k.name for k in db.scalars(select(DistributionRule))}
    return [
        {
            "run_id": run,
            "kural_id": kural,
            "kural": adlar.get(kural, f"#{kural}"),
            "parti_id": parti,
            "hedef": hedef,
            "hedef_adi": HEDEFLER.get(hedef, {}).get("ad", hedef),
            "kullanici": aktor,
            "zaman": iso(zaman),
            "yazilan": toplam,
            "geri_alinan": int(geri or 0),
        }
        for run, kural, parti, hedef, aktor, zaman, toplam, geri in gruplu
    ]
