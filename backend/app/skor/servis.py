# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Final skor servisi (TAM Utilizasyon): kriter tablolari, hesap, kayit, agac, personel agirligi, onay talebi.

Uretim karsiliklari: kutucuklar/utilizasyon/{toplu_atama.py, servis.py}, blueprints/projects_bp.py (save_customer_score,
skor_toplu_*, skor_agaci, istirak_final_dahil, puanlama_personeli, request_score_approval), blueprints/operations_bp.py
(util_criteria*). Hesap kurali motor.py, metrik kaynaklari kaynaklar.py, kriter veri kaynagi secimi kaynak_secimi.py.
Hesap HER ZAMAN sunucuda; istemcinin gonderdigi skor yalniz tek musteri ucunda (sayfa) kabul edilir.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.authz import yonetici_mi
from app.kullanicilar import kullanici_kaydi, personel_kosulu
from app.models import (
    AffiliateFinalFlag,
    AppUser,
    Customer,
    IngestBatch,
    ScoreApprovalRequest,
    ScoreDetail,
    ScoreHistory,
    ScoringExclusion,
    UtilCriteriaSet,
)
from app.ortak import UygulamaHatasi, iso
from app.session import Principal
from app.skor import kaynak_secimi, kaynaklar, urun_tutar
from app.skor import motor as skor

SCOPES = ("parent", "affiliate")
KAYNAKLAR = ("sayfa", "toplu", "kriter_degisikligi", "gunluk")
IZINLI_ALANLAR = ("title", "type", "metric", "weight", "b30", "b50", "b70", "b100", "servis_puanlari", "servis_dahil", "kaynak_secimi")
EN_FAZLA_KRITER = 50
EN_FAZLA_TOPLU = 5000
# 2026-10-20 kullanici karari: "db kaynaklarindan otomatik veri ile puanlama simdilik manuele cevrilecek; manuel kisim yalniz toplu
# atama kriter dokumunde". False iken kaynaklar (OneDesk, Urun-Tutar, segment, rapor) okunmaz; her cati musterinin her kriteri dokumde
# secilir (manuel_ata); kayitli secimler (ScoreDetail dokumu) toplu uygulamada ve kriter degisikliginde yeniden kullanilir.
# 2026-11-21 kullanici: "utilizasyon skorunu dinamik hesaplamak icin sabaha karsi bir isci kur (06:00); kapanmis kayitlari baz
# alacagiz" -> KARMA: veri kaynagi olan kriter otomatik (gunluk ozet, Urun-Tutar, segment, rapor), verisi olmayan kriter dokumdeki
# kayitli secime duser (motor.kriter_degerlendir). Dokumde secim yalniz verisi olmayan kriterlerde yapilir; gunluk isci skoru yazar.
OTOMATIK_PUANLAMA = True
DEGISIM_ESIGI = 0.05  # kriter degisikliginde bundan kucuk fark "degismeyen" sayilir (uretim toplu_atama.uygula)
ACIL_HESAP = "ladinadmin"  # siralamada gosterilmez (uretim _build_util_ranking)


class SkorHata(UygulamaHatasi):
    """kod = HTTP durumu."""


def simdi() -> datetime:
    return datetime.now(UTC)


# --- kriterler -------------------------------------------------------------------------------
def _kapsam(scope: str) -> str:
    if scope not in SCOPES:
        raise SkorHata(404, "Kriter kapsami bulunamadi.")
    return scope


def _son_surum(db: Session, scope: str) -> UtilCriteriaSet | None:
    return db.scalar(select(UtilCriteriaSet).where(UtilCriteriaSet.scope == _kapsam(scope)).order_by(UtilCriteriaSet.version.desc()))


def kriterler_oku(db: Session, scope: str) -> tuple[int, list[dict]]:
    """(surum, kriterler). Hic kayit yoksa (ya da kayit bozuksa) uretimdeki 7 varsayilan kriter, surum 0."""
    satir = _son_surum(db, scope)
    if satir is None or not isinstance(satir.criteria, list):
        return 0, skor.varsayilan_kriterler()
    return satir.version, [dict(k) for k in satir.criteria if isinstance(k, dict)]


def kriter_tablosu(db: Session, scope: str) -> dict:
    satir = _son_surum(db, scope)
    surum, kriterler = kriterler_oku(db, scope)
    return {
        "scope": scope,
        "version": surum,
        "criteria": kriterler,
        "varsayilan": surum == 0,
        "updated_by": satir.updated_by if satir else None,
        "updated_at": iso(satir.updated_at) if satir else None,
    }


def cati_kriterleri(db: Session) -> list[dict]:
    return kriterler_oku(db, "parent")[1]


