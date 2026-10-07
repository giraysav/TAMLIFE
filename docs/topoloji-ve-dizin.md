# TAMLIFE v3.5 — topoloji ve dizin yapısı (mevcut durum)

> Güncellendi (2026-10-07, temizlik ve sadeleştirme sonrası): özellik paketleri, tek hata sözleşmesi, ince `main.py`, `web/`/`contract.py`/`ingest.py`/`trmetin.py`/`external_source` kaldırıldı. Ayrıntı: `yonetim-ve-tampon-tasarimi.md` §7–8.

Kaynak: kodun kendisi (import grafiği, `catalog.py`, `models.py`, `alembic/`, `ekran-react/src`). Bu belge **mevcut durumu** anlatır; hedef tasarım ayrı yazılacak. `E:\TAMLIFE` (eski üretim) kapsam dışıdır.

Durum işaretleri: **[canlı]** çalışan ve testli · **[iskelet]** tablo/katalog var, servis/API/arayüz yok · **[üretilen]** git'te yok.

## 1. Çalışma topolojisi (yalnız lokal)

```
                         E:\TAMLIFE_Dev   (tek makine, tek kullanıcı: TURKCELL\tamlifeadlog)
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                             │
│  Tarayıcı ──┬── http://127.0.0.1:5173 ── Vite dev sunucusu ──┐ /api/* vekil                 │
│             │   (npm run dev, sıcak yeniden yükleme)         │                              │
│             │                                                ▼                              │
│             └── http://127.0.0.1:8117 ───────────► uvicorn (tek süreç, --workers 1)          │
│                 (backend\dev.ps1 [-Arayuz])          FastAPI "app.main:app"                 │
│                                                       ├─ /api/v1/**       JSON API          │
│                                                       ├─ /, /assets, /x   ekran-react/dist  │
│                                                       │  (yalnız -Arayuz ile)               │
│                                                       ├─ /docs, /openapi.json  (env=dev)    │
│                                                       └─ oturumlar + denetim halkası: BELLEK│
│                                                              │ SQLAlchemy (senkron)         │
│                                                              ▼                              │
│                                            backend/var/dev.db  (SQLite, Alembic ile kurulur)│
│                                                                                             │
│  ┌─ ayrı proje, birbirinden habersiz ───────────────────────────────────────────────────┐   │
│  │ tamlife-api  127.0.0.1:8000  FastAPI async + SQLite data/tamlife.db  (servis.ps1)    │   │
│  └──────────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
 Kapalı / yok: canlı AD bind, Oracle (Onedesk/Onent/Ürün-Tutar), PostgreSQL, dış ağ, E:\TAMLIFE
```

| Port | Süreç | Başlatma |
|---|---|---|
| 8117 | API (+ derlenmiş arayüz) | `backend\dev.ps1` · arayüzle: `-Arayuz` |
| 5173 | Vite dev | `cd ekran-react; npm run dev` |
| 5174 | Playwright `baseURL` | `npm run e2e` (sunucuyu önceden siz açarsınız) |
| 8000 | `tamlife-api` | `tamlife-api\scripts\calistir.ps1` |

## 2. Backend katman topolojisi

`backend/app` = **çekirdek** (21 dosya, ~1.750 satır) + **5 özellik paketi** (30 dosya). Toplam 51 dosya, ~5.300 satır. Oklar `import` satırlarından çıkarıldı.

```
main.py ──┬─ oturum_api · katalog_api · rol_api      çekirdek uçlar (giriş/çıkış, modüller/ana sayfa, /roller)
          ├─ yonetim.router ─► arizalar, gunlukler, veritabani, saglik, ozet, dosya_gunlugu, kalici_yazici ─► ariza, ortak, models
          ├─ tampon.router ──► depo, analiz, dagitim, kaynak ─► eslestirme, profil, ortak, models
          ├─ musteri.api ────► musteri.servis ─► skor.servis ─► skor.motor (saf hesap)
          │                └─► rapor.servis ──┬─► musteri.servis, skor.servis
          │                                   └─► rapor.metin
          ├─ skor.api ───────► skor.servis
          └─ security ───────► session ─► config
çekirdek: rolgorunum ─► catalog, authz, models · navigation ─► catalog, authz · deps ─► authz, gateway, session, config
          authz ─► catalog, session · baglantilar ─► ad, external, config · audit ─► models (tembel)
bağımsızlık: yonetim ↔ tampon birbirini import etmez; müşteri alanı tek yönlü: skor ← musteri ← rapor
```

