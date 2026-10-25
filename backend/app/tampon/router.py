"""Tampon (Veri Girisi) HTTP katmani (/api/v1/tampon). Hepsi yalniz admin; yazanlar CSRF'li. Is kurali paketin modullerindedir."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import ariza
from app.audit import audit_log
from app.config import get_settings
from app.db import get_db, oturum
from app.deps import require_admin
from app.dil import m
from app.models import IngestBatch
from app.ortak import KimlikTipi, UygulamaHatasi, govde_oku, iso, ok, sayfa_bilgisi
from app.session import Principal
from app.tampon import (
    akislar,
    analiz,
    dagitim,
    depo,
    eslesme,
    fark,
    katalog,
    kaynak,
    musteri_aktar,
    musteri_ham,
    oracle,
    postgres,
    temip_atama,
)

router = APIRouter(
    prefix="/api/v1/tampon", tags=["tampon"], dependencies=[Depends(require_admin)]
)  # Yonetim alani: yeni uc eklense de admin disi giremez


def _denetim(admin: Principal, islem: str, detay: str = "") -> None:
    audit_log.remember(actor=admin.username, action=islem, outcome="allow", module_key="tampon", detail=detay)


def _parti_satiri(p: IngestBatch) -> dict[str, Any]:
    return {
        "id": p.id,
        "kaynak": p.source_key,
        "etiket": p.label,
        "durum": p.status,
        "satir": p.row_count,
        "sutun_sayisi": len(p.columns or []),
        "hata": p.error,
        "olusturan": p.created_by,
        "zaman": iso(p.received_at),
        "bitis": iso(p.finished_at),
    }


def _parti(db: Session, parti_id: int) -> IngestBatch:
    parti = db.get(IngestBatch, parti_id)
    if parti is None:
        raise HTTPException(status_code=404, detail="Parti yok.")
    return parti


class OnizleGovde(BaseModel):
    parti_id: KimlikTipi


class UygulaGovde(BaseModel):
    parti_id: KimlikTipi
    onay: bool = False


class HamOnizleGovde(BaseModel):
    parti_id: KimlikTipi
    yeni_olustur: bool = False


class HamUygulaGovde(BaseModel):
    parti_id: KimlikTipi
    yeni_olustur: bool = False
    plan_ozeti: str = Field(default="", max_length=64)
    onay: bool = False


class EtkinGovde(BaseModel):
    etkin: bool


class KuralGovde(BaseModel):
    """Alanlar dagitim.dogrula'da denetlenir; burada yalniz boyut/tur sinirlanir."""

    name: str = Field(default="", max_length=120)
    source_key: str = Field(default="", max_length=40)
    match_field: str = Field(default="customer_no", max_length=20)
    key_column: str = Field(default="", max_length=160)
    target: str = Field(default="", max_length=60)
    operation: str = Field(default="", max_length=20)
    value_column: str = Field(default="", max_length=160)
    conditions: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    zero_unmatched: bool = False
    max_age_minutes: int | None = None


