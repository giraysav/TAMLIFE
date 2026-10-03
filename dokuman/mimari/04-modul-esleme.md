# 04 ? Modul esleme

Yalniz kodda gorulen satirlar. Uydurma yol yok. Oncelik: P0 kimlik ve kabuk, P1 musteri/takvim/rapor, P2 diger kartlar, P3 bos icerik. Risk: veri sahibi belirsizse yuksek.

## Kararlar

- Hedef modul adi prod `MODULLER.anahtar` degeridir. v3.5 `modul.id` (`ozet`, `sms`, `izin`, `gelir`) hedef klasor adi degildir.
- Kutucuk klasoru `portfoy` hedefte `musteri` modulune gider. `ictapn` hedefte `tamsms` olur. `tamapn` ayri modul olarak kalir; prod'da ayri kutucuk klasoru yoktur.
- Ortak servisler modul degildir. `core` veya `adapters` altina iner. Tablo sahibi olmazlar; istisna denetim ve hiz siniri sayaclari (`05`, `06`).
- `topoloji`: ayri modul iskeleti acilir ama katalog bayragi `enabled=false` yazilir, ta ki acik soru kapanana kadar. Gerekce asagida.

## Acik sorular

- `topoloji` ana sayfa kutusu degil (`dash_card_id` None) ama `kutucuklar/topoloji/` (engine.py 12194 bayt) ve `POST /api/topology/analyze` vardir. Modul mu, `musteri` alt yetenegi mi?
- `gelir_uretim` ve `toptan` kart metni "icerik yakinda" (`moduller.py` aciklama alanlari). Tablo eslemesi `MODUL_TABLOLARI` icinde yok.
- `matrix_configs` hangi module ait: dogrulanmadi. Rota `operations_bp.py` `/api/matrix_config/<key>`.
- `daily_tasks` (0 satir) sahibi dogrulanmadi.

## Katalog satirlari

| Prod kaynak | Hedef modul | Oncelik | Risk | Bagimlilik |
|---|---|---|---|---|
| `moduller.py` `musteri`; `kutucuklar/portfoy/` (servis, kart, urun_tutar, ozet); blueprint `customer_bp.py` | musteri | P1 | yuksek: customers 200 satir, baska moduller customer_id tasir | roller/kimlik, rapor ozeti, onedesk ozeti, utilizasyon ozeti |
| `moduller.py` `takvim`; `kutucuklar/takvim/`; `operations_bp` takvim rotalari | takvim | P1 | orta: tek tablo iki katalog anahtari | kimlik (user_id) |
| `moduller.py` `takvim_ozet`; ayni takvim klasoru, kart `dash-card-takvim` | takvim_ozet | P1 | yuksek: tablo sahibi cakismasi | takvim.summary |
| `moduller.py` `onedesk`; `kutucuklar/onedesk/`; `topology_bp` `/api/onedesk/incidents` | onedesk | P1 | yuksek: analiz.db ats/sla + sahte Oracle | adapters.oracle_fake, musteri kimligi |
| `moduller.py` `utilizasyon` yalniz_admin; `kutucuklar/utilizasyon/` (skor_motoru, toplu_atama, veri_kaynaklari); `operations_bp` util rotalari | utilizasyon | P1 | yuksek: skor yazimi proje blueprint'inde de var | musteri.summary, adapters.oracle_fake, veri yonlendirici |
| `moduller.py` `roller` yalniz_admin; ayri kutucuk klasoru yok; `admin_bp` kullanici rotalari | roller | P0 | yuksek: `users` tablosu kimlikle ortak | core.session, core.authz |
| `moduller.py` `talep` herkese_acik; `kutucuklar/talep/`; `talep_bp.py` | talep | P2 | dusuk: gelistirme_talepleri 5 satir | kimlik |
| `moduller.py` `ekip`; `kutucuklar/ekip/`; `operations_bp` `/api/tam_personal_summary/<user_id>` | ekip | P1 | orta: kendi tablosu yok, `MODUL_TABLOLARI` degeri `users` | tum kart summary |
| `moduller.py` `rapor`; `kutucuklar/rapor/`; `customer_bp` aylik rapor rotalari | rapor | P1 | yuksek: panel.reports + analiz rapor_gonderim/taslak | eposta servisi, musteri, ceviri |
| `moduller.py` `proje`; `kutucuklar/proje/`; `projects_bp` proje rotalari | proje | P2 | orta | musteri.summary |
| `moduller.py` `tamsms`; `kutucuklar/ictapn/` (modul_kodu tamsms) | tamsms | P2 | orta: ict_revenues 0 satir | kimlik |
| `moduller.py` `tamapn`; klasor yok; `projects_bp` apn rotalari | tamapn | P2 | orta: apn_revenues 0 satir | kimlik |
| `moduller.py` `gelir_uretim`; klasor yok; `MODUL_TABLOLARI` yok | gelir_uretim | P3 | dusuk: bos kart | yok |
| `moduller.py` `toptan`; klasor yok; `MODUL_TABLOLARI` yok | toptan | P3 | dusuk: bos kart | yok |
| `moduller.py` `sunum`; `kutucuklar/sunum/`; `operations_bp` qbr rotalari | sunum | P2 | dusuk: qbr_reports 1 satir | kimlik |
| `moduller.py` `radar`; `kutucuklar/radar/`; `operations_bp` radar rotalari | radar | P2 | dusuk: radar_prospects 0 satir | kimlik |
| `moduller.py` `baglantili`; `kutucuklar/baglantili/` durum stub; `servis.py` 48 bayt | baglantili | P3 | dusuk | yok |
| `registry.py` id `topoloji`; `kutucuklar/topoloji/engine.py`; `POST /api/topology/analyze` (`modul_gerekli('musteri')`) | topoloji (bayrak kapali) veya musteri alt yetenek | P2 | yuksek: karar yok | musteri yetkisi |

