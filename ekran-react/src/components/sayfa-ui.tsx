import { useState } from "react"
import type { ReactNode } from "react"
import type { LucideIcon } from "lucide-react"
import { ChevronDown, CircleAlert, CircleCheck, Inbox, Info, LoaderCircle } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"

/** Ortak arayuz ogeleri (tek kaynak). Gorsel dil: lacivert baslik, mavi vurgu, sari serit; katlanir bolumler, buyuk harf basliklar. */

/**
 * Alan basligi standardi (Turkcell paleti): 1. seviye = lacivert->mavi gradyanli bant, beyaz buyuk harf baslik, sari dikey serit ve
 * sari alt cizgi (ust cubukla ayni dil); 2. seviye (ic ice katlananlar) = acik mavi bant, lacivert baslik, sari serit.
 * Bolum, Panel ve Veri Girisi rehberi bu sabitleri kullanir; yeni bir alan basligi icin de bunlar kullanilir.
 */
export const BASLIK_BANDI = "flex items-center gap-2 border-b-2 border-tl-yellow bg-gradient-to-r from-tl-navy via-[#003a7a] to-tl-blue px-4 py-2.5 text-white"
export const BASLIK_YAZISI = "min-w-0 text-[0.75rem] font-black uppercase tracking-widest text-white"
export const ALT_BASLIK_BANDI = "flex items-center gap-2 bg-gradient-to-r from-tl-blue/15 to-tl-blue/5 px-3 py-2 text-tl-navy"
export const ALT_BASLIK_YAZISI = "min-w-0 text-[0.6875rem] font-black uppercase tracking-widest text-tl-navy"

export const GIRDI =
  "w-full rounded-lg border border-slate-300 bg-white px-2 py-2 text-xs font-bold text-slate-700 outline-none focus:border-tl-blue focus-visible:ring-2 focus-visible:ring-tl-yellow/60 disabled:opacity-60"

export const DUGME =
  "inline-flex items-center justify-center gap-1.5 rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-bold text-tl-navy shadow-sm transition-colors hover:bg-slate-50 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow disabled:opacity-60"
export const DUGME_ANA =
  "inline-flex items-center justify-center gap-1.5 rounded-xl border border-tl-blue bg-white px-4 py-2 text-xs font-bold text-tl-blue shadow-sm transition-colors hover:bg-tl-blue/5 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow disabled:opacity-60"
export const DUGME_SARI =
  "inline-flex min-w-[12rem] items-center justify-center gap-2 rounded-xl bg-tl-yellow px-5 py-2.5 text-xs font-black text-tl-navy shadow transition-colors hover:bg-yellow-400 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-navy disabled:cursor-not-allowed disabled:opacity-50"

const ANAHTAR = "mkBolum:"

function acikMi(anahtar: string, varsayilan: boolean): boolean {
  try {
    const ham = window.localStorage.getItem(ANAHTAR + anahtar)
    return ham === null ? varsayilan : ham === "1"
  } catch {
    return varsayilan
  }
}

/** Katlanir bolum (yerel <details>: klavye ve ekran okuyucu hazir). Acik/kapali durumu tarayicida hatirlanir. */
export function Bolum({ anahtar, baslik, children, ek = "", varsayilanAcik = true }: { anahtar: string; baslik: string; children: ReactNode; ek?: string; varsayilanAcik?: boolean }) {
  const [acik, setAcik] = useState(() => acikMi(anahtar, varsayilanAcik))
  return (
    <details
      open={acik}
      onToggle={(e) => {
        const yeni = e.currentTarget.open
        setAcik(yeni)
        try {
          window.localStorage.setItem(ANAHTAR + anahtar, yeni ? "1" : "0")
        } catch {
          /* depolama kapali */
        }
      }}
      className={`group overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm ${ek}`}
    >
      <summary className={`${BASLIK_BANDI} cursor-pointer select-none list-none transition-[filter] hover:brightness-110 [details:not([open])_&]:border-b-transparent [&::-webkit-details-marker]:hidden`}>
        <span aria-hidden className="h-4 w-1 shrink-0 rounded-full bg-tl-yellow" />
        <h3 className={`flex-1 ${BASLIK_YAZISI}`}>{baslik}</h3>
        <ChevronDown aria-hidden className="size-4 shrink-0 text-tl-yellow transition-transform duration-200 group-open:rotate-180" />
      </summary>
      <div className="p-4">{children}</div>
    </details>
  )
}

