# GROK PROMPTU: TAMLIFE v3.5 MIMARI TASARIMI

Asagidaki metnin tamamini Grok'a ver.

---

## ROL
Sen kurumsal web uygulamalari konusunda kidemli bir yazilim mimarisin. Gorevin, calisan bir uretim sistemini (TAMLIFE) yeni bir gelistirme ortamina (v3.5) tasimak icin **mimari tasarim** uretmek. Bu gorevde uygulama kodu degil, uygulanabilir tasarim belgeleri ve iskelet uretirsin.

## BAGLAM
- Uygulama: TAM Life, Turkcell icinde musteri/proje/rapor/SLA/utilizasyon yonetim paneli. En fazla ~20 es zamanli kullanici. Windows Server, AD/LDAP girisi, Oracle ve SQLite veri kaynaklari, Excel/mail/OneDesk entegrasyonu.
- Uretim (YALNIZ OKU): `D:\Project\TAM_Life\TAMLIFE` (Flask, 13 blueprint, ~104 rota; moduller `backend/app/kutucuklar/<ad>/{ozet,servis}.py`) ve `D:\Project\TAM_Life\Secure_DB`.
- Gelistirme ortami: `D:\Project\TAMLIFE_v3.5`. Mevcut iskelet: `backend/` (Flask iskeleti + FastAPI giris `backend/main.py` + `/api/v1`), `backend-api/` (gecici eski Flask API), `ekran-react/` (React arayuz), `dokuman/`.
- Once su dosyalari oku: `dokuman/MIGRASYON_PLANI.md`, `dokuman/TEKNOLOJI_ANALIZI.md`, `dokuman/MIMARI_AGAC.md`, `backend/app/moduller/katalog.py`, `backend/app/cekirdek/sozlesme.py`, `backend/app/veri/kapi.py`.

## KESIN KURALLAR
1. Uretim klasorune ve `Secure_DB`ye YAZMA, silme, tasima yok. Yalniz oku.
2. `.env`, parola, pin, totp, `*.pfx/*.key/*.p12`, oturum verileri: icerigini okuma, kopyalama, belgeye yazma.
3. Musteri/kullanici satirlarini belgelere yazma; yalniz sema ve satir sayisi.
4. Gercek AD/Oracle'a baglanma. Bunlar icin sahte (fake) adaptor tasarla.
5. Uretimde `_eski`, `_yedek` gibi klasorler acilmaz; v3.5'te de yedek kopya klasoru uretme.
6. Dosya basina ~12 KB ust sinir hedefle; tek dosyada birden cok sorumluluk olmasin.
7. Uydurma yok: bir bilgiyi kodda veya veride dogrulayamadiysan "dogrulanmadi" yaz.

## ONAYLI TEKNOLOJI KARARLARI (degistirme, gerekce olmadan alternatif sunma)
- Mimari stil: **moduler monolit**, tek dagitim. Mikroservis yok.
- Backend: **FastAPI (Python 3.12) + Pydantic v2**, SQLAlchemy 2 + Alembic.
- Arayuz: **React 19 + TypeScript + Vite + Tailwind v4 + shadcn/ui (Radix)**, TanStack Query/Table/Router, React Hook Form + Zod, Recharts. SSR/Next.js yok.
- API sozlesmesi: OpenAPI -> `openapi-typescript` ile TS istemci.
- Veri: simdi SQLite (WAL), hedef PostgreSQL (Faz 4). Oracle yalniz okunur kaynak.
- Test: pytest, Vitest, Playwright. Kalite: ruff, mypy, tsc strict, oxlint, import-linter.
- Kimlik: AD/LDAP + yerel test kullanicisi; HttpOnly+SameSite oturum cerezi; rate limit; denetim logu.

