# Yeni panel: üretim panelinin arkasında `/admin/dev`

`https://tamlife/admin/dev` yeni paneli (bu depo) üretim paneline (Flask) bağlar. Yalnız yönetici açabilir.

```
Tarayıcı ──https──> Flask (üretim) ── /admin/dev/** ──> uvicorn 127.0.0.1:8117 (yeni panel, ayrı süreç)
                     │ oturum + yönetici denetimi        └ arayüz (ekran-react/dist) + /api/v1/**
                     └ X-TAM-User / X-TAM-Role / X-TAM-Proxy-Secret ile kimliği iletir (SSO)
```

- Yeni panel dışarıya açık değil; yalnız `127.0.0.1` dinler. Vekil hedefi koda sabit (değiştirilemez).
- Yönetici ikinci kez giriş yapmaz: vekil kimliği paylaşılan sırla iletir, yeni panel kendi oturumunu açar.
  Yeni panel çerezleri (`tamlife_session`, `tamlife_csrf`) yalnız `/admin/dev` yoluna gider; üretim oturum çerezi yeni panele iletilmez.
- Yeni panel kapalıysa ya da sır yoksa `/admin/dev` 503 verir; üretim paneli etkilenmez.
- Çıkış (kullanıcı menüsü) yeni paneli kapatır ve üretim paneline döner.

## Üretimde değişen dosyalar (yalnız bunlar)

| Dosya | Değişiklik |
|---|---|
| `backend/app/blueprints/dev_panel_bp.py` | **Yeni.** Bu klasördeki `dev_panel_bp.py` ile aynı (kaynak: bu depo). |
| `backend/app/__init__.py` | `workspace` blueprint kaydından sonra, `islem_gunlugune_yaz`'dan önce 7 satır (`try/except` içinde `dev_panel_bp.kur(app)`). |

Geri alma: `__init__.py`'deki 7 satırı ve `dev_panel_bp.py`'yi sil, paneli yeniden başlat. Hızlı kapatma: `.env`'den `DEV_PANEL_SECRET` satırını kaldırmak (503 verir).

## Sunucu adımları

1. **Kod:** bu depoyu sunucuya taşı (`backend/`, `ekran-react/dist/`, `deploy/`). `dist` git'te yok: burada `cd ekran-react && npm run build:prod` ile üret, klasörü kopyala.
2. **Python 3.12 venv** (yeni panel için; üretim venv'i kullanılmaz):
   `python -m venv .venv` ardından `.venv\Scripts\python.exe -m pip install -r requirements.txt`
3. **Sır üret** (en az 32 karakter): `python -c "import secrets; print(secrets.token_urlsafe(48))"`
4. **Yeni panel ortamı:** `deploy\prod\dev-panel.env.bat.ornek` → `dev-panel.env.bat` kopyala; yolları ve `TAMLIFE_SSO_SECRET` değerini doldur.
5. **Üretim `.env`** dosyasına iki satır ekle (aynı sır):
   ```
   DEV_PANEL_SECRET=<3. adımdaki sır>
   DEV_PANEL_PORT=8117
   ```
6. **Yeni paneli başlat:** `deploy\prod\dev-panel-baslat.bat` (şemayı günceller, uvicorn'u `127.0.0.1:8117`'de, tek süreç olarak açar).
   Sunucu açılışında otomatik başlaması için zamanlanmış görev gerekir (kurmadan önce onay al).
7. **Üretim panelini yeniden başlat** (blueprint kaydı için bir kez).
8. Doğrula: yönetici olarak `https://tamlife/admin/dev` → "Hoş geldin, <kullanıcı>". Yönetici olmayan hesap: ana sayfaya yönlenir.

## Sorun giderme

| Belirti | Neden |
|---|---|
| 503 "Yeni panel yapılandırılmadı" | Üretim `.env`'de `DEV_PANEL_SECRET` yok ya da 32 karakterden kısa. |
| 503 "Yeni panel şu an çalışmıyor" | `dev-panel-baslat.bat` çalışmıyor ya da port farklı. |
| Giriş formu çıkıyor (SSO olmadı) | İki taraftaki sır farklı; uvicorn `--no-proxy-headers` olmadan açılmış; `TAMLIFE_BASE_PATH` `/admin/dev` değil. uvicorn çıktısında `POST /api/v1/session/sso 401` görünür. |
| 403 "Kaynak reddedildi" | Tarayıcının `Origin` adresi `Host` ile uyuşmuyor: `TAMLIFE_ALLOWED_ORIGINS` içine `https://<adres>` ekle. |
| 400 "Invalid host header" | `TAMLIFE_ALLOWED_HOSTS` içinde sitenin adı yok. |
| Beyaz sayfa | `ekran-react/dist` `npm run build:prod` ile (taban `/admin/dev/`) üretilmemiş. |

## Test

```
# vekil blueprint'i (üretim uygulaması ve veritabanı gerekmez)
PYTHONPATH=<üretim>\.venv\Lib\site-packages .venv\Scripts\python.exe -m pytest deploy/prod/test_dev_panel_bp.py
# yeni panel: SSO, çerez yolu, arayüz sunumu
cd backend && ..\.venv\Scripts\python.exe -m pytest tests/test_prod_gomme.py
```
