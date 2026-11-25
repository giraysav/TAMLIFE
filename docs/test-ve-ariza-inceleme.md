# Genel test ve arıza inceleme

Proje kökünde PowerShell açın:

```powershell
.\kurulum\genel_test.ps1             # Hızlı, salt okunur canlı sağlık kontrolü
.\kurulum\genel_test.ps1 -Tam        # Sağlık + backend/güvenlik + arayüz + izole yük
.\kurulum\genel_test.ps1 -Backend
.\kurulum\genel_test.ps1 -Arayuz
.\kurulum\genel_test.ps1 -Yuk
```

Rapor yolu konsola yazılır: `var/test/rapor-<tarih-saat>-<id>/rapor.md`.
Aynı klasörde makine tarafından okunabilen `sonuc.json`, test günlükleri ve backend/yük için JUnit XML bulunur.
Her aşamadan sonra sonuç güncellenir; sonraki bir aşama başarısız olsa bile önceki bulgular korunur.

Çıkış kodları: **0** tamamlanan kontroller başarılı; **1** başarısız kontrol/test veya zaman aşımı;
**2** eksik araç, eksik rapor, atlanan test veya yarıda kalan inceleme. WARN satırları ayrıca değerlendirilir;
statik analiz uyarıları doğrulanmış güvenlik açığı sayılmaz. Eksik test aracı başarı olarak raporlanmaz.

## Kapsam ve izolasyon

Varsayılan kontrol: HTTP/HTTPS sağlık yanıtı, SQLite salt okunur quick_check (5 saniye yürütme bütçesi),
disk alanı, Windows görevlerinin hesabı/durumu, hedefi eksik Watch görevleri ve geçmiş günlüklerdeki hata kodu sayıları.
Günlük mesajları, .env içerikleri, parolalar ve müşteri satırları rapora alınmaz.
Health uç noktası yalnız API'nin yanıt verdiğini gösterir; DB kontrolü bu yüzden ayrıdır.
Geçmiş hata kodları mevcut arıza kanıtı değildir; testlerden kalan kayıtlar da bulunabilir.
PostgreSQL gibi desteklenmeyen DB konumlarında DB kontrolü eksik olarak raporlanır.

Backend testlerinde canlı .env ve dış bağlantı ayarları devralınmaz; her testin fixture'ı ayrı geçici DB kullanır.
Ürün verisi kopyalanmaz. AD/Oracle/diğer DB ve API anahtarları test ortamına taşınmaz.
Yük testleri geçici boş şemalı uvicorn örneğinde, dinamik localhost portunda çalışır.
100/200 eşzamanlı istek, 300'lük ani artış, 35 saniyelik SQLite yazma kilidi,
500 yavaş bağlantı ve parçalı büyük gövdeler sınanır. **Bu işlem sunucunun CPU/RAM kaynaklarını kullanır;
arıza anında önce hızlı kontrolü çalıştırın, ağır yük testini uygun bakım saatinde yapın.**
Boş/sentetik verideki sonuç gerçek müşteri hacminde kapasite garantisi değildir.

Arayüz testi ve lint çalışır; derleme ayrı rapor klasörüne yazılır, canlı dist güncellenmez.
Araç paneli yeniden başlatmaz, görev hesaplarını değiştirmez ve veri dağıtımı başlatmaz.
Aynı anda ikinci genel test koşusu engellenir. Her alt komut için zaman aşımı varsayılan 900 saniye;
`-ZamanAsimi 1200` ile değiştirilebilir. Zaman aşımında yalnız aracın başlattığı test süreç ağacı durdurulur.

## Bağımlılıklar

Hızlı kontrol yalnız standart Python kütüphanesini kullanır. Betik önce
`var/test/ortam/Scripts/python.exe`, yoksa uygulamanın `.venv/Scripts/python.exe` yorumlayıcısını seçer;
`-Python <yol>` ile başka test yorumlayıcısı verilebilir. Araç kendiliğinden paket yüklemez.
Tam kontrol için pytest/httpx, statik inceleme için ruff, arayüz için kurulu Node/npm ve node_modules gerekir.
Eksik bağımlılıkta ilgili günlük incelenir; canlı .venv yerine ayrı test ortamı hazırlanır.
Bu sunucuda test ortamı çevrimdışı wheels kullanılarak hazırlandı; uygulama bağımlılıkları değiştirilmedi.
Async olay döngüsü testleri asyncio.run kullanır; pytest-asyncio gerektirmez.

## Güvenlik incelemesinin sınırları

Backend testleri kimliksiz erişim, roller, CSRF/Origin/Host, oturum iptali, büyük/bozuk girdiler,
yük ve SQLite yarışları için regresyon sağlar. Statik analizde dinamik SQL/subprocess gibi işaretler
çağrı kaynağıyla birlikte incelenmelidir. Bu araç güncel CVE veri tabanı taraması veya tam sızma testi değildir.
Gerçek AD/Oracle bind'i varsayılan olarak yapılmaz. REPORTDB tablosu yetkileri ayrıca doğrulanmalıdır.