export function Satir({ etiket, children }: { etiket: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-3 border-b border-slate-100 py-1.5 text-xs last:border-0">
      <span className="shrink-0 font-bold text-slate-400">{etiket}</span>
      <span className="min-w-0 break-words text-right font-bold text-slate-700">{children}</span>
    </div>
  )
}

export function Bos({ children }: { children: ReactNode }) {
  return <p className="text-xs font-bold text-slate-400">{children}</p>
}

/** Mavi/sari kenarlikli rozet gibi kucuk etiketler. */
export function Rozet({ children, ton = "gri" }: { children: ReactNode; ton?: "gri" | "sari" | "yesil" | "amber" | "kirmizi" }) {
  const sinif = {
    gri: "bg-slate-100 text-slate-500",
    sari: "bg-tl-yellow text-tl-navy",
    yesil: "bg-emerald-500/10 text-emerald-600",
    amber: "bg-amber-500/20 text-amber-800",
    kirmizi: "bg-rose-500/10 text-rose-600",
  }[ton]
  return <span className={`whitespace-nowrap rounded-md px-2 py-0.5 text-[0.625rem] font-bold ${sinif}`}>{children}</span>
}

export function SayfaKabi({ ikon: Ikon, baslik, aciklama, children }: { ikon: LucideIcon; baslik: string; aciklama?: string; children?: ReactNode }) {
  return (
    <header className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-tl-navy via-[#003a7a] to-tl-blue p-4 text-white shadow-md sm:p-5">
      <span aria-hidden className="pointer-events-none absolute -right-8 -top-10 size-44 rounded-full bg-tl-yellow/20 blur-3xl" />
      <span aria-hidden className="pointer-events-none absolute -bottom-12 left-1/3 size-40 rounded-full bg-tl-accent/20 blur-3xl" />
      <div className="relative flex flex-wrap items-center gap-4">
        <span className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-tl-yellow text-tl-navy shadow-lg shadow-black/20">
          <Ikon aria-hidden className="size-6" />
        </span>
        <div className="min-w-[13rem] flex-1">
          <h2 className="text-lg font-black leading-tight tracking-tight sm:text-xl">{baslik}</h2>
          {aciklama ? <p className="mt-0.5 text-xs font-bold text-white/70">{aciklama}</p> : null}
        </div>
        {children ? <div className="flex flex-wrap items-center gap-2">{children}</div> : null}
      </div>
    </header>
  )
}

export type SekmeSecenegi<T extends string> = { id: T; etiket: string; ikon?: LucideIcon; sayi?: number | string }

/** Buyuk, dokunmaya uygun sekme dugmeleri (rol="tablist"). */
export function Sekmeler<T extends string>({ secenekler, deger, onDegis, etiket }: { secenekler: SekmeSecenegi<T>[]; deger: T; onDegis: (id: T) => void; etiket: string }) {
  return (
    <div role="tablist" aria-label={etiket} className="flex flex-wrap gap-2">
      {secenekler.map((s) => {
        const aktif = s.id === deger
        const Ikon = s.ikon
        return (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={aktif}
            onClick={() => onDegis(s.id)}
            className={`group inline-flex min-h-11 items-center gap-2 rounded-xl border px-4 text-sm font-black shadow-sm transition-all focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow ${
              aktif ? "border-tl-yellow bg-tl-yellow text-tl-navy shadow-md" : "border-slate-200 bg-white text-tl-navy hover:-translate-y-px hover:border-tl-blue/40 hover:shadow"
            }`}
          >
            {Ikon ? <Ikon aria-hidden className="size-4" /> : null}
            {s.etiket}
            {s.sayi !== undefined ? (
              <span className={`rounded-md px-1.5 py-0.5 font-mono text-[0.6875rem] ${aktif ? "bg-tl-navy text-tl-yellow" : "bg-slate-100 text-slate-500"}`}>{s.sayi}</span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}

const KPI_TON = {
  mavi: "from-tl-blue/10 text-tl-blue",
  sari: "from-tl-yellow/30 text-tl-navy",
  kirmizi: "from-rose-500/10 text-rose-600",
  yesil: "from-emerald-500/10 text-emerald-600",
  amber: "from-amber-500/15 text-amber-700",
  gri: "from-slate-200/60 text-slate-600",
} as const

/** `kucuk`: alcak yer (Genel Bakis Ekip Ozeti): dolgu, sayi ve simge kucultulur. `sans`: sayi tek aralikli (mono) yazi yerine duz yazi tipiyle (binlik ayraci ve virgul genis bosluk birakmaz). */
export function Kpi({ etiket, deger, alt, ikon: Ikon, ton = "mavi", kucuk = false, sans = false }: { etiket: string; deger: ReactNode; alt?: ReactNode; ikon?: LucideIcon; ton?: keyof typeof KPI_TON; kucuk?: boolean; sans?: boolean }) {
  const uzunluk = typeof deger === "string" ? deger.length : 0
  // uzun degerler (para tutari) karoya sigsin diye kuculur; kucuk karoda esikler daha dusuktur
  const boyut = kucuk ? (uzunluk > 9 ? "text-base" : uzunluk > 6 ? "text-xl" : "text-2xl") : uzunluk > 9 ? "text-xl" : "text-3xl"
  return (
    <div className={`relative overflow-hidden rounded-2xl border border-slate-200 bg-gradient-to-br to-white shadow-sm ${kucuk ? "px-3 py-2.5" : "p-4"} ${KPI_TON[ton]}`}>
      {Ikon ? <Ikon aria-hidden className={`absolute opacity-30 ${kucuk ? "right-2.5 top-2.5 size-5" : "right-3 top-3 size-7"}`} /> : null}
      <div className="text-[0.625rem] font-black uppercase tracking-widest text-slate-500">{etiket}</div>
      <div className={`mt-1 font-black leading-none text-tl-navy ${sans ? "font-sans tabular-nums" : "font-mono"} ${boyut}`}>{deger}</div>
      {alt ? <div className={`font-bold text-slate-500 ${kucuk ? "mt-1 text-[0.625rem]" : "mt-1.5 text-[0.6875rem]"}`}>{alt}</div> : null}
    </div>
  )
}

/** `govdeSinif`: baslik bandinin altindaki icerik alani (varsayilan p-4); sıkışık yerlesimler dolgu ya da flex ekler. */
export function Panel({ baslik, aciklama, sag, children, sinif = "", govdeSinif = "p-4" }: { baslik?: string; aciklama?: string; sag?: ReactNode; children: ReactNode; sinif?: string; govdeSinif?: string }) {
  return (
    <section className={`overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm ${sinif}`}>
      {baslik ? (
        <div className={`${BASLIK_BANDI} shrink-0 flex-wrap justify-between`}>
          <div className="min-w-0">
            <h3 className={`flex items-center gap-2 ${BASLIK_YAZISI}`}>
              <span aria-hidden className="h-4 w-1 shrink-0 rounded-full bg-tl-yellow" />
              {baslik}
            </h3>
            {aciklama ? <p className="mt-0.5 pl-3 text-[0.6875rem] font-bold text-white/70">{aciklama}</p> : null}
          </div>
          {sag}
        </div>
      ) : null}
      <div className={govdeSinif}>{children}</div>
    </section>
  )
}

/** `iskelet`: yer tutucu kutular (yonetim bolumleri); yoksa donen ikon + metin. */
export function Yukleniyor({ metin, iskelet = false }: { metin: string; iskelet?: boolean }) {
  if (iskelet) {
    return (
      <div role="status" aria-label={metin} className="grid gap-3">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-40 rounded-xl" />
      </div>
    )
  }
  return (
    <p role="status" className="flex items-center gap-2 p-4 text-xs font-bold text-slate-500">
      <LoaderCircle aria-hidden className="size-4 animate-spin motion-reduce:animate-none" />
      {metin}
    </p>
  )
}

export function HataKutu({ metin, tekrar, tekrarEtiket }: { metin: string; tekrar?: () => void; tekrarEtiket?: string }) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs font-bold text-rose-700">
      <CircleAlert aria-hidden className="size-4 shrink-0" />
      <span className="min-w-0 flex-1">{metin}</span>
      {tekrar ? (
        <button type="button" className={DUGME} onClick={tekrar}>
          {tekrarEtiket ?? "↻"}
        </button>
      ) : null}
    </div>
  )
}

export function BosKutu({ baslik, aciklama, ikon: Ikon = Inbox, children }: { baslik: string; aciklama?: string; ikon?: LucideIcon; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-slate-300 bg-slate-50/60 px-4 py-10 text-center">
      <span className="flex size-12 items-center justify-center rounded-full bg-white text-slate-400 shadow-sm ring-1 ring-slate-200">
        <Ikon aria-hidden className="size-6" />
      </span>
      <p className="text-sm font-black text-tl-navy">{baslik}</p>
      {aciklama ? <p className="max-w-md text-xs font-bold text-slate-500">{aciklama}</p> : null}
      {children}
    </div>
  )
}

export function Bildirim({ ton = "gri", children }: { ton?: "gri" | "yesil" | "amber" | "kirmizi"; children: ReactNode }) {
  const sinif = { gri: "border-slate-200 bg-slate-50 text-slate-600", yesil: "border-emerald-200 bg-emerald-50 text-emerald-800", amber: "border-amber-200 bg-amber-50 text-amber-900", kirmizi: "border-rose-200 bg-rose-50 text-rose-700" }[ton]
  const Ikon = ton === "gri" ? Info : ton === "yesil" ? CircleCheck : CircleAlert
  return (
    <p role={ton === "gri" || ton === "yesil" ? "status" : "alert"} className={`flex items-start gap-2 rounded-xl border px-3 py-2 text-xs font-bold ${sinif}`}>
      <Ikon aria-hidden className="mt-0.5 size-4 shrink-0" />
      <span className="min-w-0">{children}</span>
    </p>
  )
}

/** Etiketli form alani (label bagli). */
export function Alan({ etiket, children, ipucu, sinif = "" }: { etiket: string; children: ReactNode; ipucu?: string; sinif?: string }) {
  return (
    <label className={`grid gap-1 ${sinif}`}>
      <span className="text-[0.625rem] font-black uppercase tracking-wide text-slate-500">{etiket}</span>
      {children}
      {ipucu ? <span className="text-[0.625rem] font-bold text-slate-400">{ipucu}</span> : null}
    </label>
  )
}

type Kolon<T> = { baslik: string; hucre: (satir: T) => ReactNode; sinif?: string }

/** Basit, erisilebilir tablo (caption sr-only, th scope=col). Satir secimi icin hucreye gercek bir buton/baglanti koyun. */
export function VeriTablosu<T>({
  baslik,
  kolonlar,
  satirlar,
  anahtar,
  vurgulu,
  bos,
  kaydirmali = false,
}: {
  baslik: string
  kolonlar: Kolon<T>[]
  satirlar: T[]
  anahtar?: (satir: T) => string | number
  vurgulu?: (satir: T) => boolean
  bos?: ReactNode
  /** true: tablo ust kutunun kalan yuksekligini doldurur, satirlar kutunun icinde kayar, baslik sabit kalir (sayfa kaymaz) */
  kaydirmali?: boolean
}) {
  if (satirlar.length === 0 && bos) return <>{bos}</>
  return (
    <div className={`rounded-xl border border-slate-200 ${kaydirmali ? "min-h-0 flex-1 overflow-auto" : "overflow-x-auto"}`}>
      <table className="w-full text-left text-xs">
        <caption className="sr-only">{baslik}</caption>
        <thead className={`bg-tl-navy text-white ${kaydirmali ? "sticky top-0 z-[1]" : ""}`}>
          <tr>
            {kolonlar.map((k, i) => (
              <th key={i} scope="col" className={`whitespace-nowrap px-3 py-2 font-black ${k.sinif ?? ""}`}>
                {k.baslik}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {satirlar.map((s, i) => (
            <tr key={anahtar ? anahtar(s) : i} className={vurgulu?.(s) ? "bg-tl-yellow/15" : "hover:bg-slate-50"}>
              {kolonlar.map((k, i) => (
                <td key={i} className={`px-3 py-2 font-bold text-slate-700 ${k.sinif ?? ""}`}>
                  {k.hucre(s)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
