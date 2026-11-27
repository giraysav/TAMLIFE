# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""PostgreSQL dis kaynaklari (2026-10-19 kullanici: "ONENTDB merkelodm / ONENT, ONEDESKDB carbonat / elysion; postgre bu ortamlar").

Ayarlar backend/.env: <ON EK>_ENABLED (yalniz 'true' acar), _HOST, _PORT (5432), _DBNAME, _USER, _PASSWORD, _SSLMODE (prefer), _TIMEOUT (10 sn).
On ekler: ONENTDB_PG, ONEDESKDB_PG. Degerler yalniz baglanirken kullanilir; ekrana parola ASLA, adres/kullanici yalniz admin kartinda.
Oturum salt okunur (default_transaction_read_only + read_only) ve zaman asimli (statement_timeout); yalniz SELECT.
Katalog (kullanici karari: "baglanti + katalog"): sema -> tablo/gorunum -> sutunlar + ornek satirlar. Tarama ISCI surecinde
(python -m app.isci pg-katalog --kaynak <id>), panel taramayi ayri surecte baslatir (katalog._ayri_baslat). Kisisel veri gibi duran
sutunlarin (telefon, e-posta, adres, kimlik no, parola, token...) ornek degeri saklanmaz ("***").
Veri: isciler dogrudan ceker (OneDesk sikayet / talep kayitlari onedesk/canli, ONENT envanteri musteri/envanter, utilizasyon
skor/gunluk). Eski '<ON EK>_IMPORT_QUERY -> tampon partisi' yolu 2026-11-21 kaldirildi.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ortak import UygulamaHatasi, iso, simdi
from app.tampon.models import SourceCatalog, SourceCatalogObject
from app.tampon.oracle import ag_adimlari, deger, maskele

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PgTanim:
    id: str
    label: str
    on_ek: str

    @property
    def enabled_key(self) -> str:
        return f"{self.on_ek}_ENABLED"


KAYNAKLAR: dict[str, PgTanim] = {
    "pg_onent": PgTanim("pg_onent", "ONENTDB", "ONENTDB_PG"),
    "pg_onedesk": PgTanim("pg_onedesk", "ONEDESKDB", "ONEDESKDB_PG"),
}
SONEKLER = ("ENABLED", "HOST", "PORT", "DBNAME", "USER", "PASSWORD", "SSLMODE", "TIMEOUT")
ZORUNLU = ("HOST", "DBNAME", "USER", "PASSWORD")
SSL_KIPLERI = ("disable", "allow", "prefer", "require", "verify-ca", "verify-full")
DISLANAN_SEMALAR = ("pg_catalog", "information_schema")
ORNEK_ADET = 20
AZAMI_NESNE = 400  # ornek satir alinan en fazla nesne; fazlasinin yalniz yapisi
SORGU_SN = 15
SAKLANAN = 5
CALISIYOR_DK = 60
TURLER = {"r": "tablo", "p": "bolumlu tablo", "v": "görünüm", "m": "somut görünüm", "f": "yabancı tablo"}
_YETKISIZ = re.compile(r"permission denied|insufficient privilege", re.IGNORECASE)
KISISEL = re.compile(
    r"(parola|password|passwd|pwd|secret|token|hash|salt|tckn|tc_?kimlik|kimlik_?no|identity|phone|telefon|tel_?no|gsm|msisdn|mobile|cep|"
    r"e_?mail|eposta|e_?posta|adres|address|iban)",
    re.IGNORECASE,
)


class PgHata(UygulamaHatasi):
    """kod = HTTP durumu."""

    def __init__(self, mesaj: str, kod: int = 400) -> None:
        super().__init__(kod, mesaj)


def _tam_sayi(anahtar: str, varsayilan: int) -> int:
    try:
        return int(os.environ.get(anahtar, "").strip() or varsayilan)
    except ValueError:
        return varsayilan


