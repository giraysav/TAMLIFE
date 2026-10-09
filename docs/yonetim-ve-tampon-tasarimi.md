# Yönetim konsolidasyonu ve veri tamponu — tasarım

Tarih: 2026-10-07. Kapsam: (1) DB, rol, arıza ve log yönetiminin tek admin alanında toplanması; (2) dış DB verileri için tampon → analiz → dağıtım hattı.
`E:\TAMLIFE` yalnız **okundu** (kod ve şema; `.env`, DB ve müşteri satırı okunmadı, hiçbir şey yazılmadı). Üretimle çalışma anı bağlantısı yoktur.

## 1. Üretimden alınan dersler

| Üretim (okunan) | Ne yapıyor | Yeni yapıda karşılığı |
|---|---|---|
| `backup.py` | tam JSON yedek, doğrulama, geri yükleme; denetim tabloları geri yüklemede korunur | Yönetim › Veritabanı: SQLite çevrimiçi yedek + doğrulama (geri yükleme **ayrı onaylı adım**, bu sürümde yok) |
| `hatalar.py` | her hata `KOD` + `KAYIT NO` taşır; ham istisna kullanıcıya dönmez, günlüğe yazılır | `fault_event` tablosu + genel istisna yakalayıcı; yönetici kayıt no ile arar |
| `kullanici_log.py`, `sistem_loglari` | kişi başı ayrı tablo (u_<id>), ayrı SQLite dosyası | **tek** `audit_event` tablosu (filtre/sayfa/CSV); kişi başı tablo anti-pattern, taşınmadı |
| `gunluk.py` | kuyruklu, dönen dosya günlüğü (5 MB × 5), istek beklemez | aynı yaklaşım: `var/logs/uygulama.log`, kayıt no ile arama |
| `izleme.py` | 14 sağlık kontrolü (disk, DB, portlar, çökmeler, veri tazeliği…) | Yönetim › Genel Durum: 8 hafif kontrol (dış bağlantı gerektirmeyen) |
| `reportdb_tampon.py` | kaynak → tampon tablosu tek işlemde değişir; küçülme koruması; tazelik; "kartlara yaz" varsayılan **kapalı**; ilk değerler saklanır, "eski değerlere dön" yalnız elle değişmemişleri geri alır | Veri Girişi hattı (§3); aynı güvenceler genelleştirildi |
| `ham_depo.py` | satırlar 2000'lik zlib JSON **blok**; kısa işlemler; set yaşam döngüsü; kaynak başına son 3 set | `ingest_block` + `ingest_batch` (aynı model) |
| `kurallar.py`, `hedefler.py` | bildirimsel kural + **sabit hedef kataloğu** (serbest hedef yok) | `distribution_rule` + `tampon/dagitim.py::HEDEFLER` |
| `musteri_no.py` | bir kartta çok numara; karşılaştırma anahtarı = baştaki sıfırsız rakam | `tampon/eslestirme.py` (aynı kural) |
| `db_kaynak.py`, `reportdb_senkron.py` | yalnız SELECT; Oracle istemcisi web sürecine yüklenmez; zamanlanmış ayrı süreç, kilit dosyası | kaynak arayüzü + (sonraki faz) ayrı işçi süreç; bu sürümde canlı bağlantı **kapalı** |

Üretimdeki kaynak sözleşmeleri (tampona girecek veriler, değerleri okunmadı): ReportDB alarm sayıları (Müşteri No, Ünvan, Aktif/Kapanan/Biletli alarm, En eski alarm, Son kapanış, Veri zamanı); Ürün-Tutar (servisler, lokasyon sayısı, segment, bağlantı tipi, fatura bedeli); Onent (lokasyon/CI sayısı); Excel (müşteri ham veri). Eşleşme anahtarı **Müşteri No / NCST**, ünvan değil.

## 2. Yönetim alanı (bilgi mimarisi)

Giriş noktası değişmedi: sağ üstteki kullanıcı menüsü › **Yönetim** (yan menüde yok; önceki karar). İçeride tek sayfa, altı bölüm, adres `#/yonetim/<bölüm>`:

