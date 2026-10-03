# 06 ? Guvenlik ve yetki

Gizli deger yok. `.env`, `ayar.json` govdesi, pin, totp, sertifika okunmadi.

## Kararlar

- Roller uctur: `admin`, `TeamMngr`, `TeamMember`. Kaynak: prod `moduller.py` `YONETICI_ROLLERI = ('admin', 'TeamMngr')` ve v3.5 `ortak.db` `rol` (3 satir, ayni adlar).
- `admin` ve `TeamMngr` tum modulleri ve tum veriyi gorur. Istisna: `utilizasyon` ve `roller` `yalniz_admin` (`moduller.py`). TeamMngr bu ikisine kapali.
- `TeamMember` yalniz isaretlenen modulu gorur ve o modulde yalniz kendi verisini gorur (yorum: atanmis musteriler, ad-soyad eslesen kayit, kendi takvimi). Hedef bunu bozmaz.
- Rol, ana sayfa kutucugunu gorme iznidir (2026-09-29 notu). Modulu goren, silme haric islem yapar. Silme, sorumlu TAM degistirme, final skor, talep yonetimi admin/TeamMngr. `MODUL_ISLEMLERI` yalniz `add/sync/duzenle -> musteri`.
- `talep` `herkese_acik`: giris yapan herkes acar.
- Oturum: HttpOnly + SameSite cerez. Prod ve v3.5 ikisi de `SESSION_COOKIE_HTTPONLY=True`, `SAMESITE=Lax`. Prod `SESSION_COOKIE_SECURE` ortamdan, varsayilan karsilastirma `'false'`. v3.5 secure bayragini config'e yazmaz; cikis cerezi `SESSION_COOKIE_SECURE` varsayilan `False` kullanir. Hedef: TLS arkasinda Secure=true.
- Hiz siniri ve denetim cekirdekte. v3.5 `api.py` icinde limiter yok (arama: `limiter` 0). Prod Flask-Limiter + `ortak_sinir.py`.
- Gizli alan veritabanina ve belgeye yazilmaz. `users.pin_code` ve `users.totp_secret` kolon adlari semada durur; tasima haric tutar (`05`).

## Acik sorular

- CSRF: prod `security.py` `csrf_protect` var. v3.5 `api.py` icinde `csrf` gecmez. Hedef cookie oturumda CSRF basligi zorunlu mu? Karar acik. SameSite=Lax cogu POST'u ayni site sayar; ters vekil tek origin ise risk duser.
- Bosluk zaman asimi prod'da `AKTIF_OTURUM_ZAMAN_ASIMI_DK = 30`, `AD_OTURUM_BOSTA_DK = 10`, kalici cerez omru `PERMANENT_SESSION_LIFETIME` 4 saat (`__init__.py`). v3.5 kopyasi dogrulanmadi (satirlar okunan aralikta yok).
- 2FA (`is_2fa_enabled`) hedefte var mi? Kolon var, akis bu belgede adim adim cikarilmadi: dogrulanmadi.
- `dev_admin` v3.5 ayar anahtari. Deger okunmadi. Hedefte yerel test kullanicisi ayri, parola repoda yok.

## Kimlik akisi

