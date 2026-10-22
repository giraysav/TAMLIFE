# Aylık rapor e-posta gönderimi (tek kutu: TAMLIFE@turkcell.com.tr)

Durum (2026-10-22): **altyapı kodda hazır, varsayılan KAPALI.** Canlıda `.eml` akışı sürüyor. SMTP kipi, aşağıdaki isterler karşılanınca tek ayarla açılır.

## İki kip

| | `RAPOR_GONDERIM_KIPI=eml` (varsayılan) | `RAPOR_GONDERIM_KIPI=smtp` |
|---|---|---|
| İletiyi kim gönderir | Personel, Outlook'ta Gönder'e basar | Panel sunucusu, onaydan hemen sonra |
| From | `SMTP_USER` (TAMLIFE@) | `SMTP_USER` (TAMLIFE@), zarf göndereni de aynı |
| Yanıt kime gider | From'a (TAMLIFE@) | `Reply-To`: raporu hazırlayan personel (`<kullanıcı>@AD_DOMAIN`) |
| İleti biçimi | `.eml`, `X-Unsent: 1` | Aynı MIME gövdesi; `X-Unsent` yok, `Message-ID` + `Date` var |
| Arşiv | Personelin Gönderilmiş Öğeleri | `SMTP_ARSIV` doluysa gizli kopya (zarfta, başlıkta yok) |
| Teslim hatası | Personel Outlook'ta görür | Gönderim kaydı oluşmaz, ay kilitlenmez, arşiv PDF'i silinir; ekranda neden yazar |

## Akış (smtp kipi)

1. Personel "Raporu gönder" → onay penceresi ("hemen gönderilecek; geri çağrılamaz").
2. `rapor/servis.gonder`: alıcılar doğrulanır, en az bir "Kime" zorunlu; PDF + SLA Excel + ekler ile ileti `eposta.eml(taslak=False)` ile kurulur.
3. Tek DB işleminde (savepoint) `Report` + `ReportDispatch` yazılır, `flush` ayda-tek kilidini (kısmi benzersiz indeks) doğrular.
4. **Kilit doğrulandıktan sonra** `smtp_gonderim.gonder` iletiyi teslim eder. Hata → savepoint geri alınır (kayıt yok), arşive yazılmış PDF silinir, istemciye 4xx/5xx + neden.
5. Kısmi ret (bazı alıcılar reddedildi): ileti diğerlerine gitmiştir, geri alınamaz → kayıt oluşur, yanıtta `reddedilen` listesi, ekranda uyarı.

Bilinen sınır: SMTP kabul ettikten sonra DB commit'i düşerse ileti gitmiş ama kayıt yok olur (çok düşük olasılık; flush kilidi önceden doğruladığı için yalnız disk/G/Ç hatasında). Gerekirse ileride `ReportDispatch`'e `message_id` + "gönderiliyor" ara durumu eklenir (aşağıda "Sonraki adımlar").

## Kod

| Dosya | Görev |
|---|---|
| `backend/app/rapor/smtp_gonderim.py` | Ayar okuma, `kip()`, `gonder()` (boyut sınırı, STARTTLS seçeneği, hata eşleme), `erisim_adimlari()` (ayar → DNS → TCP → EHLO; ileti göndermez), `durum()` |
| `backend/app/rapor/eposta.py` | `eml(taslak=..., yanit=...)`, `kisi_adresi()` |
| `backend/app/rapor/servis.py` | `gonder()` kip ayrımı, `taslak_getir()` yanıtında `gonderim_kipi` |
| `backend/app/yonetim/router.py` | `POST /api/v1/yonetim/kurum/eposta-testi` (yalnız admin; ileti göndermez) |
| `ekran-react/src/musteri/aylik-rapor.tsx` | Kipe göre not, onay metni, sonuç mesajı; smtp'de dosya inmez |
| Testler | `tests/test_musteri.py` (smtp_kipi fikstürü, sahte SMTP), `src/musteri/aylik-rapor-gonderim.test.tsx` |

## Ayarlar (`backend/.env`; değerleri sistem yöneticisi yazar)

| Anahtar | Varsayılan | Not |
|---|---|---|
| `RAPOR_GONDERIM_KIPI` | `eml` | `smtp` yapılınca panel yeniden başlatılmalı |
| `SMTP_SERVER` | — | Bugün `mail.turkcell.com.tr` |
| `SMTP_PORT` | `25` | |
| `SMTP_USER` | — | Gönderen kutu: `TAMLIFE@turkcell.com.tr` (kimlik doğrulama kullanıcısı DEĞİL) |
| `SMTP_STARTTLS` | `false` | Relay TLS istiyorsa `true` (sertifika doğrulanır) |
| `SMTP_TIMEOUT` | `20` | sn, 1–120 |
| `SMTP_AZAMI_MB` | `20` | İleti (base64 dahil) üst sınırı; relay sınırından küçük tutulmalı |
| `SMTP_ARSIV` | boş | İsteğe bağlı gizli kopya kutusu |