def _servis_puanlari(deger: object, baslik: str) -> dict:
    """Kriter tablosunda duzenlenen servis puanlari (2026-11-24: puan atamasi yalniz buradan). Servis adlari sabit listedir (veri
    eslemesi bu adlara yapilir: Urun-Tutar / ONENT kategorileri); puan 0-100. Eksik servis varsayilan puaniyla tamamlanir."""
    if not isinstance(deger, dict):
        raise SkorHata(400, f'Kriter "{baslik}" servis puanlari gecersiz.')
    adlar = {skor.normal(ad): ad for ad in skor.SERVIS_PUANLARI}
    tablo = dict(skor.SERVIS_PUANLARI)
    for ad, puan in deger.items():
        asil = adlar.get(skor.normal(str(ad)))
        if asil is None:
            raise SkorHata(400, f'"{ad}" servis listesinde yok.')
        if not isinstance(puan, (int, float)) or isinstance(puan, bool) or not math.isfinite(puan) or not 0 <= puan <= 100:
            raise SkorHata(400, f'"{asil}" servis puani 0-100 arasinda bir sayi olmali.')
        tablo[asil] = int(puan) if float(puan).is_integer() else float(puan)
    return tablo


def _kriter_temizle(db: Session, ham: object) -> list[dict]:
    if not isinstance(ham, list) or len(ham) > EN_FAZLA_KRITER:
        raise SkorHata(400, f"Kriter listesi gecersiz (en fazla {EN_FAZLA_KRITER} satir).")
    temiz: list[dict] = []
    for satir in ham:
        if not isinstance(satir, dict):
            raise SkorHata(400, "Kriter satiri gecersiz.")
        baslik = str(satir.get("title") or "").strip()[:200]
        if not baslik:
            raise SkorHata(400, "Kriter basligi bos olamaz.")
        try:
            agirlik = float(satir.get("weight") or 0)
        except (TypeError, ValueError) as exc:
            raise SkorHata(400, f"Agirlik gecersiz: {baslik}") from exc
        if not math.isfinite(agirlik) or agirlik < 0:
            raise SkorHata(400, f"Agirlik 0 veya daha buyuk olmali: {baslik}")
        kayit = {k: satir[k] for k in IZINLI_ALANLAR if k in satir}
        kayit["title"], kayit["weight"] = baslik, agirlik
        kayit["type"] = str(kayit.get("type") or "")[:40]
        if "metric" in kayit:
            kayit["metric"] = str(kayit["metric"] or "")[:200]
        for alan in ("b30", "b50", "b70", "b100"):
            if alan in kayit:
                kayit[alan] = str(kayit[alan] or "")[:120]
        if "servis_puanlari" in kayit:
            kayit["servis_puanlari"] = _servis_puanlari(kayit["servis_puanlari"], baslik)
        temiz.append(kayit)
    skor.turleri_duzelt(temiz)
    return kaynak_secimi.satirlari_temizle(db, temiz)  # kaynak_secimi dogrulanir, servis_dahil denetlenir (400)


def kriterler_kaydet(db: Session, scope: str, ham: object, actor: str, actor_id: int | None) -> dict:
    """Yeni surum yazar. Cati kriteri degisince TUM cati musterilere yeni kurallar ayni islemde uygulanir (uretim
    save_util_criteria + tumunu_uygula): eksik kriteri olan ya da skoru degismeyen musteri ellenmez."""
    kapsam = _kapsam(scope)
    satirlar = _kriter_temizle(db, ham)
    surum = (db.scalar(select(func.max(UtilCriteriaSet.version)).where(UtilCriteriaSet.scope == kapsam)) or 0) + 1
    db.add(UtilCriteriaSet(scope=kapsam, version=surum, criteria=satirlar, updated_by=actor[:120], updated_at=simdi()))
    db.flush()
    sonuc: dict = {"version": surum, "criteria": satirlar, "uygulama": None}
    if kapsam == "parent":
        sonuc["uygulama"] = uygula(db, cati_musteriler(db), "kriter_degisikligi", actor, actor_id, yalniz_degisen=True, kriterler=satirlar)
    return sonuc


def meta(db: Session) -> dict:
    """Kriter editoru (uretim veri_bp.kriter_meta): tur -> kaynak adi, baslik ipuclari, varsayilan kurallar, servis puanlari, metrik
    adlari, X kurali turleri + veri kaynagi secimi secenekleri ve hazir tampon partileri (kaynak, sutunlar)."""
    son = (
        select(IngestBatch.source_key, func.max(IngestBatch.id).label("id"))
        .where(IngestBatch.status == "ready")
        .group_by(IngestBatch.source_key)
        .subquery()
    )
    partiler = db.scalars(select(IngestBatch).join(son, IngestBatch.id == son.c.id).order_by(IngestBatch.source_key)).all()
    return {
        "kaynak_adlari": skor.KAYNAK_ADLARI,
        "tur_ipuclari": [list(x) for x in skor.TUR_IPUCLARI],
        "varsayilan_kurallar": skor.VARSAYILAN_KURALLAR,
        "servis_puanlari": skor.SERVIS_PUANLARI,
        "metrikler": {**skor.SAYISAL, **skor.KATEGORIK},
        "sabit_puan_turleri": list(skor.SABIT_PUAN_TURLERI),
        "islemler": kaynak_secimi.ISLEM_ADLARI,
        "islecler": kaynak_secimi.ISLECLER,
        "degersiz_islecler": list(kaynak_secimi.DEGERSIZ_ISLECLER),
        "eslesme_alanlari": kaynak_secimi.ESLESME_ALANLARI,
        "tur_islemleri": kaynak_secimi.tur_islemleri(),
        "partiler": [
            {"kaynak": p.source_key, "parti": p.id, "etiket": p.label, "satir": p.row_count, "sutunlar": list(p.columns or []), "zaman": iso(p.received_at)}
            for p in partiler
        ],
    }