1. Istemci `POST /api/v1/session` (hedef ad). Bugun v3.5 `POST /api/giris`, prod `POST /login` (sayfa) ve workspace `GET /api/v1/session` (mevcut oturum).
2. Once yerel test kullanicisi (sabit kisi, gizli deger ortamda). Olmazsa sahte AD adaptoru. Gercek LDAP bu fazda cagrilmaz. Prod gercek cagri `ad_service.py` icindedir; v3.5 `_AD` sinifi `api.py` icindedir, bu belge onu tasimaz.
3. Basari: sunucu cerez yazar. Govdede oturum kimligi, pin veya totp donmez. `workspace_api` bugun `csrf_token` JSON icinde dondurur; hedefte token yalniz baslik/cerez, loga yazilmaz.
4. Her istek `core/session.py`: cerez var mi, kullanici `is_active` mi, bosluk suresi doldu mu. Prod `login_required` + `oturum_dokun` (60 sn'de bir tazeleme sabiti).
5. Modul kapisi `catalog` + `allowed_modules`. v3.5 `modul_acik` ve `gorunen` `api.py` icinde ayni isi Flask oturumuyle yapar. Hedefte tek fonksiyon `core/authz.py`.
6. Cikis cerezi siler. v3.5 `POST /api/cikis`. Prod `GET /logout`.

Yerel test kullanicisi yalniz `APP_ENV=dev` iken aciktir. Uretim konfigurasyonunda bu dal kapali. Kullanici adi belgede sabitlenmez.

## Modul izni

Prod izin gruplari: `modules` ve `dashboard_cards` (`Kutucuk.izin_grubu`). Secilebilir anahtarlar, `herkese_acik` veya `yalniz_admin` veya `yalniz_yonetici` olmayanlar. Kart turu `dashboard_cards`, modul turu `modules`.

v3.5 `rol_modul` 45 satir = 3 rol x 15 modul. Bu, prod kuralinin birebir kopyasi oldugu dogrulanmadi (45/15=3, her role her modul satiri var gibi durur; `yalniz_admin` utilizasyon icin ayri kolon var). Davranis testi yok: v3.5 `tests/` klasoru yok.

Hedef kural (prod metninden, degistirmeden):

| Rol | Katalog | Veri kapsami |
|---|---|---|
| admin | hepsi, `roller` ve `utilizasyon` dahil | tum satirlar |
| TeamMngr | `yalniz_admin` haric hepsi | tum satirlar |
| TeamMember | `rol_modul` kesisimi, `talep` her zaman | yalniz kendi kapsami |

Kapsam fonksiyonu prod `Kapsam` sinifi (`moduller.py`). Hedef `core/authz.py` icinde, modul service'i `user_id` filtresini kendisi uygular; HTTP katmani yalniz "bu modul acik mi" der.

Musteri karti alan izni `MUSTERI_KARTI_ALANLARI` (21 alan, `moduller.py`). `ekip` alt alanlari `EKIP_OZET_ALANLARI` (8). 2026-09-29 notu: alt yetki kaldirildi, ozeti gorebilen hepsini gorur. Hedef ilk surum bu notu esas alir; 21 alanlik matris tasinmaz, acik soru olarak durur.

## Oturum, limit, denetim

| Kontrol | Prod (dogrulandi) | v3.5 (dogrulandi) | Hedef |
|---|---|---|---|
| Cerez HttpOnly | True | True | True |
| SameSite | Lax | Lax | Lax |
| Secure | ortam, varsayilan false | varsayilan false | TLS arkasinda true |
| Hiz siniri | `ortak_sinir.py`, `giris_siniri.db`, `istek_siniri.db` | yok | `core/rate_limit.py`, sayac tablosu core |
| Giris denetimi | `security.log_yaz`, `kullanici_log.yaz` | `guven.giris` (1 satir, icerik yok) | `audit_event` |
| Yetki red | prod ayri fonksiyon bu belgede tek tek eslenmedi | `guven.yetki_red` | ayni audit, eylem `denied` |
| Hata kodu | `hatalar.KODLAR` TL-DB-01, TL-DB-02, TL-MOD-01, TL-VAL-01, TL-EXCEL-01, TL-SMTP-01, TL-ORA-01, TL-SRV-01 | v3.5 `status/message` | ayni kodlar `07` |

Limit taslagi (sayi prod kodundan kopyalanmadi; `topology` `10 per minute` dekoratoru dogrulandi, diger limitler bu taramada tek tek okunmadi): giris ucu IP+kullanici adi, modul ucu oturum. Asim 429, govdede hesap veya parola ipucu yok.

Denetim satiri: zaman, aktor id, eylem, modul, hedef id, sonuc, istek yolu. Ayrinti alanina pin, totp, cerez, SMTP, Oracle sifresi, sertifika yolu yazilmaz. Prod `kullanici_log` ayrinti serbest metindir; hedef sema alanlari sinirlar.

## Gizli bilgi

- Repoda `.env` yok (v3.5 kokunde `.env` dosyasi bu listede gorulmedi; prod kokunde `.env` var, okunmadi).
- `ayar.json` anahtarlari: `yerel_admin`, `dev_admin`, `ad`, `sertifika`, `baglantilar`. Dosya hedef agactan cikar. Degerler ortam veya isletim kasasi.
- Log ve hata cevabi dosya yolu, sunucu adi, SQL sizdirmaz. Prod `hatalar.py` basligi bunu kilitler.
- Yedek (`backup.py`) tum `BACKUP_MODELS` tablolarini JSON yazar. Hedef yedek, haric kolon listesini `05` ile paylasir. Mevcut JSON yedek bu tasarim onaylanmadan uretilmez.

## Prod security.py yuzeyi (hedef fonksiyon eslemesi)

Dosya 314 satir. Sinif/fonksiyon adlari dogrulandi; govde satirlari tek tek ozetlenmedi.

| Prod | Hedef |
|---|---|
| establish_session, session_stamp, refresh_current_user | core/session.py |
| login_required, admin_required | core/authz.py bagimliliklari |
| csrf_protect, _login_csrf_retry | acik soru 7 cozulmeden tasinmaz |
| db_transaction | data/gateway.py |
| bosta_siniri_dk, AKTIF_OTURUM_ZAMAN_ASIMI_DK=30, AD_OTURUM_BOSTA_DK=10, AKTIF_OTURUM_TAZELEME_SN=60 | core/session.py sabitleri |
| log_yaz, islem_gunlugune_yaz, oturum_baslat_kaydi, oturum_kapat_kaydi | core/audit.py |
| KISI_GUNLUGUNE_YANSIYAN: giris, cikis, ad_kullanici_acildi, ad_alan_disi | audit eylem allow-list baslangici |

`users` kolonlari (sema, deger yok): id, username, full_name, pin_code, is_admin, role, allowed_modules, is_active, ad_domain, is_ad_user, totp_secret, is_2fa_enabled. Hedef kimlik tablosu `pin_code` ve `totp_secret` kolonunu acmaz. `ad_domain` ve `is_ad_user` kalir; sahte adapt?r bunlari test verisiyle doldurur, gercek alan adi repoda sabitlenmez.

v3.5 giris `api.py` `yerel_dene` ve `_AD` icindedir. `ayar.json` anahtari `yerel_admin` ve `dev_admin` vardir; deger okunmadi. `guven.giris` ve `guven.yetki_red` birer satir; metin basilmadi. Hiz siniri tablolari prod kopyada `sayac` ve `lim`, birer satir; v3.5'te karsilik tablo yok.
