import type { LucideIcon } from "lucide-react"
import { CircleAlert, CircleCheck, Inbox, LoaderCircle } from "lucide-react"
import type { ReactNode } from "react"
import { DUGME } from "@/components/kart-ui"

/** Yeni modul sayfalarinin ortak ogeleri. Gorsel dil: kart-ui ile ayni palet (lacivert, mavi, sari vurgu), daha cesur basliklar. */

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
              <span className={`rounded-md px-1.5 py-0.5 font-mono text-[11px] ${aktif ? "bg-tl-navy text-tl-yellow" : "bg-slate-100 text-slate-500"}`}>{s.sayi}</span>
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

export function Kpi({ etiket, deger, alt, ikon: Ikon, ton = "mavi" }: { etiket: string; deger: ReactNode; alt?: ReactNode; ikon?: LucideIcon; ton?: keyof typeof KPI_TON }) {
  return (
    <div className={`relative overflow-hidden rounded-2xl border border-slate-200 bg-gradient-to-br to-white p-4 shadow-sm ${KPI_TON[ton]}`}>
      {Ikon ? <Ikon aria-hidden className="absolute right-3 top-3 size-7 opacity-30" /> : null}
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">{etiket}</div>
      <div className={`mt-1 font-mono font-black leading-none text-tl-navy ${typeof deger === "string" && deger.length > 9 ? "text-xl" : "text-3xl"}`}>{deger}</div>
      {alt ? <div className="mt-1.5 text-[11px] font-bold text-slate-500">{alt}</div> : null}
    </div>
  )
}

export function Panel({ baslik, aciklama, sag, children, sinif = "" }: { baslik?: string; aciklama?: string; sag?: ReactNode; children: ReactNode; sinif?: string }) {
  return (
    <section className={`rounded-2xl border border-slate-200 bg-white p-4 shadow-sm ${sinif}`}>
      {baslik ? (
        <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="flex items-center gap-2 text-[11px] font-black uppercase tracking-widest text-tl-navy">
              <span aria-hidden className="h-4 w-1 rounded-full bg-tl-yellow" />
              {baslik}
            </h3>
            {aciklama ? <p className="mt-0.5 text-[11px] font-bold text-slate-400">{aciklama}</p> : null}
          </div>
          {sag}
        </div>
      ) : null}
      {children}
    </section>
  )
}

export function Yukleniyor({ metin }: { metin: string }) {
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

export function Bildirim({ ton, children }: { ton: "yesil" | "amber" | "kirmizi"; children: ReactNode }) {
  const sinif = { yesil: "border-emerald-200 bg-emerald-50 text-emerald-800", amber: "border-amber-200 bg-amber-50 text-amber-900", kirmizi: "border-rose-200 bg-rose-50 text-rose-700" }[ton]
  const Ikon = ton === "yesil" ? CircleCheck : CircleAlert
  return (
    <p role={ton === "yesil" ? "status" : "alert"} className={`flex items-start gap-2 rounded-xl border px-3 py-2 text-xs font-bold ${sinif}`}>
      <Ikon aria-hidden className="mt-0.5 size-4 shrink-0" />
      <span className="min-w-0">{children}</span>
    </p>
  )
}

/** Etiketli form alani (label bagli). */
export function Alan({ etiket, children, ipucu, sinif = "" }: { etiket: string; children: ReactNode; ipucu?: string; sinif?: string }) {
  return (
    <label className={`grid gap-1 ${sinif}`}>
      <span className="text-[10px] font-black uppercase tracking-wide text-slate-500">{etiket}</span>
      {children}
      {ipucu ? <span className="text-[10px] font-bold text-slate-400">{ipucu}</span> : null}
    </label>
  )
}

export function Tablo({ basliklar, children, sagaHizali = [] }: { basliklar: string[]; children: ReactNode; sagaHizali?: number[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full text-left text-xs">
        <thead className="bg-tl-navy text-white">
          <tr>
            {basliklar.map((b, i) => (
              <th key={b + i} scope="col" className={`whitespace-nowrap px-3 py-2.5 font-black ${sagaHizali.includes(i) ? "text-right" : ""}`}>
                {b}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">{children}</tbody>
      </table>
    </div>
  )
}
