"""Final skor servisi: kayit, yetki kurali, gecmis, onay talebi. Hesap kurali app/skor.py'dedir.

Uretim karsiliklari: kutucuklar/utilizasyon/toplu_atama.py ve blueprints/projects_bp.py
(save_customer_score, skor_toplu_*, *_score_approval*, puanlama_personeli, istirak_final_dahil).
Dogrulanmadi: metrik kaynaklari (Onedesk, Urun-Tutar, Onent, rapor sayisi) henuz bagli degil;
bu yuzden yalniz musteri karti segmenti metrik uretir, digerleri 'eksik' kalir.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AffiliateFinalFlag,
    AppUser,
    Customer,
    ScoreApprovalRequest,
    ScoreDetail,
    ScoreHistory,
    ScoringExclusion,
    UtilCriteriaSet,
)
from app.ortak import UygulamaHatasi
from app.session import Principal
from app.skor import motor as skor

SCOPES = ("parent", "affiliate")
KAYNAKLAR = ("sayfa", "toplu", "kriter_degisikligi")
IZINLI_ALANLAR = ("title", "type", "weight", "b30", "b50", "b70", "b100", "servis_puanlari", "servis_dahil")
EN_FAZLA_KRITER = 50
EN_FAZLA_TOPLU = 5000


class SkorHata(UygulamaHatasi):
    """kod = HTTP durumu."""


def simdi() -> datetime:
    return datetime.now(UTC)


def final_skor_yetkisi(user: Principal) -> bool:
    """Uretim eylem_yetkisi('final_skor_atama'): yalniz admin ve TeamMngr."""
    return bool(user.is_admin or user.role in {"admin", "TeamMngr"})


def kullanici_kaydi(db: Session, user: Principal) -> AppUser:
    """Oturumdaki kisinin app_user satiri; yoksa olusturur (yerel/dev oturumu icin)."""
    satir = db.scalar(select(AppUser).where(AppUser.username == user.username))
    if satir is None:
        satir = AppUser(username=user.username, display_name=user.username, role=user.role, is_admin=user.is_admin)
        db.add(satir)
        db.flush()
    return satir


# --- kriterler -------------------------------------------------------------------------------
def _kapsam(scope: str) -> str:
    if scope not in SCOPES:
        raise SkorHata(404, "Kriter kapsami bulunamadi.")
    return scope


def kriterler_oku(db: Session, scope: str) -> tuple[int, list[dict]]:
    satir = db.scalar(select(UtilCriteriaSet).where(UtilCriteriaSet.scope == _kapsam(scope)).order_by(UtilCriteriaSet.version.desc()))
    return (satir.version, list(satir.criteria)) if satir else (0, [])


def _kriter_temizle(ham: object) -> list[dict]:
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
        for alan in ("b30", "b50", "b70", "b100"):
            if alan in kayit:
                kayit[alan] = str(kayit[alan] or "")[:120]
        temiz.append(kayit)
    return skor.turleri_duzelt(temiz)


def kriterler_kaydet(db: Session, scope: str, ham: object, actor: str) -> dict:
    """Yeni surum yazar. Cati kriteri degisince tum cati musteriler yeniden hesaplanir."""
    kapsam = _kapsam(scope)
    satirlar = _kriter_temizle(ham)
    surum = (db.scalar(select(func.max(UtilCriteriaSet.version)).where(UtilCriteriaSet.scope == kapsam)) or 0) + 1
    db.add(UtilCriteriaSet(scope=kapsam, version=surum, criteria=satirlar, updated_by=actor[:120], updated_at=simdi()))
    db.flush()
    sonuc: dict = {"version": surum, "criteria": satirlar, "uygulama": None}
    if kapsam == "parent":
        sonuc["uygulama"] = uygula(db, cati_musteriler(db), "kriter_degisikligi", actor, yalniz_degisen=True, kriterler=satirlar)
    return sonuc


# --- hesap ----------------------------------------------------------------------------------
def cati_musteriler(db: Session, tam_id: int | None = None) -> list[Customer]:
    sorgu = select(Customer).where(Customer.parent_id.is_(None)).order_by(Customer.id)
    if tam_id is not None:
        sorgu = sorgu.where(Customer.owner_id == tam_id)
    return list(db.scalars(sorgu))


def metrikler(musteri: Customer) -> dict:
    """Metrik saglayici. Simdilik yalniz musteri karti segmenti (digerleri kaynaklar baglaninca)."""
    sonuc: dict = {}
    if musteri.segment:
        sonuc["segment"] = {"deger": musteri.segment, "kaynak": "musteri karti"}
    return sonuc


def hesapla(db: Session, liste: list[Customer], kriterler: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    """Hicbir sey yazmaz. -> (kriterler, [{id, ad, skor, mevcut, tamam, eksik}])."""
    if kriterler is None:
        kriterler = kriterler_oku(db, "parent")[1]
    detaylar = {d.customer_id: d.detail for d in db.scalars(select(ScoreDetail).where(ScoreDetail.customer_id.in_([c.id for c in liste])))} if liste else {}
    sonuc = []
    for musteri in liste:
        r = skor.musteri_skoru(kriterler, metrikler(musteri), skor.manuel_secimler(detaylar.get(musteri.id)))
        sonuc.append(
            {
                "id": musteri.id,
                "ad": musteri.name,
                "skor": r["skor"],
                "mevcut": musteri.score,
                "tamam": r["tamam"],
                "eksik": r["eksik"],
                "detay": [
                    {"baslik": k["baslik"], "tur": k["tur"], "agirlik": k["agirlik"], "puan": k["puan"]} for k in r["kriterler"]
                ],
            }
        )
    return kriterler, sonuc


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
    sonuc = []
    for satir in (ham if isinstance(ham, list) else [])[:EN_FAZLA_KRITER]:
        if not isinstance(satir, dict):
            continue
        try:
            puan = int(float(satir.get("puan") or 0))
            agirlik = float(satir.get("agirlik") or 0)
        except (TypeError, ValueError):
            continue
        if puan not in (0, 30, 50, 70, 100) or not math.isfinite(agirlik):
            continue
        sonuc.append(
            {"baslik": str(satir.get("baslik") or "")[:200], "tur": str(satir.get("tur") or "manual")[:40], "puan": puan, "agirlik": agirlik}
        )
    return sonuc


def skoru_yaz(db: Session, musteri: Customer, deger: float, detay: list[dict], kaynak: str, actor: str) -> None:
    if kaynak not in KAYNAKLAR:
        raise SkorHata(400, "Gecersiz kaynak.")
    zaman = simdi()
    musteri.score = deger
    satir = db.get(ScoreDetail, musteri.id)
    if satir is None:
        db.add(ScoreDetail(customer_id=musteri.id, score=deger, detail=detay, updated_at=zaman))
    else:
        satir.score, satir.detail, satir.updated_at = deger, detay, zaman
    db.add(ScoreHistory(customer_id=musteri.id, score=deger, source=kaynak, actor=actor[:120], at=zaman, detail=detay))
    db.flush()


def uygula(db: Session, liste: list[Customer], kaynak: str, actor: str, yalniz_degisen: bool = False, kriterler: list[dict] | None = None) -> dict:
    """Sunucuda yeniden hesaplanan skoru yazar. Eksik kriteri olan musteri atlanir."""
    kriterler, sonuc = hesapla(db, liste, kriterler)
    kisiler = {c.id: c for c in liste}
    uygulanan, atlanan = [], []
    for s in sonuc:
        if not s["tamam"]:
            atlanan.append({"id": s["id"], "ad": s["ad"], "neden": "eksik kriter: " + ", ".join(s["eksik"] or ["kriter yok"])})
            continue
        if yalniz_degisen and s["mevcut"] is not None and abs(float(s["mevcut"]) - s["skor"]) < 0.05:
            continue
        skoru_yaz(db, kisiler[s["id"]], s["skor"], [{"baslik": d["baslik"], "tur": d["tur"], "puan": d["puan"], "agirlik": d["agirlik"]} for d in s["detay"]], kaynak, actor)
        uygulanan.append({"id": s["id"], "ad": s["ad"], "skor": s["skor"]})
    return {"uygulanan": uygulanan, "atlanan": atlanan}


def toplu_uygula(db: Session, istenen: object, actor: str) -> dict:
    if not isinstance(istenen, list) or not istenen or len(istenen) > EN_FAZLA_TOPLU:
        raise SkorHata(400, "Musteri listesi gecersiz.")
    try:
        kimlikler = {int(x) for x in istenen if not isinstance(x, bool)}
    except (TypeError, ValueError) as exc:
        raise SkorHata(400, "Musteri listesi gecersiz.") from exc
    liste = [c for c in cati_musteriler(db) if c.id in kimlikler]
    sonuc = uygula(db, liste, "toplu", actor)
    bulunamayan = kimlikler - {c.id for c in liste}
    sonuc["atlanan"] += [{"id": i, "ad": "", "neden": "bulunamadi ya da cati musteri degil"} for i in sorted(bulunamayan)]
    return sonuc


def musteri_skoru_ata(db: Session, musteri_id: int, tam_id: int, deger: object, detay: object, actor: str) -> None:
    musteri = db.get(Customer, musteri_id)
    if musteri is None:
        raise SkorHata(404, "Musteri bulunamadi.")
    if musteri.owner_id != tam_id:
        raise SkorHata(400, "Musteri ve personel eslesmiyor.")
    if musteri.parent_id is not None:
        raise SkorHata(400, "Istirak musteriler icin ayri final skor atanamaz - skor cati musteri uzerinden atanir.")
    skoru_yaz(db, musteri, _gecerli_skor(deger), _detay_oku(detay), "sayfa", actor)


# --- onay talebi ----------------------------------------------------------------------------
def talep_olustur(db: Session, musteri_id: int, user: Principal) -> int:
    musteri = db.get(Customer, musteri_id)
    if musteri is None:
        raise SkorHata(404, "Musteri bulunamadi.")
    if musteri.parent_id is not None:
        raise SkorHata(400, "Istirak musteriler icin ayri final skor talebi olusturulamaz - talep cati musteri uzerinden yapilmali.")
    kisi = kullanici_kaydi(db, user)
    if musteri.owner_id != kisi.id and not final_skor_yetkisi(user):
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
    )
    return [
        {
            "id": t.id,
            "customer_id": c.id,
            "customer_name": c.name,
            "tam_id": c.owner_id,
            "requested_by_name": u.display_name or u.username,
            "requested_at": t.requested_at.isoformat() if t.requested_at else "",
        }
        for t, c, u in satirlar
    ]


def talep_karar(db: Session, talep_id: int, eylem: str, user: Principal) -> None:
    if eylem not in ("approve", "reject"):
        raise SkorHata(400, "Gecersiz islem.")
    talep = db.get(ScoreApprovalRequest, talep_id)
    if talep is None or talep.status != "pending":
        raise SkorHata(404, "Talep bulunamadi ya da zaten sonuclandirilmis.")
    talep.status = "approved" if eylem == "approve" else "rejected"
    talep.resolved_by = kullanici_kaydi(db, user).id
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
