# Veri Yönetimi (admin arkası) tasarımı

Kaynak: eski kod (`D:\Project\TAM_Life\TAMLIFE`, yalnız okundu). `.env` için yalnız anahtar adları okundu, değer okunmadı. Bu belge Final Skoru Atama ve Veri Yönlendirici'nin v3.5 karşılığını tanımlar. **Veri taşıma en son faz.**

## 1. Veritabanı ve kaynak adları (eski kodda yazılı olanlar)

### 1.1 SQLite dosyaları (`SECURE_DB_DIR`)
| Dosya | İçerik | Env |
|---|---|---|
| `veritabani/panel.db` | users, customers, util_criteria, util_criteria_istirak, score_approval_requests, matrix_configs, gelistirme_talepleri, reports… | `DATABASE_URL` |
| `veritabani/analiz.db` | skor_detaylari, skor_gecmisi, puanlama_disi_personel, urun_tutar, sla_analizleri, ats_kayitlari, ci_pivotlari, acik_kayitlari, proje_musteri_calisma, rapor_taslak, rapor_gonderim | `SLA_DB` |
| `veritabani/ham_veri.db` | veri_setleri, ham_bloklar, kurallar, metrikler, uygulama_gunlugu | `HAM_VERI_DB` |
| `veritabani/kullanici_islemleri.db` | kullanicilar, kişi başı `u_<id>` günlükleri | `KULLANICI_LOG_DB` |
| `sistem/giris_siniri.db`, `istek_siniri.db` | hız sınırı sayaçları | `HIZ_SINIRI_DB` |

### 1.2 Oracle kaynakları ve `.env` anahtarları (adlandırma kararı)
| Kaynak | Ön ek (v3.5) | Eski kodda | Not |
|---|---|---|---|
| **Onedesk DB** | `ORACLE_REPORTDB_` | `ONEDESK_DB_` | Canlı `.env` zaten `ORACLE_REPORTDB_*` tutuyor; v3.5 bu adı kullanır |
| Onent DB | `ONENTDB_DB_` | aynı | `ONENT_DB_URL` |
| Ürün-Tutar DB | `URUNTUTAR_DB_` | aynı | `URUN_TUTAR_DB_URL` |
| Onedesk REST (DB değil) | `ONEDESK_BASE_URL`, `ONEDESK_API_KEY` | aynı | adı değişmedi |
| Excel (Müşteri Ham Veri) | — | — | dosya yükleme |

Her Oracle ön eki için anahtarlar: `_ENABLED _HOST _PORT _SERVICE_NAME _USER _PASSWORD _QUERY _TIMEOUT _IMPORT_QUERY _IMPORT_TIMEOUT` (+ `_URL`). Ortak: `ORACLE_CLIENT_DIR`.

**Gözlem (yalnız anahtar adları):** canlı `.env` içinde `ORACLE_REPORTDB_*` ve `ONEDESK_DB_QUERY` var, ama eski kod `ONEDESK_DB_*` okuyor. Yani eski kodda Onedesk DB bağlantı anahtarları `.env` ile eşleşmiyor olabilir. v3.5'te ad tek yere (`ORACLE_REPORTDB_`) indiği için bu uyuşmazlık biter; devreye almadan önce canlı `.env` değerleri sahibi tarafından doğrulanmalı.

## 2. Ekran: Veri Yönetimi (yalnız admin)

Eski "Final Skoru Atama / Veri Yönlendirici" üç adımdı; v3.5'te beş sekme:

| # | Sekme | İş |
|---|---|---|
| 1 | **Veri içeri alma** | Kaynak durumu (Onedesk/REPORTDB, Onent, Ürün-Tutar, Excel), bağlantı testi, veri çekme/yükleme, set listesi (kaynak başına son 3), set sil, ilerleme |
| 2 | **Final skor kriterleri** | Çatı ve iştirak kriter tabloları (başlık, tür, ağırlık, baremler), veri kaynağı seçimi, kural önizleme/deneme |
| 3 | **Skorları dağıt** | Toplu önizleme (hesapla, yazma) → uygula; personel → çatı → iştirak ağacı; iştirak "final skora dahil" seçimi |
| 4 | **Personel skoru ve ağırlık** | Personel ağırlık/dağılım, puanlamadan çıkarılan personel listesi |
| 5 | **Onay talepleri** | TeamMember'ın skor atama talepleri; yönetici onayla/reddet |

Tek müşteriye elle skor atama müşteri kartında kalır (Müşteri modülü), ama aynı sunucu servisini çağırır.

