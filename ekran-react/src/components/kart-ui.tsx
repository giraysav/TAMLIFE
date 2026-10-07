import { useState } from "react"
import type { ReactNode } from "react"
import { ChevronDown } from "lucide-react"

/** Eski panelin kart dili: sari vurgulu katlanir bolumler, buyuk harf basliklar, lacivert tablo basligi. */

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
      <summary className="flex cursor-pointer select-none list-none items-center gap-2 border-b border-slate-100 bg-slate-50/80 px-4 py-2.5 hover:bg-slate-100/80 [details:not([open])_&]:border-b-transparent [&::-webkit-details-marker]:hidden">
        <span aria-hidden className="h-4 w-1 shrink-0 rounded-full bg-tl-yellow" />
        <h3 className="min-w-0 flex-1 text-[11px] font-black uppercase tracking-widest text-tl-navy">{baslik}</h3>
        <ChevronDown aria-hidden className="size-4 shrink-0 text-tl-navy/60 transition-transform duration-200 group-open:rotate-180" />
      </summary>
      <div className="p-4">{children}</div>
    </details>
  )
}

export function Etiket({ children }: { children: ReactNode }) {
  return <span className="mb-1 block text-[10px] font-black uppercase tracking-wide text-slate-400">{children}</span>
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

export function Metrik({ etiket, deger, alt, zemin, yazi }: { etiket: string; deger: number; alt: string; zemin: string; yazi: string }) {
  return (
    <div className={`w-full rounded-xl border border-slate-200/80 p-3 text-left ${zemin}`}>
      <div className="text-[10px] font-black uppercase tracking-wide text-slate-400">{etiket}</div>
      <div className={`mt-0.5 font-mono text-2xl font-black leading-tight ${yazi}`}>{deger.toLocaleString("tr-TR")}</div>
      <div className="mt-1 text-[10px] font-bold text-slate-500">{alt}</div>
    </div>
  )
}

export function KartTablo({ basliklar, satirlar }: { basliklar: string[]; satirlar: string[][] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full text-left text-xs">
        <thead className="bg-tl-navy text-white">
          <tr>
            {basliklar.map((b, i) => (
              <th key={i} scope="col" className="whitespace-nowrap px-3 py-2 font-black">
                {b}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {satirlar.map((s, i) => (
            <tr key={i}>
              {s.map((h, j) => (
                <td key={j} className="whitespace-nowrap px-3 py-2 font-bold text-slate-700">
                  {h}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
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
  return <span className={`whitespace-nowrap rounded-md px-2 py-0.5 text-[10px] font-bold ${sinif}`}>{children}</span>
}
