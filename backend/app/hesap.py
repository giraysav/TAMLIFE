# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Hesap yonetimi (komut satiri; Yonetim > Kullanicilar ekrani gelene kadar). cd backend; ..\\.venv\\Scripts\\python.exe -m app.hesap ...

  liste                         kullanicilari listeler
  personel                      takvim, ekip ozeti, utilizasyon, proje ve musteri listelerinin ORTAK kisi kumesini (etkin TeamMember) ve
                                disarida kalanlari nedeniyle gosterir; ayni gorunen ada sahip birden cok hesabi isaretler
  rol <kullanici> <rol>         admin | TeamMngr | TeamMember; kayit yoksa AD kullanicisi olarak acar (ilk girisi beklemeden yetki)
  aktif|pasif <kullanici>       pasif kullanici giris yapamaz (AD kullanicisi silinmez, pasife alinir)
  parola <kullanici>            YEREL ACIL HESAP parolasi (en az 12 karakter, gizli sorulur); AD kullanicisina verilmez
  sil <kullanici>... [--devret <hedef>] [--evet]
                                kullaniciyi siler (panelden silmeyle ayni kural). --evet yoksa DENEME: ne olacagini yazar, hicbir sey silmez.
                                Bagli kayitlar silen hesaba (KULLANICI_SILME_YETKILISI, varsayilan admin) devredilir; --devret verilirse
                                musteri sorumlusu dahi tum kayitlar o kisiye gecer (ornek: eski elle acilmis hesabin AD hesabi)

