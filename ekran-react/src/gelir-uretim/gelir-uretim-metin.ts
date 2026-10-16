import { ORTAK } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

export const TURLER = ["proje", "inisiyatif"] as const
export const FAYDALAR = ["gelir", "tasarruf", "verimlilik"] as const
export const DURUMLAR = ["baslamadi", "devam", "tamamlandi", "iptal"] as const
export const PARALAR = ["TRY", "USD", "EUR"] as const
export const DONEMLER = ["ay", "yil", "tek_sefer"] as const
export type Tur = (typeof TURLER)[number]
export type Fayda = (typeof FAYDALAR)[number]
export type Durum = (typeof DURUMLAR)[number]
export type Para = (typeof PARALAR)[number]
export type Donem = (typeof DONEMLER)[number]
export const ONAYLAR = ["bekliyor", "onayli", "reddedildi"] as const
export type Onay = (typeof ONAYLAR)[number]
/** Yeni giriste zorunlu alanlar (sunucu servis.ZORUNLU ile ayni sira: kullanicinin Excel basliklari). */
export const ZORUNLU = [
  "people", "title", "status_note", "roadmap", "description", "customers", "revenue_amount", "year_revenue", "hours_per_month", "hours_per_year",
  "extra_note", "start_date", "end_date",
] as const
export type ZorunluAlan = (typeof ZORUNLU)[number]

export type Kisi = { id: number; name: string }
export type Kayit = {
  id: number
  kind: Tur
  benefit_type: Fayda
  title: string
  status: Durum
  status_note: string
  description: string
  customers: string
  revenue_amount: number | null
  revenue_currency: Para
  revenue_period: Donem
  revenue_note: string
  year_revenue: number | null
  hours_per_month: number | null
  hours_note: string
  hours_per_year: number | null
  roadmap: string
  extra_note: string
  start_date: string | null
  end_date: string | null
  other_people: string
  people: Kisi[]
  created_by: string
  created_at: string | null
  updated_by: string
  updated_at: string | null
  created_by_id: number | null
  approval: Onay
  approval_note: string
  approved_by: string
  approved_at: string | null
  /** Bos zorunlu alanlar (eski kayitlarda olabilir; yeni giriste bos kalamaz). */
  eksik: ZorunluAlan[]
}
export type Ozet = {
  is_sayisi: number
  toplam_is: number
  durum_sayilari: Record<Durum, number>
  aylik_gelir: Partial<Record<Para, number>>
  yillik_gelir: Partial<Record<Para, number>>
  tek_seferlik_gelir: Partial<Record<Para, number>>
  yil_ici_gelir: number
  aylik_saat: number
  yillik_saat: number
}
export type OnayBilgisi = { sahip: { id: number; ad: string } | null; yonetebilir: boolean; bekleyen: number; benim: number | null }
export type Liste = {
  items: Kayit[]
  ozet: Ozet
  secenekler: { personel: { id: number; ad: string }[]; yillar: number[] }
  onay: OnayBilgisi
  yazabilir: boolean
}

export const SATIR_DURUMLARI = ["yeni", "var", "tekrar", "hatali"] as const
export type SatirDurumu = (typeof SATIR_DURUMLARI)[number]
export type OnizlemeSatiri = {
  satir: number
  durum: SatirDurumu
  kind: Tur
  title: string
  status: Durum | ""
  benefit_type: Fayda | ""
  people: string[]
  other_people: string
  revenue_amount: number | null
  revenue_currency: Para
  revenue_period: Donem
  revenue_note: string
  year_revenue: number | null
  hours_per_month: number | null
  hours_per_year: number | null
  start_date: string | null
  end_date: string | null
  uyarilar: string[]
}
export type Plan = { toplam: number; yeni: number; var: number; tekrar: number; hatali: number }
export type Onizleme = { dosya: string; sayfa: string; baslik_satiri: number; plan: Plan; uyarilar: string[]; satirlar: OnizlemeSatiri[] }
export type UygulaSonucu = Plan & { eklendi: number; uyarilar: string[] }

