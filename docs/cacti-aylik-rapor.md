# Cacti aylık rapor grafikleri

Müşteri Yönetimi → müşteri kartı → Aylık Rapor → CACTI kartında yönetici her satıra bir grafik ID veya tam grafik bağlantısı tanımlar (en fazla 6). Sorumlu personel grafikleri görüntüler; tanımları yalnız yönetici değiştirir. Kaynak sabit: https://trafik.superonline.net. Başka sunucuya URL vekilliği yapılmaz.

Rapor açıldığında önceki takvim ayının (Türkiye UTC+3) başlangıcı ve sonu kullanılır; kayan son 30 gün kullanılmaz. Örneğin Ekim 2026 raporu 1–30 Eylül verisini alır. PNG'ler aynı rapor şablonuna, PDF'e ve mevcut Outlook EML akışındaki PDF ekine girer. E-posta kendiliğinden gönderilmez.

## Sunucu ayarları

Cacti/Lookouteyes LDAP kimliği Windows DPAPI CurrentUser ile korunur. Yeni kimlik girişi veya parola değişimi için TURKCELL\\TAMLIFEADLOG oturumunda yerel pencereyi açın:

```powershell
.\kurulum\cacti_kimlik_koru.ps1
```

Araç kullanıcı adını ve parolayı yerel kimlik bilgisi penceresinden alır. .env içinde yalnız şifreli değerleri günceller; açık metin alanlarını boşaltır. REPORTDB ve Windows görev parolalarına dokunmaz. Parolayı komut satırına, sohbete veya .env içine düz metin olarak yazmayın.

```dotenv
TAMLIFE_CACTI_USERNAME_DPAPI=
TAMLIFE_CACTI_PASSWORD_DPAPI=
TAMLIFE_CACTI_REALM=2
TAMLIFE_CACTI_PATH=/
TAMLIFE_CACTI_MODE=browser
```

DPAPI alanlarını araç doldurur; elle yıldız yazılmaz. PATH gerçek Cacti dizinidir: grafik URL'si /cacti/graph.php ile başlıyorsa /cacti/ yazın. REALM Cacti giriş formundaki LDAP seçeneğinin değeridir; 2 varsayımdır, gerçek formdan doğrulanmalıdır. Gateway sonrasında ayrıca Cacti formu varsa aynı hesapla oturum açılır.

Açık metin USERNAME/PASSWORD alanlarına çalışma zamanında geri dönüş yoktur. Bozuk veya başka Windows hesabıyla şifrelenmiş değer erişimi durdurur. Arayüz yalnız “Tanımlı •••• / Tanımlanmamış” durumunu görür. Çalışan servis .env değişikliklerini kontrollü yeniden başlatmada okur.

DPAPI dosyayı kopyalayan farklı kullanıcıya karşı korur; aynı Windows hesabıyla çalışan kod parolayı çözebilir. Uygulama otomatik giriş sırasında parolayı bellekte çözer. Bu yöntem bir kasa/kurumsal secret manager kadar ayrı bir güven sınırı oluşturmaz. Windows profilinin/servis kimliğinin taşınması, sıfırlanması veya başka sunucuya geçişte yerel araçla yeniden tanımlama gerekebilir. [Microsoft DPAPI açıklaması](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata).

## Tarayıcı ve oturum

16 Ekim 2026 sunucu kontrolünde düz HTTP isteği Lookouteyes bekleme sayfasını; Chrome ise /webr/auth/signin LDAP formunu açtı. Varsayılan yöntem bu normal giriş akışını ayrı, geçici ve headless Chrome oturumunda kullanır. Kalıcı profil, çerez dosyası, parola dosyası, ekran görüntüsü veya tarayıcı izi kaydedilmez. Kullanıcı/parola Node işlemine standart girdiden aktarılır; komut satırına ve alt işlemlerin ortamına yazılmaz.

Gereksinimler: Node.js, Chrome ve ekran-react/node_modules/@playwright/test. Sunucuda bunlar mevcut; yeni paket kurulmadı. Dağıtımda yalnız frontend dist dosyası yetmez; backend/araclar/cacti-grafik.mjs ile Playwright çalışma bağımlılığı da bulunmalıdır. Oturumun TURKCELL\\TAMLIFEADLOG altında açılabilmesi gerekir.

TLS doğrulaması açıktır. Browser istekleri yalnız kaynak origin'e izin verir. Harici SSO, MFA veya farklı gateway formu çıkarsa işlem durur; bunları atlatmaz. Doğrudan Cacti formuna erişilen ortamlarda MODE=http kullanılabilir; mevcut Lookouteyes gateway'inde browser gerekir.

## Hatalar, kayıt ve sınırlar

Aynı müşteri/dönem/ID listesi için başarılı grafikler TAMLIFE_REPORT_DIR/cacti/<müşteri>/ altında atomik JSON olarak saklanır. Varsayılan kök backend/data/reports. Kaydın içinde yalnız başlık, ID ve PNG bulunur. Rapor gönderildikten sonra grafik tanımları kilitlenir; eksik dönem görüntüsü dış kaynaktan yeniden oluşturulmaz. Gönderilen PDF, mevcut rapor arşivinde korunur.

Grafik indirme hatası, giriş sayfası, bozuk PNG veya eksik görsel PDF hazırlamayı bekletir. Grafik tanımlanmamış müşteriler mevcut akışı kullanır. İstek başına 6 grafik, PNG başına 3 MiB, aynı anda 2 alım; istek başına zaman aşımı ve tarayıcı için toplam süre sınırı vardır. Hatalı oturumda otomatik tekrar giriş döngüsü yoktur; personel “Tekrar dene” kullanır.

PNG bütünlüğü ve boyutları doğrulanır. Cacti'nin bir hata mesajını geçerli PNG içine çizmesi otomatik olarak anlamlandırılamaz; ilk canlı kontrolde grafik başlığı, devre ve zaman ekseni görsel olarak karşılaştırılmalıdır.

## Doğrulama ve canlıya alma

Sentetik grafiklerle backend yetki/CSRF, URL sınırı, ay sınırı, dönem önbelleği ve hata davranışı; frontend otomatik alım, rapor görseli ve hata durumu test edilir. Canlı LDAP parolası ve gerçek grafik ID'si olmadan uçtan uca grafik alımı doğrulanmış sayılmaz.

İlk canlı kontrolde: yerel kimlik penceresiyle LDAP hesabını tanımlayın, gerçek grafik ID'sini tanımlayın, kontrollü servis yeniden başlatması sonrasında doğru müşterinin önceki ay grafiğini PDF üzerinde doğrulayın. 16 Ekim 2026 kullanıcı onayıyla arayüz yayımlandı ve panel görevi yeniden başlatıldı. HTTPS sağlık, sunulan arayüz hash kontrolü ve yeni korumalı Cacti route kaydı doğrulandı. Gerçek LDAP/grafik alımı için örnek grafik ID'siyle doğrulama ayrıca gereklidir.

Doğrulama kaydı (16 Ekim 2026): tüm arayüz testleri 197/197 geçti; TypeScript kontrolü, lint ve ayrı test dizinine Vite derlemesi başarılı. Backend Cacti/SLA/müşteri testleri çalıştırıldı; önceki genel incelemede hatalı olduğu saptanan test_musteri::test_yetkisiz_ve_csrf bu kapsamda dışarıda tutuldu (üretim yetki kuralı değiştirilmedi). Gerçek LDAP ile giriş ve gerçek grafik henüz doğrulanmadı.
