# Onedesk, ICT SMS / APN, İzin&Takvim ve TAM Takvim (2026-10-08)

Kaynak (yalnız okundu): `kutucuklar/onedesk`, `kutucuklar/ictapn`, `kutucuklar/takvim`, `kutucuklar/sunum`, `ats_analizi.py`, `asistan.py`, `blueprints/projects_bp.py`. Müşteri/kayıt verisi taşınmadı; yalnız şema, kural ve ekran uyarlandı.

## 1. Onedesk (`onedesk/`, `src/onedesk/`)

- **İki ana düğme:** *Aktif Alarm · Talep · Şikayet* (şu an açık) ve *Yıl Boyu Kapatılan* (seçili yılda kapanan). Her biri tür toplamları, yaş/ay grafiği ve müşteri kırılımı gösterir.
- **Top10:** yıl boyu en çok kayıt oluşan 10 müşteri; her satırda müşteri adı ve en çok kayıt oluşan lokasyonlar (ilk 3).
- **RCA ortak noktaları:** kapanan kayıtların kök sebep metinleri sayı/IP farkı yok sayılarak gruplanır (`rca.grup_anahtari`); grup başına adet, oran, müşteri/lokasyon sayısı, tür dağılımı; sık sözcükler ve tekrar eden lokasyonlar.
- **Çözüm tavsiyeleri:** *yerleşik* kural tabanlı öneriler (üretim `ats_analizi` kuralları) her zaman çalışır, hiçbir veri dışarı çıkmaz. *LLM yorumu* varsayılan **kapalıdır**; açılması için üçü birden gerekir: `TAMLIFE_YZ_SAGLAYICI=anthropic`, `TAMLIFE_YZ_VERI_PAYLASIMI=izinli`, `ANTHROPIC_API_KEY` (yalnız ortam değişkeni). Modele yalnız kırpılmış kök sebep metinleri ve sayılar gider; müşteri ve lokasyon adı gitmez. Yeni bağımlılık yok (`urllib`).
- **Veri kaynağı:** canlı Onedesk DB bağlantısı bu sürümde **kapalı**. Veri admin Veri Girişi hattından gelir: hazır partiyi `POST /onedesk/ice-al/{parti}` kayda çevirir (sütunlar başlık adından tanınır; aynı çağrı no + tür güncellenir; tür sütunu yoksa tür seçilir) ve etkilenen müşterilerin kart sayaçlarını (açık / bu yıl kapanan) kayıtlardan yeniden hesaplar. Canlı adaptör geldiğinde aynı `ice_al` yolunu kullanır.
- **Kapsam:** admin ve Manager tüm kayıtları; Member yalnız kendi müşterileri ve çatısı kendisinde olan iştirakleri (müşteriyle eşleşmeyen kayıtlar yalnız yöneticiye).

## 2. ICT SMS & Gelir ve APN Gelir ve Kurulum (`gelir/`, `src/gelir/`)

- **ICT SMS:** tek sade tablo — müşteri adı, proje bilgisi, gelir bilgisi (TRY/USD/EUR). Satır içi ekle/düzenle/sil; para birimi başına toplam kutuları.
- **APN:** iki ana düğme. *Kurulum:* müşteri adı, APN adı, talep tarihi, teslim tarihi (boşsa "Bekliyor"), gelir (TL). *Müşteri Çalışmaları:* toplantı konusu, toplantı tarihi, planlı çalışma tarihi, APN adı, müşteri.
- **Kurallar:** teslim ≥ talep, planlı ≥ toplantı; tutar `1.250,50` / `1.250` (bin ayracı) / `1250.5` biçimlerini okur; tarih `GG.AA.YYYY` ya da `YYYY-AA-GG`. Member yalnız kendi oluşturduğu ya da TAM adı kendisi olan kayıtları görür/değiştirir (üretim `ad_benim`); başkasının kaydı 404.

## 3. İzin&Takvim ve TAM Takvim (`takvim/`, `src/takvim/`, `src/sunum/`)

