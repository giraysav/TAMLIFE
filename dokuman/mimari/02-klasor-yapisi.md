# 02 ? Klasor yapisi

Bu agac hedeftir. Diskte olusturulmaz (`10-iskelet-onerisi.md` yalniz ornek metindir). Mevcut `backend/`, `backend-api/`, `ekran-react/` dosyalari yeniden adlandirilmaz.

## Kararlar

- Yeni kod dosya adlari Ingilizcedir: `models.py`, `schemas.py`, `service.py`, `routes.py`, `summary.py`, `catalog.py`, `gateway.py`, `contracts.py`.
- Modul klasor adi, katalog anahtariyla aynidir (`ekip`, `musteri`). UI'daki kisa id (`ozet`, `sms`) klasor adi degildir; esleme `04-modul-esleme.md`.
- Bir modulun SQL'i yalniz kendi `models.py` + `service.py` icindedir.
- Test, modulun yaninda degil `backend/tests/` altindadir. Arayuz testi `ekran-react` icindedir.

## Acik sorular

- `backend-api/` bugun yalniz `.venv`, `_api.log`, `_api-hata.log` icerir. `backend-api/app.py` yok. Klasor hedef agacta yoktur; silinmesi bu belgenin isi degil.
- `instance/sirket.db` v3.5 kokunde durur (`users` tablosu, 0 satir). Hedef agacta `instance/` yok. Tasima `05`.
- Prod `frontend/` (ayri Vite) v3.5 `ekran-react` ile ayni agac degil. Hedef yalniz `ekran-react`.

## Bugun duranlar (dogrulandi)

v3.5 kok: `.pytest_cache`, `.venv`, `backend`, `backend-api`, `dokuman`, `ekran-react`, `instance`, `veri`.

`backend/` icinde yalniz `api.py`, `ayar.json`, `depo.py`. Su yollar yok: `backend/app/moduller/katalog.py`, `backend/app/cekirdek/sozlesme.py`, `backend/app/veri/kapi.py`.

`ekran-react/src`: `App.tsx`, `App.css`, `index.css`, `main.tsx`, `assets/`, `components/ui/` (Radix sarmalayicilar, `app-1.tsx`, `admin-veri.tsx`, `veri-agaci.tsx`), `lib/api.ts`, `lib/api-tipler.ts`, `lib/utils.ts`. `components.json` yok. TanStack, Zod, React Hook Form, Vitest, Playwright yok (`package.json`).

Prod kod kokte `D:\Project\TAM_Life\TAMLIFE`: `backend/app`, `frontend`, `isletim`, `tests`, `server.py`, `dokuman`. Okuma kaynagidir; v3.5 agacina kopyalanmaz.

## Hedef backend

```
backend/
  pyproject.toml          # ruff, mypy, pytest, import-linter
  alembic.ini
  alembic/versions/       # sema; veri kopyasi degil
  app/
    __init__.py
    main.py               # FastAPI(), router include, health
    core/
      __init__.py
      config.py           # ortam ADLARI; deger yok, .env okunmaz repoda
      errors.py           # hata modeli
      session.py          # cerez, bosluk zaman asimi
      authz.py            # rol + modul kapisi
      audit.py            # denetim yazimi
      rate_limit.py
    data/
      __init__.py
      base.py             # DeclarativeBase
      gateway.py          # engine, session factory, WAL
      migrate.py          # salt okunur kaynak, sayim kontrolu
    adapters/
      __init__.py
      ad_fake.py
      oracle_fake.py
    modules/
      __init__.py
      catalog.py          # modul bayraklari tek kaynak
      contracts.py        # moduller arasi cagri tipleri
      musteri/ models.py schemas.py service.py routes.py summary.py __init__.py
      takvim/  ... ayni bes dosya
      onedesk/ ...
      utilizasyon/ ...
      roller/ ...
      talep/ ...
      ekip/ ...
      rapor/ ...
      proje/ ...
      tamsms/ ...
      tamapn/ ...
      gelir_uretim/ ...
      toptan/ ...
      sunum/ ...
      radar/ ...
      baglantili/ ...
      topoloji/ ...       # katalog karari acik; klasor karar belgesine kadar bos iskelet
  tests/
    conftest.py
    test_import_boundaries.py
    test_health.py
    modules/              # modul basina service testi
```

Her modul klasorunde bes dosya zorunludur (`03`). Icerik bos olabilir; baska adla is dosyasi konulmaz (`helpers.py`, `utils.py` modul icinde yasak).

## Klasor isi ve yasak

| Yol | Isi | Ait degil |
|---|---|---|
| `app/main.py` | Uygulama nesnesi, router baglama, lifespan | Modul SQL'i, rol listesi kopyasi |
| `app/core` | Oturum, hata, denetim, limit | Musteri/skor/takvim kurali |
| `app/data` | Baglanti, Alembic tabani, tasima betigi | Satir icerigini loglamak |
| `app/adapters` | Sahte dis sistem | Gercek host, gercek kimlik bilgisi, `oracledb` cagrisi |
| `app/modules/catalog.py` | Anahtar, ad, tur, bayrak | Tablo |
| `app/modules/contracts.py` | Ozet fonksiyon imzalari | Uygulama govdesi |
| `app/modules/<id>` | O modulun model/sema/servis/yol/ozet | Baska modulun `models.py` importu (yalniz `summary`) |
| `alembic/` | Sema revizyonu | Yedek zip, musteri satiri |
| `tests/` | pytest | Uretim veritabani yolu |

