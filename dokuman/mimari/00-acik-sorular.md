# 00 ? Acik sorular

Karar verilmeden kod yazilmayan basliklar. Her madde bir dosyaya baglidir. "dogrulanmadi" = bu taramada kaynak yok veya govde okunmadi.

## Kararlar

- Bu liste kapanmadan `10` iskeleti disinda is kurali yazilmaz.
- Kapali sayilanlar (tekrar acilmaz): moduler monolit, FastAPI + React 19 Vite, SQLite sonra PostgreSQL faz 4, Oracle salt okunur ve sahte adapt?r, roller `admin` / `TeamMngr` / `TeamMember`, cerez HttpOnly + SameSite, mikroservis yok, SSR yok.

## Acik sorular

1. `takvim` ve `takvim_ozet` ayni `calendar_records` tablosuna saglik kontrolunde bagli (`moduller.py`). Tek sahip kim? Oneri `05`: sahip `takvim`. Kaynak: `03`, `05`.
2. `topoloji` katalogda yok, registry'de var, HTTP yetkisi `musteri`. Ayri modul mu? Oneri `04`: klasor var, menu yok, `in_nav=false`. Kaynak: `04`.
3. `gelir_uretim` ve `toptan` icin tablo yok. Bos kart olarak mi kalacak? Kaynak: `04`, `05`.
4. `matrix_configs` ve `daily_tasks` sahibi dogrulanmadi. Kaynak: `05`.
5. `internal_scraped_data` sahibi dogrulanmadi. Kaynak: `05`.
6. Denetim: prod kisi basi `u_*` tablo + `kullanici_loglari` + `sistem_loglari` + v3.5 `kullanici/<ad>.db`. Hedef tek `audit_event` mi? Oneri `05`: tek tablo. Kaynak: `05`, `06`.
7. CSRF hedefte zorunlu mu? Prod'da `csrf_protect` var, v3.5'te yok. Kaynak: `06`.
8. 2FA akisi (`is_2fa_enabled`, `totp_secret`) hedefe girer mi? Kolon var, akis dogrulanmadi. Deger okunmadi. Kaynak: `06`.
9. Bosluk zaman asimi v3.5'te kac dakika: dogrulanmadi. Prod sabitleri `06`.
10. Windows hizmeti kurulum birimi var mi: dogrulanmadi. Prod `start_server.bat` / Waitress / `dagitici.py` / `tls_vekili.ps1`. Kaynak: `01`.
11. Tek uvicorn mu, prod gibi sinirli ciftlik mi? SQLite tek yazici notu `server.py`. Kaynak: `01`, `09`.
12. Eski `/api/*` yollari kirilinca ince uyumluluk katmani olacak mi? Kaynak: `07`.
13. JSON govde tavan 50 MiB (prod) mi 21 MiB (v3.5) mi 1 MiB (oneri) mi? Kaynak: `07`.
14. `GET /api/v1/teams` sablon adi mi, yoksa `tam_personal_summary` mi kalacak? Kaynak: `10`, `07`.
15. Musteri karti 21 alan izni (`MUSTERI_KARTI_ALANLARI`) geri gelecek mi? 2026-09-29 notu kaldirildi diyor. Kaynak: `06`.
16. EN sozluk metinleri yok. Kim cevirir? Kaynak: `08`.
17. Tailwind v4 gecisinde `tailwind.config.js` silinecek mi, token CSS'te mi kalacak? Oneri: CSS. Kaynak: `08`.
18. `App1` kabuk olarak kalacak mi? Kaynak: `08`.
19. `tsconfig` strict bugun acik mi: dogrulanmadi. Kaynak: `08`.
20. `workflow_migration.py` ve `ceviri_modeli` dizini govde/varlik: dogrulanmadi. Kaynak: `04`, `05`.
21. Port: `api.ts` 8119, `api:uret` 8118. Hangisi? Kaynak: `01`, `07`.
22. `instance/sirket.db` (users 0 satir) silinecek mi, yok sayilacak mi? `depo.py` kullanmiyor. Kaynak: `02`, `05`.
23. `backend-api/` (app.py yok) duracak mi? Kaynak: `02`.
24. Faz tarihi ve geri donus penceresi kac gun? Kaynak: `09`.
25. Maskeleme hangi kolonlarda acik? `customers.name` dahil mi? Kaynak: `05`.
26. `roller` ve `talep` v3.5 `ortak.modul` 15 satirinda yok. Tohum prod `MODULLER` (17) ile degisecek mi? Kaynak: `03`.
27. Skor yazimi `projects_bp` icinde, sahip onerisi utilizasyon. Rota tasiyinca URL degisir mi? Kaynak: `04`, `07`.
28. `sla_deposu.py` hem rapor grafigi hem ATS. Tablo bolme `05` onerisine uyulacak mi? Kaynak: `04`.
29. Playwright ve mypy kurulu mu: dogrulanmadi. v3.5 `tests/` yok. Kaynak: `09`.
30. Prod testleri yesil mi: bu oturumda calistirilmadi. Kaynak: `09`.