# --- hesap ----------------------------------------------------------------------------------
def cati_musteriler(db: Session, tam_id: int | None = None) -> list[Customer]:
    """Cati musteriler (yonetim ucu: admin hepsini gorur), ada gore (uretim toplu_atama.musteriler)."""
    sorgu = select(Customer).where(Customer.parent_id.is_(None))
    if tam_id is not None:
        sorgu = sorgu.where(Customer.owner_id == tam_id)
    return sorted(db.scalars(sorgu), key=lambda c: ((c.name or "").lower(), c.id))


def _son_atamalar(db: Session, kimlikler: list[int]) -> dict[int, dict]:
    """{musteri: {'kaynak', 'atayan', 'zaman'}} - son skor gecmisi satirindan (uretim skor_detaylari kaynak/atayan/zaman)."""
    if not kimlikler:
        return {}
    son = select(func.max(ScoreHistory.id)).where(ScoreHistory.customer_id.in_(kimlikler)).group_by(ScoreHistory.customer_id)
    return {
        h.customer_id: {"kaynak": h.source, "atayan": h.actor, "zaman": iso(h.at)}
        for h in db.scalars(select(ScoreHistory).where(ScoreHistory.id.in_(son)))
    }


def _adlar(db: Session, kimlikler: set[int | None]) -> dict[int, str]:
    temiz = [k for k in kimlikler if k is not None]
    if not temiz:
        return {}
    return {u.id: u.display_name or u.username for u in db.scalars(select(AppUser).where(AppUser.id.in_(temiz)))}


def hesapla(db: Session, liste: list[Customer], kriterler: list[dict] | None = None) -> tuple[list[dict], list[dict], list[str]]:
    """(kriterler, [musteri sonucu], uyarilar) - hicbir sey yazmaz (uretim toplu_atama.hesapla)."""
    if kriterler is None:
        kriterler = cati_kriterleri(db)
    kimlikler = [c.id for c in liste]
    metrikler, uyarilar = kaynaklar.birlesik_metrikler(db, liste, kriterler) if OTOMATIK_PUANLAMA else ({}, [])
    detaylar = {d.customer_id: d.detail for d in db.scalars(select(ScoreDetail).where(ScoreDetail.customer_id.in_(kimlikler)))} if liste else {}
    atamalar = _son_atamalar(db, kimlikler)
    tamlar = _adlar(db, {c.owner_id for c in liste})
    sonuc = []
    for c in liste:
        h = skor.musteri_skoru(kriterler, metrikler.get(c.id, {}), skor.manuel_secimler(detaylar.get(c.id)), OTOMATIK_PUANLAMA)
        mevcut = round(c.score, 1) if c.score is not None else None
        sonuc.append(
            {
                "id": c.id,
                "ad": c.name,
                "tam": tamlar.get(c.owner_id, "") if c.owner_id else "",
                "tam_id": c.owner_id,
                "mevcut": mevcut,
                "yeni": h["skor"],
                "fark": round(h["skor"] - mevcut, 1) if mevcut is not None else None,
                "tamam": h["tamam"],
                "yazilabilir": h["yazilabilir"],
                "eksik": h["eksik"],
                "kriterler": h["kriterler"],
                "son_atama": atamalar.get(c.id),
            }
        )
    return kriterler, sonuc, uyarilar


def kriter_ozeti(kriterler: list[dict]) -> list[dict]:
    return [{"baslik": k.get("title"), "tur": k.get("type") or "manual", "agirlik": k.get("weight")} for k in kriterler]


def onizleme(db: Session, tam_id: int | None) -> dict:
    """Toplu atama onizlemesi (uretim skor_toplu_onizleme): yeni skor HESAPLANIR, hicbir sey yazilmaz."""
    kriterler, sonuc, uyarilar = hesapla(db, cati_musteriler(db, tam_id))
    return {
        "manuel": True,  # karma kipte de dokumde secim yapilir (verisi olmayan kriterler)
        "kaynaklar": kaynaklar.kaynak_durumlari(db, kriterler) if OTOMATIK_PUANLAMA else [],
        "uyarilar": uyarilar,
        "kriterler": kriter_ozeti(kriterler),
        "musteriler": sonuc,
        "ozet": {"toplam": len(sonuc), "hazir": sum(1 for s in sonuc if s["tamam"])},
    }


# --- yazma ----------------------------------------------------------------------------------
def _gecerli_skor(deger: object) -> float:
    try:
        sayi = float(deger)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise SkorHata(400, "Gecersiz skor degeri.") from exc
    if not math.isfinite(sayi) or sayi < 0:
        raise SkorHata(400, "Skor 0 veya daha buyuk gecerli bir sayi olmalidir.")
    if sayi > 100.0001:
        raise SkorHata(400, "Final skor en fazla 100 olabilir (yalniz cati kriterleri).")
    return sayi