# --- Kaynaklar ve katalog -------------------------------------------------------------------------------------------
@router.get("/kaynaklar")
def kaynaklar(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(kaynak.durumlar(db))


@router.post("/kaynaklar/{anahtar}/test")
def kaynak_testi(anahtar: str, admin: Principal = Depends(require_admin)) -> dict[str, Any]:
    """Oracle baglanti testi (SELECT 1 FROM DUAL) AYRI surecte; yanit adres/parola tasimaz. Panel kimligi Oracle giris tetikleyicisinden
    gecmeyebilir: o durumda hata doner, zamanlanmis gorev (izinli kimlik) yine calisir."""
    sonuc = oracle.baglanti_testi(anahtar[:40])
    _denetim(admin, "tampon.kaynak_testi", f"kaynak={anahtar[:40]} ok={sonuc['ok']}")
    return ok(sonuc)


@router.get("/hedefler")
def hedefler(admin: Principal = Depends(require_admin)) -> dict[str, Any]:
    return ok(dagitim.katalog())


@router.get("/akislar")
def veri_akislari(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Panele veri getiren tum yollar: son gelis, durum (taze / bayat / hata / yok), yonetildigi ekran."""
    return ok(akislar.akislar(db))


@router.get("/eslesme")
def musteri_eslesmesi(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Panele gelen verinin kart / TAM eslesmesi (kaynak bazinda) ve en cok kayit tasiyan kartsiz musteri numaralari."""
    return ok(eslesme.ozet(db))


class FarkTopluGovde(BaseModel):
    musteri_nolar: list[str] = Field(min_length=1, max_length=fark.TOPLU_AZAMI)
    tam_id: KimlikTipi


class FarkRadarGovde(BaseModel):
    musteri_nolar: list[str] = Field(min_length=1, max_length=fark.TOPLU_AZAMI)


class FarkSahipGovde(BaseModel):
    kart_id: KimlikTipi
    tam_id: KimlikTipi


@router.get("/fark")
def fark_listesi(
    tur: str = Query(default="", max_length=20),
    q: str = Query(default="", max_length=100),
    sayfa: int = Query(default=1, ge=1, le=100_000),
    sirala: str = Query(default="", max_length=20),
    yon: str = Query(default="", max_length=10),
    admin: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Canli DB kayitlarinin kartla / TAM ile eslesmeyen musteri numaralari (kartsiz, belirsiz, personelsiz kart); silinenler haric."""
    if not akislar.temip_semasi_hazir(db):
        return ok({"hazir": False, "neden": "0013_onedesk_temip uygulanmadı."})
    return ok({"hazir": True, **fark.liste(db, tur, q, sayfa, sirala, yon)})


@router.post("/fark/toplu-ata")
def fark_toplu_ata(govde: FarkTopluGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Secilen kartsiz numaralari personele ata: her numaraya TEMIP unvaniyla yeni kart, kayitlar tek seferde baglanir."""
    sonuc = fark.toplu_ata(db, admin, [n[:20] for n in govde.musteri_nolar], govde.tam_id)
    _denetim(admin, "tampon.fark_toplu_ata", f"tam={govde.tam_id} atanan={sonuc['atanan']} atlanan={len(sonuc['atlanan'])}")
    return ok(sonuc)


@router.post("/fark/radara-ata")
def fark_radara_ata(govde: FarkRadarGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Secilen kartsiz numaralari Musteri Radar'a gonder (kart acilmaz); Radar sayfasinda personele atanir."""
    sonuc = temip_atama.radara_gonder(db, [n[:20] for n in govde.musteri_nolar], admin.username)
    _denetim(admin, "tampon.fark_radara_ata", f"atanan={sonuc['atanan']} atlanan={len(sonuc['atlanan'])}")
    return ok(sonuc)


@router.post("/fark/radardan-cikar")
def fark_radardan_cikar(govde: FarkRadarGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Numaralari Musteri Radar'dan cikar (kartsizsa Fark'a doner)."""
    sonuc = temip_atama.radardan_cikar(db, [n[:20] for n in govde.musteri_nolar], admin.username)
    _denetim(admin, "tampon.fark_radardan_cikar", f"cikarilan={sonuc['cikarilan']}")
    return ok(sonuc)


@router.post("/fark/sil")
def fark_sil(govde: FarkRadarGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Secilen numaralari Fark'tan sil (gizle; TEMIP kayitlari kalir). Geri alinabilir."""
    sonuc = fark.sil(db, admin, [n[:20] for n in govde.musteri_nolar])
    _denetim(admin, "tampon.fark_sil", f"silinen={sonuc['silinen']} atlanan={len(sonuc['atlanan'])}")
    return ok(sonuc)


@router.post("/fark/sil/geri-al")
def fark_sil_geri_al(govde: FarkRadarGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    sonuc = fark.silineni_geri_al(db, admin, [n[:20] for n in govde.musteri_nolar])
    _denetim(admin, "tampon.fark_sil_geri_al", f"geri={sonuc['geri_alinan']}")
    return ok(sonuc)


@router.get("/fark/silinenler")
def fark_silinenler(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(fark.silinenler(db))


@router.post("/fark/kart-sahibi")
def fark_kart_sahibi(govde: FarkSahipGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Personelsiz karta TAM sec (kayitlar karta bagli ama hicbir portfoyde degil)."""
    sonuc = fark.kart_sahibi(db, admin, govde.kart_id, govde.tam_id)
    _denetim(admin, "tampon.fark_kart_sahibi", f"kart={govde.kart_id} tam={govde.tam_id}")
    return ok(sonuc)


# --- Ham katalog (ReportDB sema -> nesne -> alt nesne -> sutun agaci) -------------------------------------------------
@router.get("/katalog")
def katalog_agaci(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Son hazir katalogun agaci (sutunlar nesne acilinca), calisan tarama ve son hata."""
    return ok(katalog.agac(db))


@router.get("/katalog/nesne/{nesne_id}")
def katalog_nesnesi(nesne_id: KimlikTipi, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(katalog.nesne(db, nesne_id))


@router.get("/katalog/nesne/{nesne_id}/ornek")
def katalog_ornegi(
    nesne_id: KimlikTipi,
    grup: str = Query(default="", max_length=60),
    admin: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """grup bos: genel ornek; grup = domain degeri: o domain'de arama metnini iceren ornek satirlar."""
    return ok(katalog.ornek(db, nesne_id, grup))


DOMAIN_SORGUSU = Query(default=[], max_length=10)  # tekrarlanan ?domain=ACCESS&domain=NOC%20DESTECH


@router.get("/katalog/veri")
def katalog_verisi(
    nesne: KimlikTipi,
    domain: list[str] = DOMAIN_SORGUSU,
    sayfa: int = Query(default=1, ge=1, le=100_000),
    adet: int = Query(default=100, ge=1, le=katalog.VERI_SAYFA_EN_COK),
    q: str = Query(default="", max_length=100),
    filtre: str = Query(default="", max_length=20_000),
    sirala: str = Query(default="", max_length=128),
    yon: str = Query(default="asc", pattern="^(asc|desc)$"),
    admin: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Ham tampon okuyucu: secili domainlerin arama metnini iceren satirlari; filtre = {sutun: [degerler]} (JSON), q = tum sutunlarda."""
    return ok(katalog.veri(db, nesne, [d[:60] for d in domain], sayfa, adet, q, filtre, sirala, yon))


@router.get("/katalog/veri/degerler")
def katalog_degerleri(
    nesne: KimlikTipi,
    sutun: str = Query(max_length=128),
    domain: list[str] = DOMAIN_SORGUSU,
    q: str = Query(default="", max_length=100),
    filtre: str = Query(default="", max_length=20_000),
    ara: str = Query(default="", max_length=100),
    admin: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Excel filtresi acilir listesi: sutunun farkli degerleri (adetli), diger filtreler uygulanmis."""
    return ok(katalog.degerler(db, nesne, [d[:60] for d in domain], sutun, q, filtre, ara))


@router.post("/katalog/yenile")
def katalog_yenile(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Isciyi ayri surecte baslatir (panel Oracle'a baglanmaz); tarama ~15 sn, bitince katalog 'ready' olur."""
    sonuc = katalog.yenile(db, admin.username)
    _denetim(admin, "tampon.katalog_yenile", f"basladi={sonuc['basladi']}")
    return ok(sonuc)


# --- PostgreSQL kaynaklari (ONENTDB / ONEDESKDB, 2026-10-19): durum, katalog agaci, nesne, yenile ------------------------------
def _pg_kaynagi(kaynak: str) -> str:
    if kaynak not in postgres.KAYNAKLAR:
        raise HTTPException(status_code=404, detail="Bilinmeyen PostgreSQL kaynağı.")
    return kaynak


@router.get("/pg")
def pg_kaynaklari(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Kaynak basina durum (yalniz anahtar adlari) ve son katalogun ozeti; adres / parola yok."""
    sonuc = []
    for k, t in postgres.KAYNAKLAR.items():
        a = postgres.agac(db, k)
        sonuc.append({"id": k, "label": t.label, "acma_anahtari": t.enabled_key, **postgres.durum(k), "katalog": a["katalog"], "son": a["son"], "calisiyor": a["calisiyor"]})
    return ok(sonuc)


@router.get("/pg/{kaynak}/katalog")
def pg_katalog(kaynak: str, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(postgres.agac(db, _pg_kaynagi(kaynak)))


@router.get("/pg/nesne/{nesne_id}")
def pg_nesne(nesne_id: KimlikTipi, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(postgres.nesne(db, nesne_id))


@router.post("/pg/{kaynak}/katalog/yenile")
def pg_katalog_yenile(kaynak: str, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Isciyi ayri surecte baslatir (panel PostgreSQL'e baglanmaz)."""
    sonuc = postgres.yenile(db, _pg_kaynagi(kaynak), admin.username)
    _denetim(admin, "tampon.pg_katalog_yenile", f"kaynak={kaynak} basladi={sonuc['basladi']}")
    return ok(sonuc)


TEMIP_DURUMLARI = ("kart", "kart_personelsiz", "radar", "belirsiz")
TEMIP_SAYFA = 50


class TemipAtamaGovde(BaseModel):
    """kart_id: personelin mevcut kartina ekle (isim karisikligi); tam_id: personele yeni kart ac (unvan bos ise TEMIP unvani)."""

    musteri_no: str = Field(max_length=20)
    kart_id: int | None = Field(default=None, ge=1, le=2_147_483_647)
    tam_id: int | None = Field(default=None, ge=1, le=2_147_483_647)
    unvan: str = Field(default="", max_length=150)


class TemipKaldirGovde(BaseModel):
    musteri_no: str = Field(max_length=20)


@router.get("/temip/kartlar")
def temip_kart_ara(
    q: str = Query(default="", max_length=100),
    tam: int | None = Query(default=None, ge=1, le=2_147_483_647),
    admin: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Elle atama icin kart arama (unvan ya da numara); tam: yalniz o personelin kartlari."""
    return ok(temip_atama.kart_ara(db, q, tam))


@router.get("/temip/personel")
def temip_personel(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Atanabilir personel (Musteri Yonetimi personel listesi)."""
    return ok(temip_atama.personeller(db))


@router.get("/temip/atamalar")
def temip_atamalari(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(temip_atama.atamalar(db))


@router.post("/temip/ata")
def temip_ata(govde: TemipAtamaGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Eslesmeyen TEMIP Musteri No'sunu karta elle ata (CRM unvan hatasi): numara kartin Musteri No'suna eklenir, kayitlar baglanir."""
    if (govde.kart_id is None) == (govde.tam_id is None):
        raise HTTPException(status_code=400, detail="Mevcut kart (kart_id) ya da yeni kart için personel (tam_id) seçin.")
    if govde.kart_id is not None:
        sonuc = temip_atama.ata(db, govde.musteri_no, govde.kart_id, admin.username)
    else:
        sonuc = temip_atama.personele_ata(db, admin, govde.musteri_no, govde.tam_id or 0, govde.unvan)
    _denetim(admin, "tampon.temip_ata", f"musteri_no={sonuc['musteri_no']} kart={sonuc['kart_id']} yeni={sonuc['yeni_kart']} kayit={sonuc['kayit']}")
    return ok(sonuc)


@router.post("/temip/ata/kaldir")
def temip_ata_kaldir(govde: TemipKaldirGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    sonuc = temip_atama.kaldir(db, govde.musteri_no, admin.username)
    _denetim(admin, "tampon.temip_ata_kaldir", f"musteri_no={sonuc['musteri_no']} kart={sonuc['kart_id']}")
    return ok(sonuc)


@router.get("/temip/eslesme")
def temip_eslesme(
    durum: str = Query(default="", max_length=20),
    q: str = Query(default="", max_length=100),
    sayfa: int = Query(default=1, ge=1, le=100_000),
    admin: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """TEMIP kayitlari: Musteri No -> kart -> sorumlu personel -> acik kayit (Oracle'siz; isci `temip-eslesme` ile ayni rapor)."""
    if not akislar.temip_semasi_hazir(db):
        return ok({"hazir": False, "neden": "0013_onedesk_temip uygulanmadı."})
    from app.tampon import temip_kayit  # gec import: oracle zinciri yalniz bu uc acilinca yuklenir

    r = temip_kayit.eslesme_raporu(db)
    musteriler = r["musteriler"]
    if durum in TEMIP_DURUMLARI:
        musteriler = [x for x in musteriler if x["durum"] == durum]
    if q.strip():
        aranan = q.strip().casefold()
        musteriler = [
            x
            for x in musteriler
            if aranan in x["musteri_no"] or aranan in f"{x['temip_unvan']} {x['panel_unvan']} {x['personel']}".casefold()
        ]
    sayfa, atla, adet = sayfa_bilgisi(sayfa, TEMIP_SAYFA, len(musteriler))
    return ok(
        {
            "hazir": True,
            "ozet": r["ozet"],
            "personel": r["personel"],
            "uyari": r["uyari"],
            "bagli_olmayan": r["bagli_olmayan"],
            "toplam": len(musteriler),
            "sayfa": sayfa,
            "adet": adet,
            "musteriler": musteriler[atla : atla + adet],
        }
    )


# --- 1. Tampon: parti yukleme ve okuma ------------------------------------------------------------------------------
def _yukle(veri: bytes, kaynak_adi: str, dosya: str, kullanici: str) -> dict[str, Any]:
    """Kendi oturumunda calisir (threadpool): her blok kisa islemle yazilir."""
    with oturum() as db:
        basliklar, satirlar = kaynak.csv_oku(veri)
        parti = depo.parti_olustur(
            db, kaynak.kaynak_anahtari(kaynak_adi or re.sub(r"\.[A-Za-z0-9]+$", "", dosya)), dosya or "yukleme.csv", kullanici
        )
        db.commit()
        try:
            parti = depo.ice_al(db, parti, basliklar, satirlar)
        except UygulamaHatasi:
            raise
        except Exception as hata:
            kayit = ariza.kaydet("TL-TAM-01", exc=hata, kaynak="tampon.yukle", kullanici=kullanici)
            raise UygulamaHatasi(500, ariza.mesaj("TL-TAM-01", kayit)) from hata
        return _parti_satiri(parti)


# --- Ham Musteri Verisi (Kaynaklar'daki dosya yuklemesi) -------------------------------------------------------------
def _ham_yukle(veri: bytes, dosya: str, kullanici: str) -> dict[str, Any]:
    tablo = musteri_ham.dosya_oku(veri, dosya)
    with oturum() as db:
        etiket = (dosya or "musteri.xlsx") + (f" · {tablo['sayfa']}" if tablo["sayfa"] else "")
        parti = depo.parti_olustur(db, musteri_ham.KAYNAK, etiket, kullanici)
        db.commit()
        try:
            parti = depo.ice_al(db, parti, tablo["basliklar"], tablo["satirlar"])
        except UygulamaHatasi:
            raise
        except Exception as hata:
            kayit = ariza.kaydet("TL-TAM-01", exc=hata, kaynak="tampon.musteri_ham", kullanici=kullanici)
            raise UygulamaHatasi(500, ariza.mesaj("TL-TAM-01", kayit)) from hata
        return {**_parti_satiri(parti), "uyum": musteri_ham.uyum_raporu(tablo["basliklar"])}


@router.put("/musteri-ham/yukle")
async def ham_yukle(
    request: Request, dosya: str = Query(default="", max_length=200), admin: Principal = Depends(require_admin)
) -> dict[str, Any]:
    """Ham Musteri Verisi (.xlsx / .csv): sayfa ve baslik satiri kendiliginden bulunur, parti olarak tampona alinir."""
    sonuc = await run_in_threadpool(_ham_yukle, await govde_oku(request, get_settings().ingest_max_mb * 1048576), dosya, admin.username)
    _denetim(admin, "tampon.musteri_ham_yukle", f"parti={sonuc['id']} satir={sonuc['satir']} durum={sonuc['durum']}")
    return ok(sonuc)


@router.get("/musteri-ham/sablon.xlsx")
def ham_sablon(dolu: bool = False, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> Response:
    """Bos sablon ya da paneldeki kartlarin GERCEK degerleriyle dolu sablon."""
    ad = musteri_ham.DOSYA_ADI.replace(".xlsx", "_dolu.xlsx") if dolu else musteri_ham.DOSYA_ADI
    return Response(
        musteri_ham.sablon_olustur(db, dolu),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{ad}"'},
    )


@router.get("/musteri-ham/partiler/{parti_id}/uyum")
def ham_uyum(parti_id: KimlikTipi, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(musteri_ham.uyum_raporu(list(_parti(db, parti_id).columns or [])))


@router.post("/musteri-ham/onizle")
def ham_onizle(govde: HamOnizleGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(musteri_aktar.onizleme(db, govde.parti_id, govde.yeni_olustur))


@router.post("/musteri-ham/uygula")
def ham_uygula(govde: HamUygulaGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    if not govde.onay:
        raise HTTPException(status_code=400, detail=m("Uygulamak için onay gerekir.", "Confirmation is required to apply."))
    sonuc = musteri_aktar.uygula(db, govde.parti_id, govde.yeni_olustur, govde.plan_ozeti, admin.username)
    db.commit()
    o = sonuc["ozet"]
    _denetim(
        admin,
        "tampon.musteri_ham_uygula",
        f"parti={govde.parti_id} kayit={sonuc['kayit_id']} guncellenen={o['guncellenen']} olusturulan={o['olusturulan']}",
    )
    return ok(sonuc)


@router.get("/musteri-ham/aktarimlar")
def ham_aktarimlar(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(musteri_aktar.kayitlar(db))


@router.post("/musteri-ham/aktarimlar/{kayit_id}/geri-al")
def ham_geri_al(kayit_id: KimlikTipi, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    sonuc = musteri_aktar.geri_al(db, kayit_id, admin.username)
    db.commit()
    _denetim(admin, "tampon.musteri_ham_geri_al", f"kayit={kayit_id} geri={sonuc['geri_alinan_alan']} silinen={sonuc['silinen_musteri']}")
    return ok(sonuc)


@router.put("/yukle")
async def yukle(
    request: Request,
    kaynak_adi: str = Query(default="", alias="kaynak", max_length=60),
    dosya: str = Query(default="", max_length=200),
    admin: Principal = Depends(require_admin),
) -> dict[str, Any]:
    """Genel CSV yuklemesi (API; arayuzde yerini Ham Musteri Verisi aldi). Cok parcali form yok: yeni bagimlilik gerektirmez."""
    sonuc = await run_in_threadpool(
        _yukle, await govde_oku(request, get_settings().ingest_max_mb * 1048576), kaynak_adi, dosya, admin.username
    )
    _denetim(admin, "tampon.yukle", f"parti={sonuc['id']} kaynak={sonuc['kaynak']} satir={sonuc['satir']} durum={sonuc['durum']}")
    return ok(sonuc)


@router.get("/partiler")
def partiler(
    kaynak_adi: str = Query(default="", alias="kaynak", max_length=40),
    durum: str = Query(default="", max_length=20),
    sayfa: int = Query(default=1, ge=1),
    adet: int = Query(default=20, ge=1, le=100),
    admin: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sorgu = select(IngestBatch)
    if kaynak_adi:
        sorgu = sorgu.where(IngestBatch.source_key == kaynak_adi)
    if durum in depo.DURUMLAR:
        sorgu = sorgu.where(IngestBatch.status == durum)
    toplam = db.scalar(select(func.count()).select_from(sorgu.subquery())) or 0
    sayfa, atla, adet = sayfa_bilgisi(sayfa, adet, toplam)
    satirlar = db.scalars(sorgu.order_by(IngestBatch.id.desc()).offset(atla).limit(adet)).all()
    return ok({"toplam": toplam, "sayfa": sayfa, "adet": adet, "satirlar": [_parti_satiri(p) for p in satirlar]})


@router.get("/partiler/{parti_id}")
def parti_ayrintisi(parti_id: KimlikTipi, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    parti = _parti(db, parti_id)
    profil = parti.profile or {}
    return ok(
        {
            **_parti_satiri(parti),
            "sutunlar": list(parti.columns or []),
            "profil": profil.get("sutunlar", []),
            "analiz": profil.get("analiz"),
            "kullanimda": depo.kullanimda_mi(db, parti_id),
        }
    )


@router.get("/partiler/{parti_id}/satirlar")
def parti_satirlari(
    parti_id: KimlikTipi,
    sayfa: int = Query(default=1, ge=1),
    adet: int = Query(default=25, ge=1, le=100),
    admin: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    parti = _parti(db, parti_id)
    sayfa, _, adet = sayfa_bilgisi(sayfa, adet, parti.row_count)
    return ok(
        {
            "basliklar": list(parti.columns or []),
            "satirlar": depo.sayfa_oku(db, parti_id, sayfa, adet),
            "toplam": parti.row_count,
            "sayfa": sayfa,
            "adet": adet,
        }
    )


# --- 2. Analiz ------------------------------------------------------------------------------------------------------
@router.post("/partiler/{parti_id}/analiz")
def parti_analizi(parti_id: KimlikTipi, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    parti = _parti(db, parti_id)
    if parti.status not in ("ready", "rejected"):
        raise HTTPException(status_code=409, detail="Parti analiz için hazır değil.")
    sonuc = analiz.analiz_et(db, parti)
    db.commit()
    return ok(sonuc)


@router.post("/partiler/{parti_id}/kabul")
def parti_kabul(parti_id: KimlikTipi, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    parti = depo.kabul_et(db, parti_id)
    db.commit()
    _denetim(admin, "tampon.kabul", f"parti={parti_id}")
    return ok(_parti_satiri(parti))


@router.delete("/partiler/{parti_id}")
def parti_sil(parti_id: KimlikTipi, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    depo.sil(db, parti_id)
    db.commit()
    _denetim(admin, "tampon.sil", f"parti={parti_id}")
    return ok({"id": parti_id})


# --- 3. Dagitim kurallari -------------------------------------------------------------------------------------------
@router.get("/kurallar")
def kural_listesi(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(dagitim.kurallar(db))


@router.post("/kurallar")
def kural_olustur(govde: KuralGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    kural = dagitim.kural_olustur(db, govde.model_dump(), admin.username)
    db.commit()
    _denetim(admin, "tampon.kural_olustur", f"kural={kural.id} hedef={kural.target}")
    return ok(dagitim.kural_satiri(kural))


@router.put("/kurallar/{kural_id}")
def kural_guncelle(
    kural_id: KimlikTipi, govde: KuralGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)
) -> dict[str, Any]:
    kural = dagitim.kural_guncelle(db, kural_id, govde.model_dump())
    db.commit()
    _denetim(admin, "tampon.kural_guncelle", f"kural={kural_id}")
    return ok(dagitim.kural_satiri(kural))


@router.post("/kurallar/{kural_id}/etkin")
def kural_etkin(
    kural_id: KimlikTipi, govde: EtkinGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)
) -> dict[str, Any]:
    kural = dagitim.kural_getir(db, kural_id)
    kural.enabled = govde.etkin
    db.commit()
    _denetim(admin, "tampon.kural_etkin", f"kural={kural_id} etkin={govde.etkin}")
    return ok(dagitim.kural_satiri(kural))


@router.delete("/kurallar/{kural_id}")
def kural_sil(kural_id: KimlikTipi, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    dagitim.kural_sil(db, kural_id)
    db.commit()
    _denetim(admin, "tampon.kural_sil", f"kural={kural_id}")
    return ok({"id": kural_id})


@router.post("/kurallar/{kural_id}/onizle")
def kural_onizle(
    kural_id: KimlikTipi, govde: OnizleGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)
) -> dict[str, Any]:
    return ok(dagitim.onizle(db, kural_id, govde.parti_id))


@router.post("/kurallar/{kural_id}/uygula")
def kural_uygula(
    kural_id: KimlikTipi, govde: UygulaGovde, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)
) -> dict[str, Any]:
    if not govde.onay:
        raise HTTPException(status_code=400, detail="Uygulamak için onay gerekir.")
    sonuc = dagitim.uygula(db, kural_id, govde.parti_id, admin.username)
    db.commit()
    _denetim(admin, "tampon.uygula", f"kural={kural_id} parti={govde.parti_id} yazilan={sonuc['yazilan']} run={sonuc['run_id'][:8]}")
    return ok(sonuc)


@router.get("/uygulamalar")
def uygulama_listesi(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ok(dagitim.uygulamalar(db))


@router.post("/uygulamalar/{run_id}/geri-al")
def uygulama_geri_al(run_id: str, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise HTTPException(status_code=400, detail="Geçersiz uygulama kimliği.")
    sonuc = dagitim.geri_al(db, run_id, admin.username)
    db.commit()
    _denetim(admin, "tampon.geri_al", f"run={run_id[:8]} geri={sonuc['geri_alinan']} korunan={sonuc['korunan']}")
    return ok(sonuc)
