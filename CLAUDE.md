# TAMLIFE v3.5 — Claude için çalışma kuralları

Yanıtları **Türkçe**, kısa ve doğrudan ver. Karşındaki uzman sistem yöneticisi/geliştirici. Dosya okurken önce `Grep`, sonra yalnız ilgili aralık.
Bu dosya GÜNCEL kuralları tutar. 18 Kasım 2026 öncesi kararların gerekçesi `docs/kararlar.md`'de (arşiv; çelişkide bu dosya geçerli).

## Çalışma düzeni (2026-11-25 kullanıcı kararı)

- **Tek kaynak GitHub:** `github.com/giraysav/TAMLIFE`. `main` = canlıda çalışan kodun tek doğrusu. Canlıya giden her sürüm `main` üzerinde `canli-YYYYMMDD-N` etiketidir.
- **Geliştirme yalnız yerel PC'de:** `D:\TAMLIFE_Product`. İş başına `gelistirme/<konu>` dalı; testler geçince `main`'e birleştirilir, etiketlenir, `main` + etiket push edilir. Push / etiket yalnız kullanıcı onayıyla.
- **Sunucu (`E:\TAMLIFE`, https://tamlife/) yalnız deploy ve işletme:** sunucudaki oturum kod ve `ekran-react/dist` DÜZENLEMEZ, commit ATMAZ, derleme YAPMAZ. Görevi: GitHub'dan gelen etiketi kontrol edip uygulamak, durum / yeniden başlatma / veri-yetki işleri. Kod değişikliği istenirse "D:'de yapılmalı" der.
- **Canlıya alma (sunucuda, TAMLIFEADLOG ile yönetici PowerShell):**
  1. `.\kurulum\canliya_al.ps1 -Etiket canli-YYYYMMDD-N -YalnizDene` → gelen commit'ler, değişen dosyalar, paket / göç (migration) / arayüz değişikliği raporu; hiçbir şey değişmez.
  2. Raporu kullanıcıya göster, onay al.
  3. `.\kurulum\canliya_al.ps1 -Etiket canli-YYYYMMDD-N -Evet` → DB yedeği, durdur, etikete geçiş, gerekirse `pip install`, başlat (alembic panel açılışında), doğrulama (HEAD, 127.0.0.1 + https sağlık, sunulan `index.html` = git'teki dist). Doğrulanamazsa önceki sürüme kendiliğinden döner. Çıkış: 0 tamam, 10 değişiklik yok, 1 uygulanmadı, 3 geri dönüldü, 4 elle müdahale.
  - Bilerek eski sürüme dönüş: `-GeriAl`. Kayıt: `var\log\canliya_al\gecmis.csv`.
  - Betik sunucuda yalnız ileri sarar; sunucuda GitHub `main`'de olmayan commit ya da git dışı değişiklik varsa DURUR.
- **Arayüz derlemesi geliştirmede alınır** ve `ekran-react/dist` git'e girer (`git add -A ekran-react/dist`). Sunucuda Node / `npm` gerekmez. Kaynakla dist her commit'te uyumlu olmalı: `src` değiştiyse aynı commit'te `npm run build` çıktısı da olmalı.

## Ortam (D:\TAMLIFE_Product)

- Python 3.14 (`.venv`, sunucu 3.14.9). Node 24.22.1 kurulumsuz: `D:\araclar\node-v24.22.1-win-x64` (PATH'in başına ekle; sistemdeki Node 21 Vite 8 için eski).
- Backend test: `cd backend; $env:PYTHONUTF8='1'; ..\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider` · lint: `..\.venv\Scripts\python.exe -m ruff check app tests` (DTZ uyarıları bilinçli: yerel saat).
- Arayüz: `cd ekran-react; npx tsc -b; npm run lint; npx vitest run; npm run build`.
- Kırmızı testle commit / push / etiket yok.

## Sırlar ve veri

- `.env` değeri, parola, anahtar okunmaz / yazılmaz / gösterilmez; anahtar ADLARI verilebilir, değeri kullanıcı yazar. Windows parolası istenmez.
- Git'e asla: `backend/.env`, `backend/var/` (canlı DB, günlük, yedek), `backend/data/reports/` (müşteri raporları), `.venv`, `node_modules`.
- Üretimden ham veri / müşteri satırı kopyalanmaz; testler kendi geçici DB'sini kurar (`tests/conftest._canli_yollardan_izole`).
- Depo GitHub'da: iç adres / kurum bilgisi içeren yeni dosya eklerken dikkat (2026-11-25 itibarıyla depo herkese açık; private yapılması önerildi).

## Kod kuralları

- `.ps1` / `.bat` saf ASCII; PowerShell fonksiyon adı yerleşik takma adla çakışmaz (`Get-Alias <ad>` boş olmalı).
- `backend/app/db.dispose_engines` ve `session.reset_for_tests` yalnız testlerde kullanılır: "ölü kod" diye SİLME (2026-11-20'de silinip testleri kırmıştı).
- Hata sözleşmesi: servis hatası `ortak.UygulamaHatasi(kod, mesaj)`; başarı `{"status":"success","data":...}`, hata `{"detail":...}`; durum değiştiren istek `x-csrf-token` ister; yeni uç → test.
- DB: Alembic `backend/alembic` (açık `op.create_table/add_column`, idempotent, revizyon `app.models` import etmez); model değişikliği → yeni revizyon. Göçler ekleyici olmalı (canliya_al geri dönüşte şemayı geri almaz).
- Arayüz: ortak UI `src/components/sayfa-ui.tsx`, API yalnız `src/lib/sorgu.ts`, rem tabanlı ölçü (`text-[Npx]` yok), ekran metni büyük harf (`lib/buyuk-harf.ts`), iki dilli metin (`*-metin.ts`). Yeni bağımlılık eklemeden mevcut olanla çöz; kullanılmayan dosya bırakma.
- `ekran-react/public/{rapor-trafik,topo-harita,util-puanlama,veri-ozeti}.js` canlıda derlenmiş dosyaya elle eklenmiş bağımsız betiklerdi; Aşama 0'da (2026-11-25) olduğu gibi `public/`'e alındı, `index.html`'den `<script defer>` ile yüklenir. Değiştirirken bu dosyaları doğrudan düzenle; ileride TSX'e taşınabilir.
- Ayrıntılı mimari / modül kuralları: `docs/architecture.md`, `docs/kararlar.md` (18 Kasım hali; sonrası commit mesajlarında).

## Commit

- Mesaj Türkçe `tür(alan): özet` + madde listesi + `Co-Authored-By`. `--no-verify` / amend yok. Commit yalnız o işte değiştirdiğin dosyaları içerir.