def _detay_oku(ham: object) -> list[dict]:
    """Sayfadan gelen kriter dokumu -> temiz liste (gecersiz satir atlanir; dokum istege bagli)."""
    sonuc = []
    for satir in (ham if isinstance(ham, list) else [])[:EN_FAZLA_KRITER]:
        if not isinstance(satir, dict):
            continue
        try:
            puan = int(float(satir.get("puan") or 0))
            agirlik = float(satir.get("agirlik") or 0)
        except (TypeError, ValueError):
            continue
        if not 0 <= puan <= 100 or not math.isfinite(agirlik):  # Sozlesme alt kriterleri 15 / 85 de verir
            continue
        sonuc.append(
            {"baslik": str(satir.get("baslik") or "")[:200], "tur": str(satir.get("tur") or "manual")[:40], "puan": puan, "agirlik": agirlik}
        )
    return sonuc


def dokum(kriter_sonuclari: list[dict]) -> list[dict]:
    """Kaydedilen kriter dokumu: kaynak ve deger de saklanir (uretim toplu_atama.dokum); dokumde yapilan liste secimi (Servis
    Cesitliligi / Sozlesme) 'secim' olarak saklanir, sonraki hesaplarda kullanilir."""
    return [
        {"baslik": k["baslik"], "tur": k["tur"], "puan": k["puan"], "agirlik": k["agirlik"], "kaynak": k["kaynak"], "deger": k["deger"]}
        | ({"secim": k["secim"]} if k.get("secim") is not None else {})
        for k in kriter_sonuclari
    ]


def skoru_yaz(db: Session, musteri: Customer, deger: float, detay: list[dict], kaynak: str, actor: str, actor_id: int | None) -> None:
    """Sayfa / toplu / kriter degisikligi AYNI yoldan: skor + bekleyen 'Iste' talebi + dokum/gecmis (uretim toplu_atama.skoru_yaz)."""
    if kaynak not in KAYNAKLAR:
        raise SkorHata(400, "Gecersiz kaynak.")
    zaman = simdi()
    eski = musteri.score
    musteri.score = deger
    # Bekleyen "Iste" talebi varsa skorun fiilen atanmasi talebi de sonuclandirir.
    bekleyen = db.scalar(select(ScoreApprovalRequest).where(ScoreApprovalRequest.customer_id == musteri.id, ScoreApprovalRequest.status == "pending"))
    if bekleyen is not None:
        bekleyen.status, bekleyen.resolved_by, bekleyen.resolved_at = "approved", actor_id, zaman
    satir = db.get(ScoreDetail, musteri.id)
    if satir is None:
        db.add(ScoreDetail(customer_id=musteri.id, score=deger, detail=detay, updated_at=zaman))
    else:
        satir.score, satir.detail, satir.updated_at = deger, detay, zaman
    db.add(ScoreHistory(customer_id=musteri.id, old_score=eski, score=deger, source=kaynak, actor=actor[:120], at=zaman, detail=detay))
    db.flush()


def uygula(
    db: Session, liste: list[Customer], kaynak: str, actor: str, actor_id: int | None, yalniz_degisen: bool = False, kriterler: list[dict] | None = None
) -> dict:
    """Hesaplar ve yazar: tum kriterleri dolu olanlar ve (2026-11-21) eksigi olsa da en az bir kriteri dolu olanlar - ara skor,
    dolu kriterlerle orantili. {'uygulanan': [...], 'atlanan': [...], 'degismeyen': n, 'kismi': n}."""
    _, sonuc, _ = hesapla(db, liste, kriterler)
    kimlikten = {c.id: c for c in liste}
    uygulanan, atlanan, degismeyen, kismi = [], [], 0, 0
    for s in sonuc:
        if not s["yazilabilir"]:
            atlanan.append({"id": s["id"], "ad": s["ad"], "neden": "eksik kriter: " + ", ".join(s["eksik"] or ["kriter yok"])})
            continue
        if not s["tamam"]:
            kismi += 1
        if yalniz_degisen and s["mevcut"] is not None and abs(s["yeni"] - s["mevcut"]) < DEGISIM_ESIGI:
            degismeyen += 1
            continue
        skoru_yaz(db, kimlikten[s["id"]], s["yeni"], dokum(s["kriterler"]), kaynak, actor, actor_id)
        uygulanan.append({"id": s["id"], "ad": s["ad"], "eski": s["mevcut"], "yeni": s["yeni"]})
    return {"uygulanan": uygulanan, "atlanan": atlanan, "degismeyen": degismeyen, "kismi": kismi}


