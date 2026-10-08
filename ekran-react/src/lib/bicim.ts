/** Gosterim bicimleri (tr-TR). Sunucu ISO tarih/zaman verir; ekranda yerel bicim kullanilir. */

export function sayi(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : n.toLocaleString("tr-TR")
}

const SEMBOL: Record<string, string> = { TRY: "₺", USD: "$", EUR: "€" }

/** 12500.5 -> "12.500,50 ₺" (para birimi kodu bilinmiyorsa kod yazilir). */
export function para(n: number | null | undefined, birim = "TRY"): string {
  if (n === null || n === undefined) return "—"
  const tutar = n.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const s = SEMBOL[birim]
  return s ? `${tutar} ${s}` : `${tutar} ${birim}`
}

/** "2026-03-10" -> "10.03.2026"; bos/gecersiz -> "—". Saat dilimi kaymasi olmasin diye metin parcalanir. */
export function tarih(iso: string | null | undefined): string {
  if (!iso) return "—"
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}.${m[2]}.${m[1]}` : "—"
}

/** ISO zaman damgasi -> yerel "10.03.2026 14:05". */
export function zaman(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })
}

export const AY_ADLARI = {
  tr: ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"],
  en: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
} as const

/** Yerel bugunun "YYYY-MM-DD" hali (UTC kaymasi olmadan; form varsayilanlari icin). */
export function bugunYerel(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

export function baslangicHarfleri(ad: string): string {
  const parcalar = ad.trim().split(/\s+/).filter(Boolean)
  if (parcalar.length === 0) return "?"
  const ilk = parcalar[0]?.[0] ?? ""
  const son = parcalar.length > 1 ? (parcalar[parcalar.length - 1]?.[0] ?? "") : (parcalar[0]?.[1] ?? "")
  return (ilk + son).toLocaleUpperCase("tr-TR")
}