| Katman | Dosyalar | Not |
|---|---|---|
| Kimlik/oturum | `session.py`, `security.py`, `authz.py`, `deps.py` | bellek içi oturum, CSRF, hız sınırı, `can_open` |
| Katalog/görünüm | `catalog.py` (17 modül), `rolgorunum.py`, `navigation.py` | tek kaynak; yetki sunucuda |
| Çekirdek uçlar | `oturum_api.py`, `katalog_api.py`, `rol_api.py` | `main.py` yalnız kurar ve bağlar (~80 satır) |
| Müşteri alanı | `musteri/{api,servis}.py`, `rapor/{servis,metin}.py`, `skor/{api,servis,motor}.py` | `skor/motor.py` üretimden birebir; golden test |
| Veri | `models.py` (33 alan tablosu), `gateway.py`, `alembic/` | senkron `Session`, istek başına; PostgreSQL bağlantısı 3 sn zaman aşımlı |
| Yönetim (paket) | `yonetim/*` (11 dosya) | yalnız admin; tek `ozet` isteği, yedek, arıza durumu, denetim sorgusu |
| Tampon (paket) | `tampon/*` (9 dosya) | kaynak → tampon → analiz → dağıtım; geri alınabilir |
| Ortak | `ariza.py` (kod + kayıt no), `ortak.py` (`UygulamaHatasi`, `ok()`, zaman, sayfalama, TR metin) | paketlerin tek ortak noktası |
| Bağlantı yuvaları | `ad.py`, `external.py`, `baglantilar.py` | yalnız anahtar adı/doluluk; bağlantı kodu yok |

**İstek yaşam döngüsü:** `TrustedHost` → güvenlik kapısı (yazma isteklerinde Origin + CSRF, yalnız login muaf) → route → `require_user` / `require_admin` / `_modul(anahtar)` (rol görünümü + `can_open`) → servis → `db.commit()` endpoint'te → `audit_log` (bellek halkası + kuyruklu kalıcı yazıcı → `audit_event`) → yanıt başlıkları (CSP, no-store).

**Hata sözleşmesi:** servis hataları `UygulamaHatasi(kod, mesaj)` alt sınıfıdır; tek işleyici `{"detail": mesaj}` + durum kodu döner. Yakalanmayan istisna: `yonetim/yakalayici` → `fault_event` + `{"detail", "hata_kodu", "kayit_no"}`. Başarı gövdesi `ortak.ok(data)` = `{"status":"success","data":…}`.

## 3. Modül ve veri sahipliği

`catalog.py` modülü, `models.py` `TABLE_OWNER` tabloyu sahiplenir. Katman sütunu bugünkü gerçek durumdur.

