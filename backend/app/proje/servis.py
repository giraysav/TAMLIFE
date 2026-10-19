"""Takip Edilen Projeler. Uretim karsiligi: kutucuklar/proje (servis.py, musteri_calisma.py), blueprints/projects_bp.py.

Uc bolum:
  - Ozet: TAM bazinda kategori sayilari + kapanan / devam eden (tekil projelerden hesaplanir; uretimdeki yil/ceyrek sayi tablosu
    yalniz Excel semasi icindi, tasinmadi).
  - Proje Detay Takibi (Jira/ITIL tarzi): proje basina durum, oncelik, hedef tarih ve kronolojik aksiyon gecmisi.
    Acilis ve durum/oncelik degisimi aksiyon olarak yazilir; 'kapandi' olunca kapanis tarihi bir kez yazilir.
  - Musteri Bazli Calismalar: musteri + kategori basina "yapildi" isareti ve detay; Excel rapor.
Kapsam (uretim aktif_kapsam): admin ve TeamMngr hepsini; TeamMember yalniz sorumlusu oldugu projeleri ve kendi musterilerini
(cati + istirakleri) gorur/degistirir. Member proje acarken sorumlu her zaman kendisidir (TAM adini degistiremez).
"""

from __future__ import annotations

import io
from datetime import date

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, aliased

from app import dil
from app.authz import yonetici_mi
from app.kullanicilar import kullanici_kaydi, personel, personel_mi
from app.models import AppUser, Customer, ProjectAction, ProjectCustomerWork, ProjectItem
from app.ortak import UygulamaHatasi, eslestirme_anahtari, iso, simdi
from app.session import Principal

KATEGORILER = {"proje": "Proje", "calisma": "Çalışma", "ddos": "Ddos Optimizasyonu", "dc_tasima": "DC Taşıması", "topoloji": "Topoloji İyileştirme"}
DURUMLAR = {"acik": "Açık", "devam": "Devam Ediyor", "beklemede": "Beklemede", "kapandi": "Kapandı"}
ONCELIKLER = {"dusuk": "Düşük", "orta": "Orta", "yuksek": "Yüksek", "kritik": "Kritik"}
AZAMI_DETAY = 2000


class ProjeHata(UygulamaHatasi):
    """kod = HTTP durumu."""


def _ad(kisi: AppUser | None) -> str:
    return (kisi.display_name or kisi.username) if kisi else ""


# --- proje detay takibi ----------------------------------------------------------------------------------------------
def _gorunur(db: Session, user: Principal, kalem: ProjectItem | None) -> ProjectItem:
    """Gorunmeyen proje icin de 404 (varligi sizdirilmaz)."""
    if kalem is None or not (yonetici_mi(user) or kalem.owner_id == kullanici_kaydi(db, user).id):
        raise ProjeHata(404, "Proje bulunamadı.")
    return kalem


def _aksiyon(db: Session, kalem_id: int, metin: str, yapan: str) -> None:
    db.add(ProjectAction(item_id=kalem_id, text=metin, actor=yapan, at=simdi()))


def kalem_ekle(db: Session, user: Principal, veri: dict) -> int:
    ben = kullanici_kaydi(db, user)
    sahip_id = ben.id
    if yonetici_mi(user):
        # Sorumlu yalniz TAM personeli olabilir (yonetici ve admin kisi listelerinde yer almaz); secilmediyse kendisi, o da personel degilse hata.
        sahip = db.get(AppUser, veri["owner_id"]) if veri.get("owner_id") else ben
        if not personel_mi(sahip):
            raise ProjeHata(400, "Sorumlu TAM bulunamadı." if veri.get("owner_id") else "Sorumlu TAM seçin.")
        sahip_id = sahip.id
    baslik = (veri.get("title") or "").strip()
    if not baslik:
        raise ProjeHata(400, "Proje başlığı zorunlu.")
    if veri.get("start_date") and veri.get("target_date") and veri["target_date"] < veri["start_date"]:
        raise ProjeHata(400, "Hedef tarih başlangıçtan önce olamaz.")
    an = simdi()
    kalem = ProjectItem(
        owner_id=sahip_id,
        category=veri["category"],
        title=baslik,
        description=(veri.get("description") or "").strip(),
        status="acik",
        priority=veri.get("priority") or "orta",
        start_date=veri.get("start_date"),
        target_date=veri.get("target_date"),
        created_by=_ad(ben),
        created_at=an,
        updated_at=an,
    )
    db.add(kalem)
    db.flush()
    _aksiyon(db, kalem.id, "Proje kaydı oluşturuldu.", _ad(ben))
    return kalem.id


