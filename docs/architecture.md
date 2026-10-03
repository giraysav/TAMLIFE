# TAMLIFE v3.5 mimari

Üç alan. Canlı AD ve canlı Oracle bağlantısı yoktur. Üretim `TAM_Life` ve `Secure_DB` bu ağacın dışındadır ve salt okunurdur. Müşteri satırı kopyalanmaz.

## 1. Dizin (AD/LDAP)

Kimlik `backend/app/ad_fake.py` içindeki sahte adaptörle doğrulanır. `ldap3` yoktur, soket açılmaz, bind yapılmaz.

Yuvalar ortam değişkenidir: `TAMLIFE_AD_HOST`, `TAMLIFE_AD_PORT`, `TAMLIFE_AD_USE_SSL`, `TAMLIFE_AD_BASE_DN`, `TAMLIFE_AD_BIND_USER`, `TAMLIFE_AD_BIND_PASSWORD`. Parola dosyaya yazılmaz. Yuva dolu olsa bile adaptör gerçek dizine gitmez.

Yerel deneme kullanıcısı yalnız `TAMLIFE_LOCAL_USER`, `TAMLIFE_LOCAL_PASSWORD` ve `TAMLIFE_LOCAL_ROLE` ile bellekte kontrol edilir. Oturum çerezi HttpOnly ve SameSite Lax'tir. Çerez değeri JSON gövdesine konmaz.

Roller: `admin`, `TeamMngr`, `TeamMember`. `utilizasyon` ve `roller` yalnız admin içindir. `talep` giriş yapana açıktır.

## 2. Panel veritabanı (PostgreSQL)

Tüm panel şeması PostgreSQL içindir. Adres `TAMLIFE_DATABASE_URL`. Boş ise varsayılan `postgresql+psycopg://localhost:5432/tamlife` (parola yok; veritabanı `tamlife`, sunucu `localhost`, port `5432`).

Geçit `backend/app/gateway.py` içe aktarılırken bağlanmaz. Şema `backend/app/models.py`. Sürüm `backend/alembic` (`0001_panel_schema`). Alembic aynı adresi kullanır.

Tablolar modül sahibine göre boş açılır: müşteri, takvim, rapor, proje, onedesk, utilizasyon, talep, sms, apn, radar, sunum, gelir üretim, toptan. Kimlik `app_user`. Denetim tek tablodur: `audit_event`. `pin_code` ve `totp_secret` kolonları yoktur. Denetim metninde parola, pin ve çerez reddedilir.

Bu makinede `psql` yoksa PostgreSQL kurulu sayılmaz. Adres ayarlanmıştır; sunucu başlatılmamıştır.

## 3. Dışarıdan gelen veritabanı

Oracle REPORTDB ve ikinci kaynak yalnız yuvadır.

| Anahtar | Tür | Ortam değişkeni |
|---|---|---|
| reportdb | oracle | `TAMLIFE_REPORTDB_DSN` |
| secondary | unconfigured | `TAMLIFE_SECONDARY_DSN` |

DSN değeri repoda ve `external_source` satırında yoktur. Satır yalnız ortam değişkeninin adını tutar. Sürücü yüklenmez, canlı sorgu yoktur. `connect()` her zaman kapalı kalır.

Gelen veri `ingest_batch` ve `ingest_record` tablolarına düşer. Dosya bırakma yeri `data/incoming` boş bırakılır.

## Kök

İngilizce kök: `backend`, `web`, `data`, `docs`. React kabuğu `web` altındadır ve iş kuralı taşımaz.