| Modül | Tablolar | Servis | API | Arayüz |
|---|---|---|---|---|
| core | `app_user`, `audit_event` | — | `/session/*` | giriş, profil — **[canlı]** |
| musteri | `customer`, `customer_team`, `matrix_config` | `musteri/` | `/musteri/**` | `src/musteri/` — **[canlı]** |
| rapor | `report`, `report_draft`, `report_dispatch`, `report_recipient` | `rapor/` | `/rapor/**`, `/musteri/{id}/rapor/**` | `aylik-rapor.tsx`, `rapor-sayfasi.tsx` — **[canlı]** |
| utilizasyon | `util_criteria_set`, `score_detail`, `score_history`, `score_approval_request`, `scoring_exclusion`, `affiliate_final_flag` | `skor/` | `/skor/**` | **yok** (kriter/dağıtım ekranı bekliyor) |
| roller | `role_view` | `rolgorunum.py` | `/roller` | `shell/roller-sayfasi.tsx` + Yönetim › Roller — **[canlı]** |
| yonetim | `fault_event` (+ `audit_event`) | `yonetim/` | `/yonetim/**` | `src/yonetim/` 6 bölüm — **[canlı]** |
| ingest (Veri Girişi) | `ingest_batch`, `ingest_block`, `distribution_rule`, `distribution_log` | `tampon/` | `/tampon/**` | `src/yonetim/tampon/` — **[canlı]** (CSV + örnek; Oracle kapalı) |
| takvim, proje, onedesk, talep, tamsms, tamapn, radar, sunum, gelir_uretim | `calendar_entry`, `project*`, `onedesk_record`, `demand*`, `sms_revenue`, `apn_revenue`, `radar_prospect`, `presentation`, `income_production` | yok | yok | genel `ModulSayfasi` **[iskelet]** |
| baglantili, topoloji | — | yok | yok | `ready=False` / müşteri iznine bağlı **[iskelet]** |

**Alembic zinciri:** `0001_panel_schema` → `0002_final_skor` → `0003_rol_gorunumu` → `0004_musteri_karti_rapor` → `0005_yonetim_tampon` → `0006_ingest_record_kaldir` → `0007_external_source_kaldir`. Dikkat: `0001` `Base.metadata.create_all()` çağırır, yani **canlı model**den tablo üretir; sonraki adımlar `checkfirst`/`batch_alter_table` ile tamamlar. Revizyonlar dondurulmuş şema değildir (bkz. §6).

## 4. Frontend topolojisi (`ekran-react`)

```
main.tsx → App.tsx ──useOturum()──► durum: yukleniyor | yok | var
              ├─ yok  → shell/giris.tsx
              └─ var  → shell/panel.tsx  (SidebarProvider + hash yönlendirme: #/<modul>[/<alt>]?sorgu)
                          ├─ nav.tsx / kullanici-menu.tsx / arama.tsx
                          └─ içerik (aktif kimliğe göre):
                             ozet → components/ui/ozet-orbit.tsx
                             musteri → musteri/musteri-sayfasi → musteri-listesi + musteri-karti (+ musteri-rapor, aylik-rapor)
                             rapor → musteri/rapor-sayfasi · roller → shell/roller-sayfasi
                             yonetim/<bolum> → yonetim/yonetim-sayfasi (lazy; durum, tampon, veritabani, roller, arizalar, gunlukler; yalnız admin)
                             eski #/admin, #/veri, #/integrations, #/roller → admin için yeni bölümlere yönlenir
                             diğer modüller → shell/modul-sayfasi.tsx (yer tutucu)

components/  kart-ui.tsx (ortak görsel dil: Bolum, Rozet, DUGME, GIRDI) · ui/ (button, card, badge, input, label, sheet, sidebar, skeleton, orbit)
lib/         http.ts (taban yol, CSRF başlığı, 401) · oturum.ts (oturum, boşta süre) · api-yaz.ts (gonder/iste/apiYukle)
             api-types.ts (üretilen: `npm run api:uret`; elle düzenlenmez) · utils.ts
```

Gerçek arayüz kodu `src/shell` (13 dosya, ~1.100 satır), `src/musteri`, `src/yonetim`, `src/components`. TanStack Query yalnız `src/yonetim`de kullanılıyor; çalışma zamanı bağımlılıkları 11 pakettir (React, TanStack Query, Radix dialog/label/slot, framer-motion, lucide, tailwind-merge, clsx, cva).

## 5. Dizin yapısı

