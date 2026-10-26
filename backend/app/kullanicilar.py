"""Panel kullanici kaydi (app_user): oturum sahibinin satiri, AD ile ilk giriste acilan kisi, yerel acil hesap parolasi, giris yapmislar."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import imza
from app.config import get_settings
from app.models import AppUser, Base
from app.ortak import UygulamaHatasi, simdi
from app.session import Principal

# alan -> (etiket, azami uzunluk): kisinin kendi duzenledigi profil alanlari. Kullanici adi (AD) bunlarda YOK, degistirilemez.
PROFIL_ALANLARI = {
    "first_name": ("Ad", 100),
    "last_name": ("Soyad", 100),
    "phone": ("Telefon", 40),
    "company": ("Şirket", 200),
    "website": ("Web adresi", 200),
}
_TELEFON = re.compile(r"^[0-9+()\-\s.]+$")
_KONTROL = re.compile(r"[\x00-\x1f\x7f]")
_ALAN_ADI = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$")


class ProfilHata(UygulamaHatasi):
    """kod = HTTP durumu."""


class SilmeHata(UygulamaHatasi):
    """kod = HTTP durumu."""


def kullanici_kaydi(db: Session, user: Principal) -> AppUser:
    """Oturumdaki kisinin app_user satiri; yoksa olusturur (yerel/dev oturumu icin)."""
    satir = db.scalar(select(AppUser).where(AppUser.username == user.username))
    if satir is None:
        satir = AppUser(username=user.username, display_name=user.username, role=user.role, is_admin=user.is_admin)
        db.add(satir)
        db.flush()
    return satir


def ad_soyad(satir: AppUser) -> tuple[str, str]:
    """Kayitli ad ve soyad; ikisi de bossa display_name'den: son sozcuk soyad, oncesi ad (tek sozcuk yalniz ad)."""
    if satir.first_name or satir.last_name:
        return satir.first_name, satir.last_name
    parcalar = (satir.display_name or "").split()
    if len(parcalar) >= 2:
        return " ".join(parcalar[:-1]), parcalar[-1]
    return (parcalar[0] if parcalar else ""), ""


def profil_sozlugu(satir: AppUser | None, user: Principal) -> dict:
    """/session/me ve profil yanitinin profil bolumu. Satir yoksa (kaydi henuz olmayan yerel oturum) bos alanlar doner."""
    if satir is None:
        return {"username": user.username, "display_name": user.username, "ad_user": False, "first_name": "", "last_name": "", "phone": "", "company": "", "website": ""}
    ad, soyad = ad_soyad(satir)
    return {
        "username": satir.username,
        "display_name": satir.display_name or satir.username,
        "ad_user": bool(satir.is_ad_user),
        "first_name": ad,
        "last_name": soyad,
        "phone": satir.phone,
        "company": satir.company,
        "website": satir.website,
    }


def imza_sozlugu(satir: AppUser) -> dict:
    """E-posta imzasi (GET/PUT /session/imza; /me'ye girmez: gomulu gorselle ~200 KB). Bossa hazir sablon da doner: Teknocan +
    ad / unvan / sirket / iletisim; kaydedilmedikce maile girmez."""
    ad, soyad = ad_soyad(satir)
    sablon = imza.varsayilan(
        " ".join(p for p in (ad, soyad) if p) or satir.display_name or satir.username, "Teknik Müşteri Yöneticisi (TAM)", satir.company, satir.phone, satir.website
    )
    return {"html": satir.signature_html or "", "sablon": sablon, "kayitli": bool(satir.signature_html)}


def imza_kaydet(db: Session, user: Principal, ham: object) -> AppUser:
    """Kisinin kendi imzasi; izin listesiyle temizlenir (app.imza). Bos gonderilirse imza silinir (maile hazir imza girer)."""
    satir = kullanici_kaydi(db, user)
    satir.signature_html = imza.temizle(ham)
    db.flush()
    return satir


