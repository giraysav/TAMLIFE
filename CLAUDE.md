# TAMLIFE – çalışma kuralları

<!-- Copyright (c) 2026 Giray Sav. Tüm hakları saklıdır. TAMLIFE paneli - izinsiz kopyalanamaz, dağıtılamaz. -->

Kod sahibi: Giray Sav (Technical Account Manager; Fullstack Designer). Yeni dosyalara telif satırı eklenir.
Ayrıntılı mimari, kurulum ve test komutları: [README.md](README.md).

## Dil ve kimlik
- Tüm yanıtlar, mesajlar ve arayüz metinleri **Türkçe**.
- Sunucu işleri `TURKCELL\TAMLIFEADLOG` kimliğiyle yapılır. Oracle (ReportDB) giriş tetikleyicisi SYSTEM / makine hesabını
  reddeder (ORA-04088): Oracle'a bağlanan her işçi TAMLIFEADLOG servis kopyasından başlatılır, panel sürecinden değil.
- Geliştirme canlı sunucuda yapılır.

## Veri kuralları
- Alarm: ReportDB · şikayet/talep: OneDesk · envanter (CMDB): ONENT · devre trafiği: MSSQL LOE. Eşleşme Müşteri No + CI adı.
- Kullanıcı ekranlarında kaynak adı (ReportDB / OneDesk / ONENT / TEMIP) ve ham DB hatası **gösterilmez**.
- Envanterden IP, SNMP, e-posta, VAN/LAN ve kullanıcı adı **alınmaz ve gösterilmez**. MSSQL `tempcilist`ten yalnız CINAME ve RRD_ID okunur.
  Kaynağa `SELECT *` atılmaz; yalnız gereken sütunlar seçilir.
- Otomatik gelen veri için elle aktarma yolu, ölü kod, bayat parti bırakılmaz; bir alanı iki yer yazmaz.

## Arayüz (ekran-react)
- Canlı paket `ekran-react/dist` kaynaktan (`src`) ileride (18 Kasım sonrası yamalar). Kaynaktan derleme dist'i ezmemeli.
- dist JS yamasında yalnız derlenmiş CSS'te olan Tailwind sınıfları; yoksa satır içi style. Yamadan önce yedek, sonra `node --check`.
- `dist/rapor-trafik.js` gibi yardımcı betikler değişince `dist-demo/` ve `public/` kopyaları da güncellenir.

## Test, commit, yayın
- `cd backend; ..\.venv\Scripts\python -m pytest` (76) ve ayrı komutla `pytest tests_v35` (734 geçer, 110 gerekçeli atlanır).
- Paneli yeniden başlatmadan önce commit edilir.
- Push yalnız kullanıcı isteyince, tek dal, etkileşimsiz; `.env`, veritabanı ve sırlar asla gönderilmez; `--all` / `--mirror` / force yok.
