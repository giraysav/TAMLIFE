# 05 ? Veri mimarisi

Sayimlar 2026-10-03, salt okunur acilis, `D:\Project\TAM_Life\Secure_DB` kopyasi ve `D:\Project\TAMLIFE_v3.5\veri`. Canli `C:\Secure_DB` acilmadi. Satir icerigi yazilmaz. `users` tablosunda `pin_code` ve `totp_secret` kolonlari vardir; deger yok.

## Kararlar

- Simdiki motor SQLite. Prod `panel.db` `journal_mode=wal` (dogrulandi). v3.5 `shared.db` `journal_mode=delete`; `depo.py` WAL pragma yazmaz.
- Hedef faz 0-3: SQLite WAL, tek yazici. Faz 4: PostgreSQL, ayni SQLAlchemy modelleri, Alembic revizyonu. Oracle yalniz okunur dis kaynaktir ve bu tasarimda sahte adaptordur.
- Her tablonun tek modul sahibi vardir. Iki katalog anahtari ayni tabloyu paylasamaz (`takvim` / `takvim_ozet`).
- Tasima betigi salt okunur kaynak, idempotent, satir sayisi kontrolu, gizli kolon haric, maskeleme opsiyonel. Betik bu belgede tasarlanir, calistirilmaz.
- Alembic yalniz sema icindir. Veri tasimasi `data/migrate.py` isidir; revizyon dosyasina `INSERT` konmaz.

## Acik sorular

- `takvim` ve `takvim_ozet` sahibi (`03`).
- `matrix_configs`, `daily_tasks` sahibi dogrulanmadi.
- `gelir_uretim`, `toptan` tablosu yok.
- Prod `kullanici_islemleri.db` kisi basi `u_<sayi>` tablolari (13 kullanici ozeti, 12 adet `u_*` tablo sayildi). Hedef tek `audit_event` tablosu mu, kisi basi dosya mi? `depo.py` kisi basi dosyayi (`veri/users/<ad>.db`) zaten acar. Iki desen catisir.
- `workflow_migration.py` govdesi bu belgede ozetlenmedi.

## Prod dosyalari (yol dogrulandi)

`backend/app/depo_yollari.py` yerlesimi. Kopya kok `D:\Project\TAM_Life\Secure_DB`.

| Anahtar | Goreli yol | Bayt (ana dosya) | Tablo sayisi |
|---|---|---|---|
| ana / panel | `veritabani/panel.db` | 270336 (+ wal 4120032) | 25 |
| analiz | `veritabani/analiz.db` | 3579904 | 11 |
| ham_veri | `veritabani/ham_veri.db` | 49152 | 5 |
| islem_gunlugu | `veritabani/kullanici_islemleri.db` | 233472 | 15 |
| giris_siniri | `sistem/giris_siniri.db` | 12288 | 1 (`sayac`) |
| istek_siniri | `sistem/istek_siniri.db` | 12288 | 1 (`lim`) |

Eski adlar ayni dosyada yazilidir: `tam_raporlama_v3.db`, `sla_analizleri.db`, `kullanici_loglari.db`, `hiz_siniri.db`, `flask_limiter.db`. Bu kopyada o eski adlar kokte gorulmedi.

## panel.db sahip tablosu

Satir sayisi parantez icinde. Sahip "oneri" ise kod yorumundan cikarimdir, ayri test ile kilitli degildir.

| Tablo | Satir | Sahip |
|---|---|---|
| customers | 200 | musteri |
| destech_contacts | 2 | musteri |
| rapor_alicilari | 1 | rapor (musteri kartindan yazilir; sahip rapor) |
| internal_scraped_data | 0 | dogrulanmadi |
| calendar_records | 7 | takvim (takvim_ozet okur) |
| reports | 1 | rapor |
| qbr_reports | 1 | sunum |
| project_items | 2 | proje |
| project_actions | 2 | proje |
| projects | 0 | proje |
| ict_revenues | 0 | tamsms |
| apn_revenues | 0 | tamapn |
| radar_prospects | 0 | radar |
| util_criteria | 1 | utilizasyon |
| util_criteria_istirak | 1 | utilizasyon |
| score_approval_requests | 0 | utilizasyon (rota `projects_bp` icinde; sahip onerisi) |
| gelistirme_talepleri | 5 | talep |
| gelistirme_talebi_loglari | 16 | talep |
| talep_bildirim_okundu | 5 | talep |
| users | 24 | core kimlik; roller alani `role`, `allowed_modules`, `is_admin` |
| aktif_oturumlar | 13 | core oturum |
| sistem_loglari | 285 | core audit |
| kullanici_loglari | 310 | core audit (ayrica ayri db) |
| daily_tasks | 0 | dogrulanmadi |
| matrix_configs | 1 | dogrulanmadi |

Gizli kolonlar tasimada yok: `users.pin_code`, `users.totp_secret`. `aktif_oturumlar` oturum kaydidir; tasinmaz, hedefte bos acilir.

