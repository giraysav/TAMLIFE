# Aylık rapor e-posta gönderimi

Durum (2026-10-31): **panel ileti göndermez.** SMTP kipi (TAMLIFE@turkcell.com.tr tek kutudan sunucu gönderimi, 2026-10-22'de
hazırlanmış, canlıda hiç açılmamıştı) kullanıcı kararıyla kaldırıldı: `rapor/smtp_gonderim.py`, `RAPOR_GONDERIM_KIPI`,
`SMTP_*` ayarları, Yönetim › Kurum Bağlantıları e-posta testi ve sağlık denetimindeki SMTP adımı yok.

## Akış

1. Personel "Raporu gönder" → onay penceresi.
2. `rapor/servis.gonder`: alıcılar doğrulanır; PDF + o dönemin SLA Excel'i + personelin eklediği dosyalarla ileti
   `rapor/eposta.eml` ile kurulur. Başlıkta **From yazılmaz** (Outlook taslağı personelin kendi hesabından açar), `X-Unsent: 1` var.
3. Tek DB işleminde `Report` + `ReportDispatch` yazılır; ayda-tek kilidi (kısmi benzersiz indeks) her dönem için ayrı uygulanır.
4. `.eml` tarayıcıya iner; personel Outlook'ta açıp kontrol eder ve Gönder'e kendisi basar.

Beklenmeyen hata (5xx) admin'e TL-RAP-01 arıza kaydı + üst çubuk bildirimi olarak düşer (`rs.gonderim_hatasi_bildir`).

## Rapor dönemi

Varsayılan dönem önceki aydır (Ekim'de Eylül raporu). 2026-10-31'den beri içinde bulunulan ay da seçilebilir
(`?donem=YYYY-MM`, `rs.secilebilir_donemler`); daha eski aylar kapalıdır. İçinde bulunulan ay seçiliyken ekranda
"ay henüz bitmedi" uyarısı çıkar.