def kalem_guncelle(db: Session, user: Principal, kalem_id: int, degisiklik: dict) -> list[str]:
    """status / priority / target_date. Durum ve oncelik degisimi aksiyon gecmisine yazilir (uretim metinleriyle)."""
    kalem = _gorunur(db, user, db.get(ProjectItem, kalem_id))
    yapan = _ad(kullanici_kaydi(db, user))
    degisen: list[str] = []
    durum = degisiklik.get("status")
    if durum and durum != kalem.status:
        _aksiyon(db, kalem.id, f"Durum güncellendi: {DURUMLAR.get(kalem.status, kalem.status)} → {DURUMLAR[durum]}", yapan)
        kalem.status = durum
        if durum == "kapandi" and kalem.closed_date is None:
            kalem.closed_date = simdi().date()
        degisen.append("status")
    oncelik = degisiklik.get("priority")
    if oncelik and oncelik != kalem.priority:
        _aksiyon(db, kalem.id, f"Öncelik güncellendi: {ONCELIKLER.get(kalem.priority, kalem.priority)} → {ONCELIKLER[oncelik]}", yapan)
        kalem.priority = oncelik
        degisen.append("priority")
    if "target_date" in degisiklik and degisiklik["target_date"] != kalem.target_date:
        kalem.target_date = degisiklik["target_date"]
        degisen.append("target_date")
    if degisen:
        kalem.updated_at = simdi()
    return degisen


def aksiyon_ekle(db: Session, user: Principal, kalem_id: int, metin: str) -> None:
    kalem = _gorunur(db, user, db.get(ProjectItem, kalem_id))
    metin = (metin or "").strip()
    if not metin:
        raise ProjeHata(400, "Aksiyon metni boş olamaz.")
    _aksiyon(db, kalem.id, metin, _ad(kullanici_kaydi(db, user)))
    kalem.updated_at = simdi()


def kalem_sil(db: Session, user: Principal, kalem_id: int) -> None:
    kalem = _gorunur(db, user, db.get(ProjectItem, kalem_id))
    db.execute(delete(ProjectAction).where(ProjectAction.item_id == kalem.id))
    db.delete(kalem)


def _musteri_isaretleri(db: Session, user: Principal) -> list[tuple[str, int | None]]:
    """Gorunen musterilerdeki 'yapildi' isaretleri: (kategori, cati TAM'i). Kapsam musteriler() ile ayni."""
    ust = aliased(Customer)
    sorgu = (
        select(ProjectCustomerWork.category, func.coalesce(ust.owner_id, Customer.owner_id))
        .join(Customer, Customer.id == ProjectCustomerWork.customer_id)
        .outerjoin(ust, Customer.parent_id == ust.id)
        .where(ProjectCustomerWork.done.is_(True), ProjectCustomerWork.category.in_(list(KATEGORILER)))
    )
    if not yonetici_mi(user):
        uid = kullanici_kaydi(db, user).id
        sorgu = sorgu.where(or_(Customer.owner_id == uid, ust.owner_id == uid))
    return [(k, s) for k, s in db.execute(sorgu).all()]