def _profil_degeri(alan: str, ham: object) -> str:
    etiket, azami = PROFIL_ALANLARI[alan]
    if ham is None:
        return ""
    if not isinstance(ham, str):
        raise ProfilHata(400, f"{etiket} geçersiz.")
    deger = " ".join(_KONTROL.sub(" ", ham).split())
    if len(deger) > azami:
        raise ProfilHata(400, f"{etiket} en fazla {azami} karakter olabilir.")
    if alan == "phone" and deger and not _TELEFON.match(deger):
        raise ProfilHata(400, "Telefon yalnızca rakam, +, (, ), - ve boşluk içerebilir.")
    if alan == "website" and deger:
        if "://" in deger and not re.match(r"^https?://", deger, re.IGNORECASE):
            raise ProfilHata(400, "Web adresi yalnızca http ya da https olabilir.")
        if "://" not in deger:
            deger = "https://" + deger
        parca = urlsplit(deger)
        try:
            kapi = parca.port
        except ValueError:
            kapi = -1
        if kapi == -1 or not parca.hostname or not _ALAN_ADI.match(parca.hostname) or " " in deger or len(deger) > azami:
            raise ProfilHata(400, "Web adresi geçersiz.")
    return deger


def profil_guncelle(db: Session, user: Principal, girdi: dict) -> tuple[AppUser, list[str]]:
    """Oturum sahibinin kendi profili: yalniz PROFIL_ALANLARI; gelmeyen alan degismez. Ad ya da soyad girilirse display_name
    (Takvim, Ekip, sorumlu TAM listeleri) 'Ad Soyad' olur. Dondurulen: (satir, degisen alanlar); commit cagiranda."""
    fazla = set(girdi) - set(PROFIL_ALANLARI)
    if fazla:
        raise ProfilHata(400, "Bu alan değiştirilemez.")
    satir = kullanici_kaydi(db, user)
    onceki = ad_soyad(satir)
    degisen: list[str] = []
    for alan in PROFIL_ALANLARI:
        if alan not in girdi:
            continue
        deger = _profil_degeri(alan, girdi[alan])
        eski = {"first_name": onceki[0], "last_name": onceki[1]}.get(alan, getattr(satir, alan))
        if deger != eski:
            degisen.append(alan)
        setattr(satir, alan, deger)
    if "first_name" in girdi or "last_name" in girdi:
        # Yalniz biri gonderildiyse digeri gosterilen (turetilmis) degerle kalir: ad/soyad tutarsiz kaymasin.
        satir.first_name = satir.first_name if "first_name" in girdi else onceki[0]
        satir.last_name = satir.last_name if "last_name" in girdi else onceki[1]
        tam = " ".join(p for p in (satir.first_name, satir.last_name) if p)
        if tam:
            satir.display_name = tam
    db.flush()
    return satir, degisen


def giris_isle(db: Session, user: Principal) -> None:
    """Basarili girisi kaydeder: kisi yoksa eklenir, rol ve son giris zamani guncellenir (TAM Takvim listesi buradan beslenir)."""
    satir = kullanici_kaydi(db, user)
    satir.role, satir.is_admin, satir.last_login_at = user.role, user.is_admin, simdi()
    db.commit()


PERSONEL_ROLU = "TeamMember"


def personel_kosulu() -> list:
    """TAM personeli: etkin, rolu TeamMember, admin degil. Takvim, ekip ozeti, utilizasyon, proje ve musteri listelerinin TEK kumesi;
    TeamMngr ve admin hicbir kisi listesinde satir olmaz (kullanici karari 2026-10-13). Yeni bir 'personel listesi' bunu kullanir."""
    return [AppUser.active.is_not(False), AppUser.role == PERSONEL_ROLU, AppUser.is_admin.is_not(True)]


def personel_mi(kisi: AppUser | None) -> bool:
    return bool(kisi is not None and kisi.active is not False and kisi.role == PERSONEL_ROLU and not kisi.is_admin)