## analiz.db

| Tablo | Satir | Sahip onerisi |
|---|---|---|
| sla_analizleri | 14 | rapor (grafik, `sla_deposu.py` basligi aylik rapora baglar) |
| rapor_gonderim | 1 | rapor |
| rapor_taslak | 1 | rapor |
| ats_kayitlari | 6 | onedesk |
| acik_kayitlari | 3 | onedesk |
| ci_pivotlari | 2 | onedesk |
| skor_detaylari | 5 | utilizasyon |
| skor_gecmisi | 5 | utilizasyon |
| urun_tutar | 4 | musteri |
| proje_musteri_calisma | 6 | proje |
| puanlama_disi_personel | 3 | utilizasyon |

## ham_veri.db ve islem gunlugu

`ham_veri.db`: `kurallar` 4, `metrikler` 4, `uygulama_gunlugu` 4, `ham_bloklar` 0, `veri_setleri` 0. Sahip: utilizasyon / veri yonlendirici. Katalog anahtari yok (`04`).

`kullanici_islemleri.db`: `kullanicilar` 13, `meta` 1, `u_*` tablolari 12 adet (satir sayilari 2 ile 661 arasi; kisi kimligi belgeye yazilmaz). Sahip: core audit. Hedef desende `u_*` acilmaz.

`giris_siniri.sayac` 1 satir, `istek_siniri.lim` 1 satir. Sahip: core rate limit. Tasimada sayac tasinmaz.

## v3.5 veri (dosya var)

`depo.py` `ADLAR = shared, system, realtime, security, backup`. `journal_mode` shared icin `delete`.

| Dosya | Tablolar (satir) |
|---|---|
| `veri/shared.db` | modul 15, rol 3 (`admin`, `TeamMngr`, `TeamMember`), rol_modul 45, musteri 0 |
| `veri/system.db` | ice_aktarim 0, olay 0 |
| `veri/realtime.db` | is_kaydi 0, skor 0 |
| `veri/security.db` | giris 1, yetki_red 1 (icerik yazilmadi) |
| `veri/backup.db` | yedek 0 |
| `veri/users/admin.db` | profil 4, notlar 0 (profil degerleri yazilmadi) |
| `instance/sirket.db` | users 0; `depo.py` bu dosyayi acmaz |

v3.5 tablolari prod tablolarinin yerine gecmez. `shared.modul` katalog tohumudur. `realtime.skor` prod `skor_gecmisi` ile ayni sema degildir. Tasima, v3.5 tablolarini genisletmek yerine modul `models.py` semasina yazar; mevcut v3.5 dosyalari faz 0'da yalniz katalog/rol tohumu olarak okunur.

## Alembic

- Bir `target_metadata`, modeller `modules/*/models.py` icinden import edilir (`app/data/base.py`).
- Ilk revizyon bos prod kopyasi degil, hedef semadir.
- SQLite ve PostgreSQL ayni revizyonu kosar. SQLite'ta `ALTER` sinirliysa yeni revizyon tablo yeniler; veri kopyasi revizyonda degil tasima betigindedir.
- Downgrade zorunlu degildir; geri donus uygulama paketini onceki surume almak ve sqlite dosya yedegidir (`09`).

## Tasima betigi tasarimi

`data/migrate.py` calistirma kurallari:

1. Kaynak yol parametre. Varsayilan yok. `C:\Secure_DB` ve `.env` okunmaz.
2. Baglanti `mode=ro` URI. Yazma denemesi hata.
3. Hedef bos sema (Alembic upgrade). Hedefte ayni is kurali satiri varsa anahtar karsilastirilir; ikinci kosu ayni sayida satiri tekrar eklemez (idempotent).
4. Haric kolon: `pin_code`, `totp_secret`, oturum, hiz sayaci, `ayar.json`, sertifika yolu.
5. Opsiyonel `--mask`: ad/eposta/telefon benzeri kolonlar sabit token. Hangi kolonlar maskelenir listesi betikte acik dizi; bu belge kolon uydurmaz. `customers.name` maskesi is kuralidir, ayrica onaylanir.
6. Bitis: kaynak `COUNT(*)` ile hedef `COUNT(*)` tablo tablodur. Haric tutulan tablo sayima girmez ve raporda "atlandi" denir.
7. Uyusmazlikta hedef islem geri alinir (tek transaction mumkun degilse hedef dosya silinip yeniden acilir). Kaynak dosyaya dokunulmaz.
8. Cikti yalniz sayidir: tablo adi, kaynak sayisi, hedef sayisi, atlanan kolon adlari. Satir basmaz.

Faz 4 PostgreSQL: ayni betik hedef URL'i `postgresql+psycopg` olur. SQLite dosyasi salt okunur kaynak olarak kalir. Iki canli yazici ayni anda yok. Gecis penceresi `09` cikis olcutundedir.