`ayar.json` hedefte yoktur. Icerigi bu belgelere yazilmaz. Anahtar adlari (dogrulandi, deger yok): `yerel_admin`, `dev_admin`, `ad`, `sertifika`, `baglantilar`. Bunlar ortam veya gizli depoya gider; sema `06`.

## Hedef ekran-react

Mevcut `src/components/ui/*` durur. Yeni sayfalar `src/modules` altina eklenir; `app-1.tsx` icine modul is kurali yazilmaz.

```
ekran-react/
  index.html
  vite.config.ts          # alias "@" -> src (bugun var)
  tsconfig.json           # strict (hedef; bugunku strict bayragi bu belgede dogrulanmadi)
  package.json
  src/
    main.tsx              # QueryClient, Router
    index.css             # token; bugunku :root degiskenleri 08'de
    app/
      router.tsx          # TanStack Router
      providers.tsx
    shell/
      layout.tsx          # sidebar + ust cubuk
      nav.tsx             # katalog sirasi
    modules/
      <modul_id>/
        page.tsx
        table.tsx         # varsa
        form.tsx          # varsa
        api.ts            # yalniz o modulun /api/v1 cagrilari
    shared/
      ui/                 # mevcut components/ui buraya TASINMAZ; yeni sarmalayici
      data-table.tsx
      empty.tsx
      loading.tsx
      error.tsx
      form.tsx
    lib/
      api.ts              # taban URL, credentials include
      api-types.ts        # openapi-typescript ciktisi
      i18n/
        tr.ts
        en.ts
    test/
      setup.ts
```

## Ne zaman hangi dosya

Sira `OZET.md` ile aynidir. Klasor, is kurali yazilmadan once acilir. Bir modul sayfasi, o modulun `routes.py` OpenAPI'ye dustukten sonra `api-types.ts` uretilerek baglanir. El ile cift tip yazilmaz: `package.json` icinde `api:uret` bugun `openapi-typescript` cagirir ama uretici FastAPI ucu yoktur.

Prod `frontend/` ve `backend/app/kutucuklar/<ad>/servis.py` + `ozet.py` hedef adlar degildir. Karsilik: `service.py` ve `summary.py`. `portfoy` klasoru hedefte `musteri` olur (`04`). `ictapn` klasoru `tamsms` olur; `tamapn` ayri klasordur cunku prod katalogda ayri anahtardir.

## Prod kutucuk dosyalari (okuma kaynagi)

Yol koku `backend/app/kutucuklar/`. Bayt, 2026-10-03 liste. Hedef ad sagda. `register` hepsinde `return None`.

| Prod | Bayt | Hedef |
|---|---|---|
| registry.py | 6056 | modules/catalog.py |
| ekip/ozet.py, servis.py | 1243, 14281 | ekip/summary.py, service.py |
| sunum/ozet.py, servis.py | 351, 3118 | sunum |
| radar/ozet.py, servis.py | 1253, 2018 | radar |
| portfoy/ozet.py, servis.py, urun_tutar.py, kart/servis.py, kart/duzenleme.py | 359, 6072, 11927, 10121, 8879 | musteri |
| utilizasyon/ozet, servis, skor_motoru, toplu_atama, veri_kaynaklari, kaynak_secimi | 1288, 7333, 12070, 10585, 12505, 7515 | utilizasyon |
| takvim/ozet.py, servis.py | 1258, 6278 | takvim + takvim_ozet summary |
| rapor/ozet.py, servis.py, aylik.py | 1269, 10792, 10388 | rapor |
| proje/ozet.py, servis.py, musteri_calisma.py | 1253, 3851, 2618 | proje |
| onedesk/ozet.py, servis.py, incidents.py | 1251, 2057, 352 | onedesk |
| ictapn/ozet.py, servis.py | 1254, 3528 | tamsms (tamapn ayri, dosya yok) |
| baglantili/ozet.py, servis.py | 161, 48 | baglantili, durum stub |
| talep/ozet.py, servis.py | 355, 7727 | talep |
| topoloji/ozet.py, servis.py, engine.py | 358, 2952, 12194 | topoloji, menu karari acik |
| veri/db_al, db_kaynak, ham_depo, hedefler, ice_al, kaynaklar, kurallar | 2354, 8166, 21287, 2063, 1726, 6545, 16537 | utilizasyon veri; katalog anahtari yok |
| _cekirdek/ortak.py, rapor_cikti.py, yonetim.py | 965, 5442, 1514 | core ve rapor |

Bu dosyalar v3.5'e kopyalanmaz. Yeni iskelet bos `NotImplementedError` ile acilir (`10`).