Kimlik doğrulama (SMTP AUTH) bilinçli olarak YOK: relay IP tabanlı anonim olarak tasarlandı, `.env`'e parola girmez. Relay AUTH isterse ayrı karar (DPAPI ile saklama, `cacti_kimlik.py` deseni).

## İsterler (açılmadan önce karşılanmalı)

**Ağ / güvenlik duvarı**
1. `172.28.100.7` (panel) → `mail.turkcell.com.tr` (10.218.130.70) **TCP 25** izni. *2026-10-22 ölçümü: zaman aşımı, kapalı.*
2. Relay TLS istiyorsa 587/STARTTLS yolu ve sertifika zinciri bu sunucunun güven deposunda.

**E-posta (Exchange) ekibi**
3. Relay izni: panel IP'si için **anonim relay**, iç ve **dış alanlara** (müşteri adresleri kurum dışı) teslim.
4. `TAMLIFE@turkcell.com.tr` adresinin varlığı (paylaşılan posta kutusu ya da dağıtım grubu) ve relay üzerinden bu adresle gönderme (Send-As / gönderici kısıtı kuralı).
5. SPF / DKIM / DMARC: relay'in turkcell.com.tr adına imzalaması (iletiler müşteri tarafında spam'e düşmesin).
6. İleti boyutu sınırı (PDF + SLA Excel + ekler; base64 ~%33 büyütür) → `SMTP_AZAMI_MB` buna göre.
7. Gönderim hızı/kota sınırı (ay başında toplu gönderim: ~yüzlerce müşteri, aynı gün).
8. Geri dönen iletiler (NDR/bounce) TAMLIFE@ kutusuna düşer: bu kutuyu **kim izleyecek** (TAM'lar mı, tek sorumlu mu).
9. DLP / şifreleme / yasal altbilgi politikası: müşteri raporu dışarı gidiyor; zorunlu sınıflandırma etiketi veya altbilgi var mı.

**İş kararları (ekip)**
10. Reply-To = raporu hazırlayan TAM (öneri, kodda böyle). Alternatif: yanıt TAMLIFE@'e.
11. TAM her raporda otomatik Bilgi (Cc) olsun mu? (Şu an hayır; alıcı listesi kartta.)
12. Arşiv kutusu (`SMTP_ARSIV`) gerekli mi, hangisi.
13. Geçiş: tüm müşterilerde bir anda mı, önce pilot TAM/müşteri ile mi (kod tek anahtar; pilot gerekirse müşteri/kişi bazlı anahtar eklenir).
14. Personelin Outlook'ta son kontrolü kalkıyor: onay penceresi yeterli mi, yoksa "kendime deneme gönder" adımı mı istenir.

**`.eml` kipi için not (bugün canlı)**
- `.eml` From'u da `SMTP_USER` = TAMLIFE@. Personel Outlook'tan gönderirken bu adres için **Send-As / Send-on-behalf** yetkisi yoksa ileti NDR ile döner. Yetki verilmemişse ya yetki verilmeli ya da `.eml` From'u personelin kendi adresine çekilmeli (karar gerekir).

## Doğrulama ve devreye alma

1. Yönetim → `POST /api/v1/yonetim/kurum/eposta-testi` (ileti göndermez): ayar → DNS → TCP → EHLO; EHLO adımı sunucunun boyut sınırını ve STARTTLS desteğini yazar.
2. Pilot: `RAPOR_GONDERIM_KIPI=smtp`, test müşteri kartına kurum içi alıcı, raporu gönder, ileti başlıklarını (From, Reply-To, SPF/DKIM sonucu) alıcı tarafında kontrol et; gerekirse admin "Geri al" ile ayı yeniden açar.
3. Geri dönüş: `RAPOR_GONDERIM_KIPI=eml` + panel yeniden başlatma (kod değişmez).

## Sonraki adımlar (isterlerden sonra)

- Kurum Bağlantıları ekranına "E-posta (SMTP)" kartı (uç hazır, arayüz bağlanmadı).
- `ReportDispatch`'e `message_id`, `teslim` (gönderiliyor / gönderildi / kısmi) sütunları (Alembic revizyonu) ve geçmişte gösterim.
- Toplu gönderimde sıra/kuyruk (relay hız sınırı çıkarsa).
