# 08 ? Arayuz mimarisi

Mevcut `ekran-react` dosyalari yeniden adlandirilmaz. Yeni sayfa `src/modules/<anahtar>/` altina eklenir (`02`).

## Kararlar

- SPA. Vite. React 19. TypeScript. SSR yok. `package.json`: `react` ve `react-dom` `^19.2.8`, `vite` `^8.3.0`, `typescript` `~6.0.2`.
- Hedef stil: Tailwind v4 + shadcn/ui. Bugun Tailwind `^3.4.19`, `postcss.config.cjs`, `tailwind.config.js`. `@tailwind base/components/utilities` `src/index.css` icinde. v4'e gecis ayri is; token isimleri korunur.
- Tablo/sorgu/yonlendirme: TanStack Table, Query, Router. Form: React Hook Form + Zod. Grafik: Recharts `^3.10.1` (pakette var). Bugun TanStack, Hook Form, Zod, Vitest, Playwright yok.
- Bilesenler Radix uzerine: avatar, dialog, label, progress, separator, slot, tooltip (`package.json`). `components.json` yok. `src/components/ui/` altinda button, card, chart, input, skeleton, sheet, badge, separator, progress, label, tooltip, avatar, `app-1.tsx`, `admin-veri.tsx`, `veri-agaci.tsx`.
- Dil: TR varsayilan, EN sozluk ayni anahtar. Prod i18n anahtarlari `moduller.py` `Kutucuk.i18n` alaninda durur (`card.ekip.title` vb.). v3.5 ekranda sozluk dosyasi yok.
- API tipleri `openapi-typescript`. El ile cift tip yok. Mevcut `src/lib/api-tipler.ts` uretici calismadan kaynak sayilmaz.

## Acik sorular

- Tailwind v4 gecisinde `tailwind.config.js` kalkar; token'lar CSS'te kalir mi? Oneri: evet, asagidaki `:root` aynen tasinir.
- `App.tsx` bugun tek `App1`. Router eklenince `App1` kabuk olarak kalir mi, `shell/layout.tsx` ile degisir mi? Dosya silinmez; yeni kabuk yanina yazilir, gecis bitince `09` cikisinda `App1` cagrisi kalkar.
- Koyu tema token'i `:root` disinda yok. Tasarimda yok sayilir.
- `tsconfig` `strict` bayragi bu belgede acilmadi: dogrulanmadi.

## Tasarim tokenlari

Kaynak: `ekran-react/src/index.css` ve `tailwind.config.js`. Degerler oldugu gibi.

| Token | Deger |
|---|---|
| background / foreground | `hsl(0 0% 100%)` / `hsl(240 10% 3.9%)` |
| card, popover | ayni beyaz / ayni foreground |
| primary | `hsl(240 5.9% 10%)`, foreground `hsl(0 0% 98%)` |
| secondary, muted, accent | `hsl(240 4.8% 95.9%)` |
| muted-foreground | `hsl(240 3.8% 46.1%)` |
| destructive | `hsl(0 84.2% 60.2%)` |
| border, input | `hsl(240 5.9% 90%)` |
| ring | `hsl(240 5.9% 10%)` |
| radius | `0.625rem` |
| sidebar | `hsl(0 0% 98%)`, foreground `hsl(240 5.3% 26.1%)`, border `hsl(220 13% 91%)` |
| yazi | Inter, Segoe UI, system-ui |

Tailwind eslemesi `theme.extend.colors` icinde ayni isimler (`primary`, `sidebar.accent`, ...). `borderRadius.lg = var(--radius)`. Yeni renk eklenmez; modul kendi hex'ini yazmaz.

## Kabuk

