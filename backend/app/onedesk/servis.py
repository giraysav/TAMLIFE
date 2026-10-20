"""Onedesk sorgulari: aktif / kapanan sayilar, top10 musteri+lokasyon, RCA ortak noktalari, cozum tavsiyeleri.

Kapsam (uretim _build_ats_summary): admin ve Manager tum kayitlari, Member yalniz kendi portfoyunu (kendi musterileri ve
catisi kendisinde olan istirakler) gorur; musteriyle eslesmemis kayitlar yalniz yoneticiye gorunur.
"""

from __future__ import annotations

import threading
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime

from sqlalchemy import and_, extract, func, literal, literal_column, or_, select
from sqlalchemy.orm import Session

from app.models import Customer, OnedeskRecord
from app.onedesk import rca, yz
from app.ortak import UygulamaHatasi, iso, simdi
from app.session import Principal

TURLER = ("alarm", "talep", "sikayet")
KAPSAMLAR = ("acik", "kapali")
EN_COK_MUSTERI_SATIRI = 200
YASLANMA = (("0-24 saat", 0, 24), ("1-7 gün", 24, 168), ("7-30 gün", 168, 720), ("30 gün+", 720, None))
RCA_ORNEKLEM = 20_000  # RCA analizi icin okunacak en fazla kapanan kayit


class OnedeskHata(UygulamaHatasi):
    """kod = HTTP durumu."""


def _yil(yil: int | None) -> int:
    return yil if yil else simdi().year


def _aralik(yil: int) -> tuple[datetime, datetime]:
    return datetime(yil, 1, 1, tzinfo=UTC), datetime(yil + 1, 1, 1, tzinfo=UTC)


RADAR_KAYNAGI = "temip"  # karti olmayan TEMIP kaydi TAM Radar'indir (radar.servis); Onedesk sayilarina girmez


def _kapsam_kosulu():
    """2026-10-20 kullanici karari: herkes tum verileri gorur; yalniz kartsiz TEMIP kaydi (TAM Radar'in) Onedesk sayilarina girmez."""
    return or_(OnedeskRecord.customer_id.is_not(None), OnedeskRecord.source != RADAR_KAYNAGI)


def _musteri_adi():
    return func.coalesce(func.nullif(Customer.name, ""), func.nullif(OnedeskRecord.customer_label, ""), literal("—"))


def _kosullar(*ek):
    return and_(_kapsam_kosulu(), *ek)


def kaynak_bilgisi(db: Session) -> dict:
    toplam, son = db.execute(select(func.count(), func.max(func.coalesce(OnedeskRecord.closed_at, OnedeskRecord.opened_at)))).one()
    return {"kayit": int(toplam), "son_kayit": iso(son)}


def durum(db: Session, user: Principal, kapsam: str, yil: int | None = None) -> dict:
    """Ust kutular (tur toplamlari), musteri kirilimi ve grafik verisi."""
    if kapsam not in KAPSAMLAR:
        raise OnedeskHata(400, "Kapsam acik ya da kapali olmali.")
    yil = _yil(yil)
    if kapsam == "acik":
        kosul = _kosullar(OnedeskRecord.status == "open")
    else:
        bas, son = _aralik(yil)
        kosul = _kosullar(OnedeskRecord.status == "closed", OnedeskRecord.closed_at >= bas, OnedeskRecord.closed_at < son)

    ad = _musteri_adi()
    satirlar = db.execute(
        select(OnedeskRecord.customer_id, ad.label("ad"), OnedeskRecord.kind, func.count())
        .select_from(OnedeskRecord)
        .outerjoin(Customer, Customer.id == OnedeskRecord.customer_id)
        .where(kosul)
        .group_by(OnedeskRecord.customer_id, ad, OnedeskRecord.kind)
    ).all()
    toplam = dict.fromkeys(TURLER, 0)
    musteriler: dict[tuple[int | None, str], dict] = {}
    for cid, musteri, tur, adet in satirlar:
        if tur not in TURLER:
            continue
        toplam[tur] += adet
        m = musteriler.setdefault((cid, musteri), {"id": cid, "ad": musteri, **dict.fromkeys(TURLER, 0)})
        m[tur] += adet
    liste = sorted(({**m, "toplam": sum(m[t] for t in TURLER)} for m in musteriler.values()), key=lambda m: (-m["toplam"], m["ad"]))
    return {
        "kapsam": kapsam,
        "yil": yil,
        "toplam": {**toplam, "hepsi": sum(toplam.values())},
        "musteriler": liste[:EN_COK_MUSTERI_SATIRI],
        "musteri_sayisi": len(liste),
        "grafik": _yaslanma(db, kosul) if kapsam == "acik" else _aylik(db, kosul),
        "kaynak": kaynak_bilgisi(db),
    }