class PgKaynak:
    def __init__(self, tanim: PgTanim) -> None:
        on = tanim.on_ek
        self.tanim = tanim
        self.ENABLED = os.environ.get(tanim.enabled_key, "").strip().lower() == "true"
        self.HOST = os.environ.get(f"{on}_HOST", "").strip()
        self.PORT = _tam_sayi(f"{on}_PORT", 5432)
        self.DBNAME = os.environ.get(f"{on}_DBNAME", "").strip()
        self.USER = os.environ.get(f"{on}_USER", "").strip()
        self.PASSWORD = os.environ.get(f"{on}_PASSWORD", "")
        ssl = os.environ.get(f"{on}_SSLMODE", "").strip().lower()
        self.SSLMODE = ssl if ssl in SSL_KIPLERI else "prefer"
        self.TIMEOUT = max(1, min(_tam_sayi(f"{on}_TIMEOUT", 10), 60))

    def eksikler(self) -> list[str]:
        return [f"{self.tanim.on_ek}_{ad}" for ad in ZORUNLU if not getattr(self, ad).strip()]

    def gizliler(self) -> tuple[str, ...]:
        return tuple(v for v in (self.PASSWORD, self.HOST, self.DBNAME, self.USER) if len(v) >= 3)

    def baglan(self, sorgu_sn: int = SORGU_SN) -> Any:
        """Salt okunur, otomatik onayli oturum (uzun islem acik kalmaz). Kapali / eksik ayarda PgHata."""
        if not self.ENABLED:
            raise PgHata(f"Kaynak kapalı ({self.tanim.enabled_key}=true değil).", 409)
        if eksik := self.eksikler():
            raise PgHata("Bağlantı ayarı eksik: " + ", ".join(eksik))
        import psycopg

        conn = psycopg.connect(
            host=self.HOST, port=self.PORT, dbname=self.DBNAME, user=self.USER, password=self.PASSWORD, sslmode=self.SSLMODE,
            connect_timeout=self.TIMEOUT, application_name="tamlife-panel",
            options=f"-c default_transaction_read_only=on -c statement_timeout={int(sorgu_sn) * 1000}", autocommit=True,
        )  # fmt: skip
        conn.read_only = True
        return conn


def ayar(anahtar: str) -> PgKaynak:
    if anahtar not in KAYNAKLAR:
        raise PgHata("Bu kaynak bir PostgreSQL kaynağı değil.", 404)
    return PgKaynak(KAYNAKLAR[anahtar])


def hata_metni(hata: BaseException, gizliler: tuple[str, ...]) -> str:
    ham = str(hata) or type(hata).__name__
    return maskele((ham.splitlines() or [type(hata).__name__])[0], gizliler)[:220]


def durum(anahtar: str) -> dict[str, Any]:
    a = ayar(anahtar)
    eksik = a.eksikler() if a.ENABLED else []
    return {"acik": a.ENABLED, "eksik": eksik, "hazir": a.ENABLED and not eksik, "state": "disabled" if not a.ENABLED else ("incomplete" if eksik else "ready")}  # fmt: skip


def bilgiler(anahtar: str) -> dict[str, Any]:
    """Kurum Baglantilari karti (yalniz admin): sunucu, port, veritabani, kullanici gorunur; parola yalniz tanimli mi."""
    a = ayar(anahtar)
    return {"sunucu": a.HOST, "port": a.PORT, "veritabani": a.DBNAME, "kullanici": a.USER, "parola": bool(a.PASSWORD), "ssl": a.SSLMODE,
            "zaman_asimi": a.TIMEOUT}  # fmt: skip