## Dogrulanamayan dosyalar

v3.5'te yok: `dokuman/MIGRASYON_PLANI.md`, `dokuman/MIMARI_AGAC.md`, `backend/app/moduller/katalog.py`, `backend/app/cekirdek/sozlesme.py`, `backend/app/veri/kapi.py`, `backend-api/app.py`, `backend/app/` tamami, `tests/`, `alembic/`, `pyproject.toml`, `requirements.txt`, `ekran-react/components.json`.

Var olan v3.5 kodu: `backend/api.py`, `backend/depo.py`, `backend/ayar.json` (icerik yazilmadi), `dokuman/TEKNOLOJI_ANALIZI.md`, `ekran-react` SPA, `veri/*.db`.


## Dogrulama 2026-10-03 (uygulama)

Kod yazildi. Asagisi arama sonucu; tasarim kararlarinin yerine gecmez.

- Q1 takvim tablo sahibi: gecici varsayilan `takvim`. Kod tasimadi.
- Q2 topoloji: katalogda ayri modul, `in_nav=false`, `yetki=musteri`. `10` metni router'i `main.py` icinde yalniz yorum satiri der. Kod, router dosyasi `router` verirse baglar (bugun routes bos, bagli degil). Celiski burada kayitli; `10` sessiz degistirilmedi.
- Q3 gelir_uretim ve toptan: ana sayfa karti durur, kabukta "Kayit yok".
- Q4 matrix_configs ve daily_tasks sahibi: prod `models.py` siniflari var. `daily_tasks` okumasi `kutucuklar/ekip/servis.py`. `matrix_configs` okumasi `operations_bp.py` ve `kutucuklar/portfoy/kart/`. Katalogda tek sahip alani yok. Sahip karari dogrulanmadi.
- Q5 internal_scraped_data: `Customer` iliskisi ve `kutucuklar/portfoy/kart/servis.py` icinde `customer_id` sorgusu var. Sahip alani yok. Sahip karari dogrulanmadi.
- Q6 tek `audit_event`: uygulandi (`0002_audit`).
- Q7 CSRF: durum degistiren istekte zorunlu. Prod kod listesinde ayri oturum kodu yok; 401 `TL-SRV-01`, 403 `TL-MOD-01`. Bu esleme gecicidir.
- Q8 2FA akisi yok. `users.is_2fa_enabled` kolonu durur; `pin_code` ve `totp_secret` yok.
- Q11 tek surec, bellek ici oturum. SQLite dosyasi `backend/var/tamlife.db` (test/dev). `instance/sirket.db` acilmadi.
- Q12 eski `/api` koprusu yok.
- Q13 JSON 1 MiB, multipart 20 MiB.
- Q17 Tailwind v4 yok. Q18 `App.tsx` hala `App1`. Yeni kabuk `src/shell`, App1'e baglanmadi.
- Q19 `ekran-react/tsconfig.app.json` icinde `strict` anahtari yok (TypeScript varsayilani kapali). Acik degil.
- Q20 `backend/app/workflow_migration.py` var (3556 bayt, skor/yetki gecis yardimcisi). `ceviri_modeli/` dizini bu makinede yok; yalniz `backend/app/ceviri.py` ve dokuman referansi. Dizin varligi dogrulanmadi (yok).
- Q21 port 8117 yalniz `core/config.py`. `package.json` ve `api.ts` (8119) degistirilmedi; cakisma suruyor.
- Q25 maskeleme varsayilan acik. Yardimci `musteri/schemas.py` `mask_text`. Musteri satiri henuz donmuyor.
- import-linter sozlesmesi modulun kendi `service`/`models` importunu da yasakliyor. `03` buna izin verir. Kod sozlesmeyi bozmamak icin routes icinden service import etmiyor. Sozlesme dosyasi degismedi.
- `05` `base.py` modul modellerini import eder der. Linter `data` -> `modules` yasak. Kayit `alembic/env.py` icinden. `data/base.py` import etmiyor.
