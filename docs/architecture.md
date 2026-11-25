# TAMLIFE v3.5 — güncel mimari (2026-10-12, canlı)

TAMLIFE, Turkcell TAM ekipleri için iç kullanım paneldir. v3.5, eski Flask panelinin (`E:\TAMLIFE`, silindi; arşiv: `TAMLIFE.zip`) FastAPI + React ile yeniden yazımıdır ve 2026-10-12'den beri `https://tamlife/` adresinde canlıdır (≤20 eşzamanlı kullanıcı). Bu belge kodun bugünkü halini anlatır; ayrıntılı tasarım notları `docs/` altındaki diğer dosyalardadır.

## 1. Çalışma düzeni (sunucu LADIN01, `E:\TAMLIFE\TAMLIFE_v3.5`)

```
Tarayıcı ──HTTPS 443──► Windows http.sys (TLS'i sonlandırır; özel anahtar kilitli olduğu için sertifika mağazada kalır)
                          └─► kurulum\tls_vekili.ps1 (HttpListener vekili, -Ad '+')  ──HTTP──► 127.0.0.1:8117
                                                                                       uvicorn, tek süreç (--workers 1)
                                                                                       FastAPI "app.main:app"
                                                                                         ├─ /api/v1/**        JSON API
                                                                                         ├─ /, /assets, /<dosya>   ekran-react\dist
                                                                                         └─ oturum + denetim halkası: BELLEK
                                              SQLAlchemy ─► backend\var\dev.db            ortak panel DB (adı yanıltıcı; CANLI DB budur)
                                                         ─► backend\var\kullanicilar\<kullanici>.db   kişisel veri (takvim, SMS/APN geliri)
İşçi süreçler (panel dışı, kendi çıkış kodu ve kilit dosyası):
  python -m app.isci reportdb      ─► Oracle REPORTDB (yalnız tek SELECT) ─► tampon (ingest_batch / ingest_block)   [görev kapalı: DBA izni bekleniyor]
  python -m app.rapor.ceviri --isci ─► CTranslate2 TR→EN (aylık rapor çevirisi; çökerse yalnız alt süreç ölür)
```