## 3. Final skor kuralları (eski koddan, değişmeden taşınır)
- Skor yalnız **çatı müşteriye** atanır; iştirak kendi skorunu almaz (metrikleri çatıya toplanır).
- Aralık 0–100; geçersiz/sonsuz/aralık dışı değer **reddedilir**, sessizce kırpılmaz.
- Her kriterde tek barem: **30 / 50 / 70 / 100** puan (hiçbir kural tutmazsa 0). Katkı = ağırlık × puan/100. Final = Σkatkı / Σağırlık × 100.
- Barem hücreleri kuraldır: sayısal (`1-49`, `500+`, `>=500`, `<50`) veya kategorik (`SMB`, `SA, PA, WHOLESALE`).
- **Hesap yalnız sunucuda**; istemcinin gönderdiği skor kabul edilmez. Eksik kriteri olan müşteri atlanır (neden raporlanır).
- Kriter tablosu kaydedilince tüm çatı müşteriler yeniden hesaplanır; yalnız skoru değişene yazılır, geçmişe `kriter_degisikligi` düşer. Geçmiş kaynağı: `sayfa` | `toplu` | `kriter_degisikligi`.
- Metrik kaynak önceliği: Ürün-Tutar DB > Excel özeti; şikayet/talep: Onedesk DB (REPORTDB) > panel; lokasyon: Ürün-Tutar > Onent > panel.
- Yetki: `final_skor_atama` yalnız **admin ve TeamMngr**. TeamMember kendi çatı müşterisi için **talep** açar (müşteri başına tek bekleyen talep); yönetici onaylar/reddeder.

## 4. Hedef veri modeli

Tek kaynak PostgreSQL (SQLite dosyaları tek şemada toplanır; geliştirmede SQLite). Tablo adları İngilizce, mevcut `models.py` ile hizalanır.

| Hedef tablo | Eski karşılığı | Not |
|---|---|---|
| `util_criteria_set` (scope: `parent`/`affiliate`, `criteria` jsonb, `version`, `updated_by`, `updated_at`) | util_criteria, util_criteria_istirak | Sürüm artar; eski sürümler tutulur |
| `score_detail` (customer_id PK, score, detail jsonb, updated_at) | skor_detaylari | |
| `score_history` (customer_id, score, source, actor_id, at, detail) | skor_gecmisi | indeks (customer_id, at) |
| `score_approval_request` (customer_id, requested_by, requested_at, status, resolved_by, resolved_at) | score_approval_requests | Kısmi benzersiz indeks: müşteri başına tek `pending` |
| `scoring_exclusion` (user_id, set_by, at) | puanlama_disi_personel | |
| `affiliate_final_flag` (customer_id, included) | istirak final dahil | |
| `ingest_set` / `ingest_block` | veri_setleri / ham_bloklar | blok = zlib sıkıştırılmış JSON satır listesi |
| `ingest_rule` / `ingest_metric` / `ingest_apply_log` | kurallar / metrikler / uygulama_gunlugu | |
| `product_amount` | urun_tutar | Ürün-Tutar özeti |
| `data_source` | — | kaynak anahtarı, tür, durum (parola/host yok) |

`models.py` içindeki basit `utilization_criterion`/`utilization_score` bu şemaya göre değiştirilir (Alembic revizyonu).

## 5. API sözleşmesi (`/api/v1/veri/...`, hepsi yalnız admin, durum değiştirenler CSRF'li)

| Yöntem ve yol | İş | Eski karşılık |
|---|---|---|
| `GET /veri/kaynaklar` | kaynak durumu + set listesi + kapasite | `/api/veri/kaynaklar` |
| `POST /veri/kaynaklar/{kaynak}/test` | bağlantı testi (`SELECT 1 FROM DUAL`), 6/dk | `/api/veri/db/<k>/test` |
| `POST /veri/kaynaklar/{kaynak}/cek` | DB'den ham veri çekimi (arka plan işi) | `/api/veri/db/<k>/cek` |
| `POST /veri/yukle` | Excel yükleme (arka plan işi) | `/api/veri/yukle` |
| `GET/DELETE /veri/setler/{id}` | set ilerleme/özet, silme | `/api/veri/set/<id>` |
| `GET /veri/kriter-meta` | kriter editörü seçenekleri | `/api/veri/kriter_meta` |
| `POST /veri/kaynak-onizle`, `POST /veri/kriter-dene` | kural önizleme/deneme, 30/dk | aynı adlar |
| `GET/PUT /skor/kriterler/{scope}` | çatı/iştirak kriter tablosu (sürümlü) | `/api/util_criteria*` |
| `POST /skor/toplu/onizleme` | hesapla, yazma | `/api/skor_toplu/onizleme` |
| `POST /skor/toplu/uygula` | seçili müşterilere yaz (≤5000) | `/api/skor_toplu/uygula` |
| `GET /skor/agac` | personel → çatı → iştirak | `/api/skor_agaci` |
| `PUT /skor/istirak/{id}/final-dahil` | iştirak seçimi | `/api/istirak_final_dahil` |
| `PUT /skor/puanlama-disi` | dışarıda kalan personel (tam liste) | `/api/puanlama_personeli` |
| `PUT /skor/musteri/{id}` | tek müşteri skoru (yetki: final_skor_atama) | `/api/save_customer_score` |
| `GET/POST /skor/talepler`, `POST /skor/talepler/{id}/karar` | onay akışı | `/api/*score_approval*` |