```
Yönetim
├─ Genel Durum    sağlık kontrolleri + 4 gösterge (DB, arıza, günlük, tampon) + bağlantı yuvaları
├─ Veri Girişi    tampon hattı: Partiler → Analiz → Dağıtım kuralları → Uygulamalar
├─ Veritabanı     motor/sürüm/boyut, tablo sayıları, bütünlük, yedek al/doğrula
├─ Roller         rol görünümleri (mevcut ekran, taşındı)
├─ Arızalar       hata kayıtları (kod + kayıt no), durum: açık → incelemede → kapalı
└─ Günlükler      denetim olayları (süz/sayfala/CSV), aktif oturumlar (kapat), uygulama günlüğü
```

Önceki 5 admin girişi (`admin`, `integrations`, `veri`, `roller`, kartlı Yönetim açılış sayfası) bu 6 bölüme indi; eski adresler (`#/admin`, `#/veri`, `#/integrations`, `#/roller`) yeni bölümlere yönlenir. `utilizasyon` (skor) ayrı modül olarak kalır; arayüzü yazılınca Yönetim'e taşınabilir.

**Arayüz ilkeleri**
- *Durum önce:* her bölüm 3–4 göstergeyle açılır, sonra tablo, ikincil işlemler en altta.
- *Tek mod:* bölüm içinde ikinci sekme yok; akış varsa (Veri Girişi) numaralı adımlar.
- *Güvenli eylem:* yazan her işlem önizleme → onay → geri alma sırasını izler; silme/geri yükleme tek tıkla olmaz.
- *Performans:* Yönetim ayrı JS parçası (yalnız admin indirir); veri TanStack Query ile önbellekli, arka planda yenilenir; sunucuda sayfalama (≤200); özet tek istek.
- *Erişilebilirlik:* durum rengi + metin + ikon; tablolarda `scope`/başlık; canlı bölgeler `role=status`.
- *Dil:* TR/EN, bölüm metinleri `src/yonetim/metin.ts`.

## 3. Veri Girişi hattı (tampon → analiz → dağıtım)

```
 Kaynak ──► [1 TAMPON]  ──► [2 ANALİZ] ──► [3 DAĞITIM]            ──► panel tabloları
 CSV        ingest_batch    sütun profili   kural + sabit hedef         customer.alarm_count …
 Örnek      ingest_block    anahtar önerisi önizleme → uygula          distribution_log (geri al)
 (Oracle*)  değişmez ham    eşleşme oranı   tek işlem, onaylı
 * kapalı: aynı arayüz, canlı bağlantı yok
```