def _yaslanma(db: Session, kosul) -> list[dict]:
    """Acik kayitlarin yas dagilimi (alarm/talep/sikayet)."""
    simdi_ = simdi()
    kovalar = [{"etiket": e, **dict.fromkeys(TURLER, 0)} for e, _, _ in YASLANMA]
    for tur, acilis in db.execute(select(OnedeskRecord.kind, OnedeskRecord.opened_at).where(kosul)):
        if tur not in TURLER:
            continue
        if acilis is None:
            saat = 0.0
        else:
            saat = max(0.0, (simdi_ - (acilis if acilis.tzinfo else acilis.replace(tzinfo=UTC))).total_seconds() / 3600)
        for i, (_, alt, ust) in enumerate(YASLANMA):
            if saat >= alt and (ust is None or saat < ust):
                kovalar[i][tur] += 1
                break
    return kovalar


def _aylik(db: Session, kosul) -> list[dict]:
    """Yil icinde kapanan kayitlarin ay dagilimi."""
    ay = extract("month", OnedeskRecord.closed_at)
    aylar = {m: dict.fromkeys(TURLER, 0) for m in range(1, 13)}
    for a, tur, adet in db.execute(select(ay, OnedeskRecord.kind, func.count()).where(kosul).group_by(ay, OnedeskRecord.kind)):
        if tur in TURLER and a:
            aylar[int(a)][tur] = adet
    return [{"ay": m, **v} for m, v in aylar.items()]


# 2026-10-20 performans: top10 353 bin kaydi gruplar (~1 sn, indeksle de). Sonuc (yil, aralik, son kayit no, TEMIP yazim surumu) icin
# bellekte tutulur: yeni kayit ya da isci yazimi anahtari degistirir; ONBELLEK_SN yalniz Onedesk dosya ice alma gibi diger yazimlar icin
# ust sinir. app.isitici panel acilisinda ve veri degisince onceden hesaplar (ilk ziyaretci beklemez).
ONBELLEK_SN = 900
_onbellek: dict[tuple, tuple[float, dict]] = {}
_onbellek_kilidi = threading.Lock()


def top10(db: Session, user: Principal, yil: int | None = None, aralik: tuple[datetime, datetime] | None = None) -> dict:
    """Yil boyunca (aralik verilirse o aralikta, ornek ceyrek) en cok alarm/talep/sikayet olusan 10 musteri ve en cok kayit olusan lokasyonlari.
    toplam: araliktaki tum kayitlarin tur toplamlari."""
    yil = _yil(yil)
    bas, son = aralik or _aralik(yil)
    from app.tampon.temip_kayit import surum  # gec import: tampon zinciri yalniz gerekince

    anahtar = (yil, bas, son, db.scalar(select(func.max(OnedeskRecord.id))), surum(db))
    with _onbellek_kilidi:
        kayit = _onbellek.get(anahtar)
    if kayit is not None and time.monotonic() - kayit[0] < ONBELLEK_SN:
        return kayit[1]
    sonuc = _top10_hesapla(db, yil, bas, son)
    with _onbellek_kilidi:
        if len(_onbellek) > 64:
            _onbellek.clear()
        _onbellek[anahtar] = (time.monotonic(), sonuc)
    return sonuc