## 6. Güvenlik ve işletim kuralları
- Sorgu (`*_QUERY`, `*_IMPORT_QUERY`) **yalnız `.env`'den**; arayüzden SQL girilmez; yalnız `SELECT`/`WITH` kabul edilir.
- Hata ayrıntısında parola, host, DSN taşınmaz; yanıtlar yalnız durum + eksik anahtar adı.
- Ağır işler (Excel 200 bin × 35, DB çekimi) web sürecinde değil **ayrı işçi sürecinde** koşar; ilerleme `ingest_set.progress` üzerinden izlenir; kapasite sınırları (`azami_satir`, `saklama adedi`) korunur.
- Yazma işlemleri tek veritabanı işleminde; skor yazımında `score_history` aynı işlemde yazılır.
- Her yazma `audit_event` kaydı üretir (aktör, işlem, müşteri/kaynak anahtarı; değer yok). Skor değişimi eski/yeni skor ile.
- Bu geliştirme ortamında gerçek Oracle/AD yok: Oracle için **sahte adaptör + sabit veri** (kaynak anahtarı aynı, `connect()` kapalı kalır).

## 7. Test planı
- **Hesap motoru**: saf fonksiyon; eski `skor_motoru.py` davranışı için sabit test vektörleri (barem sınırları, kategorik eşleşme, eksik kriter, 100 sınırı).
- **Eşdeğerlik**: aynı kriter + aynı metrikle yeni motor skoru = eski motor skoru (örnek müşteri kümesi, veri taşıma fazında).
- API: yetki matrisi (anonim 401, TeamMember 403, TeamMngr/admin 200), CSRF, aralık dışı skor 400, iştirak 400, tek bekleyen talep, toplu uygula ≤5000.
- Güvenlik: yanıt/audit/log'da sır sızıntısı yok (mevcut `integrations` testi gibi).
- Arayüz: Playwright ile kriter kaydet → önizle → uygula → ağaçta skor.

## 8. Fazlar (veri taşıma en sonda)
| Faz | İş | Çıkış ölçütü |
|---|---|---|
| V0 | Anahtar adları (`ORACLE_REPORTDB_`), kaynak durum API, `data_source` | Durum ekranı gerçek yapılandırma anahtarlarını gösterir |
| V1 | Şema + Alembic (bölüm 4) | `alembic upgrade head` temiz |
| V2 | Skor motoru + kriter CRUD (sürümlü) | Test vektörleri geçer |
| V3 | Önizleme/uygula + geçmiş + ağaç + puanlama dışı | Yetki ve aralık testleri geçer |
| V4 | Talep/onay akışı | Tek bekleyen talep, karar denetim kaydı |
| V5 | İçe alma: Excel + sahte Oracle adaptörü, işçi süreç | Büyük dosya web'i yavaşlatmaz |
| V6 | Arayüz: 5 sekme | Playwright akışı geçer |
| V7 | **Veri taşıma** (prod → v3.5) ve eşdeğerlik testi | Skorlar eski sistemle aynı |

## 9. Açık sorular
1. Canlı `.env`'de Onedesk DB gerçekten `ORACLE_REPORTDB_*` ile mi tanımlı, eski kod neden `ONEDESK_DB_*` okuyor? (Değer paylaşılmadan, sahibi doğrulamalı.)
2. Skor geçmişi saklama süresi var mı?
3. Veri Yönlendirici kuralları (ham_depo → metrik) eski kodda 2026-09-29'da skordan kaldırılmış; hâlâ taşınsın mı yoksa yalnız kriter kaynak seçimi mi kalsın?
4. İştirak "final skora dahil" etkisi (katsayı) tanımlı değil; ertelensin mi?
5. Musteri verisi dev'e maskeli mi taşınacak (V7 öncesi karar)?