```
E:\TAMLIFE_Dev\
├─ tamlife-api\                    ayrı proje: feature-first FastAPI iskeleti (git yok; bu depo ona dokunmaz)
└─ TAMLIFE_v3.5\                   ◄── bu depo (git: main, uzak yok)
   ├─ CLAUDE.md · .gitignore · requirements.txt (yalnız çalışma zamanı)
   ├─ backend\
   │  ├─ app\                      çekirdek (21) + 5 paket, bkz. §2
   │  │  ├─ main.py  config.py  catalog.py  models.py  gateway.py  audit.py
   │  │  ├─ session.py security.py authz.py deps.py  rolgorunum.py navigation.py
   │  │  ├─ oturum_api.py katalog_api.py rol_api.py
   │  │  ├─ ad.py external.py baglantilar.py  ariza.py ortak.py
   │  │  ├─ yonetim\                 router · ozet · saglik · veritabani · arizalar · gunlukler · kalici_yazici · dosya_gunlugu · yakalayici · models
   │  │  ├─ tampon\                  router · depo · analiz · dagitim · kaynak · eslestirme · profil · models
   │  │  ├─ musteri\                 api · servis
   │  │  ├─ rapor\                   servis · metin
   │  │  └─ skor\                    api · servis · motor
   │  ├─ alembic\{env.py, versions\0001..0007}    alembic.ini
   │  ├─ tests\                    test_{yonetim,tampon,auth_security,kimlik_siniri,roller,musteri,skor,skor_api,arayuz_sunumu}.py · conftest.py · skor_golden.json
   │  ├─ dev.ps1  pytest.ini  ruff.toml
   │  └─ var\                      [üretilen, git'te yok]  dev.db · logs\ · prod_geri_al\
   ├─ ekran-react\                 TS arayüzü (Vite 8, React 19, Tailwind 4, oxlint, vitest, Playwright)
   │  ├─ src\{shell, musteri, yonetim\{bolumler,tampon}, components\{kart-ui.tsx, ui}, lib, app\providers.tsx, test}
   │  ├─ e2e\{giris,musteri}.spec.ts
   │  ├─ public\ · index.html · vite.config.ts · vitest.config.ts · playwright.config.ts · tsconfig*.json · package.json
   │  └─ dist\ node_modules\   [üretilen]
   ├─ docs\                        architecture.md · musteri-karti.md · veri-yonetimi.md · yonetim-ve-tampon-tasarimi.md · topoloji-ve-dizin.md
   ├─ data\                        PDF arşivi için (çalışırken oluşur, git'te yok; şu an boş)
   └─ .venv\ .git\                 [üretilen] Python 3.12.10 venv
```

## 6. Tasarıma girdi olacak gözlemler

1. **Senkron vs async:** v3.5 senkron `Session`, `tamlife-api` async. Hedef için tek yol seçilmeli.
2. **Migration zinciri deterministik değil:** `0001` `create_all` ile canlı modele bağlı; model değişince "eski" revizyon farklı şema üretir. Hedef şema için dondurulmuş (açık `op.create_table`) başlangıç revizyonu gerekir.
3. **Kalıcılık:** denetim kalıcı (kuyruklu yazıcı → `audit_event`); **oturumlar hâlâ bellekte** (yeniden başlatmada herkes düşer; `--workers 1` şartı buradan).
4. **Kapsam boşluğu:** 17 modülün 3'ü canlı (musteri, rapor, roller) + Yönetim/Veri Girişi; 9'unun yalnız tablosu, 2'sinin hiçbir şeyi yok. Utilizasyon API'si hazır, arayüzü yok (skor kriter/dağıtım ekranı Veri Girişi ile birleşebilir).
5. **Bilerek kalan artıklar:** `backend/var/prod_geri_al/` (git dışı; üretim dosyalarının geri alma kopyaları, silme kullanıcıya bırakıldı), `lib/api-types.ts` (OpenAPI akışının parçası, bayat olabilir; `npm run api:uret`).
6. **Açık kararlar:** Excel yükleme (`openpyxl` yeni bağımlılık), yedekten geri yükleme, günlük saklama süresi, canlı Oracle adaptörleri (kaynak sorguları sözleşmesi + ayrı işçi süreç).