def _top10_hesapla(db: Session, yil: int, bas: datetime, son: datetime) -> dict:
    acilis = func.coalesce(OnedeskRecord.opened_at, OnedeskRecord.closed_at)
    kosul = _kosullar(acilis >= bas, acilis < son)
    ad = _musteri_adi()
    sayim: dict[str, dict] = {}
    for musteri, tur, adet in db.execute(
        select(ad, OnedeskRecord.kind, func.count()).select_from(OnedeskRecord).outerjoin(Customer, Customer.id == OnedeskRecord.customer_id).where(kosul).group_by(ad, OnedeskRecord.kind)
    ):
        if tur in TURLER:
            sayim.setdefault(musteri, dict.fromkeys(TURLER, 0))[tur] += adet
    ilk = sorted(sayim.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))[:10]
    adlar = [m for m, _ in ilk]
    lokasyonlar: dict[str, list[tuple[str, int]]] = defaultdict(list)
    if adlar:
        lok = func.nullif(OnedeskRecord.location, "")
        for musteri, yer, adet in db.execute(
            select(ad, func.coalesce(lok, literal("(lokasyon yok)")), func.count())
            .select_from(OnedeskRecord)
            .outerjoin(Customer, Customer.id == OnedeskRecord.customer_id)
            .where(kosul, ad.in_(adlar))
            .group_by(ad, func.coalesce(lok, literal("(lokasyon yok)")))
        ):
            lokasyonlar[musteri].append((yer, adet))
    musteriler = []
    for sira, (musteri, sayilar) in enumerate(ilk, start=1):
        yerler = sorted(lokasyonlar.get(musteri, []), key=lambda x: (-x[1], x[0]))
        musteriler.append(
            {
                "sira": sira,
                "ad": musteri,
                **sayilar,
                "toplam": sum(sayilar.values()),
                "lokasyon": yerler[0][0] if yerler else "",
                "lokasyonlar": [{"ad": y, "adet": n} for y, n in yerler[:3]],
            }
        )
    toplam = {t: sum(v[t] for v in sayim.values()) for t in TURLER}
    return {"yil": yil, "musteriler": musteriler, "toplam": {**toplam, "hepsi": sum(toplam.values())}, "musteri_sayisi": len(sayim)}


def _kapananlar(db: Session, user: Principal, yil: int) -> list[dict]:
    """RCA analizi icin yil boyu kapanan kayitlar (kok sebebi dolu olanlar)."""
    bas, son = _aralik(yil)
    ad = _musteri_adi()
    kosul = _kosullar(
        # Kismi indeksin (models.RCA_INDEKS_KOSULU) kullanilmasi icin kosul ayni LITERAL ile yazilir (bagli parametreyle kullanilmaz).
        OnedeskRecord.status == literal_column("'closed'"),
        OnedeskRecord.root_cause != literal_column("''"),
        OnedeskRecord.closed_at >= bas,
        OnedeskRecord.closed_at < son,
    )
    satirlar = db.execute(
        select(OnedeskRecord.root_cause, ad, OnedeskRecord.location, OnedeskRecord.kind, OnedeskRecord.category)
        .select_from(OnedeskRecord)
        .outerjoin(Customer, Customer.id == OnedeskRecord.customer_id)
        .where(kosul)
        .order_by(OnedeskRecord.closed_at.desc())
        .limit(RCA_ORNEKLEM)
    ).all()
    return [{"root_cause": r, "customer": m, "location": lok, "kind": t, "category": k} for r, m, lok, t, k in satirlar]


def rca_ozeti(db: Session, user: Principal, yil: int | None = None) -> dict:
    """Kok neden ortak noktalari: gruplar, anahtar kelimeler, tekrar eden lokasyonlar."""
    yil = _yil(yil)
    kayitlar = _kapananlar(db, user, yil)
    return {
        "yil": yil,
        "kapsanan": len(kayitlar),
        "ortak_noktalar": rca.ortak_noktalar(kayitlar),
        "anahtar_kelimeler": rca.anahtar_kelimeler(kayitlar),
        "tekrar_lokasyonlar": rca.tekrar_eden_lokasyonlar(kayitlar),
        "kategoriler": [{"ad": k, "adet": n} for k, n in Counter(r["category"] for r in kayitlar if r["category"]).most_common(6)],
    }


def oneriler(db: Session, user: Principal, yil: int | None = None) -> dict:
    """Cozum tavsiyeleri: yerlesik (kural tabanli, her zaman) + LLM durumu."""
    ozet = rca_ozeti(db, user, yil)
    return {
        "yil": ozet["yil"],
        "kapsanan": ozet["kapsanan"],
        "gruplar": [
            {"kok_sebep": g["kok_sebep"], "adet": g["adet"], "oran": g["oran"], "oneriler": g["oneriler"]} for g in ozet["ortak_noktalar"]
        ],
        "yz": yz.durum(),
    }


def yz_yorumu(db: Session, user: Principal, yil: int | None = None) -> dict:
    """LLM yorumu (acik degilse 503). Yalniz kok sebep metni ve sayilar modele gider."""
    ozet = rca_ozeti(db, user, yil)
    return {"yil": ozet["yil"], "yorum": yz.yorumla(ozet["ortak_noktalar"]), "model": yz.durum()["model"]}