- **Kalıcı çalıştırma:** `kurulum\canli_gorev_kur.ps1` iki TURKCELL\TAMLIFEADLOG görevi kurar: `TAMLIFE_v35_Panel` (`canli_baslat.ps1`: prod modu, AD girişi, 127.0.0.1:8117) ve `TAMLIFE_v35_TLS_Vekil` (443 → 8117). İkisi açılışta başlar, kapanırsa 15 sn sonra yeniden açar. Günlük: `var\log\canli_panel.log`, `canli_vekil.log` (10 MB'ta döner). `-Hemen`, `-Durum`, `-Kaldir`.
- **Yalnız 443.** 80'den yönlendirme yoktur. Eski panelin `https://+:443/` kaydı yüzünden eski panel kapatılmış, vekil `-Ad '+'` ile başlatılmıştır.
- **Prod kipi:** `TAMLIFE_ENV=prod` → yerel admin girişi yok, `/docs` ve `/openapi.json` kapalı, `TrustedHost` yalnız `TAMLIFE_ALLOWED_HOSTS`, `Origin` ya `scheme://Host` olmalı ya da `TAMLIFE_ALLOWED_ORIGINS`'te, `X-Forwarded-For` yalnız `TAMLIFE_TRUSTED_PROXIES`'ten kabul edilir.
- **Geliştirme:** `backend\dev.ps1` (API 8117, SQLite `var/dev.db`), arayüz için `cd ekran-react; npm run dev` (Vite 5173, `/api` → 8117) ya da `dev.ps1 -Arayuz`.

## 2. Backend (`backend/app`, ~17 bin satır Python, 138 API işlemi)

Çekirdek + özellik paketleri. `main.py` yalnız uygulamayı kurar (ara katmanlar, hata işleyiciler, router'lar, derlenmiş arayüz).

| Katman | Dosyalar | İş |
|---|---|---|
| Çekirdek | `config.py`, `db.py`, `models.py`, `catalog.py`, `ortak.py` | Ayarlar (`backend/.env`, git dışı), motor önbelleği ve oturumlar, şema, tek modül kataloğu, hata sözleşmesi (`UygulamaHatasi(kod, mesaj)`) |
| Kimlik / yetki | `oturum_api.py`, `ad.py`, `kullanicilar.py`, `session.py`, `security.py`, `authz.py`, `deps.py`, `erisim.py`, `rolgorunum.py`, `rol_api.py`, `navigation.py`, `katalog_api.py` | Giriş, AD/LDAPS, kullanıcı kaydı, bellek oturumu, CSRF/Origin, rol görünümü, menü |
| Özellik paketleri | `musteri`, `rapor`, `skor`, `onedesk`, `gelir`, `takvim`, `sunum`, `talep`, `radar`, `proje`, `topoloji`, `ekip` | Her biri `api.py` (router) + `servis.py` (iş kuralı) |
| Yönetim (yalnız admin) | `yonetim/*`, `tampon/*` | DB, arızalar, günlükler, sağlık, kurum bağlantıları; Veri Girişi hattı |
| Araçlar | `isci.py`, `hesap.py`, `eski_aktar.py` | ReportDB işçisi, hesap/rol/acil parola CLI, eski panelden tek seferlik aktarım |

Bağımlılık yönü: `skor ← musteri ← rapor`; `onedesk → tampon.depo` (yalnız okuma); `yonetim` ile `tampon` birbirini import etmez. Dil: `dil.py` (`X-Dil: tr|en` → `m("Türkçe", "English")`).

API grupları (işlem sayısı): musteri 24 · tampon 26 · skor 16 · yonetim 15 · gelir 13 · proje 8 · onedesk 7 · takvim 6 · sunum 4 · talep 4 · rapor 3 · session 3 · modules 2 · roller 2 · ekip, radar, topoloji, home, health 1'er. Başarı gövdesi `{"status":"success","data":…}`, hata `{"detail":…}` (yakalanmayanda `hata_kodu` + `kayit_no`). Durum değiştiren istek `x-csrf-token` taşır.

## 3. Veri

- **Ortak panel DB** (`TAMLIFE_DATABASE_URL`, SQLite; PostgreSQL desteklenir): 33 tablo — müşteri (`customer`, `customer_team`, `report*`, `affiliate_final_flag`), skor (`score_*`, `util_criteria_set`, `scoring_exclusion`, `urun_tutar_ozet`), Onedesk (`onedesk_record`), Veri Girişi (`ingest_batch`, `ingest_block`, `distribution_rule/log`, `customer_import_run`), yönetim (`app_user`, `role_view`, `audit_event`, `fault_event`, `app_setting`), talep/proje/sunum (`demand*`, `project_*`, `presentation`). Şema Alembic ile yönetilir: `0001_baslangic` … `0008_profil_kisi_yetki`, açık `op.create_table`; `tests/test_alembic.py` modelle karşılaştırır.
- **Kullanıcı başına SQLite** (`var/kullanicilar/<kullanici>.db`): yalnız kişisel veri (`calendar_day`, `sms_revenue`, `apn_revenue`, `apn_work`); ilk açılışta `create_all`, Alembic dışı.
- **Veri yalnız gerçek kaynaktan gelir:** Veri Girişi dosya yüklemesi (xlsx/csv), REPORTDB/ONENTDB/GALAPAGOSDB okumaları ve eski panelden tek seferlik aktarım. Uydurma/örnek veri yolu yoktur.
- **Veri Girişi hattı:** kaynak → tampon (sıkıştırılmış bloklar) → analiz/önizleme → onaylı dağıtım (geri alınabilir). Ham müşteri yüklemesi `tampon/musteri_ham.py` + `musteri_aktar.py`.
- **Dış kaynaklar:** Oracle için python-oracledb thick mod (`ORACLE_CLIENT_DIR`, Instant Client 19.32), yalnız tek `SELECT`, `*_ENABLED=true` ve anahtarlar doluysa bağlanır. REPORTDB'de oturum açılır ama `ADMIN.DB_LOGIN_TR` logon tetikleyicisi (DB kullanıcısı + OS kullanıcısı + makine) ORA-20099 ile reddeder; çözüm DBA iznidir (erişim talebi formu), tetikleyiciyi aşmak yoktur.

## 4. Kimlik, yetki ve güvenlik

- Giriş sırası: pasif kullanıcı reddi → AD kullanıcısı AD ile (LDAPS, kullanıcının kendi bind'i, parola saklanmaz) → yerel acil hesap (scrypt) → dev yerel hesap (yalnız dev) → kaydı olmayan AD kullanıcısı `TeamMember` olarak açılır (`AD_OTOMATIK_AC`). Rol her zaman `app_user`'dan; ilk admin `python -m app.hesap rol <kullanici> admin`.
- Roller: `admin`, `TeamMngr`, `TeamMember`. Modül erişimi `erisim.modul_erisim("modul")` (rol görünümü + eylem yetkileri); kural sunucuda zorlanır, arayüz yansıtır.
- **Yönetim alanı yalnız admin:** `/yonetim/*`, `/tampon/*`, `/roller` ve skor yönetim uçları `require_admin` ister. `utilizasyon` ve `roller` modülleri (`admin_only`) hiçbir rol görünümüyle açılmaz. **Veri yazma yalnız admin:** müşteri, gelir ve proje kalemleri (`require_veri_yazma`). Bilerek açık kalanlar: rapor akışı, takvim, talep açma, skor talepleri, proje çalışma işaretleri.
- Denetim kalıcıdır (`audit_log` → kuyruklu yazıcı → `audit_event`); yakalanmayan hata kod + kayıt no ile `fault_event`e düşer, ham istisna kullanıcıya dönmez. Parola, anahtar, `.env` değerleri hiçbir yerde yazılmaz/gösterilmez.

## 5. Arayüz (`ekran-react`, ~16,7 bin satır TS/TSX)

React 19, TypeScript 7, Vite 8, TanStack Query, Tailwind 4, framer-motion, lucide. Tek API yolu `src/lib/sorgu.ts` (`oku`/`yaz`/`yukle`).

- `src/shell`: giriş, çatı (`panel.tsx`), menü, hesap kartı, rol sayfası. `src/components`: ortak UI (`sayfa-ui.tsx` + alan başlığı bantları `BASLIK_BANDI`/`ALT_BASLIK_BANDI`, grafikler, çekmece, çoklu seçim filtresi, düzenlenebilir tablo, `ui/` ilkeller; Genel Bakış yayı `ui/modul-yayi.tsx` + `ui/ozet-orbit.tsx`).
- Özellik klasörleri: `musteri`, `onedesk`, `gelir`, `takvim`, `sunum`, `talep`, `radar`, `proje`, `topoloji`, `ekip`, `yonetim` (8 bölüm: Genel Durum, TAM Utilizasyon, Veri Girişi, Kurum Bağlantıları, Veritabanı, Roller, Arızalar, Günlükler).
- Derleme çıktısı `ekran-react/dist` API tarafından sunulur (`TAMLIFE_STATIC_DIR`); `index.html` her istekte okunur, yeniden derleme paneli yeniden başlatmaz (`assets/` açılışta bağlanır, `dist` boşken açılmışsa yeniden başlat).
- Görünüm ölçeği: arayüz rem tabanlı; kök yazı boyutu `<html data-yazi>` (`lib/yazi.ts`: normal / büyük (varsayılan 1,125×) / çok büyük), hesap menüsünden seçilir.
- Genel Bakış: yatayda gerilmiş iki yarım elips üzerinde 92×68 modül kartları, ortada Teknocan (104×180 kutu), altında Ekip Özeti.

## 6. Test ve doğrulama

- Backend: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider` (654 test, 1 atlanır; `ruff check .` temiz).
- Arayüz: `cd ekran-react; npm test` (162 test), `npm run lint`, `npm run build`.
- Alembic, rol/yetki (`test_yonetim_uclari_admin_disina_kapali` tüm Yönetim uçlarını OpenAPI'den dener), skor altın vektörleri (`skor_golden.json`), eski aktarım (`test_eski_aktar.py`) ayrı testlidir.

## 7. Depo düzeni

```
TAMLIFE_v3.5/
├─ backend/      app/ (paketler yukarıda) · alembic/ · tests/ · dev.ps1 · .env.example · ruff.toml · pytest.ini
│                var/ (git dışı: dev.db, kullanicilar/, logs/, yedek/)  ·  .env (git dışı, sır)
├─ ekran-react/  src/ · public/ (html2canvas, jsPDF, rapor görselleri) · e2e/ · dist/ (git dışı)
├─ kurulum/      canli_baslat.ps1 · canli_gorev_kur.ps1 · tls_vekili.ps1 · reportdb_gorev_kur.ps1 · ceviri_kur.ps1 · sertifika/
├─ docs/         bu belge + tasarım notları
├─ requirements.txt   CLAUDE.md
```

Git dışı, sunucuda kalıcı: `backend\.env`, `backend\var\`, `ekran-react\dist`, `.venv`, `ceviri_modeli\tr_en`, Instant Client klasörü.

## 8. Açık işler

- REPORTDB: Windows çalışma hesabı `TURKCELL\TAMLIFEADLOG`; aynı hesapla Oracle bağlantısı 2026-10-16'da doğrulandı. `TAM_Life_v35_ReportDB_6dk` görev hesabı da buna taşındı; otomatik veri çekimi mevcut devre dışı durumunda korundu (`kurulum\reportdb_gorev_kur.ps1`).
- **Windows kimliği:** `kurulum/calisma_kimligi.ps1` çalışma hesabını tek yerde tanımlar. Kurulum Windows kimlik bilgisi penceresinden parola alır; parola kodda/günlükte tutulmaz, oturum kapalıyken çalışma için Task Scheduler tarafından saklanır. Mevcut görevleri taşıma: yükseltilmiş PowerShell'de `kurulum/kimlik_gecir.ps1` (önce aynı görev hesabında salt okunur Oracle testi, sonra hesap geçişi ve panel/TLS yeniden başlatma; görevlerin etkin/devre dışı durumları korunur). `kurulum/kimlik_kontrol.ps1` yalnız bağlantı ve kimlik doğrular. Görev tanımı kopyaları `var/isletim/kimlik-<tarih-saat>/`, geçiş günlüğü `var/log/kimlik-gecis.log`.
- 114 çatı müşterinin segmenti boş (eski panelde de boştu): Veri Girişi › ham müşteri yüklemesiyle doldurulur.
- GALAPAGOSDB anahtarları ve ONENTDB/Ürün-Tutar bağlantıları sunucu `.env`'inde doğrulanacak.
- Çeviri modeli `ceviri_modeli\tr_en` altında olmalı; `kurulum\ceviri_kur.ps1 -Dogrula` dosyayı, SHA256'yı ve deneme çevirisini denetler (eski panel klasörü silindi; internetsiz sunucuda `-Paket`).
