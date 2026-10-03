# TEKNOLOJI ANALIZI (web arastirmasi, 2026-10-03)

Kaynak kalitesi uyarisi: arastirma sonuclari agirlikla blog ve ozet sitelerinden geldi. Yon gostericidir, kesin olcum degildir. Stack Overflow anketi birincil kaynaktir.

## Bulgular

| Konu | Bulgu | Kaynak |
|---|---|---|
| Dil/kutuphane payi | JavaScript %66 ile en cok kullanilan dil; Python 2025'te +7 puan; TypeScript +2,5. Web cercevelerinde Node.js %29,7, React %30,7 | [Stack Overflow 2025](https://survey.stackoverflow.co/2025/technology/) |
| Mimari | 2026'da varsayilan: iyi yapilandirilmis (moduler) monolit; servis ayirma yalniz olcek ve takim sayisi gerektirince. CNCF 2025: mikroservis benimseyenlerin %42'si birlestirmeye donuyor | [dev.to](https://dev.to/codewithamrendra/microservices-vs-modular-monolith-in-2026-which-architecture-actually-scales-1iie), [cloudmagazin](https://www.cloudmagazin.com/en/2026/03/31/microservices-vs-monolith-2026-when-refactoring-really-pays-off/) |
| Moduler monolit kurali | Tek dagitim, modullerin dar arayuzu, modul kendi tablosuna sahip, modullerarasi dogrudan DB erisimi yok | [hyscaler](https://hyscaler.com/insights/microservices-vs-monolith/) |
| Yonetim paneli arayuzu | React 19 + TypeScript + Tailwind + shadcn/ui (Radix, WAI-ARIA) + TanStack Table/Query + React Hook Form + Zod + Recharts fiili standart | [freeCodeCamp](https://www.freecodecamp.org/news/build-an-admin-dashboard-with-shadcnui-and-tanstack-start/), [dev.to sablonlar](https://dev.to/bishoy_semsem/11-best-open-source-shadcn-dashboard-templates-for-2026-479d) |
| Backend | Kurumsal/regule alanda Spring Boot ve ASP.NET Core baskin; FastAPI Python API ve veri/AI isleri icin en iyi; Django guclu admin katmani ve guvenli varsayilanlar icin | [daily.dev](https://daily.dev/posts/top-10-backend-frameworks-for-enterprise-development-in-2026-juuerwuxx), [analyticsinsight](https://www.analyticsinsight.net/programming/top-backend-frameworks-every-developer-should-learn-in-2026) |

## TAMLIFE icin degerlendirme

Baglam: en fazla ~20 es zamanli kullanici, Windows Server + AD/LDAP, Oracle ve SQLite, Excel/mail/OneDesk entegrasyonu, mevcut Python is mantigi, kucuk ekip.

| Aday | Artilari | Eksileri | Sonuc |
|---|---|---|---|
| **FastAPI + React/TS (mevcut secim)** | Prod Python kodu (skor motoru, Excel, Oracle, LDAP) tasinir; tip + OpenAPI -> TS istemci; en az kod | Admin/kimlik/izin katmanini kendimiz kurariz | **Onerilen** |
| Django + DRF + React | Hazir admin, ORM, izin sistemi, guvenli varsayilanlar; Python | Agir; mevcut Flask/SQLAlchemy kodundan daha buyuk gecis; API tipleri FastAPI kadar otomatik degil | Yedek secenek |
| ASP.NET Core + React | Windows/AD ile en dogal uyum, kurumsal destek | Tum Python kodu yeniden yazilir; ekip becerisi ve maliyet; veri/Excel isleri zayiflar | Yalniz kurum standardi zorlarsa |
| Spring Boot | Regule sistemlerde guclu | Bu olcek icin asiri agir, Java'ya tam gecis | Onerilmez |
| Next.js / TanStack Start (SSR) | SEO, SSR | Ic panel, AD arkasinda, SEO gerekmez; ek sunucu katmani | Gereksiz: Vite SPA yeterli |
| Mikroservis | Bagimsiz olcek | 20 kullaniciya 3-6 kat isletme maliyeti | Onerilmez |

## Sonuc

Mevcut karar dogrulanir: **moduler monolit + FastAPI (Python 3.12) + React 19 / TypeScript / Vite / Tailwind / shadcn/ui + TanStack + Zod**.

Eklenmesi onerilen iyilestirmeler:
1. **Veritabani:** 20 kullanici icin SQLite+WAL yeterli, ama kurumsal varsayilan PostgreSQL. Faz 4'te gecis; SQLAlchemy+Alembic bunu kolaylastirir. Oracle yalniz okunur kaynak kalir.
2. **Modul siniri kurali** (arastirmadaki moduler monolit ilkesi): modul kendi tablolarina sahip, baska modulun tablosuna dogrudan erismez; `sozlesme` uzerinden konusur. Sinir ihlalini otomatik yakalamak icin import-linter (Python) eklenir.
3. **Arayuz:** Tailwind v4 ve TanStack Table/Query/Router ekran-react'e eklenir (su an Tailwind 3, TanStack yok). Tasarim sistemi `shadcn/ui` token'lari ile tek yerde.
4. **Kimlik:** AD/LDAP korunur; oturum cerezi HttpOnly+SameSite; rate limit ve denetim logu cekirdekte.
5. **Gozlemlenebilirlik:** yapisal log + saglik ucu (`/api/v1/saglik`); hata izleme (Sentry benzeri) opsiyonel.
6. **Isletim:** Windows servis olarak uvicorn/gunicorn benzeri sureç yoneticisi (prod'daki Waitress'in karsiligi) ve ters vekil (IIS/nginx) uzerinden TLS.

## Acik karar

Kurumda ASP.NET Core ya da Java zorunlulugu var mi? Yoksa yukaridaki yigin degismeden devam eder.
