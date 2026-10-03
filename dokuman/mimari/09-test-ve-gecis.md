# 09 ? Test ve gecis

## Kararlar

- Piramit: cok sayida pytest (servis, yetki, sayim), az Vitest (saf fonksiyon, sozluk anahtari), az Playwright (giris, menu, bir liste).
- Uretim veritabanina test yazmaz. Prod kopyasi salt okunur sayim kaynagidir (`05`).
- Parite: ayni girdi ozeti, ayni sayi. Piksel paritesi yok. HTML sayfa ile SPA gorunumu karsilastirilmaz.
- Araclar: pytest, Vitest, Playwright, ruff, mypy, `tsc` strict, oxlint (bugun `ekran-react` script `lint`: oxlint), import-linter.
- v3.5'te `tests/` yok, `alembic/` yok, `pyproject.toml` yok, `requirements.txt` yok. `.pytest_cache` kokte var; bu, test dosyasi oldugu anlamina gelmez.
- Prod `D:\Project\TAM_Life\TAMLIFE\tests` altinda 40 `test_*.py` sayildi (boyutlar dosya listesinde). Bunlar Flask uygulamasini kosar. v3.5'e kopyalanmaz; cikis olcutu olarak hangi davranisi kilitledikleri okunur.

## Acik sorular

- Playwright tarayici paketi kurulu mu: dogrulanmadi.
- Prod testleri bu oturumda calistirilmadi. Yesil/kirmizi bilinmiyor.
- Faz tarihleri yok. `MIGRASYON_PLANI.md` yok.
- Geri donus penceresi kac gun: karar yok. Asagidaki rollback tekniktir.

## Piramit

| Katman | Ne | Nerede | Veri |
|---|---|---|---|
| Birim | `service` saf hesap, katalog bayragi, hata kodu | `backend/tests/modules` | bellek ici SQLite |
| Sozlesme | OpenAPI semasi, 401/403, sayfalama siniri | `backend/tests/test_api_*.py` | bos sema + tohum rol |
| Sinir | import-linter | `pyproject` + CI komutu | kod |
| Arayuz birim | sozluk anahtari esittir, bos/hata bileseni | Vitest | ag yok |
| U?tan uca | yerel kullanici giris, menu sirasi, musteri liste bos/dolu | Playwright | ayri sqlite dosyasi |
| Parite | asagida | pytest | salt okunur prod kopyasi |

Prod'da kilit oldugu dosya adindan gorulenler (govde tek tek okunmadi): `test_kutucuk_agaci.py`, `test_route_gates.py`, `test_security_gate.py`, `test_access_auth.py`, `test_workspace_api.py`, `test_depo_yerlesimi.py`, `test_moduller_2026_09_28.py`. Parite senaryosu yazilirken bu adlar kontrol listesidir; iddia "test gecti" degildir.

## Parite testi

Girdi: salt okunur kopya yolu parametre. Cikti: sayi.

1. Katalog anahtarlari prod `MODULLER` ile hedef `catalog.py` kumesel esit (17 anahtar; topoloji eklenirse kume 18 olur, karar 00).
2. Rol kurallari: admin 17, TeamMngr 15 (utilizasyon ve roller haric), TeamMember bos izin + talep.
3. Tablo sayimi `05` betigi: kaynak count = hedef count, haric tablolar ayri satir.
4. Bir musteri listesi sayfasi: `total` prod sorgu sayisiyla ayni. Satir govdesi teste basilmaz; yalniz `total` ve ilk sayfanin `id` kumesi (id sayi, ad degil) karsilastirilir.
5. Ozet karti: prod `ozet_hepsi` hata yutma davranisi ? bir modul exception, diger anahtarlar durur.

Basarisiz parite gecisi durdurur. Uretim DNS'i cevrilmez.

## Fazlar ve cikis

Hepsi tasarim. Tarih yok.

| Faz | Is | Cikis (olculebilir) |
|---|---|---|
| 0 | Iskelet: klasor, bos modul, health, catalog, import-linter, bos sqlite WAL | `GET /api/v1/health` 200; import-linter 0 ihlal; `journal_mode=wal`; mevcut `api.py` hala durur |
| 1 | core oturum, roller, sahte AD, audit, rate limit, SPA kabuk | yerel kullanici 200; yanlis parola 401; TeamMember admin 403; denetim satiri sayisi +1; pin/totp kolonu yok |
| 2 | P1 moduller: musteri, takvim, takvim_ozet, onedesk (sahte), utilizasyon, ekip, rapor | `04` P1 satirlari icin en az bir GET testi; parite sayimi `05` tablolari icin esit; Oracle gercek host cagrisi 0 |
| 3 | P2/P3 kartlar, e-posta sahte, talep, topoloji bayragi | katalog menusu prod sirasiyla ayni (Playwright veya JSON); bos kartlar 200 + empty |
| 4 | PostgreSQL | ayni pytest yesil; sqlite yazici kapali; geri donus dump'i alindi; WAL sqlite dosyasi salt okunur arsiv |

