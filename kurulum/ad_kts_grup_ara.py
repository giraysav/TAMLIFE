# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""AD'de KTS_ ile baslayan gruplari listeler (SALT OKUNUR). Parola yalniz gizli girdiyle alinir; hicbir yere yazilmaz.

Calistirma (kendi terminalinizde):
  E:\\TAMLIFE\\.venv\\Scripts\\python.exe -I E:\\TAMLIFE\\kurulum\\ad_kts_grup_ara.py
Cikti: grup adi | aciklama | uye sayisi | DN, ardindan giren hesabin kendi KTS_ uyelikleri.
"""

from __future__ import annotations

import getpass
import sys

sys.path.insert(0, r"E:\TAMLIFE\backend")
import dotenv  # noqa: E402

dotenv.load_dotenv(r"E:\TAMLIFE\backend\.env")

from app import ad  # noqa: E402
from app.config import get_settings  # noqa: E402


def main() -> int:
    a = get_settings()
    kullanici = input("AD kullanici adi (kisa ad / ad@alan / ALAN\\ad): ").strip()
    parola = getpass.getpass("AD parolasi (gizli): ")
    kisa, _ = ad.domain_ayristir(kullanici)
    lib = ad._ldap()  # noqa: SLF001
    conn = lib.Connection(ad._sunucu(lib, a), user=ad._oturum_adi(kullanici), password=parola, authentication=lib.SIMPLE, receive_timeout=30)  # noqa: SLF001
    parola = ""
    if not conn.bind():
        print("[-] AD baglantisi reddedildi.")
        return 1
    kok = a.ad_arama_koku.strip() or ",".join(f"DC={p}" for p in a.ad_domain.strip().split("."))
    print(f"[i] Arama koku: {kok}")
    try:
        conn.search(kok, "(&(objectClass=group)(cn=KTS_*))", attributes=["cn", "description", "distinguishedName", "member"], paged_size=200)
        gruplar = list(conn.entries)
        print(f"[+] KTS_ ile baslayan grup: {len(gruplar)}")
        for g in gruplar:
            uye = len(g.member.values) if "member" in g else 0
            print(f"    {g.cn.value} | {g.description.value if 'description' in g else ''} | uye={uye} | {g.distinguishedName.value}")
            if "--uyeler" in sys.argv and uye:  # her grubun uyeleri (dogrudan uyelik; CN = gorunen ad)
                for dn in sorted(str(d) for d in g.member.values):
                    print("        -", dn.split(",OU=")[0].split(",DC=")[0])
        conn.search(kok, f"(&(objectClass=user)(sAMAccountName={lib.kacis(kisa)}))", attributes=["memberOf"], size_limit=1)
        if conn.entries and "memberOf" in conn.entries[0]:
            benim = [str(d) for d in conn.entries[0].memberOf.values if "CN=KTS_" in str(d).upper()]
            print(f"[i] Bu hesabin KTS_ uyelikleri: {len(benim)}")
            for d in benim:
                print("    ", d)
    finally:
        conn.unbind()
    return 0


if __name__ == "__main__":
    sys.exit(main())