Rol/pasif degisikligi acik oturumlara yeniden giriste yansir (oturumlar panel surecinin belleginde).
"""

from __future__ import annotations

import getpass
import sys
from collections import Counter

from sqlalchemy import func, select

from app import kullanicilar
from app.config import env_dosyasi_yukle
from app.db import oturum
from app.models import AppUser, Customer, ProjectItem
from app.ortak import UygulamaHatasi, eslestirme_anahtari
from app.session import Principal

ROLLER = ("admin", "TeamMngr", "TeamMember")


def _personel(db) -> int:
    """personel: tum modullerin ortak kisi kumesi ve disarida kalanlar; ayni kisi gibi gorunen hesaplar (silme/devir adayi)."""
    tum = list(db.scalars(select(AppUser).order_by(AppUser.display_name, AppUser.username)))
    ici = [u for u in tum if kullanicilar.personel_mi(u)]
    print(f"PERSONEL ({len(ici)} kisi; takvim, ekip ozeti, utilizasyon, proje ve musteri listelerinde ayni kume):")
    for u in ici:
        print(f"  {u.username:<24} {u.display_name or u.username}")
    print("DISARIDA:")
    for u in tum:
        if kullanicilar.personel_mi(u):
            continue
        neden = "PASIF hesap" if u.active is False else ("admin" if u.is_admin or u.role == "admin" else f"rol {u.role}")
        print(f"  {u.username:<24} {u.display_name or u.username}  -> {neden}")
    dis = {u.id: u for u in tum if not kullanicilar.personel_mi(u)}
    musteri = Counter(db.scalars(select(Customer.owner_id).where(Customer.owner_id.in_(dis))))
    proje = Counter(db.scalars(select(ProjectItem.owner_id).where(ProjectItem.owner_id.in_(dis))))
    sahipsiz = db.scalar(select(func.count()).select_from(Customer).where(Customer.owner_id.is_(None))) or 0
    if musteri or proje or sahipsiz:
        print("SAHIBI PERSONEL OLMAYAN KAYITLAR (listelerde 'Atanmamis' satirina duser; Musteri Karti > Sorumlu TAM ile personele devredin):")
        for kimlik in sorted(set(musteri) | set(proje)):
            u = dis[kimlik]
            print(f"  {u.username:<24} {u.display_name or u.username}  -> musteri: {musteri[kimlik]}, proje: {proje[kimlik]}")
        if sahipsiz:
            print(f"  (sahibi bos)             -> musteri: {sahipsiz}")
    gruplar: dict[str, list[AppUser]] = {}
    for u in tum:
        gruplar.setdefault(eslestirme_anahtari(u.display_name or u.username), []).append(u)
    ayni = [g for g in gruplar.values() if len(g) > 1]
    if ayni:
        print("AYNI KISI OLABILIR (ayni gorunen ad, birden cok hesap):")
        for g in ayni:
            print("  " + " | ".join(f"{u.username} ({u.role}, {'aktif' if u.active is not False else 'pasif'})" for u in g))
    return 0


def _sil(db, arg: list[str]) -> int:
    """sil <kullanici>... [--devret <hedef>] [--evet]: once deneme (geri alinir), --evet ile gercek silme."""
    evet = "--evet" in arg
    kalan = [a for a in arg if a != "--evet"]
    devret_ad = None
    if "--devret" in kalan:
        i = kalan.index("--devret")
        if i + 1 >= len(kalan):
            print("--devret icin kullanici adi gerekli.")
            return 2
        devret_ad = kalan[i + 1]
        del kalan[i : i + 2]
    if not kalan:
        print("Silinecek kullanici adi gerekli.")
        return 2
    yetkili = kullanicilar.silme_yetkilisi_ad()
    sahip = kullanicilar.bul(db, yetkili) if yetkili else None
    if sahip is None:
        print("Silme yetkilisi hesap (KULLANICI_SILME_YETKILISI, varsayilan admin) panelde kayitli degil; once o hesabi gorun: liste.")
        return 1
    devret = None
    if devret_ad:
        devret = kullanicilar.bul(db, devret_ad)
        if devret is None:
            print(f"Devir hedefi yok: {devret_ad}")
            return 1
    yapan = Principal(sahip.username, "admin", True)
    hata = False
    for ad in kalan:
        satir = kullanicilar.bul(db, ad)
        if satir is None:
            print(f"{ad}: kullanici yok")
            hata = True
            continue
        try:
            o = kullanicilar.sil(db, yapan, satir.id, devret)
        except UygulamaHatasi as exc:
            print(f"{ad}: {exc.mesaj}")
            hata = True
            continue
        hedef = f" -> {devret.username}" if devret else f" -> {sahip.username}"
        print(f"{o['username']:<24} devredilen={o['devredilen']} bosaltilan={o['bosaltilan']} silinen={o['silinen']}{hedef}")
    if hata:
        db.rollback()
        print("Hata var: hicbir sey silinmedi.")
        return 1
    if evet:
        db.commit()
        print("SILINDI.")
    else:
        db.rollback()
        print("DENEME: hicbir sey silinmedi. Gercekten silmek icin ayni komutun sonuna --evet ekleyin.")
    return 0


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # Windows konsol kod sayfasinda olmayan harf (orn. ı) cokertmesin
    env_dosyasi_yukle()
    if not argv or argv[0] not in {"liste", "personel", "rol", "aktif", "pasif", "parola", "sil"}:
        print(__doc__)
        return 2
    komut, *arg = argv
    with oturum() as db:
        if komut == "liste":
            for u in db.scalars(select(AppUser).order_by(AppUser.username)):
                tur = "AD" if u.is_ad_user else ("yerel" if u.password_hash else "-")
                print(f"{u.username:<24} {u.role:<11} {'aktif' if u.active else 'PASIF':<6} {tur:<6} {u.display_name}")
            return 0
        if komut == "personel":
            return _personel(db)
        if komut == "sil":
            return _sil(db, arg)
        if not arg:
            print("Kullanici adi gerekli.")
            return 2
        satir = kullanicilar.bul(db, arg[0])
        if komut == "rol":
            if len(arg) < 2 or arg[1] not in ROLLER:
                print(f"Rol: {' | '.join(ROLLER)}")
                return 2
            if satir is None:
                satir = AppUser(username=arg[0].strip().lower(), display_name=kullanicilar.tam_ad_uret(arg[0].strip()), role=arg[1], is_ad_user=True)
                db.add(satir)
            satir.role, satir.is_admin = arg[1], arg[1] == "admin"
        elif satir is None:
            print("Kullanici yok.")
            return 1
        elif komut in {"aktif", "pasif"}:
            satir.active = komut == "aktif"
        else:  # parola
            if satir.is_ad_user:
                print("AD kullanicisina yerel parola verilmez (AD kapaliyken bile yerel girise dusmez).")
                return 1
            parola = getpass.getpass("Yeni parola (gizli): ")
            if parola != getpass.getpass("Tekrar: "):
                print("Parolalar ayni degil.")
                return 1
            try:
                satir.password_hash = kullanicilar.parola_ozeti(parola)
            except ValueError as exc:
                print(exc)
                return 1
        db.commit()
        print(f"Tamam: {satir.username} rol={satir.role} {'aktif' if satir.active else 'PASIF'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
