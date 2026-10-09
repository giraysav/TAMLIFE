# TAMLIFE v3.5 (dev) — Claude için çalışma kuralları

Yanıtları **Türkçe**, kısa ve doğrudan ver (selamlama/özür/kapanış cümlesi yok). Karşındaki uzman sistem yöneticisi/geliştirici; temel kavramları açıklama.
Değişiklikleri tam dosya yerine yalnız değişen blok/diff olarak göster. Dosya okurken önce `Grep`, sonra yalnız ilgili aralık.

## Kapsam ve yön (2026-10-07 kararı — aşağıdaki eski bölümlerin önüne geçer)

- Bu depo ileride yapılacak **yeni migration'ın hedef kodudur**; tasarımı paralel yürütülür. Şimdilik **yalnız lokalde** çalışır.
- **`E:\TAMLIFE` (eski üretim, canlı) kapsam dışıdır:** ona bağlantı, API, vekil, SSO, dosya kopyası kurma/önerme. Tek istisna (2026-10-07, kullanıcı izni): **yalnız OKUMA** — panelin ihtiyacı olan kod/şema/mantık referans için okunup yeni yapıya uyarlanabilir. Yazma, çalıştırma, `.env`/DB/anahtar dosyası okuma, müşteri satırı kopyalama yok. Aşağıdaki "Üretime dokunma kuralları" üretimi korumak için geçerliliğini sürdürür.
- Üretim paneline gömme (Flask vekili, SSO ucu, `/admin/dev`, `deploy/prod/`, `build:prod`) 2026-10-07'de koddan **kaldırıldı**; geri dönüş yalnız git geçmişinde. Üretimde kalıntı: `backend/app/blueprints/dev_panel_bp.py` dosyası (`__init__.py`'de kayıtlı değil, zararsız); kaldırmak üretim tarafında kullanıcının işidir.
- Yerel çalıştırma: `backend\dev.ps1` (API `127.0.0.1:8117`, SQLite `backend/var/dev.db`). Arayüz: `cd ekran-react; npm run dev` (Vite `/api`'yi 8117'ye yönlendirir) ya da `backend\dev.ps1 -Arayuz` (derler, aynı portta sunar).
- Çalışma kimliği bu oturumda `TURKCELL\tamlifeadlog` (yerel yönetici); `E:\TAMLIFE_Dev` ağacının sahibi ve tam yetkilisidir.

## Kurumsal sunucu ve kimlik düzeni (EN ÖNEMLİ KURAL)

- Bu sunucu kurumsal (AD/LDAP) mimaridedir. **`TURKCELL\tcgsav` LDAP kullanıcısıdır; sunucuya yalnız onunla RDP login olunur.**
- **`ladinadmin` servis hesabıdır, yerel admin yetkisi vardır.** Tüm işlemlerde (yazma, git, süreç, servis, `.env`) `ladinadmin` kimliği kullanılır. Başka kullanıcıyla sunucuya login olunmaz/önerilmez.
- Oturum başında `whoami` ve yazma yetkisini doğrula. `E:\TAMLIFE` altında mevcut dosya değiştirilemiyorsa (EPERM) kimlik atlatmaya çalışma; **komutu veya betiği kullanıcıya ver**, kullanıcı `ladinadmin` ile çalıştırır. Yetki/izin gerekiyorsa aynı kural.
- `ladinadmin` parolasını isteme, yazma, saklama. Kimlik bilgisi deposunu (cmdkey vb.) araştırma.
- **Sır** (`.env` değerleri, parola, anahtar): ben üretmem/yazmam/göstermem.

## Ortamlar

| | Yol | Rol |
|---|---|---|
| **Üretim** | `E:\TAMLIFE` (Flask, canlı, ≤20 eşzamanlı kullanıcı) | Tek canlı klasör. Birinci kriter stabilite. |
| **Dev (bu depo)** | `E:\TAMLIFE_Dev\TAMLIFE_v3.5` (FastAPI + React) | Yeni panel tasarımı. Üretimden bağımsız süreç ve DB. |