def personel(db: Session) -> list[AppUser]:
    """Etkin TAM personeli (gorunen ada gore)."""
    return list(db.scalars(select(AppUser).where(*personel_kosulu()).order_by(AppUser.display_name, AppUser.username)))


def musteri_personeli_mi(kisi: AppUser | None) -> bool:
    """Musteri sorumlusu (TAM) olabilir mi. 2026-10-20 kullanici: modul sahipleri (KAAN USTUN, UGUR KULEKCI, OKAN COLAK, AHMET SOZMEN)
    listelere geri eklendi; 2026-10-17'deki 'modul sahibi musteri listesinde yer almaz' kurali kalkti. Kume = personel kumesi."""
    return personel_mi(kisi)


def musteri_personeli(db: Session) -> list[AppUser]:
    """Musteri Yonetimi personel listesi = personel kumesi (modul sahipleri dahil, 2026-10-20)."""
    return personel(db)


# --- Modul yonetimi (2026-10-20 kullanici karari) ---------------------------------------------------------------------
# Yonetimli moduller: icerigi herkes gorur, degistirme yalniz admin ve o modulun sahibi (app_user.module_owner). Sahipler:
# tamsms OKAN COLAK, tamapn AHMET SOZMEN, toptan KAAN USTUN, baglantili UGUR KULEKCI (isimler kodda degil, kullanici kaydinda).
YONETIMLI_MODULLER = ("tamsms", "tamapn", "toptan", "baglantili")


def modul_sahibi(db: Session, user: Principal) -> str:
    """Kullanicinin sahibi oldugu modul anahtari (yoksa bos)."""
    kisi = bul(db, user.username)
    return (kisi.module_owner or "").strip() if kisi is not None and kisi.active is not False else ""


def modul_yoneticisi_mi(db: Session, user: Principal, modul: str) -> bool:
    """Yonetimli modulde yazma: admin ya da modulun sahibi."""
    from app.authz import is_admin

    return is_admin(user) or (modul in YONETIMLI_MODULLER and modul_sahibi(db, user) == modul)


def silme_yetkilisi_ad() -> str:
    """Kullanici silebilen TEK hesabin adi (KULLANICI_SILME_YETKILISI, varsayilan admin); bos ayar = kimse silemez."""
    return get_settings().kullanici_silme_yetkilisi.strip().lower()


def silebilir_mi(user: Principal) -> bool:
    """Kullanici silme yalniz ayardaki hesapta ve hesabin rolu admin iken: admin rolu verilmis baska kisi bile silemez."""
    ad = silme_yetkilisi_ad()
    return bool(ad) and user.is_admin and user.username.strip().lower() == ad