`shell/layout.tsx` uc bolge: sol menu (katalog sirasi), ust cubuk (kullanici, cikis, talep girisi prod'da sag ust menu), icerik. Yukseklik bugunku gibi `h-dvh` (`App.tsx`). Menu ogesi `GET /api/v1/session` izin haritasindan gelir; gizli modul linki cizilmez. Prod `navigation_for` ayni isi workspace API'de yapar.

Menu sirasi prod `ANA_SAYFA_KUTUCUKLARI` ile kilitlenir (`03` tablosu). v3.5 `modul.sira` 0-14 ayri siradir (`id` farkli). Hedef sira prod ana sayfa sirasidir. `talep` menu ogesi degil, ust cubuk. `utilizasyon` ve `roller` yalniz admin. `topoloji` menu disi (`04`).

## Modul sayfa sablonu

Her `src/modules/<anahtar>/page.tsx`:

1. Baslik: katalog adi (TR).
2. `loading.tsx` ? iskelet (`skeleton` bileseni var).
3. `error.tsx` ? `code` + `reference`, ham metin yok (`07`).
4. `empty.tsx` ? "kayit yok"; hata ile ayni bilesen degil.
5. Icerik: ya `data-table.tsx` (TanStack Table) ya ozet kartlari (Recharts, bugun `chart.tsx` var).
6. Yazma: `form.tsx` + Zod semasi, sunucu `schemas.py` ile ayni alan adlari. Istemci semasi elle kopyalanmaz; OpenAPI'den uretilen tip kullanilir, Zod ince katman o tipten yazilir.

Tablo: sayfa, sayfa boyu, arama. Sunucu sayfalar (`07`). Tum satiri tarayiciya cekmek yok. Musteri listesi prod'da `per_page` tavan 100.

Erisilebilirlik: shadcn/Radix WAI-ARIA. Her form alaninda `label`. Ikon dugmesinin `aria-label`i sozlukten. Odak halkasi `--ring`. Kontrast: primary koyu zemin + acik yazi (token). Klavye: dialog `sheet.tsx` var; yeni dialog Radix disina cikmaz. Dil `html lang` hedef `tr`, EN secilince `en`.

## Sozluk

Dosya: `src/lib/i18n/tr.ts` ve `en.ts`. Anahtar prod i18n ile baslar, eksik olanlar `modul.<anahtar>.title`.

Dogrulanan prod anahtarlari (`Kutucuk.i18n`): `card.ekip.title`, `card.takvim.title`, `card.sunum.title`, `card.radar.title`, `musteri.tamPortfoy`, `card.rapor.title`, `card.proje.title`, `card.ats.title`, `card.toptan.title`, `card.tamSms.title`, `card.tamApn.title`, `card.gelirUretim.title`, `tab.takvim`, `card.placeholder.title`.

v3.5 `MODUL_AD` duz metin (ASCII, ornek "Musteri Yonetimi"). Sozluk ilk deger olarak prod gorunen adi kullanir (`M??teri Y?netimi` vb. `moduller.py`). Ingilizce karsilik bu taramada dosyada yok: EN degerleri ceviri isi, uydurulup kilitlenmez; bos anahtar testte kirilir.

## Mevcut ekrandan gecis

| Bugun | Hedef | Not |
|---|---|---|
| `src/App.tsx` `App1` | `app/router.tsx` + `shell/layout.tsx` | App.tsx silinmez |
| `components/ui/app-1.tsx` ve `app-1-utils/` | kabuk parcasi | is kurali yok |
| `components/ui/admin-veri.tsx`, `veri-agaci.tsx` | admin sayfasi, `roller` / ice aktarma | API `07` admin yollari |
| `lib/api.ts` `API_KOK` 8119 | ayni origin veya tek `VITE_API_URL` | port 8118 scripti ile celiski |
| `lib/api-tipler.ts` | `openapi-typescript` ciktisi | elde yazim durur |
| `tailwind.config.js` | v4 CSS | token tablosu korunur |
| Radix ui dosyalari | `shared/ui` yeni sarmalayici; eski dosya yerinde | tasima degil, import yolu sonra |

Sayfa ekleme sirasi `OZET.md` P0 kabuk, sonra P1 modul. Bir sayfa, karsilik gelen `/api/v1` OpenAPI'de yoksa baglanmaz; sahte JSON yok.

## ekran-react dosya envanteri

`package.json` script: `dev`, `build` (`tsc -b && vite build`), `lint` (oxlint), `preview`, `api:uret`. Bagimliliklarda TanStack, Zod, react-hook-form, vitest, playwright yok. `tailwindcss` 3.4.19. `vite.config.ts` host `127.0.0.1`, `strictPort: false`, alias `@` -> `src`.

| Dosya | Bayt |
|---|---|
| src/main.tsx | 230 |
| src/App.tsx | 171 |
| src/index.css | 1225 |
| src/lib/api.ts | 47 |
| src/lib/api-tipler.ts | 5503 |
| src/lib/utils.ts | 165 |
| src/components/ui/app-1.tsx | 22753 |
| src/components/ui/admin-veri.tsx | 11985 |
| src/components/ui/veri-agaci.tsx | 2813 |
| src/components/ui/app-1-utils/app-1-data.ts | 10889 |
| src/components/ui/app-1-utils/app-1-sidebar.tsx | 6954 |
| src/components/ui/chart.tsx | 3383 |

`App.tsx` yalniz `App1` render eder. `api.ts` tek sabit: `API_KOK = "http://127.0.0.1:8119"`. Prod `frontend/` ayri pakettir; bu belgenin gecis kaynagi degil, v3.5 `ekran-react`tir. Prod `tests/test_frontend_assets.py` ve `test_arayuz_sadelestirme.py` vardir; govde okunmadi.

Sayfa sablonu durumlari dort bilesende kalir (`empty`, `loading`, `error`, tablo veya form). `app-1.tsx` icine yeni modul sayfasi eklenmez. Mevcut ui dosyalari silinmez.