## Topoloji karari (tasarim, kod yazilmaz)

Prod iki yere birden koyar: motor kutucukta, HTTP yetkisi `musteri` kapisinda, katalog anahtari yok. Hedef: `app/modules/topoloji/` iskeleti durur, `catalog` kaydi `in_nav=false` olur, rota `musteri` iznine bagli kalir. Ayri ana sayfa karti eklenmez. Bu, registry'deki `dash_card_id: None` ile uyumludur. Kataloga `topoloji` anahtari eklemek ayri bir karar ister (`00`).

## Ortak servisler

Hepsi `D:\Project\TAM_Life\TAMLIFE\backend\app\` altinda dogrulandi.

| Prod dosya | Hedef | Oncelik | Risk | Bagimlilik |
|---|---|---|---|---|
| `ad_service.py` (`ADConfig`, `ADAuthService`) | `adapters/ad_fake.py` + `core/session.py` giris kapisi | P0 | yuksek: canli AD yasak | yok (sahte) |
| `security.py` (login_required, admin_required, csrf, oturum) | `core/session.py`, `core/authz.py` | P0 | yuksek | users semasi, cerez |
| `eposta.py` | `core` yaninda `adapters/mail_fake.py` (dosya adi oneri) | P2 | orta: SMTP gercek gonderim bu fazda yok | rapor |
| `api_services.py` (Oracle kaynaklari, mock incidents listesi dosyada var) | `adapters/oracle_fake.py` | P1 | yuksek: canli Oracle yasak | onedesk, utilizasyon |
| `ats_analizi.py` | `onedesk/service.py` icine tasinacak saf fonksiyon | P1 | orta | onedesk tablolari |
| `sla_deposu.py` | `onedesk` + `rapor` sahipligi bolunmeli; tek dosya iki db | P1 | yuksek: analiz.db cok sahip | `05` sahip tablosu |
| `sla_takip.py` | `onedesk/service.py` | P1 | orta | sla_deposu acik kayit |
| `backup.py` | `data/migrate.py` degil; ayri `core` yedek iskeleti. JSON tum tablolari doker; gizli kolon ayiklanmadan calismaz | P2 | yuksek: pin/totp | `05` hari? tutma listesi |
| `ceviri.py` | `rapor` altinda `adapters` veya modul ici; model dizini `ceviri_modeli/tr_en` | P3 | orta: model dosyasi bu taramada dogrulanmadi | rapor |
| `asistan.py` | `core` disi ayri modul degil; rota bugun `POST /api/asistan` (`auth_bp`). Hedef modul yok, P3 | P3 | orta: dis model cagrisi | oturum |
| `kullanici_log.py` | `core/audit.py`; prod ayri sqlite, kisi basi `u_<id>` tablosu | P0 | yuksek: kisi tablosu deseni hedefte tek audit tablosu onerilir | `05` |
| `ortak_sinir.py` | `core/rate_limit.py` | P0 | orta | sistem db |
| `depo_yollari.py` | `data/gateway.py` yol politikasi | P0 | dusuk | yok |
| `hatalar.py` | `core/errors.py` | P0 | dusuk | yok |
| `extensions.py` (limiter, tr siralama) | `core/rate_limit.py` + `shared` TR sort | P1 | dusuk | yok |
| `models.py` | parcalanip modul `models.py` dosyalarina | P1 | yuksek | `05` |
| `moduller.py` | `catalog.py` + `authz.py` | P0 | yuksek: uc kopya | v3.5 ortak.db |
| `kutucuklar/registry.py` | `catalog.py` | P0 | orta | modul summary |
| `kutucuklar/veri/` (db_al, ham_depo, kurallar, ...) | `utilizasyon` alt yetenek; ayri katalog anahtari yok | P1 | yuksek: ham_veri.db | oracle_fake |
| `kutucuklar/_cekirdek/` | `core` + rapor cikti yardimcisi `rapor` | P2 | dusuk | rapor |
| `application/dashboard.py`, `navigation.py`, `workspace.py` | `ekip`/`shell` ozet toplayici; HTTP `workspace_api_bp` | P1 | orta | summary |
| `infrastructure/integrations.py` | `GET /api/v1/integrations` envanter; sir degeri yayinlamaz (dosya basligi) | P2 | yuksek: sir sizdirmama | admin |
| `workflow_migration.py` | `data/migrate.py` notu; govde bu belgede ozetlenmedi | P2 | dogrulanmadi | `05` |

v3.5 `backend/depo.py` bes dosya semasini acar (`ortak`, `sistem`, `canli`, `guven`, `yedek`) ve `kullanici/<ad>.db`. Bu, prod dort veritabaninin yerine gecen taslak depodur; tablo adlari prod ile ayni degildir (`05`).

## Blueprint -> modul (rota sayisi)

Prod backend'de 104 route dekoratoru sayildi (`@route` / `@get`). Dagitim:

| Dosya | Adet | Hedef |
|---|---|---|
| `app/__init__.py` `/api/health` | 1 | `main.py` health |
| `admin_bp.py` | 13 | roller + core audit/mail test |
| `auth_bp.py` | 4 | core.session + asistan P3 |
| `customer_bp.py` | 24 | musteri + rapor |
| `dashboard_bp.py` | 3 | eski HTML; hedefte yok (SPA) |
| `integrations_bp.py` | 1 | admin envanter |
| `operations_bp.py` | 14 | takvim, sunum, radar, ekip, utilizasyon, matrix (sahip acik) |
| `projects_bp.py` | 21 | proje, tamsms, tamapn, skor (utilizasyon) |
| `talep_bp.py` | 4 | talep |
| `topology_bp.py` | 2 | onedesk incidents + topoloji |
| `veri_bp.py` | 10 | utilizasyon veri yonlendirici |
| `workspace_api_bp.py` on ek `/api/v1` | 3 | shell: session, dashboard, customers |
| `workspace_bp.py` | 4 | eski HTML kabuk; hedefte yok |

Ayrinti yol listesi `07-api-tasarimi.md`.