const TR = {
  ...ORTAK.tr,
  baslik: "Gelir Faydası Sağlanan İşler",
  aciklama: "Gelir, tasarruf ya da verimlilik faydası sağlayan işler ve TAM inisiyatifleri",
  kapat: "Kapat",
  yeniKayit: "Yeni kayıt",
  excelAktar: "Excel'e aktar",
  excelIceAktar: "Excel'den içe aktar",
  // KPI
  kpiIs: "İş sayısı",
  kpiIsAlt: (devam: number, tamam: number) => `${devam} devam · ${tamam} tamamlandı`,
  kpiIsSuzulu: (toplam: number) => `${toplam} kayıttan`,
  kpiAylik: "Aylık gelir faydası",
  kpiYilIci: "Yıllık gelir faydası",
  kpiSaat: "Aylık efor kazancı",
  kpiYilSaat: (n: string) => `yıllık ${n} saat`,
  saat: "saat",
  saatAy: "saat/ay",
  tekSeferlik: "tek seferlik",
  // suzgec
  ara: "Başlık, müşteri veya kişi ara…",
  tur: "Tür",
  tumTurler: "Tüm türler",
  durum: "Durum",
  tumDurumlar: "Tüm durumlar",
  fayda: "Fayda türü",
  tumFaydalar: "Tüm faydalar",
  tam: "TAM",
  tumTam: "Tüm TAM",
  yil: "Yıl",
  tumYillar: "Tüm yıllar",
  temizle: "Temizle",
  yilIpucu: "Yıl seçilince başlangıç tarihi olmayan işler listelenmez.",
  toplamKayit: (n: number) => `${n} kayıt`,
  // listeler
  hicKayit: "Henüz kayıt yok",
  hicKayitAlt: "Yeni kayıt ekleyin ya da Excel dosyasından içe aktarın.",
  hicKayitAltOkur: "Henüz bir kayıt eklenmedi.",
  sonucYok: "Sonuç bulunamadı",
  sonucYokAlt: "Aramayı ya da filtreleri değiştirmeyi deneyin.",
  devamEdiyor: "devam ediyor",
  tarihYok: "Tarih yok",
  yilIciKisa: "Yıllık",
  tutarYok: "Tutar yok",
  // enumlar
  tur_: { proje: "Proje", inisiyatif: "TAM inisiyatifi" } satisfies Record<Tur, string>,
  fayda_: { gelir: "Gelir", tasarruf: "Tasarruf", verimlilik: "Verimlilik" } satisfies Record<Fayda, string>,
  durum_: { baslamadi: "Başlamadı", devam: "Devam ediyor", tamamlandi: "Tamamlandı", iptal: "İptal" } satisfies Record<Durum, string>,
  para_: { TRY: "TL (₺)", USD: "USD ($)", EUR: "EUR (€)" } satisfies Record<Para, string>,
  donem_: { ay: "Aylık", yil: "Yıllık", tek_sefer: "Tek seferlik" } satisfies Record<Donem, string>,
  donemKisa: { ay: "/ ay", yil: "/ yıl", tek_sefer: "tek sefer" } satisfies Record<Donem, string>,
  suzgecler: "Filtreler",
  // ayrinti
  detayBaslik: "İş ayrıntısı",
  grupGenel: "Genel bilgiler",
  grupKayit: "Kayıt bilgisi",
  guncelDurum: "Güncel durum",
  aciklamaAlani: "Detaylı açıklama",
  musteriler: "Etkilenen müşteriler",
  tamKisiler: "İlgili TAM",
  digerKisiler: "Diğer kişiler",
  gelirBilgisi: "Gelir faydası",
  tutar: "Tutar",
  tutarNotu: "Tutar notu",
  yilIci: "Yıllık gelir faydası (TL/12 ay)",
  verimlilikBilgisi: "Verimlilik faydası",
  aylikSaat: "Aylık efor kazancı",
  yillikSaat: "Yıllık efor kazancı",
  yolHaritasi: "Yol haritası",
  eforNotu: "Efor notu",
  ekAciklama: "Ek açıklamalar",
  baslangic: "Başlangıç tarihi",
  bitis: "Bitiş tarihi",
  olusturan: "Oluşturan",
  guncelleyen: "Son güncelleyen",
  yok: "—",
  // form
  formYeni: "Yeni kayıt",
  formDuzenle: "Kaydı düzenle",
  formAciklama: "Yıldızlı alanların hepsi zorunlu (Excel başlıkları). Fayda yoksa sayı alanlarına 0 yazın; açıklamayı not alanlarına ekleyin.",
  formOnayNotu: "Kaydettiğinizde iş modül sahibinin onayına gider; onaylanınca listeye, toplamlara ve çeyrek sunuma girer.",
  baslikAlani: "İşin özeti",
  baslikZorunlu: "Başlık zorunlu.",
  zorunluEksik: (alanlar: string) => `Zorunlu alanlar boş: ${alanlar}.`,
  yolAlani: "Yol haritası",
  yilSaatAlani: "Yıllık efor kazancı (saat/12 ay)",
  durumNotu: "Güncel durum notu",
  musterilerAlani: "Etkilenen müşteriler",
  gelirTutari: "Gelir tutarı",
  paraBirimi: "Para birimi",
  donem: "Dönem",
  yilIciAlani: "Yıllık gelir faydası (TL/12 ay)",
  eforAlani: "Aylık efor kazancı (saat/ay)",
  ekAlani: "Ek açıklamalar",
  baslangicAlani: "Başlangıç tarihi",
  bitisAlani: "Bitiş tarihi",
  bitisIpucu: "Süren işte planlanan bitiş tarihini yazın.",
  sayiIpucu: "Binlik ayracı olmadan yazın, ondalık için virgül ya da nokta (ör. 1250,75).",
  sayiHata: (alan: string) => `${alan}: sıfır ya da pozitif bir sayı girin (ör. 1250,75).`,
  tarihHata: "Bitiş tarihi başlangıçtan önce olamaz.",
  personel: "İlgili TAM (panel kullanıcıları)",
  personelIpucu: "Yalnızca etkin TAM personeli seçilebilir.",
  personelYok: "Seçilebilir personel yok.",
  pasif: "(pasif)",
  digerAlani: "Diğer kişiler",
  digerIpucu: "Panelde hesabı olmayanların adları.",
  kaydedilemedi: "Kaydedilemedi.",
  silinemedi: "Silinemedi.",
  silOnay: (b: string) => `“${b}” kaydı silinsin mi?`,
  // ice aktarma
  iceBaslik: "Excel'den içe aktar",
  iceAciklama: "Kaynak tablo biçimindeki .xlsx dosyası okunur; önce önizleme gösterilir, onaylayınca yalnızca yeni satırlar eklenir.",
  dosyaSec: "Excel dosyası seç (.xlsx)",
  dosyaKural: "En fazla 5 MB ve 500 satır. Sütunlar başlıklarına göre bulunur; yalnızca ‘İşin özeti’ zorunludur. Aynı tür ve başlıktaki kayıtlar yeniden eklenmez. İçe aktarılan işler onaylı eklenir.",
  dosyaBuyuk: "Dosya çok büyük (en fazla 5 MB).",
  okunuyor: "Dosya okunuyor…",
  okunamadi: "Dosya okunamadı.",
  onizleme: "Önizleme",
  planSuz: "Satırları sonuca göre süz",
  satirlar: "Önizleme satırları",
  onizlemeDosya: (d: string, s: string) => `${d} · sayfa: ${s}`,
  planToplam: "Satır",
  planYeni: "Yeni",
  planVar: "Zaten var",
  planTekrar: "Dosyada tekrar",
  planHatali: "Hatalı",
  genelUyarilar: "Genel uyarılar",
  kolSatir: "Satır",
  kolDurum: "Sonuç",
  kolTur: "Tür",
  kolBaslik: "Başlık",
  kolTam: "TAM",
  kolTutar: "Tutar",
  kolTarih: "Tarih",
  kolUyari: "Uyarı",
  satirDurum_: { yeni: "Yeni", var: "Zaten var", tekrar: "Dosyada tekrar", hatali: "Hatalı" } satisfies Record<(typeof SATIR_DURUMLARI)[number], string>,
  uygula: (n: number) => `${n} yeni kaydı ekle`,
  uygulaniyor: "Ekleniyor…",
  hicYeni: "Eklenecek yeni satır yok.",
  eklendi: (n: number) => `${n} kayıt eklendi.`,
  eklendiAlt: (atlanan: number) => (atlanan > 0 ? `${atlanan} satır eklenmedi (zaten var, tekrar ya da hatalı).` : ""),
  baskaDosya: "Başka dosya seç",
  eklenemedi: "İçe aktarma tamamlanamadı.",
  // onay akisi
  onay: "Onay",
  onay_: { bekliyor: "Onay bekliyor", onayli: "Onaylı", reddedildi: "Reddedildi" } satisfies Record<Onay, string>,
  tumOnaylar: "Tüm onay durumları",
  bekleyenVar: (n: number) => `${n} iş onayınızı bekliyor.`,
  bekleyenleriGoster: "Bekleyenleri göster",
  sahip: "Modül sahibi",
  sahipYok: "Atanmadı (onayı admin verir)",
  sahipAta: "Modül sahibini seç",
  sahipIpucu: "Personelin girdiği yeni işler bu kişinin onayına düşer. Admin her zaman onaylayabilir.",
  sahipKaydedilemedi: "Modül sahibi kaydedilemedi.",
  onaylaDugme: "Onayla, canlıya al",
  reddetDugme: "Reddet",
  geriAlDugme: "Onayı geri al",
  retGerekce: "Ret gerekçesi (giren kişi görür):",
  onayIslemHata: "Onay işlemi yapılamadı.",
  onayGrup: "Onay durumu",
  onaylayan: "Onaylayan",
  reddeden: "Reddeden",
  retNotu: "Ret gerekçesi",
  bekliyorAlt: "Modül sahibi kontrol edip onaylayınca canlıya alınır.",
  reddedildiAlt: "Düzeltip kaydettiğinizde yeniden onaya gider.",
  eksikBilgi: (n: number) => `${n} zorunlu alan boş`,
  // rapor
  rapor: "Rapor",
  excelRapor: "Excel rapor",
  pdfRapor: "PDF rapor",
  pdfHazirlaniyor: "PDF hazırlanıyor…",
  pdfHata: "PDF oluşturulamadı.",
  raporBaslik: "Gelir Faydası Sağlanan İşler Raporu",
  raporKapsam: (n: number) => `Onaylı işler · ${n} kayıt`,
  raporTarihi: (z: string) => `Rapor tarihi: ${z}`,
  raporFiltre: (f: string) => `Filtre: ${f}`,
  raporIpucu: "Rapor ekrandaki filtrelere uyan onaylı işleri kapsar.",
}

