# Cacti aylık rapor grafikleri

Müşteri Yönetimi → müşteri kartı → Aylık Rapor → CACTI kartında (sağ sütun, SLA kartlarının altı) her satıra bir Lookouteyes grafik bağlantısı ya da Cacti grafik ID tanımlanır (en fazla 6). **Standart (2026-10-17 kullanıcı kararı, grafikler değişebildiği için):** bağlantıları müşterinin sorumlu personeli (iştirakte çatının sorumlusu da) kendi girer ve değiştirir; admin de değiştirebilir, yönetici başkasının müşterisini değiştirmez. Rapor gönderilince o dönemin tanımları kilitlenir. Yalnız bilinen adreslere gidilir (Lookouteyes / trafik.superonline.net); başka sunucuya URL vekilliği yapılmaz.

Rapor açıldığında önceki takvim ayının (Türkiye UTC+3) başlangıcı ve sonu kullanılır; kayan son 30 gün kullanılmaz. Örneğin Ekim 2026 raporu 1–30 Eylül verisini alır. PNG'ler aynı rapor şablonuna, PDF'e ve mevcut Outlook EML akışındaki PDF ekine girer. E-posta kendiliğinden gönderilmez.

## Lookouteyes grafikleri (2026-10-17)

Personelin kullandığı grafik Cacti değil, Lookouteyes'tır: `http://lookouteyes/lookouteyes/Modules/Graph.aspx?ct=Stock&miid=…&fn=AVG&val=…`. Kart bu bağlantıyı (Graph.aspx ya da Graph.ashx; iç ad ya da ağ geçidi biçimi) kabul eder ve `http://lookouteyes/...` biçiminde saklar.

**Kimlik (kullanıcı kararı 2026-10-17):** Lookouteyes grafiği grafiği isteyen kişinin kendi LDAP hesabıyla alınır; `.env`'deki DPAPI hesabı Lookouteyes için kullanılmaz. Dönem kaydı yoksa `GET …/cacti/grafikler` 428 döner, kart parola sorar, `POST …/cacti/grafikler {parola}` panel kullanıcı adı + bu parolayla bir kez alır. Parola saklanmaz, günlüğe/denetime/hata metnine yazılmaz (şema sınırı yok: 422 girdiyi geri yazardı; uzunluk servis katmanında). Sonuç dönem dosyasına yazıldığı için aynı ay yeniden parola sorulmaz. Cacti ID'leri ile Lookouteyes aynı istekte ise tüm alım kişinin hesabıyla yapılır.

**Adres:** İstek kökü `TAMLIFE_LOOKOUTEYES_URL` (varsayılan `http://lookouteyes`; izinli: `http://lookouteyes`, `https://lookouteyes`, `https://trafik.superonline.net`). Bu sunucudan (LADIN01, 172.28.100.7) `lookouteyes` (10.222.244.213) 80/443 kapalıdır (2026-10-17 ölçümü): doğrudan alım için ağ ekibinden 172.28.100.7 → 10.222.244.213 TCP 80 (varsa 443) izni gerekir. İzin gelene kadar `TAMLIFE_LOOKOUTEYES_URL=https://trafik.superonline.net` ile ağ geçidi kullanılabilir. `http://` adresinde Lookouteyes giriş formu parolayı ağda şifresiz taşır; `https://lookouteyes` açıksa o tercih edilmelidir. Yalnız Lookouteyes tanımlı müşteride trafik.superonline.net'e hiç gidilmez. Alım sırası:

1. `/lookouteyes/DefaultMetro.aspx` → oturum yoksa `/lookouteyes/Pages/Login/Login.aspx?CALLBACK=…`; kişinin kullanıcı adı + parolası (Domain alanını sunucu doldurur).
2. `/lookouteyes/Modules/Graph.aspx?ct&miid&fn&val`: grafik adı (`ametric_name`, yoksa `metric_name`) ve `<img id="graph">` data alanları okunur.
3. `/lookouteyes/Modules/Graph.ashx?<data alanları>&s=<ay başı>&e=<ay sonu>&r=<rastgele>`: sayfanın yakınlaştırmasıyla aynı istek. Eylül raporu için `s=1788210000` (01.09.2026 00:00 TR), `e=1790801999` (30.09.2026 23:59:59 TR). GIF/JPEG gelirse PNG'ye çevrilir. PDF başlığı `<grafik adı> · 01.09.2026 00:00 – 30.09.2026 23:59`.

Oturumsuz Graph.ashx boş gövde döndürür. `TAMLIFE_CACTI_MODE=http` Lookouteyes'ı desteklemez. Eksen etiketleri Lookouteyes sunucusunun saat dilimiyle çizilir; ilk canlı denemede ilk/son etiket kontrol edilmelidir.

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
