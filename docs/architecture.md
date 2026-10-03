# TAMLIFE v3.5 mimari

Üretim uygulaması `D:\Project\TAM_Life\TAMLIFE` bu ağacın dışındadır ve salt okunurdur. Müşteri satırı kopyalanmaz. Canlı AD bind ve canlı Oracle bağlantısı yoktur.

Eski yapıda her kutu `backend/app/kutucuklar/<ad>` altında ayrı duruyordu. v3.5 bunu tek listeye indirir: klasör başına modül yoktur.

## 1. Katalog

Tek kaynak `backend/app/catalog.py`. Kimlik, ad ve bayrak üç üretim kaydından birleştirildi:

- `backend/app/moduller.py` içindeki `MODULLER`
- aynı dosyadaki `ANA_SAYFA_KUTUCUKLARI`
- `backend/app/kutucuklar/registry.py` içindeki `KUTU_TANIMLARI`

Uydurma modül yoktur. Listede olmayan bir kutu eklenmedi. `ictapn` ayrı modül değildir; kayıt `tamsms` anahtarına bağlıdır. `portfoy` ayrı modül değildir; anahtar `musteri`dir. `talep`, `roller` ve `utilizasyon` ana sayfa kutusu değildir. `topoloji` ana sayfada yoktur ve `musteri` iznine bağlıdır.

Kimlikler: `musteri`, `takvim`, `takvim_ozet`, `onedesk`, `utilizasyon`, `roller`, `talep`, `ekip`, `rapor`, `proje`, `tamsms`, `tamapn`, `gelir_uretim`, `toptan`, `sunum`, `radar`, `baglantili`, `topoloji`.

Bayraklar üretimdeki anlamıyla durur. `yalniz_admin` olanlar `utilizasyon` ve `roller`. `herkese_acik` olan `talep`. Ana sayfada hazır olmayanlar `gelir_uretim`, `toptan` ve `baglantili` (`baglantili` kayıt durumu `stub`). Sağlık tabloları `MODUL_TABLOLARI` ile aynıdır.

## 2. Dizin (AD/LDAP)

Kimlik yuvası `backend/app/ad.py`. `ldap3` yoktur, soket açılmaz, bind yapılmaz. Ayrı `LDAP_*` anahtarı yoktur; eski servis LDAPS ayarını `AD_*` adlarıyla okur.

Anahtarlar (değer yok, varsayılan boş):

`AD_ENABLED`, `AD_SERVER`, `AD_DOMAIN`, `AD_USE_SSL`, `AD_CA_CERT_FILE`, `AD_IZINLI_ALANLAR`, `AD_ALAN_KONTROLU`, `AD_KIMLIK_KONTROLU`, `AD_IZINLI_GRUPLAR`, `AD_ARAMA_KOKU`, `AD_OTOMATIK_AC`.

Dolu sayılması için `AD_ENABLED=true` ve `AD_SERVER` ile `AD_DOMAIN` dolu olmalıdır. Yuva dolu olsa bile adaptör dizine gitmez. Parola ve anahtar değeri bu dosyaya ve API yanıtına yazılmaz; yanıt yalnız anahtar adını ve dolu olup olmadığını söyler.

Panel oturumu dizin değildir. `TAMLIFE_LOCAL_USER`, `TAMLIFE_LOCAL_PASSWORD` ve `TAMLIFE_LOCAL_ROLE` yalnız bellek içi panel kapısıdır. Oturum çerezi HttpOnly ve SameSite Lax'tir. Çerez değeri JSON gövdesine konmaz.

Roller: `admin`, `TeamMngr`, `TeamMember`. `utilizasyon` ve `roller` yalnız admin içindir. `talep` giriş yapana açıktır.

## 3. Dış kaynak (Oracle / OneDesk)

Liste `backend/app/external.py`. Her kaynak üretimdeki anahtar adlarını taşır. DSN değeri repoda yoktur. Sürücü yüklenmez. `connect()` kapalıdır.

Ortak: `ORACLE_CLIENT_DIR`.

OneDesk DB (REPORTDB) / Oracle (`ORACLE_REPORTDB_ENABLED`): `ORACLE_REPORTDB_ENABLED`, `ORACLE_REPORTDB_HOST`, `ORACLE_REPORTDB_PORT`, `ORACLE_REPORTDB_SERVICE_NAME`, `ORACLE_REPORTDB_USER`, `ORACLE_REPORTDB_PASSWORD`, `ORACLE_REPORTDB_QUERY`, `ORACLE_REPORTDB_TIMEOUT`, `ORACLE_REPORTDB_IMPORT_QUERY`, `ORACLE_REPORTDB_IMPORT_TIMEOUT`, `ORACLE_REPORTDB_URL`, `ONEDESK_BASE_URL`, `ONEDESK_API_KEY`.

