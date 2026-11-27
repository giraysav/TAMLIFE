import { CircleDollarSign, Gauge, PiggyBank } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { para, sayi, tarih } from "@/lib/bicim"
import type { Dil } from "@/shell/metin"
import { gelirUretimMetin } from "@/gelir-uretim/gelir-uretim-metin"
import type { Durum, Fayda, Kayit, Onay, SatirDurumu, ZorunluAlan } from "@/gelir-uretim/gelir-uretim-metin"

/** Modulun ortak parcalari: API yolu, sorgu anahtari, rozetler ve tutar/tarih metinleri (sayfa, ayrinti, form ve ice aktarma kullanir). */
export const TABAN = "/api/v1/gelir-uretim"
/** Liste ve ozet tek anahtar altindadir: her yazma ve ice aktarma hepsini birlikte yeniler. */
export const ANAHTAR = ["gelir-uretim"] as const
export const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

export type Metin = ReturnType<typeof gelirUretimMetin>
type Ton = "gri" | "sari" | "yesil" | "amber" | "kirmizi"

export const DURUM_TON: Record<Durum, Ton> = { baslamadi: "gri", devam: "amber", tamamlandi: "yesil", iptal: "kirmizi" }
export const ONAY_TON: Record<Onay, Ton> = { bekliyor: "amber", onayli: "yesil", reddedildi: "kirmizi" }
export const SATIR_TON: Record<SatirDurumu, Ton> = { yeni: "yesil", var: "gri", tekrar: "amber", hatali: "kirmizi" }

const FAYDA_SINIF: Record<Fayda, string> = {
  gelir: "bg-emerald-500/10 text-emerald-700",
  tasarruf: "bg-sky-500/10 text-sky-700",
  verimlilik: "bg-violet-500/10 text-violet-700",
}
const FAYDA_IKON: Record<Fayda, LucideIcon> = { gelir: CircleDollarSign, tasarruf: PiggyBank, verimlilik: Gauge }

/** Fayda turu rozeti: renk + simge (yalniz renge dayanmaz). */
export function FaydaRozeti({ fayda, dil }: { fayda: Fayda; dil: Dil }) {
  const Ikon = FAYDA_IKON[fayda]
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-0.5 text-[0.625rem] font-bold ${FAYDA_SINIF[fayda]}`}>
      <Ikon aria-hidden className="size-3" />
      {gelirUretimMetin(dil).fayda_[fayda]}
    </span>
  )
}

/** "1.250,75 ₺ / ay"; tutar yoksa bos metin (not alani ayrica gosterilir). */
export function tutarMetni(k: Pick<Kayit, "revenue_amount" | "revenue_currency" | "revenue_period">, t: Metin): string {
  return k.revenue_amount === null ? "" : `${para(k.revenue_amount, k.revenue_currency)} ${t.donemKisa[k.revenue_period]}`
}

export function saatMetni(saat: number | null, t: Metin): string {
  return saat === null ? "" : `${sayi(saat)} ${t.saatAy}`
}

/** "01.03.2026 – 31.12.2026"; bitis bos ve is surerken "… – devam ediyor"; tarih yoksa "Tarih yok". */
export function tarihAraligi(k: Pick<Kayit, "start_date" | "end_date" | "status">, t: Metin): string {
  if (!k.start_date && !k.end_date) return t.tarihYok
  if (!k.start_date) return `${t.bitis}: ${tarih(k.end_date)}`
  if (k.end_date) return `${tarih(k.start_date)} – ${tarih(k.end_date)}`
  return k.status === "devam" ? `${tarih(k.start_date)} – ${t.devamEdiyor}` : tarih(k.start_date)
}

/** Panel kullanicilari ve panelde hesabi olmayan kisiler tek metinde. */
export function kisilerMetni(adlar: string[], diger: string): string {
  return [...adlar, diger].map((s) => s.trim()).filter(Boolean).join(", ")
}

/** Zorunlu alanin formdaki adi (eksik alan uyarilari). */
export function zorunluEtiket(alan: ZorunluAlan, t: Metin): string {
  const etiketler: Record<ZorunluAlan, string> = {
    people: t.tamKisiler, title: t.baslikAlani, status_note: t.durumNotu, roadmap: t.yolAlani, description: t.aciklamaAlani, customers: t.musterilerAlani,
    revenue_amount: t.gelirTutari, year_revenue: t.yilIciAlani, hours_per_month: t.eforAlani, hours_per_year: t.yilSaatAlani, extra_note: t.ekAlani,
    start_date: t.baslangicAlani, end_date: t.bitisAlani,
  }  // prettier-ignore
  return etiketler[alan]
}