- **İzin&Takvim Yönetimi:** kişi kendi aylık takvimini girer; gün durumu üretimle aynı kodlar (çalışıyor, yıllık izin, şirket izni, raporlu, arife, resmi tatil, hafta sonu) + online / yüz yüze toplantı sayısı; tarih aralığına toplu atama (en çok 62 gün, hafta sonu atlanabilir).
- **TAM Takvim:** panele **giriş yapmış herkes** (`app_user.last_login_at`; giriş kaydı oturum açılırken yazılır). Yalnız isimler ve İzin&Takvim'e girilen veriler listelenir; ekstra filtre yok (yalnız çeyrek/yıl). Satır açılınca kişinin kayıtlı günleri görünür.
- **Grafik:** *Grafik oluştur* ile istenince çizilir: izin/tatil halkası, kişi bazında gün dağılımı, toplantılar (online / yüz yüze). 'Çalışıyor' (yalnız toplantı girilen günler) grafikten çıkarılır ki izin görünür kalsın.
- **Çeyrek bazlı sunuma gönder:** grafiğin yanındaki kutu. Yetki `takvim.sunuma_gonder`: **admin Rol Yönetimi › Ek yetkiler**'den role verir (varsayılan kapalı, admin hepsine sahip); sunucuda zorlanır. Dönem başına tek kayıt (`presentation`, kaynak `takvim`); yeniden gönderim günceller, işareti kaldırmak siler. Alıcı: *Çeyrek Bazlı Sunum* sayfası (`/sunum/ogeler`).

## 4. Müşteri Yönetimi portföyü

Üretim *Müşterilerim* kart ızgarası uyarlandı: çatı müşteri kartları (kısa ünvan, segment, TAM, açık alarm/şikayet/talep, final skor çubuğu, iştirak adedi); arama iştirak adını da kapsar; segment ve (yönetici için) TAM filtreleri; KPI şeridi; *Müşteri ekle* çekmecesi (ana/iştirak, çatı seçimi, segment, TAM; canlı kart önizlemesi). İş kuralları değişmedi (`musteri_ekle`: ünvan benzersiz, Member başkası adına ekleyemez, iştirak çatının segmentini ve TAM'ini alır). Uçlar: `GET /musteri/portfoy`, `GET /musteri/secenekler`.

## 5. Arayüz

- **Hesap kartı sol altta** (`shell/kullanici-karti.tsx`): dönen halkalı avatar, rol rozeti, çevrimiçi noktası; admin için sarı parıltı ve *Yönetim konsolu* kısayolu. Menü yukarı açılır; Esc/dışarı tık kapatır.
- **Genel bakış yayı** (`components/ui/modul-yayi.tsx`): iki eş merkezli yay, cam kartlar, imlece göre ±5° 3B eğim ve iç yayda paralaks, yayda akan ışık; kartlar ilgili modüle götürür. `prefers-reduced-motion` ve dokunmatik/dar ekranda hareket/eğim yok, kart listesi.
  Netlik ilkeleri: sahne `scale()` ile küçültülmez (ölçek yalnız yarıçap, kart ve yazı boyutuna uygulanır), kartlar tam sayı piksel konumunda ve sabit boyutlu kutulardır (`translate(-50%)` yok), `backdrop-filter` yok, yüzme yalnız simgeye uygulanır, 3B eğim ve derinlik durgunken tam sıfırdır (katman ölçeklenmez, metin keskin kalır).
- Grafikler yeni bağımlılık olmadan SVG/CSS (`components/grafik.tsx`).
- **Üst bar** Turkcell mavi paletinde (lacivert → mavi gradyan, beyaz başlık/simge, sarı alt çizgi); **sol üstte TAM Life logosu** (`src/assets/tam_life_logo.png`, üretim login ekranındaki logo). Genel bakışta büyük başlık cümlesi yoktur; yayın altında yalnız küçük ipucu satırı durur.

## 6. Dev örnek verisi

`python -m app.ornek_veri [--temizle|--yenile]` (yalnız `TAMLIFE_ENV=dev`): 10 çatı + 5 iştirak müşteri, 6 TAM, 480 Onedesk kaydı (RCA gruplarının belirgin çıkması için ağırlıklı kök sebepler), SMS/APN/çalışma kayıtları, takvim günleri. Hepsi uydurma ve işaretli (`ORNEK-*`, `ornek.*`, `source='ornek'`, `created_by='ornek'`); `--temizle` yalnız bunları siler. Onedesk ekranı örnek veri varken sarı uyarı gösterir.

## 7. Bilerek yapılmayanlar

- Canlı Onedesk/Oracle çekimi (kaynak sorgu sözleşmesi + ayrı işçi süreç bekliyor); LLM yorumu gerçek anahtarla denenmedi (testte HTTP sahte, kapı mantığı ve veri sınırı doğrulandı).
- Türkiye resmi tatillerinin otomatik doldurulması (durum elle seçilir).
- Çeyrek Bazlı Sunum'da başka kaynaklar (şimdilik yalnız TAM Takvim özeti), sunum düzenleme ve dışa aktarma.
- Excel ile SMS/APN yükleme; APN `installation_pct` alanı şemada duruyor, yeni ekranda kullanılmıyor.
- Yeni sayfaların EN metinleri çevirisi hazırlandı ama gözden geçirilmedi; Playwright e2e yeni sayfalar için yazılmadı (parola gerektirir).