def ekran(db: Session, user: Principal) -> dict:
    """Ozet + proje listesi (en son guncellenen ustte) + sorumlu secenekleri."""
    yonetici = yonetici_mi(user)
    ben = kullanici_kaydi(db, user)
    sorgu = select(ProjectItem).order_by(ProjectItem.updated_at.desc(), ProjectItem.id.desc())
    if not yonetici:
        sorgu = sorgu.where(ProjectItem.owner_id == ben.id)
    kalemler = list(db.scalars(sorgu))
    kisiler = {k.id: k for k in db.scalars(select(AppUser).where(AppUser.id.in_({k.owner_id for k in kalemler} | {ben.id})))}
    aksiyonlar: dict[int, list[ProjectAction]] = {}
    if kalemler:
        for a in db.scalars(select(ProjectAction).where(ProjectAction.item_id.in_([k.id for k in kalemler])).order_by(ProjectAction.at.desc(), ProjectAction.id.desc())):
            aksiyonlar.setdefault(a.item_id, []).append(a)

    personeller = personel(db) if yonetici else [ben]
    kimlikler = {p.id for p in personeller}
    ozet: dict[int | None, dict] = {}
    for p in personeller:  # projesi olmayan personel de satir olur (0); tum modullerle ayni kisi kumesi
        ozet[p.id] = {"tam": _ad(p), **dict.fromkeys(KATEGORILER, 0), "kapanan": 0, "devam_eden": 0}
    for k in kalemler:
        sahip = k.owner_id if k.owner_id in kimlikler else None  # personel olmayan sahip (yonetici/admin): tek 'Atanmamis' satiri
        d = ozet.setdefault(sahip, {"tam": _ad(kisiler.get(k.owner_id)) if sahip else dil.m("Atanmamış", "Unassigned"), **dict.fromkeys(KATEGORILER, 0), "kapanan": 0, "devam_eden": 0})
        if k.category in KATEGORILER:
            d[k.category] += 1
        d["kapanan" if k.status == "kapandi" else "devam_eden"] += 1
    # 2026-10-19 kullanici istegi: Musteri Bazli Calismalar'da isaretlenen kutu da personelin ilgili kategori sutununa yazilir
    # (musteri basina kategori basina 1; istirak catisinin TAM'ina sayilir, Excel suzgeciyle ayni kural).
    for kategori, sahip_id in _musteri_isaretleri(db, user):
        sahip = sahip_id if sahip_id in kimlikler else None
        d = ozet.setdefault(sahip, {"tam": _ad(db.get(AppUser, sahip_id)) if sahip else dil.m("Atanmamış", "Unassigned"), **dict.fromkeys(KATEGORILER, 0), "kapanan": 0, "devam_eden": 0})
        d[kategori] += 1
    for d in ozet.values():
        d["toplam"] = sum(d[c] for c in KATEGORILER)
    ozet_listesi = [d for _, d in sorted(ozet.items(), key=lambda kv: (kv[0] is None, -kv[1]["toplam"], eslestirme_anahtari(kv[1]["tam"])))]

    secenek = personeller
    return {
        "yonetici": yonetici,
        "kendi_id": ben.id,
        "varsayilan_sorumlu": ben.id if personel_mi(ben) else (secenek[0].id if secenek else ben.id),
        "ozet": ozet_listesi,
        "genel_toplam": sum(d["toplam"] for d in ozet_listesi),
        "tamlar": [{"id": k.id, "ad": _ad(k)} for k in secenek],
        "kalemler": [
            {
                "id": k.id,
                "tam_id": k.owner_id,
                "tam": _ad(kisiler.get(k.owner_id)),
                "kategori": k.category,
                "baslik": k.title,
                "aciklama": k.description,
                "durum": k.status,
                "oncelik": k.priority,
                "baslangic": k.start_date.isoformat() if k.start_date else None,
                "hedef": k.target_date.isoformat() if k.target_date else None,
                "kapanis": k.closed_date.isoformat() if k.closed_date else None,
                "aksiyonlar": [{"id": a.id, "metin": a.text, "yapan": a.actor, "zaman": iso(a.at)} for a in aksiyonlar.get(k.id, [])],
            }
            for k in kalemler
        ],
    }


# --- musteri bazli calismalar ------------------------------------------------------------------------------------------
def musteriler(db: Session, user: Principal, tam_id: int | None = None) -> list[dict]:
    """Gorunen musteriler (cati, altinda istirakleri), cati TAM'i ve adina gore. tam_id: o TAM'in cati musterileri ve istirakleri."""
    ust = aliased(Customer)
    sorgu = select(Customer, ust).outerjoin(ust, Customer.parent_id == ust.id)
    if not yonetici_mi(user):
        uid = kullanici_kaydi(db, user).id
        sorgu = sorgu.where(or_(Customer.owner_id == uid, ust.owner_id == uid))
    if tam_id:
        sorgu = sorgu.where(or_(Customer.owner_id == tam_id, ust.owner_id == tam_id))
    satirlar = db.execute(sorgu).all()
    sahipler = {k.id: _ad(k) for k in db.scalars(select(AppUser).where(AppUser.id.in_({c.owner_id for c, _ in satirlar if c.owner_id})))}
    sahipler |= {k.id: _ad(k) for k in db.scalars(select(AppUser).where(AppUser.id.in_({u.owner_id for _, u in satirlar if u and u.owner_id})))}

    def anahtar(satir) -> tuple:
        c, u = satir
        cati = u or c
        return (eslestirme_anahtari(sahipler.get(cati.owner_id, "")), eslestirme_anahtari(cati.name or ""), cati.id, u is not None, eslestirme_anahtari(c.name or ""))

    return [
        {"id": c.id, "ad": c.name or "", "tam": sahipler.get(c.owner_id, ""), "tam_id": c.owner_id, "istirak": u is not None}
        for c, u in sorted(satirlar, key=anahtar)
    ]


