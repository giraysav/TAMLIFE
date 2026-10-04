# TAMLIFE v3.5 (dev) — Claude için çalışma kuralları

Yanıtları **Türkçe**, kısa ve doğrudan ver (selamlama/özür/kapanış cümlesi yok). Karşındaki uzman sistem yöneticisi/geliştirici; temel kavramları açıklama.
Değişiklikleri tam dosya yerine yalnız değişen blok/diff olarak göster. Dosya okurken önce `Grep`, sonra yalnız ilgili aralık.

## Kurumsal sunucu ve kimlik düzeni (EN ÖNEMLİ KURAL)

- Bu sunucu kurumsal (AD/LDAP) mimaridedir. **`TURKCELL\tcgsav` LDAP kullanıcısıdır; sunucuya yalnız onunla RDP login olunur.**
- **`ladinadmin` servis hesabıdır, yerel admin yetkisi vardır.** Tüm işlemlerde (yazma, git, süreç, servis, `.env`) `ladinadmin` kimliği kullanılır. Başka kullanıcıyla sunucuya login olunmaz/önerilmez.
- Oturum başında `whoami` ve yazma yetkisini doğrula. `E:\TAMLIFE` altında mevcut dosya değiştirilemiyorsa (EPERM) kimlik atlatmaya çalışma; **komutu veya betiği kullanıcıya ver**, kullanıcı `ladinadmin` ile çalıştırır. Yetki/izin gerekiyorsa aynı kural.
- `ladinadmin` parolasını isteme, yazma, saklama. Kimlik bilgisi deposunu (cmdkey vb.) araştırma.
- **Sır** (`TAMLIFE_SSO_SECRET`, `DEV_PANEL_SECRET`, `.env` değerleri, parola): ben üretmem/yazmam/göstermem. Sır içeren dosyaları kullanıcının çalıştırdığı betik yazar (`deploy\prod\uretime_bagla.ps1`).

## Ortamlar

| | Yol | Rol |
|---|---|---|
| **Üretim** | `E:\TAMLIFE` (Flask, canlı, ≤20 eşzamanlı kullanıcı) | Tek canlı klasör. Birinci kriter stabilite. |
| **Dev (bu depo)** | `E:\TAMLIFE_Dev\TAMLIFE_v3.5` (FastAPI + React) | Yeni panel tasarımı. Üretimden bağımsız süreç ve DB. |

`https://tamlife/admin/dev` = dev paneli üretimin arkasında: Flask yalnız ters vekil (`deploy/prod/dev_panel_bp.py`) → uvicorn `127.0.0.1:8117`. Yalnız yönetici açar; kimlik `X-TAM-*` + paylaşılan sırla iletilir (SSO). Ayrıntı: `deploy/prod/README.md`, `docs/architecture.md`.

### Üretime dokunma kuralları
- Üretimde bu proje için **yalnız** şunlar değişir: `backend/app/blueprints/dev_panel_bp.py` (yeni) ve `backend/app/__init__.py` içindeki 6 satırlık `try/except` kaydı; `.env`'de `DEV_PANEL_SECRET`, `DEV_PANEL_PORT`.
- Üretimi **onay almadan** durdurma/başlatma/yeniden başlatma (`yonet.bat`), süreç öldürme, dosya silme, `pip install`, zamanlanmış görev/güvenlik duvarı değişikliği, `.env` düzenleme yok. Yapmadan önce komutu ve etkisini yaz.
- Üretim kodunu "ileride lazım olur" diye değiştirme. Şüphede kalırsan değiştirmeden sor.
- `_eski`, `_yeni`, `_onceki`, `_yedek` adlı klasör/dosya oluşturma (`E:\TAMLIFE` içinde). Sürüm numarası artırma, etiket (tag) atma yok; "sürüm" yalnız klasör adıdır.
- `.env`, veritabanı (`E:\Secure_DB`, `C:\Secure_DB`), `*.pfx/*.key/*.p12` taşınmaz ve içeriği paylaşılmaz. `.bat` dosyaları CRLF + saf ASCII, `.ps1` betikleri saf ASCII.
- AD/LDAP ile giren kullanıcı hiçbir yolla veritabanından silinmez. Acil durum hesabı `ladinadmin`; parolasına dokunma.
- Serbest (salt okuma): `yonet.bat durum|log`, `logs\` okuma, `isletim\saglik_kontrolu.ps1`.

## Yapı ve komutlar

- `backend/app/` FastAPI paneli. Tek katalog: `catalog.py` (modül, bayrak, alt modül). Yetki: `authz.py`, `rolgorunum.py`, `session.py`, `security.py`. Şema: `models.py` + `backend/alembic`.
- `ekran-react/` TS arayüzü (Vite, TanStack Router/Query, Tailwind). Derleme çıktısı `ekran-react/dist` → `TAMLIFE_STATIC_DIR`. `web/` eski JSX kabuğu: yeni iş için kullanma, kaldırma kararı bekliyor.
- Backend testi: `cd backend` → `..\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider`
- Vekil testi: `PYTHONPATH=E:\TAMLIFE\.venv\Lib\site-packages .venv\Scripts\python.exe -m pytest deploy/prod/test_dev_panel_bp.py -q -p no:cacheprovider`
- Arayüz: `cd ekran-react` → `npm test`, `npm run lint`, `npm run build:prod` (taban `/admin/dev/`). `dist` yeniden derlenince panel yeniden başlatılmaz: `index.html` her istekte okunur; `assets/` bağlaması açılışta yapıldığı için `dist` boşken açılmış bir panel varsa yeniden başlat.
- API tipleri: `npm run api:uret` (çalışan panelin `/openapi.json`'u; yalnız dev'de açık). Elle `api-types.ts` düzenleme.
- Yeni paneli başlatma: `deploy\prod\dev-panel-baslat.bat` (tek süreç, `--workers 1`, `--no-proxy-headers`). Oturumlar bellekte olduğu için çoklu worker açma.
- Panel DB: PostgreSQL gelene kadar yalnız bu panelin kendi SQLite dosyası (`backend/var/panel.db`, `TAMLIFE_SQLITE_IZIN=true`). Üretim DB'lerine bağlanma, canlı AD bind / Oracle bağlantısı açma.

## Tasarım ilkeleri

- Modül/alt modül/rol tanımı tek kaynaktan (`catalog.py`); uydurma modül ekleme. Yetki sunucuda zorlanır, arayüz yalnız yansıtır.
- Admin her şeyi görür; `utilizasyon` ve `roller` yalnız admin (Yönetim sayfaları da). Üretim rol kuralıyla (`backend/app/moduller.py`, üretim) birebir uyum korunur.
- API kontratı OpenAPI'dir. Başarı gövdesi `{"status":"success","data":...}`; hata gövdesi FastAPI `{"detail":...}` (vekil katmanı kendi hatalarında `{status:"error",message}` döner). Durum değiştiren istek `x-csrf-token` taşır. Yeni uç → test + `api:uret`.
- Ham veri ve müşteri satırı üretimden kopyalanmaz.
