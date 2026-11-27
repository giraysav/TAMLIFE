# TAMLIFE v3.5: İşletim Belgesi

Kurumsal müşteri ekiplerinin (TAM) paneli. Alarm, şikayet/talep, envanter (CMDB), devre performansı, skor ve aylık rapor tek müşteri kartında; Müşteri Erken Uyarı riskli müşteriyi nedeniyle birlikte öne çıkarır.

Bu belge paneli **çalıştıran ve bakımını yapan** kişi içindir: nerede ne çalışır, nasıl yeniden başlatılır, veri nereden gelir, yedek ve geri dönüş, testler ve sık karşılaşılan sorunlar.

---

## 1. Mimari

```
Kaynaklar                     İşçiler (ayrı süreç)                 Panel                      Kullanıcı
---------                     --------------------                 -----                      ---------
Oracle REPORTDB (TEMIP, LOE) ─┐
OneDesk  (PostgreSQL)        ─┼─> python -m app.isci reportdb ─┐
ONENT CMDB (PostgreSQL)      ─┤      (30 dk turu)               ├─> panel DB (SQLite) ─> FastAPI :8117 ─> TLS vekili :443 ─> tarayıcı
MSSQL LOE trafik (yetki bekl.)┘   python -m app.isci utilizasyon ┘     backend/var/dev.db     127.0.0.1         https://tamlife
                                     (her gün 06:00)
```

- Kaynaklara **yalnız işçiler** bağlanır; panel yalnız kendi veritabanını okur. Kullanıcı sayısı kaynak yükünü artırmaz.
- Panel yalnız `127.0.0.1:8117`'de dinler. Dışarıya TLS'i Windows (http.sys) sonlandıran `kurulum/tls_vekili.ps1` açar (443).
- Arayüz derlenmiş halde `ekran-react/dist/` altındadır (bkz. §9).

| Klasör | İçerik |
|---|---|
| `backend/app/` | FastAPI uygulaması; modüller: `musteri`, `onedesk`, `rapor`, `skor`, `radar`, `topoloji`, `yonetim`, `tampon` (kaynak bağlantıları) ... |
| `backend/app/isci.py` | Veri işçisi komutları (`python -m app.isci --help`) |
| `backend/alembic/versions/` | Veritabanı göçleri (sürümlü; panel her açılışta `alembic upgrade head` çalıştırır) |
| `backend/tests/` | Otomatik testler (bkz. §7) |
| `backend/var/` | Panel DB, günlükler (`logs/`), kullanıcı dosyaları, yedekler (git dışı) |
| `kurulum/` | Başlatma, servis görevleri, TLS vekili, yedek / geri dönüş, demo betikleri |
| `ekran-react/dist/` · `dist-demo/` | Derlenmiş arayüz · demo kopyası |
| `var/log/` | Servis döngüsü günlükleri (`canli_servis.log`, `canli_panel.log`, `canli_vekil.log`) |

---

## 2. Servisler ve zamanlanmış işler

Bütün işler **`TURKCELL\TAMLIFEADLOG`** kimliğiyle çalışır (bkz. `kurulum/calisma_kimligi.ps1`). Görevleri kaydeden ve yöneten tek betik: `kurulum/canli_gorev_kur.ps1` (yönetici PowerShell).

| Görev | Kimlik | Ne yapar |
|---|---|---|
| `TAMLIFE_Servis_Acilis` | SYSTEM, açılışta +1 dk, 5 dk'da bir bekçi | Sunucu açılınca oturum beklemeden panel + TLS vekili |
| `TAMLIFE_Servis` | TAMLIFEADLOG, oturum açılınca + 5 dk bekçi | Panel ve vekil döngüleri + **30 dk'lık veri turu** |
| `TAMLIFE_Utilizasyon_0600` | SYSTEM, her gün 06:00 | Kapanan kayıt + envanter özeti ve final skor |

Panel ve vekil döngüsü süreç kapanırsa **15 sn içinde** yeniden başlatır. İki servis kopyası bir arada olabilir; döngüler tekil kalır.