def erisim_adimlari(anahtar: str) -> list[dict[str, str]]:
    """Oracle testiyle ayni kalip: ayar -> DNS -> TCP -> oturum (SELECT 1, salt okunur); ilk kirilan halkada durur."""
    a = ayar(anahtar)
    adimlar: list[dict[str, str]] = []

    def ekle(adim: str, durum_: str, baslik: str, ayrinti: str = "") -> list[dict[str, str]]:
        adimlar.append({"adim": adim, "durum": durum_, "baslik": baslik, "ayrinti": ayrinti})
        return adimlar

    if not a.ENABLED:
        return ekle("ayar", "hata", f"{a.tanim.enabled_key}=true değil", "backend/.env içindeki satırı true yapıp paneli yeniden başlatın.")
    if eksik := a.eksikler():
        return ekle("ayar", "hata", "Bağlantı ayarı eksik", ", ".join(eksik))
    ekle("ayar", "ok", "Ayarlar tamam", f"port {a.PORT} · ssl {a.SSLMODE} · zaman aşımı {a.TIMEOUT} sn")
    if not ag_adimlari(ekle, a.HOST, a.PORT, a.TIMEOUT, "güvenlik duvarı izni gerekir"):
        return adimlar
    try:
        with a.baglan() as conn:
            surum = conn.execute("SELECT 1, current_setting('server_version')").fetchone()
        ekle("oturum", "ok", "PostgreSQL oturumu (SELECT 1, salt okunur)", f"PostgreSQL {surum[1]}")
    except Exception as e:  # noqa: BLE001 - surucu / kimlik / ag hatasi kisa mesajla
        ekle("oturum", "hata", "PostgreSQL oturumu (SELECT 1, salt okunur)", hata_metni(e, a.gizliler()))
    return adimlar


# --- katalog -----------------------------------------------------------------------------------------------------------
# 2026-10-26 kullanici: "PERMISSION DENIED veren sema, tablo, sutunlari ekrana getirme; ilk taramada engelle": katalogda yalniz hesabin
# KULLANABILDIGI sema (USAGE) ve OKUYABILDIGI nesne (SELECT). Gecici semalar (pg_temp_*) her taramada degisir, alinmaz.
_KAPSAM = """c.relkind IN ('r', 'p', 'v', 'm', 'f') AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%%' AND n.nspname NOT LIKE 'pg_temp%%' AND NOT c.relispartition"""
_OKUNUR = "has_schema_privilege(n.oid, 'USAGE') AND has_table_privilege(c.oid, 'SELECT')"
NESNE_SORGUSU = f"""
SELECT n.nspname, c.relname, c.relkind, c.reltuples::bigint, obj_description(c.oid, 'pg_class')
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE {_KAPSAM} AND {_OKUNUR}
ORDER BY n.nspname, c.relname
"""
SUTUN_SORGUSU = f"""
SELECT n.nspname, c.relname, a.attname, format_type(a.atttypid, a.atttypmod), NOT a.attnotnull, col_description(c.oid, a.attnum)
FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE a.attnum > 0 AND NOT a.attisdropped AND {_KAPSAM} AND {_OKUNUR}
ORDER BY n.nspname, c.relname, a.attnum
"""
YETKISIZ_SORGUSU = f"""
SELECT count(*) FILTER (WHERE NOT ({_OKUNUR})), count(DISTINCT n.nspname)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE {_KAPSAM}
"""


def _sikistir(veri: Any) -> bytes:
    return zlib.compress(json.dumps(veri, ensure_ascii=False, default=str).encode("utf-8"))


def _hucre(sutun: str, v: Any) -> Any:
    if v is None:
        return None
    if KISISEL.search(sutun):
        return "***"
    v = deger(v) if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False, default=str)
    return v[:200] if isinstance(v, str) else v


def _calisiyor(db: Session, kaynak: str) -> SourceCatalog | None:
    esik = simdi() - timedelta(minutes=CALISIYOR_DK)
    return db.scalars(
        select(SourceCatalog).where(SourceCatalog.source_key == kaynak, SourceCatalog.status == "receiving", SourceCatalog.started_at >= esik).limit(1)
    ).first()


