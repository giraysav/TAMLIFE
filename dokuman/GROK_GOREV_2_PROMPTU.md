# GROK PROMPTU 2: ILK 10 ISIN UYGULANMASI

`---` arasindaki metnin tamamini Grok'a ver.

---

## ROL
Kidemli backend/frontend muhendisisin. `dokuman/mimari/` altindaki tasarimi (sen yazdin) UYGULAYACAKSIN. Kapsam: `dokuman/mimari/OZET.md` icindeki "Siradaki 10 is". Is kurali (musteri, skor, SLA vb.) bu gorevde YOK.

## ONCE OKU
`dokuman/mimari/OZET.md`, `00-acik-sorular.md`, `02`, `03`, `05`, `06`, `07`, `08`, `10`; `backend/api.py`, `backend/depo.py`, `ekran-react/package.json`.
Bilinen durum: `backend/app/**`, `backend/tests/**`, `ekran-react/src/{modules,shell,shared,app}/**` altinda 201 adet BOS (0 bayt) yer tutucu dosya var. Calisan kod yalniz `backend/api.py` (Flask), `backend/depo.py` ve `ekran-react` mevcut SPA'dir.

## KESIN KURALLAR
1. **Hicbir dosyayi SILME, yeniden adlandirma, tasima yapma.** Yalniz bos yer tutucuyu doldur veya yeni dosya ekle. Mevcut calisan dosyada (`api.py`, `depo.py`, `app-1.tsx`, `package.json`) degisiklik gerekiyorsa once degisikligi ve nedenini yaz, onay bekle. (Daha once bu klasorde dosyalar kayboldu; git yok, geri donus yok.)
2. Uretim `D:\Project\TAM_Life\*` yalniz OKUNUR. Yazma yok.
3. `.env`, parola, pin, totp, `*.pfx/*.key`, `ayar.json` ve `yerel_kullanici*.json` govdeleri: okuma, kopyalama, loglama, belgeye yazma yok. Test parolasi repoya yazilmaz; ortam degiskeni veya testte uretilen gecici deger.
4. Gercek AD/Oracle'a baglanma yok; sahte adaptorler.
5. Ayni anda tek is. Bir isin kontrolu gecmeden sonrakine gecme. Her is sonunda: degisen dosya listesi, calistirilan komut ve GERCEK cikti (gecti/kaldi) yaz. Calistirmadigin kontrolu "gecti" yazma.
6. Dosya basina ~12 KB ust sinir; mimari belgelerdeki adlandirmaya uy. Belgeyle kodun cakistigi yerde belgeyi sessizce degistirme; `00-acik-sorular.md`'ye madde ekle.
7. Mevcut calisan sistemi bozma: `backend/api.py` (Flask) ve mevcut `ekran-react` arayuzu is 10 bitene kadar calismaya devam etmeli.

## ACIK SORULARA GECICI VARSAYILANLAR
(Kullanici onayi bekliyor; kod bunlara gore yazilir, degisirse tek yerden degisecek sekilde `core/config.py`/katalogda tut.)
- Q1 takvim tablo sahibi: `takvim`. Q2 topoloji: ayri modul, menude yok (`in_nav=false`), yetki `musteri`.
- Q3 gelir_uretim, toptan: bos kart, "Kayit yok".
- Q4, Q5, Q20, Q19: sahibi/varligi dogrulanmayanlari prod kodunda `Grep` ile DOGRULA ve cevabi `00-acik-sorular.md`'ye yaz; dogrulayamazsan "dogrulanmadi" kalsin.
- Q6 denetim: tek `audit_event` tablosu. Q7 CSRF: zorunlu (durum degistiren isteklerde).
- Q8 2FA: bu gorevde kapsam disi. Q11: tek uvicorn sureci, tek yazici.
- Q12 eski `/api/*` uyumluluk katmani: yok; arayuz is 10'da v1'e gecer.
- Q13 JSON govde tavani: 1 MiB, dosya yukleme ucu haric 20 MiB.
- Q17 Tailwind v4 gecisi: ayri gorev, bu 10 isin disinda. Q18: `App1` gecici kalir.
- Q21 port: tek port 8117 (`api.ts` ile ayni); `api:uret` scripti da 8117'ye bakar.
- Q22 `instance/sirket.db`: yok say, silme. Q23 `backend-api/`: dokunma.
- Q25 maskeleme: varsayilan ACIK; musteri adi ve iletisim alanlari maskelenir.

## IS LISTESI (sirayla; her biri OZET.md'deki kontrolle dogrulanir)
1. `backend/app/main.py`: FastAPI iskeleti, `GET /api/v1/health` 200. Is kurali yok.
2. `pyproject.toml` + import-linter (mevcut `backend/.importlinter` ile ayni sozlesme). Kontrol: `lint-imports` 0 ihlal.
3. `app/modules/catalog.py`: prod `MODULLER` anahtarlari ve bayraklari. Kontrol: pytest kume esitligi.
4. `app/data/gateway.py`: SQLite WAL. Kontrol: `PRAGMA journal_mode` = `wal`.
5. Alembic ilk revizyon: bos sema; `users`ta `pin_code`, `totp_secret` YOK. Kontrol: upgrade sonrasi kolon listesi.
6. `core/session.py`: HttpOnly, SameSite=Lax, Secure ayari. Kontrol: `Set-Cookie` bayraklari, govdede token yok.
7. Sahte AD + yerel test kullanicisi (parola repoda yok). Kontrol: dogru 200, yanlis 401, gercek LDAP cagrisi 0.
8. `core/authz.py`: admin/TeamMngr/TeamMember. Kontrol: TeamMember+utilizasyon=403, admin=200, talep giris yapana acik.
9. `core/audit.py`: tek tablo, gizli alan reddi. Kontrol: satirda pin/totp/cerez yok; 403 sonrasi audit +1.
10. `ekran-react` kabuk: menu sirasi prod `ANA_SAYFA_KUTUCUKLARI`; token `08`. Kontrol: 14 ana sayfa karti sirasi.

## TESLIM
Her is sonunda kisa rapor (degisen dosyalar, komut, gercek cikti, kalan risk). 10 is bitince `dokuman/mimari/UYGULAMA_RAPORU.md`: yapilanlar, kalanlar, `00-acik-sorular.md`'de yeni maddeler. Turkce yaz.

---