**30 dakikalık veri turu** (`python -m app.isci reportdb`, tur sınırı 20 dk), sırasıyla:
1. TEMIP alarm kayıtları (artımlı) → müşteri kartları / TAM Radar
2. `rapor-devre`: CMDB kopyası (günlük) + seçili rapor devrelerinin ölçümleri
3. `envanter`: müşteri envanteri / Kritik CI (4 saatte bir)
4. `onedesk-kayit`: şikayet / talep kayıtları (artımlı, günlük mutabakat)
5. `erken_uyari_bildir`: kritik çatı müşterinin sorumlu TAM'ına panel bildirimi (aynı müşteri için 7 günde bir)

> **Önemli:** Oracle giriş tetikleyicisi SYSTEM / makine hesabını reddeder (ORA-04088). Bu yüzden veri turu yalnız TAMLIFEADLOG oturumu açıkken çalışır. Sunucu yeniden başladıysa TAMLIFEADLOG ile bir kez RDP oturumu açın; panel ve vekil zaten ayaktadır ama veri, oturum açılana kadar güncellenmez. Oturumu "kapat" (sign out) **yapmayın**; RDP penceresini kapatmak sorun değildir.

### Sık kullanılan komutlar (yönetici PowerShell, `E:\TAMLIFE\kurulum`)

| Komut | Ne zaman |
|---|---|
| `.\canli_gorev_kur.ps1 -Durum` | Görevler, panel portu, günlüklerin son satırları |
| `.\canli_gorev_kur.ps1 -PanelYenile` | Kod değişikliğinden sonra **yalnız paneli** yeniden başlatır (vekil / işçi dokunulmaz) |
| `.\canli_gorev_kur.ps1 -YenidenBaslat` | Her şeyi durdurup görevleri yeniden kaydeder ve başlatır (görev bozulduysa onarır) |
| `.\canli_gorev_kur.ps1 -Durdur` | Panel, vekil ve işçiyi durdurur (görevler kayıtlı kalır) |
| `.\canli_baslat.ps1 -Kontrol` | Ön koşulları denetler, hiçbir şey başlatmaz |

Kural: **yeniden başlatmadan önce commit**. Panel açılışta göçleri uygular; kod ile şema aynı commit'te olmalıdır.

---

## 3. Yapılandırma