def tara(db: Session, kaynak: str, kullanici: str, adet: int = ORNEK_ADET, baglanti: Callable[[], Any] | None = None) -> SourceCatalog:
    """Yapi (sema, nesne, sutun) + nesne basina en fazla `adet` ornek satir. Yalniz SELECT; hata 'failed' olarak yazilir."""
    a = ayar(kaynak)
    kat = SourceCatalog(source_key=kaynak, status="receiving", started_at=simdi(), created_by=kullanici[:120], summary={}, error="")
    db.add(kat)
    db.commit()
    try:
        with (baglanti or a.baglan)() as conn:
            nesneler = conn.execute(NESNE_SORGUSU).fetchall()
            yetkisiz_nesne, tum_sema = conn.execute(YETKISIZ_SORGUSU).fetchone()
            sutunlar: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for sema, tablo, ad, tip, bos, aciklama in conn.execute(SUTUN_SORGUSU).fetchall():
                sutunlar.setdefault((sema, tablo), []).append({"ad": ad, "tip": tip, "bos": bool(bos), "aciklama": (aciklama or "")[:300]})
            from psycopg import sql

            alinan: list[tuple[str, str]] = []
            for sema, tablo, tur, satir, aciklama in nesneler:
                kolonlar = sutunlar.get((sema, tablo), [])
                kayit = SourceCatalogObject(
                    catalog_id=kat.id, owner=sema[:128], name=tablo[:128], kind=TURLER.get(tur, tur), parent="", row_count=satir if satir and satir > 0 else None,
                    analyzed="", comment=(aciklama or "")[:1000], columns=kolonlar, details={}, sample_columns=[], sample_rows=0, sample_note="", sample_data=None,
                )  # fmt: skip
                if len(alinan) >= AZAMI_NESNE:
                    kayit.sample_note = f"Örnek alınmadı (ilk {AZAMI_NESNE} nesne örneklenir)."
                else:
                    try:
                        imlec = conn.execute(sql.SQL("SELECT * FROM {}.{} LIMIT {}").format(sql.Identifier(sema), sql.Identifier(tablo), sql.Literal(int(adet))))
                        adlar = [d.name for d in imlec.description or []]
                        satirlar = [[_hucre(s, v) for s, v in zip(adlar, r, strict=False)] for r in imlec.fetchall()]
                        kayit.sample_columns, kayit.sample_rows, kayit.sample_data = adlar, len(satirlar), _sikistir(satirlar)
                        if any(KISISEL.search(s) for s in adlar):
                            kayit.sample_note = "Kişisel veri gibi duran sütunların değeri gizlendi."
                    except Exception as e:  # noqa: BLE001 - zaman asimi vb.: nesne yapisiyla kalir; yetkisizse hic alinmaz
                        if _YETKISIZ.search(str(e)):
                            yetkisiz_nesne = int(yetkisiz_nesne or 0) + 1
                            continue
                        kayit.sample_note = f"Örnek okunamadı: {hata_metni(e, a.gizliler())}"[:300]
                alinan.append((sema, tablo))
                db.add(kayit)
        kat.status, kat.finished_at = "ready", simdi()
        semalar = sorted({s for s, _ in alinan})
        kat.summary = {"semalar": semalar, "nesne": len(alinan), "sutun": sum(len(sutunlar.get(k, [])) for k in alinan), "ornek_adet": adet,
                       "yetkisiz_nesne": int(yetkisiz_nesne or 0), "yetkisiz_sema": max(int(tum_sema or 0) - len(semalar), 0)}  # fmt: skip
        db.commit()
    except Exception as e:
        db.rollback()
        kat = db.get(SourceCatalog, kat.id) or kat
        kat.status, kat.finished_at, kat.error = "failed", simdi(), hata_metni(e, a.gizliler())
        db.commit()
        raise PgHata(f"Katalog taraması başarısız: {kat.error}", 502) from e
    _eskileri_sil(db, kaynak)
    return kat


