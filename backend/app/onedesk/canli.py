"""OneDesk sikayet / talep kayitlari -> onedesk_record (2026-11-21 kullanici: "talep ve sikayet kayitlarini da panele aktar. acik
kapali hepsini aktar. alarmdaki kurallara gore esitle; 01.01.2026 00:00 itibari ile acik kayitlar ve kapanmislari kartlara aktar").

Kural (TEMIP alarm aktarimiyla ayni: tampon/temip_kayit):
- Kapsam: REPORTDB_KAYIT_BASLANGIC'tan (vars. 2026-01-01 00:00, Turkiye saati) itibaren ACILAN kayitlar; yalniz panel kartlarindaki
  Musteri No'lar (OneDesk tum Turkcell kayitlarini tutar; kartsiz numara cekilmez).
- Eski sistem T_SOL_INCIDENT_TICKETS: TICKETTYPEID 1, TICKETSUBTYPEID 1 = sikayet, 2 = talep (3 = alarm; alarm ReportDB'den gelir).
  Yeni sistem T_OCT_CORPORATE_MAIN: TICKETTYPE_DESC Sikayet / Talep (tarih alanlari bos: acilis / kapanis icin UPDATEUSERTIME).
- Durum: CLOSE / Kapatildi ve SOLUTION / Cozuldu (cozum verildi, musteri onayi bekleniyor; 2026-11-23 karari) = kapali, kapanis
  CLOSEDATE yoksa SOLUTIONDATE (yeniden acilirsa sonraki turda acik olur); CANCEL / REJECT / Reddedildi = sayilmaz (panelde varsa
  silinir); digerleri (OPEN, SUSPEND, WORKINPROGRESS, REOPEN, DATAREQUEST, Acik, Bekleniyor, Calisiliyor) = acik.
- Yeni sistemin gecis donemi test kayitlari (ozette 'test...' / 'deneme' / betik denemesi) sayilmaz (TEST_KAYDI).
- Kayit = OneDesk is akisi (external_key = WFINSTANCEID, source = 'onedesk'). Atama: Musteri No tek karta duserse o karta; birden
  cok kartta ise kart bos (temip_kayit._kart ile ayni). Kart numarasi degisince her turda yeniden baglanir.
- Kipler: 'tam' / 'mutabakat' (baslangictan bugune hepsi; gunde bir), 'artimli' (her 6 dk: acik olanlar + son 2 gunde kapananlar +
  panelde acik gorunenlerin son durumu).
- Kisisel veri alinmaz: bildiren kisi, telefon, e-posta ve serbest cozum metni cekilmez; ozet yalniz kategori yoksa (kisaltilmis).
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import musteri_alani
from app.models import AppSetting, Customer, OnedeskRecord
from app.onedesk.sayac import TR_SAATI, sayaclari_yenile, tarih_oku
from app.ortak import normal, simdi
from app.tampon import postgres
from app.tampon.eslestirme import musteri_anahtarlari
from app.tampon.temip_kayit import _kart, baslangic, harita

KAYNAK = "pg_onedesk"
KAYNAK_ADI = "onedesk"  # onedesk_record.source
DURUM_ANAHTARI = "onedesk.kayit_durum"
KIPLER = ("tam", "artimli", "mutabakat")
ARTIMLI_GUN = 2
MUTABAKAT_SAATI = 2  # Turkiye saati: bu saatten sonraki ilk tur gunun mutabakatini yapar
DENEME = 3  # salt okunur kopya: uzun sorgu "conflict with recovery" ile kesilebilir
SORGU_SN = 300
PARCA = 1000

ESKI_TUR = {1: "sikayet", 2: "talep"}
KAPALI = {"CLOSE", "SOLUTION"}
SAYILMAZ = {"CANCEL", "REJECT"}
TEST_KAYDI = re.compile(r"\b(test(?!i\b)\w*|deneme)\b|<script", re.IGNORECASE)  # yalniz yeni sistem ozeti; 'hiz testi' gercek kayit
DURUM_ADI = {"OPEN": "Açık", "SOLUTION": "Çözüldü (onay bekliyor)", "SUSPEND": "Askıda", "WORKINPROGRESS": "Çalışılıyor",
             "REOPEN": "Yeniden açıldı", "DATAREQUEST": "Bilgi bekleniyor", "CLOSE": "Kapandı"}  # fmt: skip

_ESKI_KOLON = (
    '"WFINSTANCEID"::text AS kimlik, LTRIM("CUSTOMERNO"::text, \'0\') AS mno, "TICKETSUBTYPEID"::int AS tur, "STATUS" AS durum, '
    '"CREATEDDATE" AS acilis, COALESCE("CLOSEDATE", "SOLUTIONDATE") AS kapanis, LEFT("CUSTOMERFULLNAME", 200) AS unvan, '
    'LEFT(COALESCE(NULLIF("LOCATIONNAME", \'\'), NULLIF("CICIRCUITNO", \'\'), \'\'), 200) AS yer, '
    'LEFT(COALESCE(NULLIF("CICATEGORYDESC", \'\'), \'\'), 200) AS kategori, LEFT("SUMMARY", 200) AS ozet'
)
_ESKI = (
    f'SELECT {_ESKI_KOLON} FROM elysion_customdata_fix."T_SOL_INCIDENT_TICKETS" '
    'WHERE "TICKETTYPEID" = 1 AND "TICKETSUBTYPEID" IN (1, 2) AND "CREATEDDATE" >= %(bas)s '
    "AND LTRIM(\"CUSTOMERNO\"::text, '0') = ANY(%(nolar)s)"
)
# artimli: kapanmamislar + son N gunde kapananlar + panelde acik gorunenler (kapanmis / iptal olmus olabilir)
_ESKI_ARTIMLI = _ESKI + (
    ' AND ("STATUS" NOT IN (\'CLOSE\', \'CANCEL\', \'REJECT\') OR "CLOSEDATE" >= %(geri)s OR "WFINSTANCEID"::text = ANY(%(aciklar)s))'
)
_YENI = (
    'SELECT "WFINSTANCEID"::text AS kimlik, LTRIM("CUSTOMERNO"::text, \'0\') AS mno, "TICKETTYPE_DESC" AS tur, "STATUS" AS durum, '
    'COALESCE("CREATEDDATE", "CREATEUSERTIME", "UPDATEUSERTIME") AS acilis, '
    'COALESCE("CLOSEDATE", "SOLUTIONDATE", "UPDATEUSERTIME") AS kapanis, LEFT("CUSTOMERNAME_DESC", 200) AS unvan, '
    'LEFT(COALESCE(NULLIF("CINAME_DESC", \'\'), NULLIF("CICORPLOCATIONNAME", \'\'), \'\'), 200) AS yer, '
    'LEFT(COALESCE(NULLIF("CATEGORY_DESC", \'\'), NULLIF("CICATEGORYDESC", \'\'), \'\'), 200) AS kategori, LEFT("SUMMARY", 200) AS ozet, '
    'LEFT("ROOTCAUSE_DESC", 200) AS kok FROM elysion_soxdata_octopuscorp."T_OCT_CORPORATE_MAIN" '
    "WHERE LTRIM(\"CUSTOMERNO\"::text, '0') = ANY(%(nolar)s) "
    'AND COALESCE("CREATEDDATE", "CREATEUSERTIME", "UPDATEUSERTIME") >= %(bas)s'
)


def _metin(v: Any, azami: int) -> str:
    return " ".join(str(v).split())[:azami] if v not in (None, "") else ""


def _ozet(v: Any) -> str:
    m = _metin(v, 200)
    return m.split(":", 1)[1].strip() if m.upper().startswith("[EXTERNAL]:") else m


def _cek(sorgu: str, parametre: dict[str, Any]) -> list[dict[str, Any]]:
    a = postgres.ayar(KAYNAK)
    for deneme in range(1, DENEME + 1):
        try:
            with a.baglan(SORGU_SN) as conn, conn.cursor() as cur:
                cur.execute(sorgu, parametre)
                adlar = [d.name for d in cur.description]
                return [dict(zip(adlar, s, strict=True)) for s in cur.fetchall()]
        except Exception as e:
            if deneme == DENEME:
                raise postgres.PgHata(postgres.hata_metni(e, a.gizliler()), 502) from e
            time.sleep(5 * deneme)
    return []


def alanlar(s: dict[str, Any], yeni: bool, h: dict[str, set[int]]) -> tuple[str, dict[str, Any] | None]:
    """OneDesk satiri -> (kimlik, onedesk_record alanlari). Sayilmayan (iptal / red / tanimsiz tur) satir icin alanlar None."""
    kimlik = _metin(s.get("kimlik"), 80)
    if yeni:
        n = normal(s.get("tur") or "")
        tur = "sikayet" if n.startswith("sikayet") else "talep" if n.startswith("talep") else None
        d = normal(s.get("durum") or "")
        durum = "closed" if d.startswith(("kapat", "cozul")) else None if d.startswith(("redd", "iptal")) else "open"
        if TEST_KAYDI.search(_ozet(s.get("ozet"))):
            durum = None
        detay = _metin(s.get("durum"), 80)
    else:
        tur = ESKI_TUR.get(int(s.get("tur") or 0))
        ham = _metin(s.get("durum"), 40).upper()
        durum = None if ham in SAYILMAZ else "closed" if ham in KAPALI else "open"
        detay = DURUM_ADI.get(ham, ham.title())
    if not kimlik or tur is None or durum is None:
        return kimlik, None
    mno = _metin(s.get("mno"), 20)
    acilis = tarih_oku(s.get("acilis")) or simdi()
    kapanis = (tarih_oku(s.get("kapanis")) or acilis) if durum == "closed" else None
    return kimlik, {
        "kind": tur,
        "source": KAYNAK_ADI,
        "external_key": kimlik,
        "customer_no": mno,
        "customer_id": _kart(h, mno),
        "customer_label": _metin(s.get("unvan"), 200),
        "ticket_no": kimlik,
        "location": _metin(s.get("yer"), 200),
        "category": _metin(s.get("kategori"), 200) or _ozet(s.get("ozet")),
        "status": durum,
        "opened_at": acilis,
        "closed_at": kapanis,
        "root_cause": _metin(s.get("kok"), 200) if yeni else "",
        "detail": detay,
    }


def yaz(db: Session, kayitlar: list[dict[str, Any]], silinecek: set[str], etkilenen: set[int]) -> dict[str, int]:
    """(source, WFINSTANCEID) ile ekler / gunceller; iptal / red olanlari siler. OneDesk durumu esastir (kapali kayit yeniden acilabilir)."""
    sayac = {"eklenen": 0, "guncellenen": 0, "silinen": 0}
    for i in range(0, len(kayitlar), PARCA):
        parca = kayitlar[i : i + PARCA]
        mevcut = {
            r.external_key: r
            for r in db.scalars(
                select(OnedeskRecord).where(
                    OnedeskRecord.source == KAYNAK_ADI, OnedeskRecord.external_key.in_([k["external_key"] for k in parca])
                )
            )
        }
        for k in parca:
            r = mevcut.get(k["external_key"])
            if r is None:
                db.add(OnedeskRecord(**k, resolution=""))
                sayac["eklenen"] += 1
            else:
                if r.customer_id:
                    etkilenen.add(r.customer_id)
                if any(getattr(r, a) != v for a, v in k.items() if a not in ("opened_at", "closed_at")) or (
                    r.status == "closed" and (r.closed_at is None) != (k["closed_at"] is None)
                ):
                    for a, v in k.items():
                        setattr(r, a, v)
                    sayac["guncellenen"] += 1
            if k["customer_id"]:
                etkilenen.add(k["customer_id"])
        db.commit()
    liste = sorted(silinecek)
    for i in range(0, len(liste), PARCA):
        parca = liste[i : i + PARCA]
        kosul = (OnedeskRecord.source == KAYNAK_ADI) & OnedeskRecord.external_key.in_(parca)
        etkilenen.update(c for (c,) in db.execute(select(OnedeskRecord.customer_id).where(kosul)) if c)
        sayac["silinen"] += db.execute(delete(OnedeskRecord).where(kosul)).rowcount or 0
        db.commit()
    return sayac


@musteri_alani.tum_alanlarda
def yeniden_bagla(db: Session, h: dict[str, set[int]], etkilenen: set[int]) -> int:
    degisen = 0
    for r in db.scalars(select(OnedeskRecord).where(OnedeskRecord.source == KAYNAK_ADI)):
        beklenen = _kart(h, r.customer_no or "")
        if beklenen != r.customer_id:
            etkilenen.update(i for i in (r.customer_id, beklenen) if i)
            r.customer_id = beklenen
            degisen += 1
    db.commit()
    return degisen


def durum_oku(db: Session) -> dict[str, Any]:
    kayit = db.get(AppSetting, DURUM_ANAHTARI)
    return dict(kayit.value) if kayit is not None and isinstance(kayit.value, dict) else {}


def durum_yaz(db: Session, **alanlar: Any) -> None:
    kayit = db.get(AppSetting, DURUM_ANAHTARI)
    deger = {**durum_oku(db), **alanlar}
    if kayit is None:
        db.add(AppSetting(key=DURUM_ANAHTARI, value=deger, updated_by="isci", updated_at=simdi()))
    else:
        kayit.value, kayit.updated_by, kayit.updated_at = deger, "isci", simdi()
    db.commit()


def otomatik_kip(db: Session) -> str:
    """Hic tam yukleme yoksa 'tam'; gunde bir kez (MUTABAKAT_SAATI'nden sonra) 'mutabakat'; digerleri 'artimli'."""
    d = durum_oku(db)
    if not d.get("tam_yuklendi"):
        return "tam"
    yerel = simdi().astimezone(TR_SAATI)
    return "mutabakat" if yerel.hour >= MUTABAKAT_SAATI and d.get("mutabakat_gunu") != yerel.date().isoformat() else "artimli"


@musteri_alani.tum_alanlarda
def calistir(db: Session, kip: str = "artimli") -> dict[str, Any]:
    if kip not in KIPLER:
        raise postgres.PgHata("Kip tam, artimli ya da mutabakat olmalı.")
    t0 = time.time()
    bas = datetime.combine(baslangic(), datetime.min.time())  # Turkiye saati, dilimsiz (OneDesk tarihleri yerel)
    h = harita(db)
    nolar = sorted({k for (no,) in db.execute(select(Customer.customer_no)) for k in musteri_anahtarlari(no)})
    ozet: dict[str, Any] = {"kip": kip, "baslangic": bas.date().isoformat(), "satir": 0, "eklenen": 0, "guncellenen": 0, "silinen": 0}
    if not nolar:
        return ozet
    p: dict[str, Any] = {"bas": bas, "nolar": nolar}
    if kip == "artimli":
        p["geri"] = simdi().astimezone(TR_SAATI).replace(tzinfo=None) - timedelta(days=ARTIMLI_GUN)
        p["aciklar"] = list(db.scalars(select(OnedeskRecord.external_key).where(OnedeskRecord.source == KAYNAK_ADI, OnedeskRecord.status == "open")))
        eski = _cek(_ESKI_ARTIMLI, p)
    else:
        eski = _cek(_ESKI, p)
    yeni = _cek(_YENI, {"bas": bas, "nolar": nolar})
    kayitlar: dict[str, dict[str, Any]] = {}
    silinecek: set[str] = set()
    for satirlar, yeni_mi in ((eski, False), (yeni, True)):
        for s in satirlar:
            kimlik, a = alanlar(s, yeni_mi, h)
            if a is None:
                if kimlik:
                    silinecek.add(kimlik)
            else:
                kayitlar[kimlik] = a
    if kip != "artimli":
        # tam / mutabakat: OneDesk'te artik kapsamda olmayan panel kaydi (numara karttan cikti, kayit silindi) kaldirilir
        gorulen = set(kayitlar) | silinecek
        silinecek |= {k for (k,) in db.execute(select(OnedeskRecord.external_key).where(OnedeskRecord.source == KAYNAK_ADI)) if k not in gorulen}
    ozet["satir"] = len(eski) + len(yeni)
    etkilenen: set[int] = set()
    ozet.update(yaz(db, list(kayitlar.values()), silinecek - set(kayitlar), etkilenen))
    ozet["yeniden_baglanan"] = yeniden_bagla(db, h, etkilenen)
    sayaclari_yenile(db, etkilenen)
    db.commit()
    ozet["etkilenen_kart"] = len(etkilenen)
    ozet["sure_sn"] = round(time.time() - t0, 1)
    an = simdi()
    ek: dict[str, Any] = {"son_basari": an.isoformat(), "hata": "", "son_kip": kip, "son_ozet": ozet}
    if kip != "artimli":
        ek.update(tam_yuklendi=True, mutabakat_gunu=an.astimezone(TR_SAATI).date().isoformat())
    durum_yaz(db, son_deneme=an.isoformat(), **ek)
    return ozet
