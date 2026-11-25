# Lansman öncesi açık bulgular (2026-11-06)

Bekletilen liste: lansman mailinden önce karara bağlanacak, **henüz yapılmamış** işler. Kanıtlar 2026-11-05/06 gözlemidir; "doğrulanmadı" yazanlar hipotezdir.

## Engeller

| # | Bulgu | Durum / kanıt | Önerilen ilk adım |
|---|---|---|---|
| 1 | **ReportDB işçisi ölü** | Son başarılı tur 2026-11-04 14:05 (`backend\var\logs\isci.log`); sonrası her turda "ATLANDI". Oracle özet sorgusu hızlı (13,6 sn). Son başarılı turlar 225-254 sn sürdü (31 Eki: 28 sn) ve görevin 5 dk sınırı turu sessizce öldürüyor; kilit dosyası bayatlayana kadar (600 sn) bir tur atlanıyor. 4 Kas'ta "Kartlara yaz" kurallarının açılması yazma yükünü artırmış olabilir (doğrulanmadı). | Kilidi temizleyip bir turu elle süreli çalıştırmak; yavaşlayan adımı ölçmek; geçici olarak görev süre sınırını artırmak. |
| 2 | **Zamanlanmış yedek yok** | `E:\TAMLIFE_YEDEK_KRITIK` içindeki son yedek 2026-10-23. Yalnız göç öncesi / elle yedek var. | Günlük yedek görevi (SQLite backup API, `yedek_kur.ps1` hattı) ve saklama kuralı. |
| 3 | **Gece senkronu her gün HATA** | `var\log\gece_sync\son.json`: Citrix erişimi yok, veri/kod senkronu atlanıyor. `prod_dogrula` "dist bu güncellemede derlenmemiş" diyor (yanlış alarm olması muhtemel, doğrulanmadı). | Citrix→LADIN01 RDP bağlantısı; `prod_dogrula.ps1` dist denetimini incelemek. |
| 4 | **Prod ve Citrix kodu ayrıştı** | Prod'da Citrix'te olmayan commit'ler var (26113f3 …); `E:\TAMLIFE\yamalar` bundle'ı eski. PROD_GUNCELLE / gece senkronu bu halde takılır. | Bundle'ı yeniden üretip Citrix'e almak (kullanıcı 2026-11-01: şimdilik yapılmayacak). |
| 5 | **Dış bağlantılar eksik** | ONENTDB `pg_hba` engelli; ONEDESKDB bağlanıyor ama şikayet/talep verisi akmıyor (`onedesk_record` yalnız TEMIP alarmı); SMTP 25 kapalı. | Yetki talepleri (kategori ayırma hedefi için ilk ikisi). |
| 6 | **Tek hata noktaları** | Tek uvicorn süreci, bellekte oturum, SQLite; sunucu yeniden başlarsa panel yalnız TAMLIFEADLOG girişiyle kalkar. | Kabul edilen risk ise lansman duyurusunda "bakım penceresi" notu. |
| 7 | **Testler eksik** | Playwright e2e bu sunucuda çalışmıyor (tarayıcı kurulu değil); `panel_testi.ps1` uçtan uca koşulmadı. | Citrix'te e2e; lansman öncesi `panel_testi.ps1 -SoruSorma`. |

## Mail içeriğiyle çelişen iddialar (lansman.html)

- "ReportDB'den 6 dakikada bir otomatik güncelleme" — bulgu 1 çözülmeden doğru değil.
- "Tam yedek, otomatik sağlık denetimi ve gece senkronu" — bulgu 2 ve 3'e bağlı.
- Sayılar: 363 müşteri kartı (canlıda 363 ✓), "369K +" Onedesk kaydı (canlıda 372.752, ifade hâlâ doğru ama eski), "1.100 +" test (899 backend + 244 arayüz = 1.143 ✓), 16 modül.

## 2026-11-06'da yapılanlar (referans)

- SLA analizi geri alınabilir (e31b26e); eskimiş dosya temizliği (89dd565).
- Üç test dosyasındaki tekrarlı tanımlar `git stash` ile ayrıldı (geri almak: `git stash pop`); `ruff` temiz, pytest 899 geçti.
- Yük testi (canlı DB kopyasında): 40 eşzamanlı karışık yük hatasız (p95 1,6 sn); 100 eşzamanlıda hata yok, gecikme artıyor.
- Bilerek yapılmayanlar: eski adlandırılmış yedekler (`backend\var\yedek`, 16 dosya) ve `var\isletim` silinmedi (izin denetimi geri dönüşsüz silmeyi reddetti).