1. **Tampon** — gelen veri olduğu gibi, değiştirilmeden saklanır (zlib JSON blokları). Parti durumu: `receiving → ready | failed | rejected`. Korumalar: boş dosya reddi, satır üst sınırı (300 bin), **küçülme koruması** (önceki partiden %50 küçükse ≥200 satırlıkta `rejected`, yönetici "yine de al" der), kaynak başına son 3 hazır parti tutulur.
2. **Analiz** — sütun profili (doluluk, farklı değer, tip, en sık değerler) ve **anahtar önerisi**: hangi sütun müşteri kartlarıyla (Müşteri No / NCST / ünvan) kaç % eşleşiyor. Veri değişmez, yalnız rapor.
3. **Dağıtım** — kural = (kaynak, anahtar sütunu → eşleşme alanı, **sabit hedef**, işlem, değer sütunu, koşullar, eşleşmeyeni sıfırla?). Hedef kataloğu sabittir (serbest hedef yok). Akış: **önizleme** (yazmaz; değişecek/eşleşmeyen/belirsiz sayıları + örnek) → **uygula** (onay şart, tek işlem, her değişiklik `distribution_log`'a eski/yeni değerle) → **geri al** (yalnız hâlâ yazılan değerde duranlar; elle değişen korunur). Birden çok karta düşen numara **belirsiz** sayılır ve atlanır. Kural varsayılan **kapalı** oluşur.

Güvenlik: kaynak sorguları yalnız SELECT; hata ayrıntısında parola/host yok; yükleme ham gövde (çok parçalı form yok → yeni bağımlılık yok); tüm yazma işlemleri denetim kaydı üretir.

**Bu sürümde yok (bilinçli):** canlı Oracle çekimi (ayrı işçi süreç + kaynak sorguları sözleşmesi bekliyor), Excel yükleme (`openpyxl` venv'de yok; eklemek yeni bağımlılık/wheel demek), yedekten geri yükleme, zamanlanmış çekim.

## 4. Veri modeli (Alembic 0005–0007)

| Tablo | Yeni/değişen | Not |
|---|---|---|
| `fault_event` | yeni | kayıt no (benzersiz), kod, seviye, kaynak, mesaj, aktör, durum, çözüm notu |
| `ingest_batch` | +7 sütun | etiket, satır sayısı, sütunlar, profil/analiz, oluşturan, bitiş, hata |
| `ingest_block` | yeni | (parti, blok no) → zlib JSON |
| `distribution_rule` | yeni | kural tanımı, varsayılan kapalı |
| `distribution_log` | yeni | uygulama günlüğü (run_id, müşteri, hedef, eski, yeni, geri alındı) |
| `ingest_record` | **kaldırıldı** (0006) | satır başına JSONB; hiçbir kod kullanmıyordu, yerini `ingest_block` aldı |
| `external_source` | **kaldırıldı** (0007) | kaynak listesi koddadır (`app/external.py` `SOURCES`); satır tutmak yalnız ikinci doğruluk kaynağı yaratıyordu |
| `audit_event` | kullanılmaya başladı | `audit_log` artık kalıcı yazıyor (önceden yalnız bellek) |

## 5. API (hepsi yalnız admin; yazanlar CSRF'li)

`/api/v1/yonetim/`: `ozet` (sağlık kontrolleri + göstergeler + bağlantılar, tek istek), `veritabani`, `veritabani/yedek` (POST), `veritabani/yedek/{ad}/dogrula`, `arizalar`, `arizalar/{id}/durum`, `ariza-kodlari`, `gunlukler`, `gunlukler.csv`, `oturumlar`, `oturumlar/{kullanici}/kapat`, `uygulama-gunlugu`.
`/api/v1/tampon/`: `kaynaklar`, `partiler`, `partiler/{id}`, `partiler/{id}/satirlar`, `partiler/{id}/analiz`, `partiler/{id}/kabul`, `DELETE partiler/{id}`, `yukle` (PUT ham CSV), `ornek` (POST, yalnız dev), `hedefler`, `kurallar` (GET/POST/PUT/DELETE), `kurallar/{id}/etkin`, `kurallar/{id}/onizle|uygula`, `uygulamalar`, `uygulamalar/{run}/geri-al`.

## 6. Fazlar

| Faz | İçerik | Durum |
|---|---|---|
| A | kalıcı denetim, arıza kayıtları, dosya günlüğü, yönetim API'si | **yapıldı** (2026-10-07) |
| B | tampon + analiz + dağıtım (CSV/örnek) | **yapıldı** |
| C | Yönetim arayüzü (6 bölüm) | **yapıldı** |
| D | canlı kaynak adaptörleri + ayrı işçi süreç + zamanlama | kaynak sorguları sözleşmesi gelince |
| E | Excel, yedekten geri yükleme, günlük saklama süresi/temizlik | karar bekliyor |

## 7. Uygulama notları (2026-10-07)

**Kod yerleşimi.** Özellik başına paket: `backend/app/yonetim/` (router + db/ariza/gunluk/saglik/ozet) ve `backend/app/tampon/` (router + depo/analiz/dagitim/kaynak/eslestirme/profil). Bu iki paket birbirini import etmez; ortak kod çekirdekte: `app/ariza.py` (arıza kaydı), `app/ortak.py` (`UygulamaHatasi`, zaman, sayfalama, metin yardımcıları, `ok()`). Arayüz: `ekran-react/src/yonetim/` (`bolumler/` + `tampon/`), her bölüm ayrı JS parçası (lazy), veri TanStack Query ile.

**Denetim yazımı kuyruklu.** `audit_log` olayı önce bellek kuyruğuna alır (anında), arka plan iplik toplu yazar; DB kapalıyken istek/giriş **bekletilmez** (devre kesici 30 sn, kuyruk 5000). Yönetim › Günlükler okurken önce kuyruğu boşaltır. Gerekçe: senkron yazım DB erişilemezken her girişi bağlantı zaman aşımı kadar bekletiyordu (testte yakalandı); PostgreSQL bağlantısına da 3 sn zaman aşımı eklendi.

**Doğrulama (temizlik sonrası).** Backend 289 geçti / 1 atlandı (yönetim, tampon, yetki, kimlik sınırı, skor, müşteri), arayüz 18 vitest, `tsc`/`oxlint`/`ruff` temiz, `npm run build` temiz. Alembic 0005, 0006 ve 0007: mevcut veritabanında, sıfırdan kurulumda (şema aynı, 34 tablo = 33 alan + `alembic_version`) ve `downgrade -1`/`upgrade` turunda denendi. Arayüz gerçek tarayıcıda uçtan uca gezildi (örnek parti → analiz → kural → önizle → uygula → geri al; yedek al/doğrula; yakalanmayan hata → arıza kaydı → kapatma). **Yapılmadı:** Playwright e2e (güncellendi ama çalıştırılmadı; sunucu + parola gerektirir).

**Gözlenen, kapsam dışı.** `GET /api/v1/musteri/{id}` gibi `int` yol parametreli uçlar çok büyük sayıda (`99999999999999999999`) SQLite taşması (`OverflowError`) ile 500 veriyordu; artık kod + kayıt no ile yakalanıyor, ama kök neden (`id` için üst sınır) ayrıca düzeltilmeli.

## 8. Temizlik (2026-10-07, sonra)

Kaldırıldı: üretim gömmesi (`deploy/prod/` Flask vekili + `uretime_bagla.ps1`, `POST /api/v1/session/sso`, `TAMLIFE_SSO_SECRET`, arayüzde SSO/gömülü mod, `build:prod`, SSO testleri); eski admin uçları ve işlevleri (`/api/v1/admin`, `/veri`, `/integrations`; yerlerini `/yonetim/**` aldı); kullanılmayan `ingest_record` tablosu (migrasyon 0006); 73 boş arayüz iskelet dosyası, ölü `shell/layout.tsx`, `shared/empty.tsx`, `lib/i18n/*`; kullanılmayan 21 çeviri anahtarı; boş `data/incoming`, `alembic/versions/.gitkeep`, artık `var/t.db`. Bayat testler yeni uçlara taşındı (sır sızıntısı kapsamı korunarak). `base_path`/`apiYolu` (arayüzü alt yolda sunma) genel amaçlı olduğu için kaldı.

**İkinci temizlik ve sadeleştirme (2026-10-07).** Kaldırıldı: `web/` (eski JSX kabuğu), `contract.py` (üretim kutucuk envanteri), `ingest.py`, `trmetin.py` (içerik `ortak.py`ye), `external_source` tablosu ve `ExternalSource`/`seed_source_slots` (migrasyon 0007), tanı uçları `/summary` `/schema` `/sources` `/directory`, 5 kullanılmayan UI ilkeli, 10 kullanılmayan npm bağımlılığı (`react-hook-form`, `zod`, `@hookform/resolvers`, `recharts`, `@tanstack/react-router`, `@tanstack/react-table`, `@radix-ui/react-{avatar,progress,separator,tooltip}`).
Yeniden düzenlendi: `main.py` ~80 satıra indi (`oturum_api`, `katalog_api`, `rol_api` ayrıldı); müşteri/rapor/skor kodu `musteri/`, `rapor/`, `skor/` paketlerine taşındı; `admin.py` → `baglantilar.py`; tüm servis hataları `UygulamaHatasi` alt sınıfı, tek işleyici (`{"detail": mesaj}`); arayüzde `shell/kart-ui.tsx` → `components/kart-ui.tsx`, müşteri/rapor sayfaları `shell/` → `musteri/`, `lib/http.ts` yalnız taban yol + CSRF + 401.

**Kaldırılanlar (2026-10-09):** `lib/api-types.ts` (kullanılmıyordu), `tamlife-api/` (kullanılmayan ayrı iskelet; `wheels/` üst klasöre taşındı).