def sil(db: Session, yapan: Principal, kullanici_id: int, devret: AppUser | None = None) -> dict:
    """Panel kullanicisini siler (yalniz `silebilir_mi` hesabi). Kisiye bagli kayitlar metadata'dan bulunur, hicbiri yetim kalmaz:
    bos olabilen baglar bosaltilir (musteri sorumlusu, talep atananı vb.), zorunlu baglar (rapor, talep, proje kalemi, skor talebi)
    silen hesaba DEVREDILIR, kisiye ozel dislama satiri silinir. Kisinin kendi SQLite dosyasi (takvim/izin) dokunulmaz.
    `devret` verilirse (komut satiri temizligi: ayni kisinin AD hesabi) bos olabilenler dahil TUM baglar o kisiye gecer, hicbiri bosalmaz.
    Donus: ozet (username, display_name, devredilen, bosaltilan, silinen)."""
    if not silebilir_mi(yapan):
        raise SilmeHata(403, f"Kullanıcı silme yetkisi yalnızca '{silme_yetkilisi_ad() or '-'}' hesabındadır.")
    hedef = db.get(AppUser, kullanici_id)
    if hedef is None:
        raise SilmeHata(404, "Kullanıcı bulunamadı.")
    if hedef.username.strip().lower() == yapan.username.strip().lower():
        raise SilmeHata(400, "Kendi hesabınızı silemezsiniz.")
    if devret is not None and devret.id == hedef.id:
        raise SilmeHata(400, "Devir hedefi silinen kişiyle aynı olamaz.")
    sahip = devret or kullanici_kaydi(db, yapan)
    devredilen = bosaltilan = silinen = 0
    for tablo in Base.metadata.sorted_tables:
        for sutun in tablo.columns:
            if not any(fk.column.table.name == AppUser.__tablename__ for fk in sutun.foreign_keys):
                continue
            kosul = sutun == hedef.id
            if sutun.primary_key:
                silinen += db.execute(delete(tablo).where(kosul)).rowcount
            elif sutun.nullable and devret is None:
                bosaltilan += db.execute(update(tablo).where(kosul).values({sutun.name: None})).rowcount
            else:
                devredilen += db.execute(update(tablo).where(kosul).values({sutun.name: sahip.id})).rowcount
    ozet = {"id": hedef.id, "username": hedef.username, "display_name": hedef.display_name or hedef.username, "devredilen": devredilen, "bosaltilan": bosaltilan, "silinen": silinen}
    db.delete(hedef)
    db.flush()
    return ozet


def bul(db: Session, kisa_ad: str) -> AppUser | None:
    """Kullanici adi buyuk/kucuk harfe duyarsiz."""
    return db.scalar(select(AppUser).where(func.lower(AppUser.username) == kisa_ad.strip().lower()))


def tam_ad_uret(kisa_ad: str) -> str:
    """'giray.sav' -> 'Giray Sav' (Turkce i/I)."""
    parcalar = [p for p in kisa_ad.replace("_", ".").split(".") if p]
    return " ".join({"i": "İ", "ı": "I"}.get(p[0], p[0].upper()) + p[1:] for p in parcalar) or kisa_ad


IZINLI_ONEKLER = ("tc", "ng", "te")  # 2026-10-15 kullanici karari: panelde yalniz admin ve tc/ng/te ile baslayan kullanicilar


def onek_izinli(kisa_ad: str) -> bool:
    """AD ile ilk kez giren kisiye hesap acilabilir mi (kullanici adi tc/ng/te ile baslamali)."""
    return kisa_ad.strip().lower().startswith(IZINLI_ONEKLER)


def ad_kullanicisi_ac(db: Session, kisa_ad: str, alan: str) -> AppUser:
    """AD'de DOGRULANMIS, panelde kaydi olmayan kisi: TeamMember, yonetici degil, yalniz AD ile girer. Ayni anda iki giris olursa mevcut satir doner."""
    satir = AppUser(username=kisa_ad.lower(), display_name=tam_ad_uret(kisa_ad), role="TeamMember", is_admin=False, active=True, is_ad_user=True, ad_domain=alan.lower())
    db.add(satir)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        mevcut = bul(db, kisa_ad)
        if mevcut is None:
            raise
        return mevcut
    return satir


# --- yerel acil hesap parolasi (scrypt; ayar degeri koda gomulu degil) ------------------------------------------------
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}
EN_KISA_PAROLA = 12


def parola_ozeti(parola: str) -> str:
    if len(parola) < EN_KISA_PAROLA:
        raise ValueError(f"Parola en az {EN_KISA_PAROLA} karakter olmali.")
    tuz = secrets.token_bytes(16)
    ozet = hashlib.scrypt(parola.encode(), salt=tuz, dklen=32, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${tuz.hex()}${ozet.hex()}"


def parola_dogru(parola: str, kayit: str | None) -> bool:
    try:
        tur, n, r, p, tuz, ozet = (kayit or "").split("$")
        if tur != "scrypt":
            return False
        aday = hashlib.scrypt(parola.encode(), salt=bytes.fromhex(tuz), dklen=32, n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(aday.hex(), ozet)
