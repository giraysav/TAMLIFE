# Mimari durum raporu (2026-10-03, bagimsiz dogrulama)

Kaynak: Claude'un kendi calistirdigi komutlar. Grok'un `UYGULAMA_RAPORU.md` iddialari yeniden calistirilarak dogrulandi.

## Dogrulanan (calistirildi)
| Kontrol | Sonuc |
|---|---|
| `pytest` (backend) | 14 gecti |
| `lint-imports` | 2 sozlesme, 0 ihlal (modul bagimsizligi `independence`, cekirdek -> modul yasagi) |
| `ruff check app tests` | 0 hata |
| `mypy app` | 0 hata (121 dosya) |
| `vitest` (ekran-react) | 2 gecti (14 ana sayfa karti, prod sirasi) |
| `npm run build` (TS 7, Tailwind 4, Vite 8) | gecti |
| `npm audit` | 0 acik |
| FastAPI 8117 `/api/v1/health` | 200 |

## Mimari karsilastirma
| Katman | Tasarim | Kodda |
|---|---|---|
| Cekirdek (config, errors, session, authz, audit) | tamam | uygulandi, testli |
| Veri (SQLite WAL, Alembic: users, audit_event; pin/totp yok) | tamam | uygulandi |
| Kimlik (yerel test + sahte AD, HttpOnly/SameSite cerez) | tamam | uygulandi |
| Yetki (admin/TeamMngr/TeamMember, 401/403) | tamam | uygulandi |
| Katalog (17 prod anahtar + topoloji) | tamam | uygulandi |
| Moduller (musteri, takvim, ... 17) | tasarlandi | **182 dosya bos (0 bayt); hicbir modulde is mantigi yok** |
| Veri gocu (`data/migrate.py`) | tasarlandi | bos |
| Oracle sahte adaptor | tasarlandi | bos |
| Arayuz kabugu (nav, kart listesi) | tamam | yazildi ama `App.tsx` hala eski `App1` |
| Arayuz modulleri (page/table/form/api) | tasarlandi | bos |
| API tipleri (OpenAPI -> TS) | tamam | `api-types.ts` uretildi |

## Calisan sistem (gecis donemi)
- Eski Flask `backend/api.py` :8119 (canli arayuz bunu kullaniyor, `api.ts`)
- Yeni FastAPI `backend/app` :8117 (yalniz health, kimlik, yetki, denetim)
- Vite :5173
- Prod'dan **hicbir is fonksiyonu** henuz tasinmadi (104 rotanin 0'i v1'de).

## Bu turda eksik olarak tamamlananlar
- Ruff/mypy hatalari, import-linter ihlali (kendi service'ini yasaklama), sozlesme/test uyumu.
- Eksik arac ve kutuphaneler: ruff, mypy, import-linter, TanStack Query/Router/Table, Hook Form, Zod, Vitest, Playwright.
- Port: tek hedef 8117; `api:uret` ona ve `/openapi.json`'a baglandi.
- Kazara kalan `_gen_task1.py`, `_catalog_src.json` silindi.

## Acik riskler
1. Is fonksiyonlari tasinmadi; proje %0 islevsel gecis. Sonraki is: Faz 2 (modul is mantigi).
2. `audit_event` hem Alembic hem calisma aninda `create_all(checkfirst)` ile aciliyor; tek kaynak Alembic olmali.
3. Iki backend ve iki giris sistemi paralel; arayuz henuz FastAPI kimligini kullanmiyor.
4. Playwright e2e dosyasi yazildi ama tarayici indirilmedigi icin calistirilmadi.
5. `api.ts` hala 8119; FastAPI'ye gecis modul tasima ile birlikte yapilmali.
6. Veri gocu betigi ve maskeleme karari (musteri verisi) bekliyor.