const EN: typeof TR = {
  ...ORTAK.en,
  baslik: "Revenue-Benefit Work",
  aciklama: "Work and TAM initiatives that delivered revenue, savings or efficiency benefit",
  kapat: "Close",
  yeniKayit: "New record",
  excelAktar: "Export to Excel",
  excelIceAktar: "Import from Excel",
  kpiIs: "Work items",
  kpiIsAlt: (devam, tamam) => `${devam} ongoing · ${tamam} completed`,
  kpiIsSuzulu: (toplam) => `of ${toplam} records`,
  kpiAylik: "Monthly revenue benefit",
  kpiYilIci: "Yearly revenue benefit",
  kpiSaat: "Monthly effort saved",
  kpiYilSaat: (n) => `${n} hours a year`,
  saat: "hours",
  saatAy: "hours/month",
  tekSeferlik: "one-time",
  ara: "Search title, customer or person…",
  tur: "Type",
  tumTurler: "All types",
  durum: "Status",
  tumDurumlar: "All statuses",
  fayda: "Benefit type",
  tumFaydalar: "All benefits",
  tam: "TAM",
  tumTam: "All TAM",
  yil: "Year",
  tumYillar: "All years",
  temizle: "Clear",
  yilIpucu: "When a year is selected, work without a start date is not listed.",
  toplamKayit: (n) => `${n} records`,
  hicKayit: "No records yet",
  hicKayitAlt: "Add a record or import an Excel file.",
  hicKayitAltOkur: "No record has been added yet.",
  sonucYok: "No results",
  sonucYokAlt: "Try changing the search or the filters.",
  devamEdiyor: "ongoing",
  tarihYok: "No date",
  yilIciKisa: "Yearly",
  tutarYok: "No amount",
  tur_: { proje: "Project", inisiyatif: "TAM initiative" },
  fayda_: { gelir: "Revenue", tasarruf: "Savings", verimlilik: "Efficiency" },
  durum_: { baslamadi: "Not started", devam: "In progress", tamamlandi: "Completed", iptal: "Cancelled" },
  para_: { TRY: "TRY (₺)", USD: "USD ($)", EUR: "EUR (€)" },
  donem_: { ay: "Monthly", yil: "Yearly", tek_sefer: "One-time" },
  donemKisa: { ay: "/ month", yil: "/ year", tek_sefer: "one-time" },
  suzgecler: "Filters",
  detayBaslik: "Work details",
  grupGenel: "General information",
  grupKayit: "Record information",
  guncelDurum: "Current status",
  aciklamaAlani: "Description",
  musteriler: "Affected customers",
  tamKisiler: "Responsible TAM",
  digerKisiler: "Other people",
  gelirBilgisi: "Revenue benefit",
  tutar: "Amount",
  tutarNotu: "Amount note",
  yilIci: "Yearly revenue benefit (TRY/12 months)",
  verimlilikBilgisi: "Efficiency benefit",
  aylikSaat: "Monthly effort saved",
  yillikSaat: "Yearly effort saved",
  yolHaritasi: "Roadmap",
  eforNotu: "Effort note",
  ekAciklama: "Additional notes",
  baslangic: "Start date",
  bitis: "End date",
  olusturan: "Created by",
  guncelleyen: "Last updated by",
  yok: "—",
  formYeni: "New record",
  formDuzenle: "Edit record",
  formAciklama: "All starred fields are required (the Excel headers). Enter 0 in number fields when there is no benefit and explain in the notes.",
  formOnayNotu: "When you save, the work goes to the module owner for approval; once approved it appears in the list, the totals and the quarterly presentation.",
  baslikAlani: "Work summary",
  baslikZorunlu: "Title is required.",
  zorunluEksik: (alanlar) => `Required fields are empty: ${alanlar}.`,
  yolAlani: "Roadmap",
  yilSaatAlani: "Yearly effort saved (hours/12 months)",
  durumNotu: "Current status note",
  musterilerAlani: "Affected customers",
  gelirTutari: "Revenue amount",
  paraBirimi: "Currency",
  donem: "Period",
  yilIciAlani: "Yearly revenue benefit (TRY/12 months)",
  eforAlani: "Monthly effort saved (hours/month)",
  ekAlani: "Additional notes",
  baslangicAlani: "Start date",
  bitisAlani: "End date",
  bitisIpucu: "For ongoing work enter the planned end date.",
  sayiIpucu: "Write without a thousands separator; use a comma or a dot for decimals (e.g. 1250.75).",
  sayiHata: (alan) => `${alan}: enter zero or a positive number (e.g. 1250.75).`,
  tarihHata: "The end date cannot be before the start date.",
  personel: "Responsible TAM (panel users)",
  personelIpucu: "Only active TAM staff can be selected.",
  personelYok: "No staff to select.",
  pasif: "(inactive)",
  digerAlani: "Other people",
  digerIpucu: "Names of people without a panel account.",
  kaydedilemedi: "Could not save.",
  silinemedi: "Could not delete.",
  silOnay: (b) => `Delete the record “${b}”?`,
  iceBaslik: "Import from Excel",
  iceAciklama: "An .xlsx file in the source table layout is read; a preview is shown first and only new rows are added once you confirm.",
  dosyaSec: "Choose Excel file (.xlsx)",
  dosyaKural: "At most 5 MB and 500 rows. Columns are found by their headers; only ‘İşin özeti’ (work summary) is required. Records with the same type and title are not added again. Imported work is added as approved.",
  dosyaBuyuk: "The file is too large (max 5 MB).",
  okunuyor: "Reading file…",
  okunamadi: "The file could not be read.",
  onizleme: "Preview",
  planSuz: "Filter rows by result",
  satirlar: "Preview rows",
  onizlemeDosya: (d, s) => `${d} · sheet: ${s}`,
  planToplam: "Rows",
  planYeni: "New",
  planVar: "Already exists",
  planTekrar: "Repeated in file",
  planHatali: "Invalid",
  genelUyarilar: "General warnings",
  kolSatir: "Row",
  kolDurum: "Result",
  kolTur: "Type",
  kolBaslik: "Title",
  kolTam: "TAM",
  kolTutar: "Amount",
  kolTarih: "Date",
  kolUyari: "Warning",
  satirDurum_: { yeni: "New", var: "Already exists", tekrar: "Repeated in file", hatali: "Invalid" },
  uygula: (n) => `Add ${n} new records`,
  uygulaniyor: "Adding…",
  hicYeni: "There are no new rows to add.",
  eklendi: (n) => `${n} records added.`,
  eklendiAlt: (atlanan) => (atlanan > 0 ? `${atlanan} rows were not added (already exist, repeated or invalid).` : ""),
  baskaDosya: "Choose another file",
  eklenemedi: "The import could not be completed.",
  onay: "Approval",
  onay_: { bekliyor: "Awaiting approval", onayli: "Approved", reddedildi: "Rejected" },
  tumOnaylar: "All approval states",
  bekleyenVar: (n) => `${n} items are waiting for your approval.`,
  bekleyenleriGoster: "Show pending",
  sahip: "Module owner",
  sahipYok: "Not assigned (an admin approves)",
  sahipAta: "Choose the module owner",
  sahipIpucu: "New work entered by staff goes to this person for approval. An admin can always approve.",
  sahipKaydedilemedi: "The module owner could not be saved.",
  onaylaDugme: "Approve and publish",
  reddetDugme: "Reject",
  geriAlDugme: "Withdraw approval",
  retGerekce: "Reason for rejecting (the person who entered it sees this):",
  onayIslemHata: "The approval action failed.",
  onayGrup: "Approval status",
  onaylayan: "Approved by",
  reddeden: "Rejected by",
  retNotu: "Reason for rejecting",
  bekliyorAlt: "It goes live once the module owner checks and approves it.",
  reddedildiAlt: "Correct it and save to send it for approval again.",
  eksikBilgi: (n) => `${n} required fields empty`,
  rapor: "Report",
  excelRapor: "Excel report",
  pdfRapor: "PDF report",
  pdfHazirlaniyor: "Preparing PDF…",
  pdfHata: "The PDF could not be created.",
  raporBaslik: "Revenue-Benefit Work Report",
  raporKapsam: (n) => `Approved work · ${n} records`,
  raporTarihi: (z) => `Report date: ${z}`,
  raporFiltre: (f) => `Filter: ${f}`,
  raporIpucu: "The report covers the approved work matching the filters on screen.",
}

export const gelirUretimMetin = (dil: Dil) => (dil === "en" ? EN : TR)
