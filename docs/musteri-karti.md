# Müşteri Yönetimi: müşteri kartı ve aylık rapor (üretimden uyarlama)

Kaynak (yalnız okundu): `kutucuklar/portfoy/{servis.py,kart/servis.py,kart/duzenleme.py}`, `kutucuklar/rapor/{servis.py,aylik.py}`, `blueprints/customer_bp.py`, `moduller.py`, `models.py`, `sla_deposu.py`. Müşteri verisi taşınmadı; yalnız şema, kural ve ekran uyarlandı. Veri geçişi en son faz.

## Tablo eşlemesi (alembic 0004)

| v3.5 | Üretim | Fark |
|---|---|---|
| `customer` (+ alanlar) | `customers` | `user_id`→`owner_id`, `parent_customer_id`→`parent_id`, `envanter_count`→`inventory_count`, `sikayet_*`→`complaint_*`, `talep_*`→`request_*`, `ft_hacim`→`ft_volume`; tutarlar üretimdeki gibi metin (`0,00 ₺`). `pinned_entries` JSON'unda duran **NCST** ve **ayrı rapor** artık gerçek sütun (`ncst`, `separate_report`). `sub_customers` JSON kaldı yok: iştirak `parent_id` ile. |
| `customer_team` | `destech_contacts` | Üretimde **ünvan metniyle** bağlıydı (ünvan değişince bağ kopmasın diye yeniden adlandırma kodu vardı). Burada müşteri kimliği. |
| `matrix_config` (destech/ci/raci) | `matrix_configs` | `data_json` → `headers` + `rows` JSON. Müşteriye hâlâ ünvan eşleşmesiyle bağlanır (Excel'den geldiği için kimlik yok). |
| `sms_revenue`, `apn_revenue` | `ict_revenues`, `apn_revenues` | Alanlar üretimle aynı; müşteriye ünvan eşleşmesi. |
| `report` | `reports` | Alan adları birebir. `sun_success_text`… anlamları üretim kodunda yorumlanmadı (dogrulanmadi). |
| `report_draft` | `analiz.db rapor_taslak` | (müşteri, yıl, ay) başına tek taslak. |
| `report_dispatch` | `analiz.db rapor_gonderim` | `durum`→`status` (`sent`/`reverted`), ayda tek gönderim kısmi benzersiz indeks. |
| `report_recipient` | `rapor_alicilari` | `kime/bilgi` → `to_addrs/cc_addrs`, `;` ile ayrılmış. |
| *(yok)* | `internal_scraped_data`, `daily_tasks` | Kazıma ve günlük görev bu sürümde yok. |

## Kurallar (üretimden)
- **Kapsam:** admin ve Manager tüm müşterileri; Member yalnız kendi müşterisi ve kendi çatısının iştirakini görür. Görünmeyen müşteri 404 verir (varlığı sızdırılmaz).
- **Eylemler:** ekle/düzenle/ekip-iletişim Müşteri Yönetimi'ni görene açık (Member başkası adına ya da başkasının çatısı altına ekleyemez); sil, sorumlu TAM devri ve final skor yetkisi yalnız admin/Manager. Aylık rapor geri alma yalnız admin.
- **Kimlik:** ünvan benzersiz (büyük/küçük harf ve boşluk farkı yok sayılır, 409); segment `SMB/SA/MA/PA/WHOLESALE` (eski değer yalnız müşterinin mevcut değeriyse korunur); ünvan değişince gelirler ve Destech/CI/RACI satırları yeni ünvana taşınır.
- **Ekip ve iletişim:** e-posta ve GSM biçimi doğrulanır; boş değer alanı temizler.
- **Kart bölümleri:** kimlik, operasyon özeti (kendisi / iştirak dahil), ekip (Destech), iletişim, kritik CI, raporlar (**Gönderilen Aylık Rapor** modülü verilmişse), gelirler (**ICT Sms & Gelir** / **APN Gelir ve Kurulum** modülleri verilmişse), izleme (Cacti adresleri).
- **Rapor birimi:** çatı müşteri; iştirak yalnız "ayrı aylık rapor" seçilmişse. Çatıya dahil iştirak için hazırlanan rapor çatının sayılır.
- **Aylık rapor (karttan):** taslak bu ay için (UTC) hazır tr/en metinlerle gelir; alıcılar bir kez girilir; gönderim **onaylı** ve ayda **tek**, ikinci gönderim 409 (kilit), gönderilmiş ayın taslağı değişmez; PDF isteğe bağlı (≤30 MB, `%PDF` imzası) `data/reports/<yıl>/<ay>` altına arşivlenir; yalnız admin geri alabilir (rapor kaydı silinir, sayaç azalır, gönderim `reverted` olarak kalır).

## Uçlar
`/api/v1/musteri` (liste, ekle), `/musteri/{id}` (kart), `.../kimlik`, `.../iletisim`, `.../sorumlu`, `DELETE`, `.../ayri-rapor`, `.../rapor/{taslak,alicilar,gonder,gecmis}`, `/rapor/gonderim/{id}/geri-al`, `/rapor/{gonderilenler,durum}`.

## Yapılmayan / dogrulanmadi
- Outlook taslağı (`.eml`) ve mail HTML şablonu üretimi (gönderim kaydı + kilit var).
- `rapor_ceviri` (otomatik çeviri) ve toplu aylık rapor temizliği (`aylik_rapor_kaydi_sil`, `gecmisi_temizle`).
- Excel ile müşteri/matris/gelir yükleme, Cacti kazıma.
- `report` metin alanlarının taslak alanlarıyla eşlemesi.
- Ayın sınırı UTC'dir (üretimle aynı); Türkiye saatiyle ay başı/sonu farkı doğrulanmadı.

## Ekran düzeni (eski panele uygun)
Eski panelin kart dili (`musteri_karti.js`, `customer_detail.html`) kullanıldı; renkler `index.css` içinde `tl-*` (mavi `#0055A5`, lacivert `#002855`, sarı `#FFC72C`, aksan `#00A3E0`).
- **Müşteri kartı:** lacivert kimlik kartı (sarı sol vurgu, segment/sektör/iştirak rozetleri, Düzenle, **Aylık Rapor** ve **Final skor** kutuları, 3 sütunlu bilgi satırları, iştirak çipleri); sağda küçük işlemler (iştirak ekle, sil); katlanır, sarı vurgulu başlıklı bölümler (açık/kapalı durumu tarayıcıda hatırlanır): Ekip & İletişim (Satış ekibi, TAC, Çözüm KMT, Mobil KMT), sol 2/3'te Operasyon (alarm/şikayet/talep kutuları, yıl içi kapanan), Ekip (Destech) ve Kritik CI tabloları (lacivert başlık); sağ 1/3'te Raporlar, Gelirler, İzleme.
- **Aylık rapor:** `#/musteri?m=<id>&sekme=rapor`. Sol 2/3: "Operasyonel Rapor İçeriği Girişi" (gönderildi bandı, İngilizce rapor, Taslağı kaydet / Raporu gönder, e-posta gövde bloğu, renkli etiketli beş alan); sağ 1/3: Rapor Geçmişi ve Rapor Alıcıları.
