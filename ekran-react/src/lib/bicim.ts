/** Gosterim bicimleri. Sunucu ISO tarih/zaman verir; ekranda arayuz dilinin bicimi kullanilir (varsayilan tr-TR). */

let yerel = "tr-TR"
const AD_SIRALAYICI = new Intl.Collator("tr-TR", { sensitivity: "base", numeric: true })

/** Kisi ve musteri adlarini Turkce alfabe duzeninde siralar; kaynak diziyi degistirmez. */
export function adaGoreSirala<T>(liste: readonly T[], ad: (oge: T) => string): T[] {
  return [...liste].sort((a, b) => AD_SIRALAYICI.compare(ad(a).trim(), ad(b).trim()))
}

/** Arayuz dili degisince App cagirir: sayi, para, tarih ve sure bicimleri dile uyar. */
export function bicimDili(dil: "tr" | "en") {
  yerel = dil === "en" ? "en-GB" : "tr-TR"
}

export function sayi(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : n.toLocaleString(yerel)
}

const SEMBOL: Record<string, string> = { TRY: "₺", USD: "$", EUR: "€" }

/** 12500.5 -> "12.500,50 ₺" (para birimi kodu bilinmiyorsa kod yazilir). `kisa`: kurussuz ("12.501 ₺"; ozet kartlari icin). */
export function para(n: number | null | undefined, birim = "TRY", kisa = false): string {
  if (n === null || n === undefined) return "—"
  const tutar = n.toLocaleString(yerel, kisa ? { maximumFractionDigits: 0 } : { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const s = SEMBOL[birim]
  return s ? `${tutar} ${s}` : `${tutar} ${birim}`
}

/** "2026-03-10" -> "10.03.2026"; bos/gecersiz -> "—". Saat dilimi kaymasi olmasin diye metin parcalanir. */
export function tarih(iso: string | null | undefined): string {
  if (!iso) return "—"
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? [m[3], m[2], m[1]].join(yerel === "tr-TR" ? "." : "/") : "—"
}

/** ISO zaman damgasi -> yerel "10.03.2026 14:05". */
export function zaman(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString(yerel, { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })
}

export function bayt(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—"
  if (n < 1024) return `${n} B`
  const birimler = ["KB", "MB", "GB", "TB"]
  let deger = n / 1024
  let i = 0
  while (deger >= 1024 && i < birimler.length - 1) {
    deger /= 1024
    i += 1
  }
  return `${deger.toLocaleString(yerel, { maximumFractionDigits: deger < 10 ? 1 : 0 })} ${birimler[i]}`
}

export function sureYaz(sn: number): string {
  const [s, dk, sa] = yerel === "tr-TR" ? ["sn", "dk", "sa"] : ["s", "min", "h"]
  if (sn < 90) return `${sn} ${s}`
  if (sn < 5400) return `${Math.round(sn / 60)} ${dk}`
  return `${(sn / 3600).toLocaleString(yerel, { maximumFractionDigits: 1 })} ${sa}`
}

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