Ayarlar `backend/.env` dosyasındadır (**git dışı; asla commit etmeyin, GitHub'a göndermeyin**). Örnek anahtar aileleri (değerler burada yok):

| Anahtar | Anlamı |
|---|---|
| `TAMLIFE_DATABASE_URL`, `TAMLIFE_SQLITE_IZIN` | Panel veritabanı (bugün SQLite; PostgreSQL'e hazır, bkz. §10) |
| `AD_ENABLED`, `AD_SERVER`, `AD_DOMAIN`, `AD_ROL_KONTROLU`, ... | AD/LDAPS girişi ve KTS_ rol kontrolü |
| `ORACLE_REPORTDB_ENABLED` + bağlantı anahtarları | Alarm / LOE ölçümleri (Oracle Instant Client gerekir) |
| `ONEDESKDB_PG_ENABLED`, `ONENTDB_PG_ENABLED` + bağlantı anahtarları | Şikayet/talep ve CMDB (PostgreSQL) |
| `MSSQL_LOE_ENABLED` + bağlantı anahtarları | Devre trafik tabloları (okuma yetkisi bekleniyor; kod henüz okumuyor) |

`canli_baslat.ps1` ayrıca ortamı kurar: `TAMLIFE_ENV=prod`, `TAMLIFE_STATIC_DIR`, `TAMLIFE_TRUSTED_PROXIES=127.0.0.1` (yalnız vekilden gelen `X-Forwarded-For` kabul edilir), `TAMLIFE_ALLOWED_HOSTS`, `TAMLIFE_BACKUP_DIR`.

---

## 4. Veri kuralları (değiştirmeden önce okuyun)

- **Kaynak ayrımı:** alarm REPORTDB'den, şikayet/talep OneDesk'ten, envanter ONENT'ten. Eşleşme **Müşteri No + CI adı** ile.
- Envanterden **SNMP, e-posta, IP, VAN/LAN ve kullanıcı adları alınmaz.**
- Kullanıcı ekranlarında kaynak adı (REPORTDB / OneDesk / ONENT / TEMIP) ve ham veritabanı hatası **gösterilmez**.
- Otomatik gelen veri için **elle aktarma yolu açılmaz**; bir alana iki ayrı yazan olmaz; kullanılmayan kod bırakılmaz.
- Görünürlük: admin ve TeamMngr alanın tüm kartlarını, personel yalnız kendisine atanan kartları (ve kendi iştiraklerini) görür.

---

## 5. Veritabanı, yedek ve geri dönüş

- Panel DB: `backend/var/dev.db` (SQLite, WAL). Şema `alembic` göçleriyle yönetilir; panel açılışta `alembic upgrade head` çalıştırır.
- Yeni göç: `backend/alembic/versions/00NN_<ad>.py`; `down_revision` bir öncekidir. Göçler idempotent yazılır (sütun / indeks varsa atlar).
- **Yedek:** Yönetim › Veritabanı › "Yedek al" tam yedeği `E:\TAMLIFE_YEDEK_KRITIK` altına yazar (ilk kurulum: `kurulum\yedek_kur.ps1`).
- **Geri dönüş:** panelden yapılmaz (yıkıcı işlem). `<yedek klasörü>\ROLLBACK\GERI_DON.bat` → yönetici ister, şifre sorar, yedeği seçtirir.
- Kod değişikliği öncesi elle kopya alınacaksa: `var\yedek\kod_once_<konu>_<zaman>\`.

---

## 6. Müşteri Erken Uyarı

`backend/app/musteri/erken_uyari.py`. Her çatı müşteriye 0–100 risk puanı; nedenler ekranda yazılı.

| Sinyal | En fazla | Ölçüt |
|---|---|---|
| Alarm ivmesi | 30 | Son 14 gün / önceki 56 günün 14 günlük ortalaması (en az 5 alarm, ×1,5) |
| Şikayet | 30 | Son 14 günde yeni + şu an açık |
| Bekleyen kayıt | 20 | 7 günden uzun açık talep/şikayet (+ alarm, en çok 8) |
| Tekrarlayan arıza | 20 | Aynı CI'da 14 günde ≥3 alarm; puan en kötü CI'ya göre |
| Devre performansı | 15 | Rapor devresinde bu ay erişim < %99,5 ya da kayıp > %1 |

- Seviye: kritik ≥60, yüksek ≥35, izle ≥15. Planlı çalışma alarmları hariç. İştirakler çatıya toplanır.
- Ekranda: portföy kutusu (en riskli 5), kart rozeti, riske göre sıralama, çatı müşteri kartında nedenler.
- Bildirim: kritik çatının sahibine 7 günde bir; TAM bildirimde "İlgilendim / Gerekmedi" seçer, özet portföy kutusunda görünür.
- **Doğrulama** (Oracle'sız, ~35 sn): `cd backend; ..\.venv\Scripts\python -m app.isci erken-uyari-dogrula --hafta 16`. Puanı her pazartesi yalnız o güne kadarki veriyle hesaplar ve sonraki 14 günde şikayet gelip gelmediğine bakar. Eşik ya da ağırlık değişirse yeniden çalıştırın.

---

## 7. Testler

```powershell
cd E:\TAMLIFE\backend
..\.venv\Scripts\python -m pytest          # ~15 sn, 54 test
```

- Geçici bir SQLite üzerinde çalışır; **canlı veritabanına, AD'ye ve dış kaynaklara bağlanmaz** (`tests/conftest.py` ortamı uygulama yüklenmeden önce yazar).
- Kapsam: giriş ve oturum, CSRF / Origin kapısı, giriş sınırlayıcı, rol yetkisi, denetim izi ve ağacı, CSV formül enjeksiyonu, X-Forwarded-For, Erken Uyarı kuralları / görünürlük / bildirim / yanıt, bütün göçlerin boş veritabanına baştan uygulanması.
- Test bağımlılıkları: `requirements-test.txt` (sunucuda kurulu).
- Kural: davranış değiştiren her commit'ten önce testler geçmeli. Yeni kurala test yazın; testin kodu gerçekten yakaladığını, kodu geçici olarak bozarak deneyin.

---

## 8. Demo

```powershell
.\kurulum\demo_baslat.ps1 -Sifirla              # sahte veriyi baştan üretir, http://<sunucu>:8118
.\kurulum\demo_baslat.ps1 -ArayuzYenile         # dist değiştiyse demo arayüzünü kopyalar
```

Aynı kod + **sahte veri** + salt okunur + parolasız misafir girişi. Gerçek `.env` okunmaz, kaynaklara bağlanmaz. Sağlık paneli (`saglik_paneli.ps1`) de 8118 kullanır; ikisini aynı anda açmayın (demo için `-Port` verin). `-ArayuzYenile` PowerShell yüzünden `dist-demo/assets/demo-giris.js` başına BOM ekler; commit'ten önce `git checkout -- ekran-react/dist-demo/assets/demo-giris.js`.

---

## 9. Arayüz (derlenmiş paket)

Arayüzün kaynak kodu bu depoda **yoktur**; yalnız derlenmiş `ekran-react/dist/` vardır. Değişiklikler derlenmiş JS dosyalarına yama olarak yapılır:

- Önce dosyanın yedeği (`var\yedek\kod_once_<konu>_<zaman>\`), sonra yama betiği (her değişim tam bir kez eşleşmeli), sonra `node --check <dosya>`.
- Yalnız **derlenmiş CSS'te bulunan** Tailwind sınıfları kullanılır (`ekran-react/dist/assets/index-*.css` içinde arayın); yoksa satır içi `style`.
- Değişen dosya `dist-demo/` altına da kopyalanır (aynıysa). Commit: `git add -f ekran-react/dist/...`.
- Sunucu tüm yanıtlarda `Cache-Control: no-store` gönderir; tarayıcı yenilemesi yeter.

---

## 10. Sorun giderme

| Belirti | Bakılacak yer / çözüm |
|---|---|
| Panel açılmıyor | `var\log\canli_panel.log` (göç hatası? port dolu?); `.\canli_baslat.ps1 -Kontrol` |
| `Port 8117 dolu` | Eski panel süreci: `Get-NetTCPConnection -LocalPort 8117 -State Listen` → `-PanelYenile` |
| Veri güncellenmiyor | `backend\var\logs\isci.log` son satırlar; TAMLIFEADLOG oturumu açık mı (ORA-04088 = SYSTEM kimliği) |
| `ATLANDI baska calisma suruyor` | Önceki tur sürüyor; kilit dosyaları kendiliğinden bayatlar (`KILIT_BAYAT_SN`) |
| `canceling statement due to conflict with recovery` | Kaynak PostgreSQL yedek sunucusu; geçici, bir sonraki turda düzelir |
| Uygulama hatası (kullanıcı "kayıt no" bildirdi) | Yönetim › Kayıtlar › Arızalar; ayrıntı `backend\var\logs\uygulama.log` |
| Giriş reddi / kim ne yaptı | Yönetim › Kayıtlar › Denetim olayları (kullanıcıya göre ağaç, giriş IP'si) |
| HTTPS hatası | `var\log\canli_vekil.log`; sertifika Windows deposunda (dışa aktarılamaz) |

---

## 11. Yol haritası

1. Devre giriş/çıkış trafiği (MSSQL okuma yetkisi gelince: sürücü, bağlantı kartı, grafik tek seferde).
2. Arayüz kaynak kodunun depoya alınması; test ortamının canlıdan ayrılması.
3. Panel veritabanının PostgreSQL'e taşınması (kod `psycopg` ile hazır), yük testi, diğer bölge ekiplerine açılış.

## 12. Depo

- GitHub: `giraysav/TAMLIFE` (özel). Yalnız ilgili dal, ileri alma (fast-forward) ile gönderilir; **`--all` / `--mirror` ve force yok.** Göndermeden önce `.env`, veritabanı, Excel, anahtar ve müşteri verisi taraması yapılır.
- Commit iletileri Türkçe (ASCII), ne ve neden.
