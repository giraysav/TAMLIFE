"""Hesap yonetimi (komut satiri; Yonetim > Kullanicilar ekrani gelene kadar). cd backend; ..\\.venv\\Scripts\\python.exe -m app.hesap ...

  liste                         kullanicilari listeler
  rol <kullanici> <rol>         admin | TeamMngr | TeamMember; kayit yoksa AD kullanicisi olarak acar (ilk girisi beklemeden yetki)
  aktif|pasif <kullanici>       pasif kullanici giris yapamaz (AD kullanicisi silinmez, pasife alinir)
  parola <kullanici>            YEREL ACIL HESAP parolasi (en az 12 karakter, gizli sorulur); AD kullanicisina verilmez

Rol/pasif degisikligi acik oturumlara yeniden giriste yansir (oturumlar panel surecinin belleginde).
"""

from __future__ import annotations

import getpass
import sys

from sqlalchemy import select

from app import kullanicilar
from app.config import env_dosyasi_yukle
from app.db import oturum
from app.models import AppUser

ROLLER = ("admin", "TeamMngr", "TeamMember")


def main(argv: list[str]) -> int:
    env_dosyasi_yukle()
    if not argv or argv[0] not in {"liste", "rol", "aktif", "pasif", "parola"}:
        print(__doc__)
        return 2
    komut, *arg = argv
    with oturum() as db:
        if komut == "liste":
            for u in db.scalars(select(AppUser).order_by(AppUser.username)):
                tur = "AD" if u.is_ad_user else ("yerel" if u.password_hash else "-")
                print(f"{u.username:<24} {u.role:<11} {'aktif' if u.active else 'PASIF':<6} {tur:<6} {u.display_name}")
            return 0
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
