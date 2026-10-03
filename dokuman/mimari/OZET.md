# OZET

Tarih: 2026-10-03. Tasarim belgeleri `dokuman/mimari/`. Kod yazilmadi. Mevcut `backend/api.py` Flask'tir; hedef FastAPI modul monolitidir.

## Kararlar

- Tek dagitim, mikroservis yok, SSR yok.
- FastAPI, Python 3.12, Pydantic v2, SQLAlchemy 2, Alembic, SQLite WAL, faz 4 PostgreSQL.
- React 19, TypeScript, Vite, Tailwind v4 (bugun v3), shadcn/ui, TanStack Query/Table/Router, Hook Form, Zod, Recharts.
- Katalog anahtari prod `MODULLER` (17). v3.5 `modul.id` (`ozet`, `sms`, `izin`) klasor adi degil.
- Modul kendi tablosu; baska modulu yalniz `summary.py`.
- AD ve Oracle sahte adapt?r. Canliya baglanti yok.
- Roller: `admin`, `TeamMngr`, `TeamMember`. Cerez HttpOnly + SameSite Lax. Secure, TLS arkasinda true.
- Gizli kolon tasinmaz: `pin_code`, `totp_secret`. `.env` ve `ayar.json` govdesi belgede yok.
- Prod 104 route dekoratoru. v3.5 14 Flask yolu, `/api/v1` degil. Hedef on ek `/api/v1`.

## Acik sorular

Tam liste `00-acik-sorular.md`. Ilk uc: takvim tablo sahibi, topoloji modul mu, denetim tek tablo mu.

## Siradaki 10 is

Her madde tek basina kontrol edilir. Onceki kirilirsa sonraki baslamaz. Hicbiri mevcut `backend/`, `backend-api/`, `ekran-react/` dosyasini yeniden adlandirmaz.

1. `backend/app/main.py` iskeleti (yeni yol; `api.py` durur). Kontrol: dosya var, `GET /api/v1/health` 200, is kurali yok.
2. `pyproject.toml` + import-linter metni `10` ile ayni. Kontrol: komut 0 ihlal, modul cift import yok cunku henuz capraz import yok.
3. `app/modules/catalog.py` 17 prod anahtar, bayraklar `03` tablosu. Kontrol: pytest kume esitligi `MODULLER` anahtarlarina (topoloji haric).
4. `app/data/gateway.py` SQLite WAL. Kontrol: `PRAGMA journal_mode` = `wal` (bugun `ortak.db` = `delete`).
5. Alembic ilk revizyon, bos sema, `users` tablosunda `pin_code` ve `totp_secret` yok. Kontrol: upgrade sonra kolon listesi.
6. `core/session.py` HttpOnly, SameSite=Lax, Secure ayari TLS'te true. Kontrol: `Set-Cookie` bayraklari; govdede token yok.
7. Sahte AD + yerel test kullanicisi, parola repoda yok. Kontrol: dogru parola 200, yanlis 401, gercek LDAP host cagrisi 0.
8. `core/authz.py` uc rol. Kontrol: TeamMember + `utilizasyon` = 403; admin = 200; `talep` giris yapana acik.
9. `core/audit.py` tek tablo, gizli alan reddi. Kontrol: yazilan satirdan pin/totp/cerez kolonu yok; bir 403 sonrasi audit sayisi +1.
10. `ekran-react` kabuk: menu prod `ANA_SAYFA_KUTUCUKLARI` sirasi, token `08` tablosu bozulmadan. Kontrol: 14 ana sayfa karti JSON veya DOM sirasi; Tailwind v4 ayri madde, bu adim v3 dosyasini silmez.

Modul is kurali (musteri, skor, SLA) bu ona girmez. O is faz 2 (`09`) ve `04` P1 satiridir.
