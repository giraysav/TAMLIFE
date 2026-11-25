import { ORTAK } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

const TR = {
  ...ORTAK.tr,
  baslik: "Müşteri Yönetimi",
  aciklama: "Kurumsal müşteri portföyü ve operasyonel analiz konsolu",
  musteriEkle: "Müşteri ekle",
  ara: "Müşteri veya iştirak ara…",
  tumu: "Tümü",
  segment: "Segment",
  tam: "TAM",
  tumTam: "Tüm personel",
  temizle: "Filtreleri temizle",
  kpiCati: "Çatı müşteri",
  kpiIstirak: "İştirak",
  kpiAlarm: "Açık alarm",
  kpiSikayet: "Açık şikayet",
  kpiTalep: "Açık talep",
  kpiSkor: "Ortalama final skor",
  kpiSkorAlt: (n: number) => `${n} müşteri skorlu`,
  acikKayitlar: "Açık kayıtlar",
  onedeskKayitlar: "Kayıtlar",
  acikKapanan: "açık / yıl içi kapanan",
  alarm: "Alarm",
  sikayet: "Şikayet",
  talep: "Talep",
  istirak: "iştirak",
  skor: "Final skor",
  skorYok: "Skor yok",
  kartiAc: "Müşteri kartını aç",
  sonucYok: "Aramaya uyan müşteri yok.",
  sonucYokAlt: "Filtreleri değiştirmeyi ya da yeni müşteri eklemeyi deneyin.",
  hicMusteri: "Henüz müşteri yok",
  hicMusteriAlt: "İlk müşteriyi ekleyerek portföyü oluşturun.",
  yuklenemedi: "Müşteri portföyü yüklenemedi.",
  toplam: (n: number) => `${n} müşteri`,
  sayfa: (s: number, t: number) => `Sayfa ${s} / ${t}`,
  sayfalama: "Sayfalama",
  // form
  formBaslik: "Yeni müşteri",
  formAciklama: "Ana müşteri ya da bir çatı müşterinin iştiraki ekleyin.",
  tur: "Tür",
  turAna: "Ana müşteri",
  turIstirak: "İştirak",
  cati: "Çatı müşteri",
  catiSec: "Çatı müşteri seçin",
  catiYok: "Eklenebilecek çatı müşteri yok.",
  unvan: "Ünvan",
  unvanIpucu: "Resmî ünvanı yazın; aynı ünvan ikinci kez eklenemez.",
  segmentSec: "Segment",
  segmentYok: "Seçilmedi",
  segmentCati: "Boş bırakılırsa çatı müşterinin segmenti alınır.",
  tamSec: "Sorumlu TAM",
  tamKendi: "Kendiniz",
  kaydet: "Müşteriyi ekle",
  kaydediliyor: "Ekleniyor…",
  kapat: "Kapat",
  unvanZorunlu: "Ünvan zorunlu.",
  catiZorunlu: "İştirak için çatı müşteri seçin.",
  eklenemedi: "Müşteri eklenemedi.",
  onizleme: "Kart önizlemesi",
  unvanBos: "Müşteri ünvanı",
}

const EN: typeof TR = {
  ...ORTAK.en,
  baslik: "Customer Management",
  aciklama: "Corporate customer portfolio and operational analysis console",
  musteriEkle: "Add customer",
  ara: "Search customer or subsidiary…",
  tumu: "All",
  segment: "Segment",
  tam: "TAM",
  tumTam: "All staff",
  temizle: "Clear filters",
  kpiCati: "Parent customers",
  kpiIstirak: "Subsidiaries",
  kpiAlarm: "Open alarms",
  kpiSikayet: "Open complaints",
  kpiTalep: "Open requests",
  kpiSkor: "Average final score",
  kpiSkorAlt: (n: number) => `${n} customers scored`,
  acikKayitlar: "Open records",
  onedeskKayitlar: "Records",
  acikKapanan: "open / closed this year",
  alarm: "Alarm",
  sikayet: "Complaint",
  talep: "Request",
  istirak: "subsidiaries",
  skor: "Final score",
  skorYok: "No score",
  kartiAc: "Open customer card",
  sonucYok: "No customer matches the search.",
  sonucYokAlt: "Try changing the filters or adding a new customer.",
  hicMusteri: "No customers yet",
  hicMusteriAlt: "Add the first customer to build the portfolio.",
  yuklenemedi: "Could not load the customer portfolio.",
  toplam: (n: number) => `${n} customers`,
  sayfa: (s: number, t: number) => `Page ${s} / ${t}`,
  sayfalama: "Pagination",
  formBaslik: "New customer",
  formAciklama: "Add a main customer or a subsidiary of a parent customer.",
  tur: "Type",
  turAna: "Main customer",
  turIstirak: "Subsidiary",
  cati: "Parent customer",
  catiSec: "Select parent customer",
  catiYok: "No parent customer available.",
  unvan: "Company name",
  unvanIpucu: "Enter the official name; the same name cannot be added twice.",
  segmentSec: "Segment",
  segmentYok: "Not selected",
  segmentCati: "If left empty, the parent customer's segment is used.",
  tamSec: "Responsible TAM",
  tamKendi: "Yourself",
  kaydet: "Add customer",
  kaydediliyor: "Adding…",
  kapat: "Close",
  unvanZorunlu: "Company name is required.",
  catiZorunlu: "Select a parent customer for a subsidiary.",
  eklenemedi: "Could not add the customer.",
  onizleme: "Card preview",
  unvanBos: "Customer name",
}

export function portfoyMetin(dil: Dil) {
  return dil === "en" ? EN : TR
}

const YASAL_EKLER = new Set(["as", "a", "s", "anonim", "sirketi", "ltd", "sti", "limited", "ticaret", "sanayi", "san", "tic", "ve", "ic", "dis", "inc", "corp", "co", "gmbh", "ltdsti", "aş"])

/** Kutucukta gorunen kisa unvan (uretim kisa_unvan): sondaki yasal/ticari ekler atilir, uzunsa kelime sinirinda kesilir. Yalniz gosterimdir. */
export function kisaUnvan(ad: string, azami = 26): string {
  const kelimeler = ad.split(/\s+/).filter(Boolean)
  const duz = (k: string) =>
    k
      .toLocaleLowerCase("tr-TR")
      .replace(/ı/g, "i")
      .replace(/ş/g, "s")
      .replace(/ğ/g, "g")
      .replace(/ü/g, "u")
      .replace(/ö/g, "o")
      .replace(/ç/g, "c")
      .replace(/[^0-9a-z]/g, "")
  while (kelimeler.length > 1 && YASAL_EKLER.has(duz(kelimeler[kelimeler.length - 1] ?? ""))) kelimeler.pop()
  const kisa = kelimeler.join(" ")
  if (kisa.length <= azami) return kisa
  const bas = kisa.slice(0, azami + 1)
  return `${(bas.includes(" ") ? bas.slice(0, bas.lastIndexOf(" ")) : kisa.slice(0, azami)).replace(/[ .,&-]+$/, "")}…`
}
