# Uygulama raporu

Tarih: 2026-10-03. Kapsam: OZET.md icindeki ilk 10 is. Is kurali (musteri, skor, SLA) yok. `api.py`, `depo.py`, `app-1.tsx`, `package.json` degismedi. Flask `api.py` ve `depo.py` `py_compile` cikis 0.

## Yapilanlar

1. GECTI. `GET /api/v1/health` 200. Komut: `python -m pytest tests/test_health.py -q` -> `1 passed`.
2. GECTI. `backend/pyproject.toml`, sozlesme `backend/.importlinter` ile ayni. Komut: `lint-imports` -> `Contracts: 2 kept, 0 broken`.
3. GECTI. Katalog 17 prod anahtar + topoloji. Komut: `pytest tests/test_catalog.py -q` -> `2 passed`.
4. GECTI. SQLite `PRAGMA journal_mode` -> `wal`.
5. GECTI. Alembic `0001_users` sonra kolonlar: `id,username,full_name,is_admin,role,allowed_modules,is_active,ad_domain,is_ad_user,is_2fa_enabled`. `pin_code` ve `totp_secret` yok. `0002_audit` sonrasi tablolar: `alembic_version`, `users`, `audit_event`.
6. GECTI. Oturum cerezi: `HttpOnly; Path=/; SameSite=lax; Secure` (ayar acikken). Govdede token yok (`body_has_token False`). Secure kapaliyken `secure` bayragi yok.
7. GECTI. Yerel kullanici ortam degiskeni, parola repoda yok. Dogru 200, yanlis 401, `ldap3.Connection` cagrisi 0. Bilinmeyen kullanici sahte AD'ye duser, LDAP 0.
8. GECTI. TeamMember + utilizasyon 403, admin 200, talep giris yapana 200, anonim 401.
9. GECTI. Tek `audit_event`. 403 sonrasi satir +1. Satirda pin/totp/cookie yok. `pin_code` ayrintisi `ValueError`, satir artmaz. Kolonlar: `id,created_at,actor_id,action,module,target_id,result,path,detail`.
10. GECTI. Kabuk `src/shell`, 14 kart prod sirasi (`dash-card-ekip` ... `dash-card-baglantili`). `pytest tests/test_home_cards.py` 1 passed. `tsc -b` cikis 0. `App.tsx` hala `App1`. `app-1.tsx` degismedi.

Son tur: `pytest -q` -> `14 passed`. `lint-imports` -> `2 kept, 0 broken`.

## Degisen / eklenen dosyalar

Doldurulan yer tutucular: `backend/app/main.py`, `app/__init__.py`, `core/config.py`, `core/errors.py`, `core/session.py`, `core/authz.py`, `core/audit.py`, `data/base.py`, `data/gateway.py`, `adapters/ad_fake.py`, `modules/catalog.py`, `modules/contracts.py`, `modules/musteri/schemas.py`, `alembic.ini`, `tests/conftest.py`, `tests/test_health.py`, `tests/test_import_boundaries.py`, `ekran-react/src/shell/layout.tsx`, `shell/nav.tsx`, `shared/empty.tsx`, `lib/i18n/tr.ts`, `lib/i18n/en.ts`.

Yeni: `backend/pyproject.toml`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_users.py`, `alembic/versions/0002_audit_event.py`, test dosyalari `test_catalog.py`, `test_gateway_wal.py`, `test_alembic_users.py`, `test_session_cookie.py`, `test_login.py`, `test_authz.py`, `test_audit.py`, `test_home_cards.py`, `test_masking.py`, `ekran-react/src/shell/home-cards.ts`, bu rapor.

Kazara kalan, uygulamaya bagli degil: `backend/_gen_task1.py`, `backend/_catalog_src.json`. Silme yasağı nedeniyle duruyorlar. `backend/var/tamlife.db` test sirasinda olusmus olabilir; `instance/sirket.db` degil.

## Kalanlar

- Modul is kurallari (faz 2): musteri, takvim, onedesk, utilizasyon, ekip, rapor.
- Bos modul dosyalari (models/service/routes/summary) cogu hala 0 bayt. routes service import etmiyor; linter kendi modulunu de yasakliyor (`00`).
- Kabuk `App.tsx` icine baglanmadi. Canli ekran hala App1. Menu sirasi yeni kabuk kaynak dosyasinda.
- `package.json` `api:uret` 8118 ve `api.ts` 8119 duruyor. Hedef port 8117 yalniz ayarda. Bu dosyalar onay olmadan degistirilmedi.
- Tailwind v4, 2FA akisi, Playwright, EN ceviri, veri tasima betigi (`migrate.py` bos).
- Oracle sahte adaptoru bos. Gercek AD/Oracle cagrilmadi.
- Denetim baslangicta tablo yoksa `create(checkfirst)` ile acilir; sema kaynagi yine Alembic revizyonudur.
- CSRF 403 ara katmandan doner, `audit_event` satiri HTTP 403 (`HTTPException`) icin yazilir.

## Yeni acik sorular

`00-acik-sorular.md` sonuna 2026-10-03 dogrulama notu eklendi. Yeni basliklar:

- 401/403 icin prod kod listesinde ayri kod yok. Gecici `TL-SRV-01` / `TL-MOD-01` kalsin mi?
- import-linter kendi `service` importunu ihlal sayiyor. Sozlesme `independence` tipine donussun mu, yoksa routes service cagirmasin mi?
- Kabuk ne zaman `App.tsx` icinden acilacak? App1 kalkmadan once hangi cikis testi?
- Port celiskisi (8117 ayar, 8119 `api.ts`, 8118 script) hangi dosyada kapanacak? `package.json` bu turda kilitli.
- `audit_event` hem Alembic hem `checkfirst` ile aciliyor. Yalniz Alembic mi kalsin?
- Q4 ve Q5 sahibi hala yok: kullanim ekip / musteri karti, karar yok.