Onent / Oracle (`ONENTDB_DB_ENABLED`): `ONENTDB_DB_ENABLED`, `ONENTDB_DB_HOST`, `ONENTDB_DB_PORT`, `ONENTDB_DB_SERVICE_NAME`, `ONENTDB_DB_USER`, `ONENTDB_DB_PASSWORD`, `ONENTDB_DB_QUERY`, `ONENTDB_DB_TIMEOUT`, `ONENTDB_DB_IMPORT_QUERY`, `ONENTDB_DB_IMPORT_TIMEOUT`, `ONENT_DB_URL`.

Ürün-Tutar / Oracle (`URUNTUTAR_DB_ENABLED`): `URUNTUTAR_DB_ENABLED`, `URUNTUTAR_DB_HOST`, `URUNTUTAR_DB_PORT`, `URUNTUTAR_DB_SERVICE_NAME`, `URUNTUTAR_DB_USER`, `URUNTUTAR_DB_PASSWORD`, `URUNTUTAR_DB_QUERY`, `URUNTUTAR_DB_TIMEOUT`, `URUNTUTAR_DB_IMPORT_QUERY`, `URUNTUTAR_DB_IMPORT_TIMEOUT`, `URUN_TUTAR_DB_URL`.

İçe alma kapıları aynı Oracle ön ekini kullanır. Açık olma anahtarı sorgu adıdır: `ORACLE_REPORTDB_IMPORT_QUERY`, `ONENTDB_DB_IMPORT_QUERY`.

OneDesk DB, canlı `.env`'deki adıyla `ORACLE_REPORTDB_*` ön ekini kullanır; eski kodun `ONEDESK_DB_*` adı kaldırıldı. `ONEDESK_BASE_URL` ve `ONEDESK_API_KEY` DB değil REST ayarıdır, adı değişmedi.

Üretim ham deposunun içe alma tabloları (`ham_veri.db`): `veri_setleri`, `ham_bloklar`, `kurallar`, `metrikler`, `uygulama_gunlugu`. Paneldeki boş iniş tabloları `ingest_batch` ve `ingest_record`dır; bunlar eski ham deponun adı değildir. Dosya bırakma yeri `data/incoming` boş bırakılır.

## 4. Panel veritabanı (PostgreSQL)

Panel şeması PostgreSQL içindir. Adres `TAMLIFE_DATABASE_URL`. Boş ise varsayılan `postgresql+psycopg://localhost:5432/tamlife` (parola yok).

Geçit `backend/app/gateway.py` içe aktarılırken bağlanmaz. Şema `backend/app/models.py`. Sürüm `backend/alembic` (`0001_panel_schema`).

`pin_code` ve `totp_secret` kolonları yoktur. Denetim metninde parola, pin ve çerez reddedilir.

## Kök

İngilizce kök: `backend`, `web`, `data`, `docs`. React kabuğu `web` altındadır ve iş kuralı taşımaz.

## 5. Yonetim

Yalniz admin oturumu. `GET /api/v1/admin`. Oturum yoksa 401, admin degilse 403.

Baglanti yuvalari yalniz dolu veya bos: AD (`AD_ENABLED` ile `AD_SERVER` ve `AD_DOMAIN`), `ORACLE_REPORTDB` (OneDesk DB), `ONENT`, `URUNTUTAR`. Deger donmez.

Veri yonetimi tablolari: `veri_setleri`, `ham_bloklar`, `kurallar`, `metrikler`, `uygulama_gunlugu`, `ingest_batch`, `ingest_record`. Satirlar `TAMLIFE_DATABASE_URL` ayarliysa Postgres'e yazilir. Adres donmez.

Sayfa `web` icinde bu iki bolumu gosterir. Katalog tek listedir; modul klasoru yoktur.

## CSRF (OpenAPI'de görünmez)

Giriş sonrası sunucu `tamlife_csrf` çerezini (JS'in okuyabildiği) ve `tamlife_session` çerezini (HttpOnly) verir. Durum değiştiren her istek (login hariç) `x-csrf-token` başlığında çerez değerini taşır; sunucu bunu oturumdaki değerle karşılaştırır. Ayrı bir `/csrf` rotası yoktur. İstemci: `ekran-react/src/lib/http.ts`. Tipler `npm run api:uret` ile canlı `/openapi.json`'dan üretilir (yalnız dev ortamında açık).
