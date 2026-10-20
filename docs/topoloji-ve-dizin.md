# TAMLIFE v3.5 — topoloji ve dizin yapısı (mevcut durum)

> **Not (2026-10-12):** Bölüm 1 (çalışma topolojisi: "yalnız lokal", kapalı AD/Oracle) tarihseldir. Canlı düzen (https://tamlife/, kalıcı görevler, prod kipi, işçi süreçler) için `architecture.md` geçerlidir; bu belge paket/dosya topolojisi referansı olarak kalır.

> Güncellendi (2026-10-08): Onedesk, ICT SMS/APN, İzin&Takvim + TAM Takvim, Çeyrek Bazlı Sunum, rol eylem yetkileri, müşteri portföyü, sol alt hesap kartı ve yeni genel bakış yayı eklendi (`modul-onedesk-gelir-takvim.md`).
> Önceki güncelleme (2026-10-07, temizlik ve sadeleştirme sonrası): özellik paketleri, tek hata sözleşmesi, ince `main.py`, `web/`/`contract.py`/`ingest.py`/`trmetin.py`/`external_source` kaldırıldı. Ayrıntı: `yonetim-ve-tampon-tasarimi.md` §7–8.

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
│                                            backend/var/dev.db  (ortak panel DB, Alembic)    │
│                                            backend/var/kullanicilar/<kullanici>.db          │
│                                              (kişisel: takvim, gelir; ilk açılışta kurulur) │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
 Kapalı / yok: canlı AD bind, Oracle (Onedesk/Onent/Ürün-Tutar), PostgreSQL, dış ağ, E:\TAMLIFE
```

| Port | Süreç | Başlatma |
|---|---|---|
| 8117 | API (+ derlenmiş arayüz) | `backend\dev.ps1` · arayüzle: `-Arayuz` |
| 5173 | Vite dev | `cd ekran-react; npm run dev` |
| 5174 | Playwright `baseURL` | `npm run e2e` (sunucuyu önceden siz açarsınız) |

## 2. Backend katman topolojisi

`backend/app` = **çekirdek** (24 dosya, ~2.500 satır) + **8 özellik paketi** (42 dosya). Toplam 66 dosya, ~8.400 satır. Oklar `import` satırlarından çıkarıldı.

```
main.py ──┬─ oturum_api · katalog_api · rol_api      çekirdek uçlar (giriş/çıkış, modüller/ana sayfa, /roller)
          ├─ yonetim.router ─► arizalar, gunlukler, veritabani, saglik, ozet, dosya_gunlugu, kalici_yazici ─► ariza, ortak, models
          ├─ tampon.router ──► depo, analiz, dagitim, kaynak ─► eslestirme, profil, ortak, models
          ├─ musteri.api ────► musteri.servis ─► skor.servis ─► skor.motor (saf hesap)
          │                └─► rapor.servis ──┬─► musteri.servis, skor.servis
          │                                   └─► rapor.metin
          ├─ skor.api ───────► skor.servis
          ├─ onedesk.api ────► onedesk.servis ─► rca (saf) · yz (isteğe bağlı LLM) · ice_al ─► tampon.depo (yalnız okuma)
          ├─ gelir.api ──────► gelir.servis (SMS, APN kurulum, müşteri çalışmaları)
          ├─ takvim.api ─────► takvim.servis (kişinin günleri, TAM Takvim, sunuma gönder)
          └─ security ───────► session ─► config
çekirdek: rolgorunum ─► catalog, authz, models · navigation ─► catalog, authz · deps ─► authz, gateway, session, config
          authz ─► catalog, session · baglantilar ─► ad, external, config · audit ─► models (tembel)
bağımsızlık: yonetim ↔ tampon birbirini import etmez; müşteri alanı tek yönlü: skor ← musteri ← rapor
```

| Katman | Dosyalar | Not |
|---|---|---|
| Kimlik/oturum | `session.py`, `security.py`, `authz.py`, `deps.py` | bellek içi oturum, CSRF, hız sınırı, `can_open` |
| Katalog/görünüm | `catalog.py` (17 modül), `rolgorunum.py`, `navigation.py` | tek kaynak; yetki sunucuda |
| Çekirdek uçlar | `oturum_api.py`, `katalog_api.py`, `rol_api.py` | `main.py` yalnız kurar ve bağlar (~90 satır) |
| Erişim ve kullanıcı | `erisim.py` (`modul_erisim`, eylem yetkileri), `kullanicilar.py` (giriş kaydı, `last_login_at`) | her yeni uç `modul_erisim` kullanır |
| Onedesk (paket) | `onedesk/{api,servis,rca,yz,ice_al}.py` | aktif/kapanan A/T/Ş, top10, RCA ortak noktaları, tavsiyeler; LLM varsayılan kapalı |
| Gelir (paket) | `gelir/{api,servis}.py` | ICT SMS; APN kurulum ve müşteri çalışmaları; Member yalnız kendi kayıtları |
| Takvim (paket) | `takvim/{api,servis}.py` | gün durumu, toplu atama, TAM Takvim özeti, sunuma gönder (+ `/sunum/ogeler`) |
| Müşteri alanı | `musteri/{api,servis}.py`, `rapor/{servis,metin}.py`, `skor/{api,servis,motor}.py` | `skor/motor.py` üretimden birebir; golden test |
| Veri | `models.py` (34 alan tablosu), `gateway.py`, `alembic/` | senkron `Session`, istek başına; PostgreSQL bağlantısı 3 sn zaman aşımlı |
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
| musteri | `customer`, `customer_team`, `matrix_config` | `musteri/` | `/musteri/**` (+ `/portfoy`, `/secenekler`) | `src/musteri/` portföy kartları + ekleme çekmecesi — **[canlı]** |
| rapor | `report`, `report_draft`, `report_dispatch`, `report_recipient` | `rapor/` | `/rapor/**`, `/musteri/{id}/rapor/**` | `aylik-rapor.tsx`, `rapor-sayfasi.tsx` — **[canlı]** |
| utilizasyon | `util_criteria_set`, `score_detail`, `score_history`, `score_approval_request`, `scoring_exclusion`, `affiliate_final_flag` | `skor/` | `/skor/**` | Yönetim › TAM Utilizasyon (`src/yonetim/bolumler/utilizasyon.tsx` + `src/yonetim/utilizasyon/`) — **[canlı]** (REPORTDB/ONENTDB sorguları yok) |
| roller | `role_view` (+ `permissions`) | `rolgorunum.py` | `/roller` | `shell/roller-sayfasi.tsx` + Yönetim › Roller (sayfalar + ek yetkiler) — **[canlı]** |
| onedesk | `onedesk_record` | `onedesk/` | `/onedesk/**` | `src/onedesk/` — **[canlı]** (Veri Girişi'nden beslenir) |
| tamsms, tamapn | `sms_revenue`, `apn_revenue`, `apn_work` | `gelir/` | `/gelir/**` | `src/gelir/` — **[canlı]** |
| takvim, takvim_ozet | `calendar_day`, `app_user.last_login_at` | `takvim/` | `/takvim/**` | `src/takvim/` — **[canlı]** |
| sunum | `presentation` | `takvim/` | `/sunum/ogeler` | `src/sunum/` (şimdilik TAM Takvim'den gelenler) — **[canlı]** |
| yonetim | `fault_event` (+ `audit_event`) | `yonetim/` | `/yonetim/**` | `src/yonetim/` 8 bölüm (Kurum Bağlantıları dahil) — **[canlı]** |
| ingest (Veri Girişi) | `ingest_batch`, `ingest_block`, `distribution_rule`, `distribution_log` | `tampon/` | `/tampon/**` | `src/yonetim/tampon/` — **[canlı]** (CSV + örnek; Oracle kapalı) |
| talep | `demand`, `demand_log` | `talep/` | `/talep/**` | `src/talep/` (hesap menüsü › Geliştirme Talepleri) — **[canlı]** |
| radar | ReportDB tamponu (`ingest_batch` `oracle_reportdb`) + `customer` | `radar/` | `/radar` | `src/radar/` — **[canlı]** (elle giriş yok; `radar_prospect` kullanılmıyor) |
| proje | `project_item`, `project_action`, `project_customer_work` | `proje/` | `/proje/**` | `src/proje/` — **[canlı]** (özet, detay takibi, müşteri bazlı çalışmalar, Excel) |
| gelir_uretim | `income_production` | yok | yok | genel `ModulSayfasi` **[iskelet]** |
| topoloji (TopoMaker) | — (dosya saklanmaz) | `topoloji/` | `/topoloji/analiz` | `src/topoloji/` (müşteri kartı › Topo Maker) — **[canlı]** |
| baglantili | — | yok | yok | `ready=False` **[iskelet]** |

**Alembic zinciri (2026-10-09 sıfırlandı):** `0001_baslangic` → `0002_ad_kimlik` → `0003_utilizasyon` → `0004_sunum_ayar` → `0005_talep` → `0006_proje`. Revizyonlar açık `op.create_table`/`op.add_column` ile yazılır, `app.models` import etmez (dondurulmuş şema); `tests/test_alembic.py` zincir sonucunu modelle karşılaştırır.

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
                             onedesk → onedesk/onedesk-sayfasi (+ analiz, kaynak) · tamsms/tamapn → gelir/{sms,apn}-sayfasi
                             takvim → takvim/izin-takvim · takvim_ozet → takvim/tam-takvim · sunum → sunum/sunum-sayfasi
                             yonetim/<bolum> → yonetim/yonetim-sayfasi (lazy; durum, tampon, veritabani, roller, arizalar, gunlukler; yalnız admin)
                             eski #/admin, #/veri, #/integrations, #/roller → admin için yeni bölümlere yönlenir
                             diğer modüller → shell/modul-sayfasi.tsx (yer tutucu)

components/  sayfa-ui.tsx (SayfaKabi, Sekmeler, Kpi, Panel, Alan) · grafik.tsx (Halka, YatayCubuklar, Sutunlar: SVG) · cekmece.tsx · duzenlenebilir-tablo.tsx
             ui/ (button, card, input, label, sheet, sidebar, skeleton, ozet-orbit, modul-yayi: 3B eğimli genel bakış yayı)
lib/         http.ts (taban yol, CSRF başlığı, 401) · oturum.ts (oturum, boşta süre) · sorgu.ts (oku/yaz/yukle) · bicim.ts
             kanca.ts · utils.ts
```

Gerçek arayüz kodu `src/shell` (13 dosya), `src/musteri`, `src/yonetim`, `src/onedesk`, `src/gelir`, `src/takvim`, `src/sunum`, `src/components`. Hesap kartı sol altta (`shell/kullanici-karti.tsx`). TanStack Query yönetim ve yeni modüllerde kullanılıyor; çalışma zamanı bağımlılıkları 11 pakettir (React, TanStack Query, Radix dialog/label/slot, framer-motion, lucide, tailwind-merge, clsx, cva).

## 5. Dizin yapısı

```
E:\TAMLIFE_Dev\   (lokal geliştirme: D:\TAMLIFE_Dev)
├─ wheels\                         offline kurulum paketleri (cp312 win_amd64; requirements + pytest/httpx/ruff)
└─ TAMLIFE_v3.5\                   ◄── bu depo (git: main, uzak yok)
   ├─ CLAUDE.md · .gitignore · requirements.txt (yalnız çalışma zamanı)
   ├─ backend\
   │  ├─ app\                      çekirdek (21) + 5 paket, bkz. §2
   │  │  ├─ main.py  config.py  catalog.py  models.py  db.py  audit.py
   │  │  ├─ session.py security.py authz.py deps.py  rolgorunum.py navigation.py
   │  │  ├─ oturum_api.py katalog_api.py rol_api.py
   │  │  ├─ ad.py external.py baglantilar.py  ariza.py ortak.py  erisim.py kullanicilar.py
   │  │  ├─ yonetim\                 router · ozet · saglik · veritabani · arizalar · gunlukler · kalici_yazici · dosya_gunlugu · yakalayici · models
   │  │  ├─ tampon\                  router · depo · analiz · dagitim · kaynak · eslestirme · profil · models
   │  │  ├─ musteri\                 api · servis
   │  │  ├─ onedesk\                 api · servis · rca · yz · ice_al
   │  │  ├─ gelir\                   api · servis
   │  │  ├─ takvim\                  api · servis
   │  │  ├─ rapor\                   servis · metin
   │  │  └─ skor\                    api · servis · motor
   │  ├─ alembic\{env.py, versions\0001_baslangic}    alembic.ini
   │  ├─ tests\                    test_{yonetim,tampon,ozellikler,auth_security,kimlik_siniri,roller,musteri,skor,skor_api,arayuz_sunumu}.py · conftest.py · skor_golden.json
   │  ├─ dev.ps1  pytest.ini  ruff.toml
   │  └─ var\                      [üretilen, git'te yok]  dev.db · kullanicilar\*.db · logs\ · yedek\
   ├─ ekran-react\                 TS arayüzü (Vite 8, React 19, Tailwind 4, oxlint, vitest, Playwright)
   │  ├─ src\{shell, musteri, onedesk, gelir, takvim, sunum, yonetim\{bolumler,tampon}, components\{sayfa-ui, grafik, cekmece, duzenlenebilir-tablo, ui}, lib, app\providers.tsx, test}
   │  ├─ e2e\{giris,musteri}.spec.ts
   │  ├─ public\ · index.html · vite.config.ts · vitest.config.ts · playwright.config.ts · tsconfig*.json · package.json
   │  └─ dist\ node_modules\   [üretilen]
   ├─ docs\                        architecture.md · musteri-karti.md · veri-yonetimi.md · yonetim-ve-tampon-tasarimi.md · topoloji-ve-dizin.md
   ├─ data\                        PDF arşivi için (çalışırken oluşur, git'te yok; şu an boş)
   └─ .venv\ .git\                 [üretilen] Python 3.12.10 venv
```

## 6. Tasarıma girdi olacak gözlemler

1. **DB düzeni:** ortak panel DB + kullanıcı başına SQLite dosyası (`app/db.py`). Kişisel tablolar (`KullaniciBase`) Alembic dışında; yönetici görünümleri kullanıcı dosyalarını sırayla okur (≤20 kişi).
2. **Migration:** zincir 2026-10-09'da tek başlangıç revizyonuna (`0001_baslangic`) indirildi, 2026-10-10'da açık `op.create_table` revizyonlarına çevrildi; şema/model eşitliği `tests/test_alembic.py` ile korunur.
3. **Kalıcılık:** denetim kalıcı (kuyruklu yazıcı → `audit_event`); **oturumlar hâlâ bellekte** (yeniden başlatmada herkes düşer; `--workers 1` şartı buradan).
4. **Kapsam boşluğu:** 17 modülün 14'ü canlı (musteri, rapor, roller, onedesk, tamsms, tamapn, takvim, takvim_ozet, sunum, utilizasyon, talep, radar, proje, topoloji) + Yönetim/Veri Girişi; gelir_uretim yalnız tablo; baglantili kartının hiçbir şeyi yok. Utilizasyon API'si ve arayüzü (Yönetim › TAM Utilizasyon) hazır.
5. **İskeletler (bilerek duruyor, sırayla doldurulacak):** gelir_uretim tablosu, kullanılmayan `radar_prospect`, `baglantili` kartı, e2e (Playwright kurulu; `E2E_PASS` olmadan testler atlanır, hiç çalıştırılmadı).
6. **Açık kararlar:** Excel yükleme (`openpyxl` yalnız Ürün-Tutar için eklendi; SMS/APN/müşteri Excel'i yok), yedekten geri yükleme, günlük saklama süresi, canlı Oracle adaptörleri (kaynak sorguları sözleşmesi + ayrı işçi süreç).