def _eskileri_sil(db: Session, kaynak: str) -> None:
    eski = list(db.scalars(select(SourceCatalog.id).where(SourceCatalog.source_key == kaynak).order_by(SourceCatalog.id.desc()).offset(SAKLANAN)))
    if eski:
        db.execute(delete(SourceCatalogObject).where(SourceCatalogObject.catalog_id.in_(eski)))
        db.execute(delete(SourceCatalog).where(SourceCatalog.id.in_(eski)))
        db.commit()


def _katalog_ozeti(k: SourceCatalog | None) -> dict[str, Any] | None:
    if k is None:
        return None
    return {"id": k.id, "durum": k.status, "baslangic": iso(k.started_at), "bitis": iso(k.finished_at), "kim": k.created_by, "ozet": k.summary or {}, "hata": k.error}


def agac(db: Session, kaynak: str) -> dict[str, Any]:
    """Son hazir katalog: sema -> nesneler (tur, yaklasik satir, sutun sayisi). Son calisma (hata / suruyor) ayrica."""
    ayar(kaynak)
    son = db.scalars(select(SourceCatalog).where(SourceCatalog.source_key == kaynak).order_by(SourceCatalog.id.desc()).limit(1)).first()
    hazir = db.scalars(select(SourceCatalog).where(SourceCatalog.source_key == kaynak, SourceCatalog.status == "ready").order_by(SourceCatalog.id.desc()).limit(1)).first()
    semalar: dict[str, list[dict[str, Any]]] = {}
    if hazir is not None:
        for n in db.scalars(select(SourceCatalogObject).where(SourceCatalogObject.catalog_id == hazir.id).order_by(SourceCatalogObject.owner, SourceCatalogObject.name)):
            semalar.setdefault(n.owner, []).append({"id": n.id, "ad": n.name, "tur": n.kind, "satir": n.row_count, "sutun": len(n.columns or []), "aciklama": n.comment})
    return {
        "kaynak": kaynak,
        "son": _katalog_ozeti(son),
        "katalog": _katalog_ozeti(hazir),
        "calisiyor": _calisiyor(db, kaynak) is not None,
        "semalar": [{"ad": s, "nesneler": v} for s, v in semalar.items()],
    }


def nesne(db: Session, nesne_id: int) -> dict[str, Any]:
    n = db.get(SourceCatalogObject, nesne_id)
    k = db.get(SourceCatalog, n.catalog_id) if n else None
    if n is None or k is None or k.source_key not in KAYNAKLAR:
        raise PgHata("Nesne bulunamadı.", 404)
    satirlar = json.loads(zlib.decompress(n.sample_data).decode("utf-8")) if n.sample_data else []
    return {"id": n.id, "sema": n.owner, "ad": n.name, "tur": n.kind, "satir": n.row_count, "aciklama": n.comment, "sutunlar": n.columns or [],
            "ornek": {"sutunlar": n.sample_columns or [], "satirlar": satirlar, "not": n.sample_note}}  # fmt: skip


def yenile(db: Session, kaynak: str, kullanici: str) -> dict[str, Any]:
    """Isciyi panelin surec agacinin disinda baslatir (panel PostgreSQL'e baglanmaz). Calisan tarama varsa yenisi baslamaz."""
    from app.tampon import katalog

    d = durum(kaynak)
    if not d["hazir"]:
        raise PgHata(f"{KAYNAKLAR[kaynak].label} bağlantısı hazır değil: " + (", ".join(d["eksik"]) or f"{KAYNAKLAR[kaynak].enabled_key}=true değil"), 409)
    if _calisiyor(db, kaynak) is not None:
        return {"basladi": False, "calisiyor": True}
    backend = Path(__file__).resolve().parents[2]
    gunluk = backend / "var" / "logs"
    gunluk.mkdir(parents=True, exist_ok=True)
    kisi = re.sub(r"[^A-Za-z0-9._@-]", "", kullanici)[:120] or "panel"
    katalog._ayri_baslat([sys.executable, "-m", "app.isci", "pg-katalog", "--kaynak", kaynak, "--kullanici", kisi], backend, gunluk / "isci_pg_katalog.log")
    return {"basladi": True, "calisiyor": True}