def toplu_uygula(db: Session, istenen: object, actor: str, actor_id: int | None) -> dict:
    """Secilen musterilere sunucuda YENIDEN hesaplanan skoru yazar; eksik kriteri olan musteri ATLANIR."""
    if not isinstance(istenen, list) or not istenen or len(istenen) > EN_FAZLA_TOPLU:
        raise SkorHata(400, "Musteri listesi gecersiz.")
    try:
        kimlikler = {int(x) for x in istenen if not isinstance(x, bool)}
    except (TypeError, ValueError) as exc:
        raise SkorHata(400, "Musteri listesi gecersiz.") from exc
    liste = [c for c in cati_musteriler(db) if c.id in kimlikler]
    sonuc = uygula(db, liste, "toplu", actor, actor_id)
    bulunamayan = kimlikler - {c.id for c in liste}
    sonuc["atlanan"] += [{"id": i, "ad": "", "neden": "bulunamadi ya da cati musteri degil"} for i in sorted(bulunamayan)]
    return sonuc


def manuel_ata(db: Session, musteri_id: int, ham: object, actor: str, actor_id: int | None) -> dict:
    """Kriter dokumunde secilen puanlar (baslik -> kriterin secenegindeki 30/50/70/100; Servis Cesitliligi icin alinan servis
    listesi; Sozlesme icin isaretlenen alt kriterler) ile cati musterinin final skoru sunucuda hesaplanip yazilir (kaynak 'toplu'). Her kriter secilmis olmali (X sabit puanli
    satir haric); secimler dokumle saklanir. Servis puanlari burada degil kriter tablosunda degistirilir."""
    musteri = db.get(Customer, musteri_id)
    if musteri is None or musteri.parent_id is not None:
        raise SkorHata(404, "Cati musteri bulunamadi.")
    if not isinstance(ham, dict) or len(ham) > EN_FAZLA_KRITER:
        raise SkorHata(400, "Kriter secimleri gecersiz.")
    secimler: dict[str, int | list[str]] = {}
    for baslik, puan in ham.items():
        if isinstance(puan, list) and len(puan) <= 50 and all(isinstance(x, str) for x in puan):
            secimler[skor.normal(str(baslik))] = puan
            continue
        if not isinstance(puan, int) or isinstance(puan, bool) or puan not in skor.PUANLAR:
            raise SkorHata(400, f'"{baslik}" icin puan 30, 50, 70 ya da 100 olmali.')
        secimler[skor.normal(str(baslik))] = puan
    kriterler = cati_kriterleri(db)
    for k in kriterler:
        secim = secimler.get(skor.normal(k.get("title")))
        if secim is None or skor.sabit_puan(k) is not None:
            continue
        if skor.tur_coz(k) == "servis_cesitliligi":
            if not isinstance(secim, list):
                raise SkorHata(400, f'"{k.get("title")}" icin alinan servisler secilmeli.')
            liste = {skor.normal(s["ad"]) for s in skor.servis_listesi(k)}
            if yok := [x for x in secim if skor.normal(x) not in liste]:
                raise SkorHata(400, f'"{k.get("title")}" listesinde olmayan servis: {", ".join(yok)}')
        elif skor.tur_coz(k) == "auto_sozlesme":
            if not isinstance(secim, list):
                raise SkorHata(400, f'"{k.get("title")}" icin alt kriterler isaretlenmeli.')
            liste = {skor.normal(ad) for ad, _ in skor.SOZLESME_ALT_KRITERLER}
            if yok := [x for x in secim if skor.normal(x) not in liste]:
                raise SkorHata(400, f'"{k.get("title")}" alt kriteri degil: {", ".join(yok)}')
        elif isinstance(secim, list) or secim not in {s["puan"] for s in skor.secenekler(k)}:
            raise SkorHata(400, f'"{k.get("title")}" icin {secim} puanin kriter tablosunda kurali yok.')
    metrikler = kaynaklar.birlesik_metrikler(db, [musteri], kriterler)[0].get(musteri.id, {}) if OTOMATIK_PUANLAMA else {}
    h = skor.musteri_skoru(kriterler, metrikler, secimler, otomatik=OTOMATIK_PUANLAMA)
    if not h["yazilabilir"]:
        raise SkorHata(400, "En az bir kriter icin puan secin.")
    eski = round(musteri.score, 1) if musteri.score is not None else None
    skoru_yaz(db, musteri, h["skor"], dokum(h["kriterler"]), "toplu", actor, actor_id)
    return {"id": musteri.id, "ad": musteri.name, "eski": eski, "yeni": h["skor"]}


def musteri_skoru_ata(db: Session, musteri_id: int, tam_id: int, deger: object, detay: object, actor: str, actor_id: int | None) -> None:
    musteri = db.get(Customer, musteri_id)
    if musteri is None:
        raise SkorHata(404, "Musteri bulunamadi.")
    if musteri.owner_id != tam_id:
        raise SkorHata(400, "Musteri ve personel eslesmiyor.")
    if musteri.parent_id is not None:
        raise SkorHata(400, "Istirak musteriler icin ayri final skor atanamaz - skor cati musteri uzerinden atanir.")
    skoru_yaz(db, musteri, _gecerli_skor(deger), _detay_oku(detay), "sayfa", actor, actor_id)