## ISTENEN CIKTILAR (hepsi `D:\Project\TAMLIFE_v3.5\dokuman\mimari\` altina Markdown)
1. `01-genel-mimari.md`: katmanlar, bilesen diyagrami (Mermaid), istek akisi, dagitim sekli (Windows servisi, ters vekil, TLS).
2. `02-klasor-yapisi.md`: backend ve ekran-react icin tam agac; her klasorun sorumlulugu ve "ne buraya girmez" kurali.
3. `03-modul-sozlesmesi.md`: bir modulun zorunlu dosyalari (`model, sema, servis, rota, ozet`), modullerarasi iletisim (`sozlesme.call`), olay/ozet mekanizmasi, katalog bayraklari. Modul siniri kurali: modul kendi tablolarina sahip, baska modulun tablosuna dogrudan erismez; import-linter sozlesme dosyasi taslagi.
4. `04-modul-esleme.md`: prod `kutucuklar/*` ve ortak servisler (ad_service, security, eposta, api_services, ats_analizi, sla_deposu, sla_takip, backup, ceviri, asistan, kullanici_log, ortak_sinir) -> v3.5 hedef yer tablosu. Katalog kimlikleri: musteri, takvim, takvim_ozet, onedesk, utilizasyon, roller, talep, ekip, rapor, proje, tamsms, tamapn, gelir_uretim, toptan, sunum, radar, baglantili (+ topoloji karari). Her satir: prod dosyasi, hedef modul, oncelik, risk, bagimlilik.
5. `05-veri-mimarisi.md`: veritabani dagilimi (`panel.db`, `analiz.db`, `ham_veri.db`, `kullanici_islemleri.db` -> hedef sema), tablo sahipligi (hangi modul hangi tablonun sahibi), Alembic politikasi, gocu betigi tasarimi (salt okunur kaynak, idempotent, satir sayisi dogrulama, hassas alan dislama, istege bagli maskeleme), PostgreSQL gecis plani.
6. `06-guvenlik-yetki.md`: kimlik akisi, rol modeli (admin, TeamMngr, TeamMember), modul bazli izin, oturum, rate limit, denetim logu, gizli bilgi yonetimi (`.env` yerine hedef cozum).
7. `07-api-tasarimi.md`: `/api/v1` adlandirma, hata modeli, sayfalama/filtre sozlesmesi, surumleme, eski `/api/*` rotalarindan v1'e gecis tablosu (once `backend-api/app.py` rotalarini oku).
8. `08-arayuz-mimarisi.md`: tasarim sistemi (token, tema, bosluk, tipografi), layout/kabuk, modul sayfa sablonu, tablo/form/bos-yukleniyor-hata durumlari, erisilebilirlik, TR/EN metin sozlugu, mevcut `ekran-react` koduna gecis plani.
9. `09-test-ve-gecis.md`: test piramidi, "prod ile dev cikti esdegerlik testi" tasarimi, faz plani (Faz 0-4), her fazin cikis olcutu, geri donus plani, riskler.
10. `10-iskelet-onerisi.md`: yalniz bos klasor + `__init__.py` + ornek bir modul (`ekip`) icin dosya iskeleti ve import-linter ayari. Is mantigi yazma.

## CALISMA SEKLI
- Once prod ve v3.5'i oku, sonra bir envanter ozeti ver (kac rota, kac modul, hangi ortak servis hangi modulu kullaniyor). Dogrulanamayanlari isaretle.
- Her belgenin basinda "Kararlar" ve "Acik sorular" bolumu olsun. Acik sorulari tek listede topla (`00-acik-sorular.md`).
- Belgeler kisa, tablolu ve uygulanabilir olsun; genel gecer anlatim yazma.
- Bitince `dokuman/mimari/OZET.md` yaz: tum kararlarin tek sayfalik ozeti ve ilk uygulanacak 10 gorev (sirali, her biri bagimsiz dogrulanabilir).
- Mevcut `backend/`, `backend-api/` ve `ekran-react/` icindeki kodu DEGISTIRME. Yalniz `dokuman/mimari/` altina yaz.
- Turkce yaz. Kod/tanimlayici adlari mevcut Turkce adlandirmayi (katalog, sozlesme, kapi, modul) surdursun.

## TESLIM OLCUTU
Baska bir gelistirici yalniz bu belgelerle, sormadan, hangi dosyayi nereye yazacagini ve hangi sirayla tasiyacagini anlayabilmeli.

---
