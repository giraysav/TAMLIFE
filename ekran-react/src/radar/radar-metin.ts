import { ORTAK } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

const TR = {
  ...ORTAK.tr,
  baslik: "Müşteri Radar",
  aciklama: "TAM hizmeti almayan, ihtiyaç analizi yapılabilecek müşterileri tespit eder.",
  kural: "Kural: ReportDB'de kayıt üreten ama panelde bir TAM'a atanmamış (kartı olmayan) müşteriler, kayıt sayısına göre ilk 10. Giriş yapılmaz, liste otomatik üretilir.",
  kolUnvan: "Müşteri Ünvanı",
  kolNo: "Müşteri No",
  kolAlarm: "Alarm (Açık / Kapanan)",
  kolToplam: "Toplam Kayıt",
  kolSikayet: "Şikayet",
  kolTalep: "Talep",
  biletYok: "OneDesk bilet şeması erişimi bekleniyor",
  bos: "Panelde karşılığı olmayan, kayıt üreten müşteri bulunamadı.",
  veriYok: "ReportDB verisi henüz alınmadı; veri geldiğinde liste otomatik oluşur.",
  bayat: "ReportDB verisi güncel değil; liste son alınan veriden üretildi.",
  dipnot: "Sayılar bu yılın alarm kayıtlarıdır; şikayet ve talep için OneDesk bilet şeması erişimi gerekir.",
  veriZamani: "Veri zamanı",
}

const EN: typeof TR = {
  ...ORTAK.en,
  baslik: "Customer Radar",
  aciklama: "Finds customers without TAM service that are candidates for a needs analysis.",
  kural: "Rule: customers that produce records in ReportDB but are not assigned to a TAM in the panel (no card), top 10 by record count. No manual entry; the list is generated automatically.",
  kolUnvan: "Customer name",
  kolNo: "Customer No",
  kolAlarm: "Alarms (Open / Closed)",
  kolToplam: "Total records",
  kolSikayet: "Complaints",
  kolTalep: "Requests",
  biletYok: "Waiting for access to the OneDesk ticket schema",
  bos: "No record-producing customer without a panel card was found.",
  veriYok: "No ReportDB data yet; the list is built automatically when data arrives.",
  bayat: "ReportDB data is not current; the list was built from the last data received.",
  dipnot: "Counts are this year's alarm records; complaints and requests need access to the OneDesk ticket schema.",
  veriZamani: "Data time",
}

export const radarMetin = (dil: Dil) => (dil === "en" ? EN : TR)