# --- agac, personel agirligi, siralama (uretim toplu_atama.agac + utilizasyon/servis.py) --------------------------------------
def tam_skor_ozeti(catilar: list[Customer]) -> dict:
    """Bir personelin CATI musterilerinden utilizasyon puanlari. Skor 0/bos = atanmamis.
      final_skor    : ortalama, YALNIZ skorlu musteriler
      toplam_puan   : skorlarin toplami (musterilerin getirdigi puan)
      agirlik_puani : toplam puan / TUM musteri sayisi ('Tam Agirlik')"""
    skorlar = [c.score for c in catilar if c.score]
    toplam = sum(skorlar)
    return {
        "musteri_sayisi": len(catilar),
        "skorlu_musteri": len(skorlar),
        "toplam_puan": round(toplam, 1),
        "final_skor": round(toplam / len(skorlar), 1) if skorlar else None,
        "agirlik_puani": round(toplam / len(catilar), 1) if catilar else None,
    }


def personel_agirlik_dagilimi(personel: list[AppUser], catilar: list[Customer], istirakler: dict[int, list[Customer]] | None = None) -> dict:
    """Personel Agirlik ve Dagilim ("TAM Musteri Dagilimi" Excel'i; panel olcegi 0-100):
      her personel : musteri sayisi (cati), istiraki olan musteri, skorlu musteri, toplam puan, AGIRLIK = toplam puan / musteri sayisi
      ekip         : TAM sayisi, musteri sayisi, toplam puan, hedef agirlik = toplam / TAM sayisi, ortalama musteri puani
      dagitim      : fark = personel toplami - hedef; dengeleme musteri adedi = fark / ortalama musteri puani.
    Siralama: agirlik buyukten kucuge."""
    istirakler = istirakler or {}
    by_tam: dict[int | None, list[Customer]] = {}
    for c in catilar:
        by_tam.setdefault(c.owner_id, []).append(c)
    satirlar = []
    for u in personel:
        ms = by_tam.get(u.id, [])
        ozet = tam_skor_ozeti(ms)
        satirlar.append(
            {
                "id": u.id,
                "ad": u.display_name or u.username,
                "musteri_sayisi": ozet["musteri_sayisi"],
                "istirakli_musteri": sum(1 for c in ms if istirakler.get(c.id)),
                "skorlu_musteri": ozet["skorlu_musteri"],
                "toplam_puan": ozet["toplam_puan"],
                "agirlik_puani": ozet["agirlik_puani"],
            }
        )
    tam_sayisi = len(satirlar)
    musteri = sum(s["musteri_sayisi"] for s in satirlar)
    toplam = round(sum(s["toplam_puan"] for s in satirlar), 1)
    hedef = round(toplam / tam_sayisi, 1) if tam_sayisi else 0
    ort_musteri = round(toplam / musteri, 1) if musteri else 0
    for s in satirlar:
        s["hedef_fark"] = round(s["toplam_puan"] - hedef, 1)
        s["dengeleme_musteri"] = round(s["hedef_fark"] / ort_musteri, 1) if ort_musteri else 0
    satirlar.sort(key=lambda s: (s["agirlik_puani"] if s["agirlik_puani"] is not None else -1, s["toplam_puan"]), reverse=True)
    for i, s in enumerate(satirlar, 1):
        s["sira"] = i
    return {
        "satirlar": satirlar,
        "ozet": {
            "tam_sayisi": tam_sayisi,
            "musteri_sayisi": musteri,
            "toplam_puan": toplam,
            "hedef_agirlik": hedef,
            "ortalama_musteri_puani": ort_musteri,
            "skorlu_musteri": sum(s["skorlu_musteri"] for s in satirlar),
        },
    }


def _tam_personel(db: Session) -> list[AppUser]:
    """Aktif TeamMember'lar (agac, TAM sayisi, personel agirligi ve siralama ile ayni kume: kullanicilar.personel_kosulu)."""
    return list(db.scalars(select(AppUser).where(*personel_kosulu()).order_by(AppUser.id)))


def final_dahil_kimlikleri(db: Session) -> set[int]:
    return set(db.scalars(select(AffiliateFinalFlag.customer_id).where(AffiliateFinalFlag.included.is_(True))))