def isaretler(db: Session, kimlikler: list[int]) -> dict[int, dict[str, dict]]:
    sonuc: dict[int, dict[str, dict]] = {}
    for i in range(0, len(kimlikler), 500):
        for k in db.scalars(select(ProjectCustomerWork).where(ProjectCustomerWork.customer_id.in_(kimlikler[i : i + 500]))):
            sonuc.setdefault(k.customer_id, {})[k.category] = {"yapildi": k.done, "detay": k.detail, "guncelleyen": k.updated_by, "zaman": iso(k.updated_at)}
    return sonuc


def calisma_ekrani(db: Session, user: Principal, tam_id: int | None = None) -> dict:
    liste = musteriler(db, user, tam_id)
    return {"musteriler": liste, "isaretler": isaretler(db, [m["id"] for m in liste])}


def calisma_kaydet(db: Session, user: Principal, musteri_id: int, kategori: str, yapildi: bool, detay: str) -> str | None:
    """Isaret ve detay bossa kayit silinir. Yalniz gorulebilen musteri (Member: kendi cati musterisi ve istirakleri)."""
    if kategori not in KATEGORILER:
        raise ProjeHata(400, "Bilinmeyen çalışma türü.")
    if musteri_id not in {m["id"] for m in musteriler(db, user)}:
        raise ProjeHata(404, "Müşteri bulunamadı.")
    detay = (detay or "").strip()[:AZAMI_DETAY]
    kayit = db.get(ProjectCustomerWork, (musteri_id, kategori))
    if not yapildi and not detay:
        if kayit is not None:
            db.delete(kayit)
        return None
    an = simdi()
    if kayit is None:
        kayit = ProjectCustomerWork(customer_id=musteri_id, category=kategori)
        db.add(kayit)
    kayit.done, kayit.detail, kayit.updated_by, kayit.updated_at = yapildi, detay, _ad(kullanici_kaydi(db, user)), an
    return iso(an)


def rapor_excel(db: Session, user: Principal, tam_id: int | None = None) -> bytes:
    """Musteri bazli calisma raporu (.xlsx): hangi musteride hangi calisma yapildi + detaylar. openpyxl tembel yuklenir."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    liste = musteriler(db, user, tam_id)
    isaret = isaretler(db, [m["id"] for m in liste])
    sutunlar = [("Müşteri", 40), ("TAM", 22)] + [(ad, 14) for ad in KATEGORILER.values()] + [("Detay", 60)]
    yapilan = sum(1 for m in liste for k in KATEGORILER if isaret.get(m["id"], {}).get(k, {}).get("yapildi"))
    wb = Workbook()
    ws = wb.active
    ws.title = "Çalışmalar"
    ws.append(["Müşteri Bazlı Proje / Çalışma Raporu"])
    ws["A1"].font = Font(bold=True, size=14, color="002855")
    ws.append([f"{len(liste)} müşteri · {yapilan} işaretli çalışma · hazırlayan: {_ad(kullanici_kaydi(db, user))} · {date.today().strftime('%d.%m.%Y')}"])
    ws["A2"].font = Font(italic=True, color="64748B")
    ws.append([ad for ad, _ in sutunlar])
    for hucre in ws[3]:
        hucre.font = Font(bold=True, color="FFFFFF")
        hucre.fill = PatternFill("solid", fgColor="002855")
    for m in liste:
        k = isaret.get(m["id"], {})
        detaylar = "; ".join(f"{KATEGORILER[kat]}: {k[kat]['detay']}" for kat in KATEGORILER if k.get(kat, {}).get("detay"))
        ws.append([("   ↳ " if m["istirak"] else "") + m["ad"], m["tam"], *["✓" if k.get(kat, {}).get("yapildi") else "" for kat in KATEGORILER], detaylar])
    for i, (_, genislik) in enumerate(sutunlar, 1):
        ws.column_dimensions[get_column_letter(i)].width = genislik
    for satir in ws.iter_rows(min_row=4):
        for hucre in satir[2:-1]:
            hucre.alignment = Alignment(horizontal="center")
        satir[-1].alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A4"
    cikti = io.BytesIO()
    wb.save(cikti)
    return cikti.getvalue()