### Üretime dokunma kuralları
- Üretimi **onay almadan** durdurma/başlatma/yeniden başlatma (`yonet.bat`), süreç öldürme, dosya silme, `pip install`, zamanlanmış görev/güvenlik duvarı değişikliği, `.env` düzenleme yok. Yapmadan önce komutu ve etkisini yaz.
- Üretim kodunu "ileride lazım olur" diye değiştirme. Şüphede kalırsan değiştirmeden sor.
- `_eski`, `_yeni`, `_onceki`, `_yedek` adlı klasör/dosya oluşturma (`E:\TAMLIFE` içinde). Sürüm numarası artırma, etiket (tag) atma yok; "sürüm" yalnız klasör adıdır.
- `.env`, veritabanı (`E:\Secure_DB`, `C:\Secure_DB`), `*.pfx/*.key/*.p12` taşınmaz ve içeriği paylaşılmaz. `.bat` dosyaları CRLF + saf ASCII, `.ps1` betikleri saf ASCII.
- AD/LDAP ile giren kullanıcı hiçbir yolla veritabanından silinmez. Acil durum hesabı `ladinadmin`; parolasına dokunma.
- Serbest (salt okuma): `yonet.bat durum|log`, `logs\` okuma, `isletim\saglik_kontrolu.ps1`.

## Yapı ve komutlar

- **Özellik paketleri** (`backend/app/`): `yonetim/` (admin: DB, arıza, günlük, oturum, sağlık), `tampon/` (Veri Girişi: kaynak → tampon → analiz → dağıtım), `musteri/`, `rapor/`, `skor/` (her biri `api.py`/`servis.py`; `skor/motor.py` saf hesap), `onedesk/` (alarm/talep/şikayet, top10, RCA, LLM kapısı), `gelir/` (ICT SMS, APN kurulum + müşteri çalışmaları), `takvim/` (izin&takvim, TAM Takvim, sunuma gönder). `yonetim` ile `tampon` birbirini import etmez; müşteri alanı tek yönlüdür: `skor` ← `musteri` ← `rapor`; `onedesk` → `tampon.depo` (yalnız okuma). Ortak kod çekirdekte (`ariza.py`, `ortak.py`). Yeni admin işlevi `yonetim/`e, yeni dış veri yolu `tampon/`a girer. Tasarım: `docs/yonetim-ve-tampon-tasarimi.md`; dizin: `docs/topoloji-ve-dizin.md`.
- **Hata sözleşmesi:** her servis hatası `ortak.UygulamaHatasi(kod, mesaj)` alt sınıfıdır (`MusteriHata`, `SkorHata`, `RolHata`, tampon/yönetim hataları); `main.py` tek işleyiciyle `{"detail": mesaj}` + durum koduna çevirir. Router'da `try/except` ile çevirme yazma; hatayı fırlat.
- Arayüzde yönetim **tek giriş, 6 bölüm** (`src/yonetim/`, adres `#/yonetim/<bölüm>`): yeni yönetim ekranı yeni dal değil, mevcut bölüme eklenir. Veri TanStack Query ile; bölümler lazy.
- Denetim kalıcıdır (`audit_log` → kuyruklu yazıcı → `audit_event`): `audit_log.remember` çağrısını **commit sonrasına** koy (açık yazma işlemi varken SQLite kilidi bekletir). Yakalanmayan hata kod + kayıt no ile `fault_event`e düşer; ham istisna kullanıcıya dönmez.
- Çekirdek (`backend/app/*.py`): `main.py` yalnız uygulamayı kurar ve router'ları bağlar; çekirdek uçlar `oturum_api.py` (giriş/çıkış), `katalog_api.py` (modül/ana sayfa), `rol_api.py` (`/roller`). Tek katalog: `catalog.py` (modül, bayrak, alt modül). Yetki: `authz.py` (`is_admin`, `yonetici_mi` tek tanım), `rolgorunum.py`, `session.py`, `security.py`, `deps.py`. Modül erişimi: `erisim.modul_erisim("modul")` (rol görünümü + eylem yetkileri; her yeni uç bunu kullanır). Kullanıcı kaydı: `kullanicilar.py` (giriş `app_user` + `last_login_at` yazar; TAM Takvim listesi buradan). Bağlantı yuvaları (AD/Oracle, yalnız anahtar doluluğu): `ad.py`, `external.py`, `baglantilar.py`. DB katmanı tek dosya: `db.py` (motor önbelleği, `get_db`, istek dışı `oturum()`, kullanıcı dosyaları). Şema: `models.py` + `backend/alembic` (0001–0009).
- **Rol eylem yetkileri:** `rolgorunum.YETKILER` (şu an `takvim.sunuma_gonder`); admin Rol Yönetimi'nde role verir, admin hepsine sahiptir, varsayılan kapalı. Sunucuda `Erisim.yetkili_mi(...)` ile zorlanır, arayüz yalnız yansıtır.
- **Onedesk / LLM:** veri yalnız admin Veri Girişi hattından gelir (`/onedesk/ice-al/{parti}`); canlı Onedesk DB bağlantısı kapalıdır. LLM yorumu varsayılan KAPALI: `TAMLIFE_YZ_SAGLAYICI=anthropic` + `TAMLIFE_YZ_VERI_PAYLASIMI=izinli` + `ANTHROPIC_API_KEY` (ortam; ben yazmam/göstermem). Modele yalnız kök sebep metni ve sayı gider; müşteri/lokasyon adı gitmez.
- **Dev örnek verisi:** `cd backend; $env:TAMLIFE_ENV='dev'; $env:TAMLIFE_DATABASE_URL='sqlite:///./var/dev.db'; ..\.venv\Scripts\python.exe -m app.ornek_veri [--temizle|--yenile]` — uydurma, işaretli (`ORNEK-*`, `ornek.*`, `source='ornek'`, `created_by='ornek'`), yalnız `TAMLIFE_ENV=dev`. Üretim verisi kopyalanmaz.
- `ekran-react/` TS arayüzü (Vite, TanStack Query, Tailwind). Derleme çıktısı `ekran-react/dist` → `TAMLIFE_STATIC_DIR`. Klasörler: `src/shell` (çatı: giriş, panel, menü, rol sayfası), `src/yonetim` (admin), `src/musteri` (portföy kartları, müşteri kartı, rapor), `src/onedesk`, `src/gelir` (SMS, APN), `src/takvim` (izin&takvim, TAM Takvim, grafik), `src/sunum`, `src/components` (`sayfa-ui.tsx` tek ortak UI: düğme/girdi sınıfları, Panel, Rozet, Kpi, SayfaKabi, Sekmeler, VeriTablosu, durum kutuları, `grafik.tsx` SVG grafikler, `cekmece.tsx` form çekmecesi, `duzenlenebilir-tablo.tsx` satır içi düzenlenebilir tablo, `ui/` ilkeller), `src/lib` (http, oturum, `sorgu.ts` tek API yolu `oku`/`yaz`/`yukle`, `bicim.ts` biçimleyiciler, `kanca.ts`); ortak metinler `shell/metin.ts` `ORTAK`. Hesap kartı sol altta (`shell/kullanici-karti.tsx`), logo sol üstte, üst bar Turkcell mavisi (`shell/panel.tsx`). `index.css`te varsayılan kenarlık rengi `@layer base` içindedir; katmansız `* { border-color }` ekleme (Tailwind renkli kenarlık sınıflarını ezer). Yeni bağımlılık eklemeden önce mevcut olanla çözülüp çözülmediğine bak; kullanılmayan dosya/bağımlılık bırakma.
- Test: `backend/tests/` (`test_yonetim`, `test_tampon`, `test_ozellikler` (Onedesk, gelir, takvim, rol yetkisi, portföy, örnek veri), `test_musteri`, `test_skor*`, `test_roller`, `test_auth_security`, `test_kimlik_siniri`, `test_arayuz_sunumu`; kullanıcı dosyası sayımı `conftest.kisi_say`); arayüz `src/yonetim/yonetim.test.tsx`, `src/yeni-ozellikler.test.tsx`. Yeni tablo → kişisel veri ise `KullaniciBase`, değilse `Base`; modeli ilgili paketin `models.py`ına yaz, `TABLE_OWNER`a ekle, (yalnız `Base` için) Alembic revizyonu yaz (`create_all(checkfirst)` + `batch_alter_table` kalıbı).
- Backend testi: `cd backend` → `..\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider`
- Arayüz: `cd ekran-react` → `npm test`, `npm run lint`, `npm run build`. `dist` yeniden derlenince panel yeniden başlatılmaz: `index.html` her istekte okunur; `assets/` bağlaması açılışta yapıldığı için `dist` boşken açılmış bir panel varsa yeniden başlat.
- API tipleri elle yazılır (`yonetim/api.ts`, `onedesk/tipler.ts`); OpenAPI şeması dev'de `/openapi.json`.
- Paneli başlatma: `backend\dev.ps1` (tek süreç). Oturumlar bellekte olduğu için çoklu worker açma.
- **DB düzeni (2026-10-09):** ortak **panel DB** (`TAMLIFE_DATABASE_URL`; dev `backend/var/dev.db`, PostgreSQL gelene kadar SQLite `TAMLIFE_SQLITE_IZIN=true`) + **kullanıcı başına SQLite dosyası** (`<panel DB klasörü>/kullanicilar/<kullanici>.db`, `TAMLIFE_KULLANICI_DB_DIZINI` ile değişir). Kullanıcı dosyasında yalnız kişisel veri: `calendar_day`, `sms_revenue`, `apn_revenue`, `apn_work` (`models.KullaniciBase`); ilk açılışta `create_all` ile kurulur, Alembic'e girmez. Müşteri, rapor, skor, Onedesk, tampon, denetim ortak panel DB'sindedir (sahip değişimi, iştirak, yönetici görünümleri tek DB ister). Erişim: `db.kullanici_oturumu(ad)`, çoklu okuma `db.mevcut_oturumlar(adlar)` (okuma dosya oluşturmaz). Kullanıcı dosyası kayıt kimliği dışarıya `app_user.id * 1_000_000 + yerel id` (`db.dis_kimlik`/`kimlik_coz`). Yedek panel DB'si + `<yedek>_kullanicilar/` klasörü. Üretim DB'lerine bağlanma, canlı AD bind / Oracle bağlantısı açma.

## Tasarım ilkeleri

- Modül/alt modül/rol tanımı tek kaynaktan (`catalog.py`); uydurma modül ekleme. Yetki sunucuda zorlanır, arayüz yalnız yansıtır.
- Admin her şeyi görür; `utilizasyon` ve `roller` yalnız admin (Yönetim sayfaları da). Üretim rol kuralıyla (`backend/app/moduller.py`, üretim) birebir uyum korunur.
- API kontratı OpenAPI'dir. Başarı gövdesi `{"status":"success","data":...}`; hata gövdesi FastAPI `{"detail":...}`; yakalanmayan hatada ek olarak `hata_kodu` ve `kayit_no`. Durum değiştiren istek `x-csrf-token` taşır. Yeni uç → test.
- Ham veri ve müşteri satırı üretimden kopyalanmaz.