Faz N, N-1 cikis listesi kirilirsa baslamaz. `backend/api.py` faz 2 bitene kadar silinmez. `ekran-react` eski `App1` faz 3 bitene kadar import edilebilir kalir.

## Geri donus

- Uygulama: onceki paket (git etiket). Veritabani semasi geri alinmaz; onceki paket onceki dosyayi acar.
- SQLite: gecis oncesi dosya kopyasi baska disk (`depo_yollari.py` yedek notu: veri ile yedek ayni diskte olmasin). Kopya bu tasarimda elle; betik yazilmaz.
- PostgreSQL faz 4: gecis penceresinde sqlite durur. Yeni yazma yalniz bir motorda. Geri donus, pencerede PostgreSQL'e yazilan satiri sqlite'a islemez; pencere kisa tutulur (karar: tek bakim araligi). Sayim uyusmazsa geri donulur.
- `ayar.json` ve `.env` geri donuste de belgeye yazilmaz.

## Riskler

| Risk | Neden | Ne yapilir |
|---|---|---|
| Cift katalog | `moduller.py`, `registry.py`, `api.py` sozluk, `ortak.modul` | faz 0'da tek `catalog.py`; digerleri okunur referans |
| Iki sahip `calendar_records` | `MODUL_TABLOLARI` | karar kapanmadan tasima yok |
| Gizli kolon | `pin_code`, `totp_secret` | haric listesi testi: hedef semada kolon yok |
| Canli AD/Oracle | prod servisleri gercek | adapt?r testi host cagrisini monkeypatch ile sayar, beklenen 0 |
| SQLite tek yazici | `server.py` notu | faz 4'e kadar tek yazma sureci |
| Port celiskisi 8118/8119 | iki dize | tek ayar; test sabit port kullanmaz |
| v3.5 sema != prod sema | `canli.skor` vs `skor_gecmisi` | v3.5 tablolari hedef sema degil |
| `backup.py` tum kolon | JSON yedek | hedef yedek haric listesiz calismaz |
| IIS yok | `dagitici.py` IIS kaldirildi diyor | hedef vekil Python dagitici veya `tls_vekili.ps1`; IIS onerilmez |
| Test yok v3.5 | `tests/` yok | faz 0 cikisina ilk pytest girer |

## Prod test dosyalari (ad ve bayt)

Kok `D:\Project\TAM_Life\TAMLIFE\tests`. Calistirilmadi. v3.5'e kopyalanmaz.

`test_access_auth.py` 13028, `test_ad_kimlik.py` 3966, `test_admin_flows.py` 126966, `test_arayuz_sadelestirme.py` 6696, `test_ats_analizi.py` 12809, `test_dagitici.py` 33619, `test_denetim_2026_09_16.py` 52987, `test_depo_yerlesimi.py` 10529, `test_frontend_assets.py` 6613, `test_integrations.py` 8617, `test_istekler_2026_09_28b.py` 8331, `test_istekler_2026_09_29.py` 4457, `test_istekler_2026_09_29c.py` 9564, `test_istekler_2026_09_29d.py` 3451, `test_istekler_2026_09_30.py` 23876, `test_izleme.py` 37156, `test_kod_kontrol.py` 9708, `test_kutucuk_agaci.py` 13829, `test_log_eposta_ceviri.py` 15095, `test_moduller_2026_09_28.py` 12300, `test_musteri_karti.py` 6222, `test_musteri_karti_duzenleme.py` 12016, `test_musteri_karti_gorunum.py` 11153, `test_oturum_kilidi.py` 4282, `test_rapor_alicilari.py` 23421, `test_rapor_birimi.py` 7547, `test_route_gates.py` 2838, `test_sadelestirme.py` 14982, `test_security_gate.py` 24936, `test_skor_motoru.py` 13344, `test_sla_asistan.py` 16481, `test_sla_takip.py` 5767, `test_urun_tutar.py` 9521, `test_util_barem.py` 1622, `test_utilizasyon_portfoy.py` 8257, `test_veri_yonlendirici.py` 9318, `test_workflow_migration.py` 2584, `test_workspace_api.py` 9194, `test_workspace_delivery.py` 5112.

Faz 1 cikis testi su adlarin kapsadigi davranisi yeniden kurar, dosyayi tasimadan: `test_access_auth`, `test_security_gate`, `test_oturum_kilidi`, `test_route_gates`. Faz 2: `test_workspace_api`, `test_kutucuk_agaci`, `test_moduller_2026_09_28`, `test_sla_takip`, `test_skor_motoru`. Arac pytest. Prod `requirements-prod.txt` Flask, Flask-SQLAlchemy, Flask-Limiter, waitress, ldap3, oracledb, pandas, openpyxl icerir; FastAPI/Alembic/pytest satiri bu dosyada gorulmedi (liste kirpilmeden paket adlari okundu, pytest satiri yok).