def agac(db: Session) -> dict:
    """Skorlari Dagit agaci + Personel Agirlik ve Dagilim - hicbir sey yazmaz. personel: yalniz TAM personeli (TeamMember; musterisi olmasa da);
    sahibi yonetici/admin olan (ya da sahipsiz) musteriler "atanmamis" grubunda toplanir (2026-10-13); agirliga gore buyukten kucuge. Istirak "Final skoruna dahil" ise cati kurallari ona da
    uygulanir ve skoru gosterilir; istirak skoru hicbir yere YAZILMAZ, finale eklenmez (katsayi sonra belirlenecek)."""
    catilar = cati_musteriler(db)
    istirakler: dict[int, list[Customer]] = {}
    for c in db.scalars(select(Customer).where(Customer.parent_id.is_not(None))):
        istirakler.setdefault(c.parent_id, []).append(c)  # type: ignore[arg-type]
    dahil_set = final_dahil_kimlikleri(db)
    dahil = [i for c in catilar for i in istirakler.get(c.id, []) if i.id in dahil_set]
    kriterler, sonuc, uyarilar = hesapla(db, catilar + dahil)
    sonuc_id = {s["id"]: s for s in sonuc}

    # Puanlamaya GIRMEYEN personel ne agacta, ne TAM sayisinda, ne agirlik hesabinda; musterileri "atanmamis" grubunda.
    disi = set(db.scalars(select(ScoringExclusion.user_id)))
    tum_tam = _tam_personel(db)
    tamlar = [u for u in tum_tam if u.id not in disi]
    tam_idler = {u.id for u in tamlar}
    by_sahip: dict[int | None, list[Customer]] = {}
    for c in catilar:
        by_sahip.setdefault(c.owner_id, []).append(c)

    def musteri_dugumu(c: Customer) -> dict:
        d = dict(sonuc_id[c.id])
        d["istirakler"] = []
        for i in sorted(istirakler.get(c.id, []), key=lambda x: (x.name or "").lower()):
            evet = i.id in dahil_set
            s = sonuc_id.get(i.id) if evet else None
            d["istirakler"].append(
                {
                    "id": i.id,
                    "ad": i.name,
                    "dahil": evet,
                    "yeni": s["yeni"] if s else None,
                    "tamam": s["tamam"] if s else None,
                    "eksik": s["eksik"] if s else [],
                    "kriterler": s["kriterler"] if s else [],
                }
            )
        return d

    personel = []
    for u, tam_mi in [(u, True) for u in tamlar]:
        ms = by_sahip.get(u.id, [])
        ozet = tam_skor_ozeti(ms)
        personel.append(
            {
                "id": u.id,
                "ad": u.display_name or u.username,
                "tam": tam_mi,
                "musteri_sayisi": ozet["musteri_sayisi"],
                "skorlu_musteri": ozet["skorlu_musteri"],
                "toplam_puan": ozet["toplam_puan"],
                "agirlik_puani": ozet["agirlik_puani"],
                "musteriler": [musteri_dugumu(c) for c in ms],
            }
        )
    personel.sort(key=lambda p: (p["tam"], p["agirlik_puani"] if p["agirlik_puani"] is not None else -1, p["toplam_puan"]), reverse=True)
    atanmamis = [c for c in catilar if c.owner_id not in tam_idler]
    tum_personel = sorted(
        (
            {"id": u.id, "ad": u.display_name or u.username, "tam": tam_mi, "dahil": u.id not in disi, "musteri_sayisi": len(by_sahip.get(u.id, []))}
            for u, tam_mi in [(u, True) for u in tum_tam]
        ),
        key=lambda p: (p["ad"] or "").lower(),
    )
    cati_idler = {c.id for c in catilar}
    return {
        "manuel": True,  # karma kip: dokumde verisi olmayan kriterler secilir
        "kaynaklar": kaynaklar.kaynak_durumlari(db, kriterler) if OTOMATIK_PUANLAMA else [],
        "kriterler": kriter_ozeti(kriterler),
        "uyarilar": uyarilar,
        "personel": personel,
        "atanmamis": [musteri_dugumu(c) for c in atanmamis],
        "tum_personel": tum_personel,
        "ozet": {
            "toplam": len(sonuc),
            "cati": len(catilar),
            "hazir": sum(1 for c in catilar if sonuc_id[c.id]["tamam"]),
            "istirak": sum(len(v) for k, v in istirakler.items() if k in cati_idler),
            "istirak_dahil": len(dahil),
        },
        "dagilim": personel_agirlik_dagilimi(tamlar, catilar, istirakler),
    }


def siralama(db: Session) -> list[dict]:
    """TAM Utilizasyon Siralamasi (uretim _build_util_ranking): her kullanicinin cati musterilerinin ortalama final skoru; skoru
    hic atanmamis kisi listede yok. bar_pct = en yuksege gore yuzde."""
    kullanicilar = [u for u in _tam_personel(db) if u.username.lower() != ACIL_HESAP]  # yonetici ve admin siralamada yer almaz (2026-10-13)
    by_tam: dict[int | None, list[Customer]] = {}
    for c in cati_musteriler(db):
        by_tam.setdefault(c.owner_id, []).append(c)
    liste = []
    for u in kullanicilar:
        musteriler = by_tam.get(u.id, [])
        skorlu = [c.score for c in musteriler if c.score]
        if not skorlu:
            continue
        liste.append({"id": u.id, "full_name": u.display_name or u.username, "customer_count": len(musteriler), "avg_score": round(sum(skorlu) / len(skorlu), 1)})
    liste.sort(key=lambda r: r["avg_score"], reverse=True)
    en_yuksek = max((r["avg_score"] for r in liste), default=0) or 1
    for i, r in enumerate(liste):
        r["rank"] = i + 1
        r["bar_pct"] = round((r["avg_score"] / en_yuksek) * 100)
    return liste


# --- onay talebi ----------------------------------------------------------------------------
def talep_olustur(db: Session, musteri_id: int, user: Principal) -> int:
    """TAM tarafi (uretim request_score_approval): kendi cati musterisi icin; admin/TeamMngr kapsami herkes."""
    musteri = db.get(Customer, musteri_id)
    if musteri is None:
        raise SkorHata(404, "Musteri bulunamadi.")
    if musteri.parent_id is not None:
        raise SkorHata(400, "Istirak musteriler icin ayri final skor talebi olusturulamaz - talep cati musteri uzerinden yapilmali.")
    kisi = kullanici_kaydi(db, user)
    if musteri.owner_id != kisi.id and not yonetici_mi(user):
        raise SkorHata(403, "Sadece kendi musteriniz icin skor atamasi talep edebilirsiniz.")
    var = db.scalar(select(ScoreApprovalRequest.id).where(ScoreApprovalRequest.customer_id == musteri.id, ScoreApprovalRequest.status == "pending"))
    if var is not None:
        raise SkorHata(400, "Bu musteri icin zaten bekleyen bir talep var.")
    talep = ScoreApprovalRequest(customer_id=musteri.id, requested_by=kisi.id, requested_at=simdi(), status="pending")
    db.add(talep)
    db.flush()
    return talep.id


def talepler(db: Session) -> list[dict]:
    satirlar = db.execute(
        select(ScoreApprovalRequest, Customer, AppUser)
        .join(Customer, Customer.id == ScoreApprovalRequest.customer_id)
        .join(AppUser, AppUser.id == ScoreApprovalRequest.requested_by)
        .where(ScoreApprovalRequest.status == "pending")
        .order_by(ScoreApprovalRequest.requested_at)
    ).all()
    tamlar = _adlar(db, {c.owner_id for _, c, _ in satirlar})
    return [
        {
            "id": t.id,
            "customer_id": c.id,
            "customer_name": c.name,
            "tam_id": c.owner_id,
            "tam_name": tamlar.get(c.owner_id, "") if c.owner_id else "",
            "score": round(c.score, 1) if c.score is not None else None,
            "requested_by_name": u.display_name or u.username,
            "requested_at": iso(t.requested_at) or "",
        }
        for t, c, u in satirlar
    ]


def talep_karar(db: Session, talep_id: int, eylem: str, actor_id: int | None) -> None:
    if eylem not in ("approve", "reject"):
        raise SkorHata(400, "Gecersiz islem.")
    talep = db.get(ScoreApprovalRequest, talep_id)
    if talep is None or talep.status != "pending":
        raise SkorHata(404, "Talep bulunamadi ya da zaten sonuclandirilmis.")
    talep.status = "approved" if eylem == "approve" else "rejected"
    talep.resolved_by = actor_id
    talep.resolved_at = simdi()
    db.flush()


# --- personel / istirak ---------------------------------------------------------------------
def puanlama_disi_ayarla(db: Session, ham: object, actor: str) -> list[int]:
    """Liste TAMAMEN degisir (bos liste = herkes dahil)."""
    if not isinstance(ham, list) or len(ham) > 2000 or not all(isinstance(x, int) and not isinstance(x, bool) for x in ham):
        raise SkorHata(400, "Personel listesi gecersiz.")
    gecerli = set(db.scalars(select(AppUser.id).where(AppUser.id.in_(ham)))) if ham else set()
    for satir in db.scalars(select(ScoringExclusion)):
        db.delete(satir)
    db.flush()
    zaman = simdi()
    for kimlik in sorted(gecerli):
        db.add(ScoringExclusion(user_id=kimlik, set_by=actor[:120], at=zaman))
    db.flush()
    return sorted(gecerli)


def final_dahil_ayarla(db: Session, musteri_id: int, dahil: object) -> bool:
    musteri = db.get(Customer, musteri_id)
    if musteri is None:
        raise SkorHata(404, "Musteri bulunamadi.")
    if musteri.parent_id is None:
        raise SkorHata(400, "Bu secim yalniz istirakler icindir.")
    if not isinstance(dahil, bool):
        raise SkorHata(400, "Secim evet ya da hayir olmali.")
    satir = db.get(AffiliateFinalFlag, musteri_id)
    if satir is None:
        db.add(AffiliateFinalFlag(customer_id=musteri_id, included=dahil))
    else:
        satir.included = dahil
    db.flush()
    return dahil


def urun_tutar_listesi(db: Session) -> list[dict]:
    """Yuklenmis Urun-Tutar ozetleri (musteri adiyla, en yeni once)."""
    kayitlar = urun_tutar.hepsi(db)
    adlar = dict(db.execute(select(Customer.id, Customer.name).where(Customer.id.in_(list(kayitlar)))).all()) if kayitlar else {}
    ustler = dict(db.execute(select(Customer.id, Customer.parent_id).where(Customer.id.in_(list(kayitlar)))).all()) if kayitlar else {}
    liste = [
        {"id": cid, "ad": adlar.get(cid, ""), "cati": ustler.get(cid) is None, "dosya": k["dosya"], "yukleyen": k["yukleyen"], "zaman": k["zaman"], **k["ozet"]}
        for cid, k in kayitlar.items()
    ]
    return sorted(liste, key=lambda x: x["zaman"] or "", reverse=True)
