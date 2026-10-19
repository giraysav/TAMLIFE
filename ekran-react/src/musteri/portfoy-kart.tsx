import { Building2 } from "lucide-react"
import { baslangicHarfleri, sayi } from "@/lib/bicim"
import { useMusteriYolu } from "@/musteri/musteri-yolu"
import { kisaUnvan, portfoyMetin } from "@/musteri/portfoy-metin"
import type { Dil } from "@/shell/metin"

export type PortfoyKart = {
  id: number
  name: string
  segment: string
  owner: string | null
  owner_id: number | null
  score: number | null
  alarm: number
  sikayet: number
  talep: number
  /** yil ici kapanan (Onedesk kayitlari kutusu: acik / kapanan) */
  alarm_kapanan?: number
  sikayet_kapanan?: number
  talep_kapanan?: number
  istirakler: { id: number; name: string }[]
}
export type Secenekler = { segmentler: string[]; yonetici: boolean; kendi_id: number | null; tam: { id: number; ad: string }[]; catilar: { id: number; ad: string }[] }

const SEGMENT_RENK: Record<string, string> = {
  SMB: "bg-slate-100 text-slate-600",
  SA: "bg-sky-100 text-sky-700",
  MA: "bg-indigo-100 text-indigo-700",
  PA: "bg-violet-100 text-violet-700",
  WHOLESALE: "bg-amber-100 text-amber-800",
}

function SkorCubugu({ skor, etiket, yok }: { skor: number | null; etiket: string; yok: string }) {
  if (skor === null) return <span className="text-[0.625rem] font-bold text-slate-300">{yok}</span>
  const ton = skor >= 80 ? "bg-emerald-500" : skor >= 60 ? "bg-amber-500" : "bg-rose-500"
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2" title={`${etiket}: %${skor}`}>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full ${ton}`} style={{ width: `${Math.min(100, skor)}%` }} />
      </div>
      <span className="font-mono text-xs font-black text-tl-navy">%{skor}</span>
    </div>
  )
}

/** Onedesk kayit kutusu: "acik / yil ici kapanan" (acik renkli, kapanan sonuk). */
function Olcu({ ad, acik, kapanan, ton, ipucu }: { ad: string; acik: number; kapanan: number; ton: "kirmizi" | "amber" | "mavi"; ipucu: string }) {
  const renk = { kirmizi: "bg-rose-50 text-rose-600", amber: "bg-amber-50 text-amber-600", mavi: "bg-blue-50 text-blue-600" }[ton]
  return (
    <div className={`rounded-xl px-2 py-1.5 text-center ${acik > 0 ? renk : kapanan > 0 ? "bg-slate-50 text-slate-500" : "bg-slate-50 text-slate-300"}`} title={ipucu}>
      <div className="text-[0.5625rem] font-black uppercase tracking-wide text-slate-400">{ad}</div>
      <div className="whitespace-nowrap font-mono text-sm font-black leading-tight">
        {sayi(acik)} <span className="font-bold text-slate-400">/ {sayi(kapanan)}</span>
      </div>
    </div>
  )
}

export function MusteriKarti({ m, dil, onizleme = false }: { m: PortfoyKart; dil: Dil; onizleme?: boolean }) {
  const t = portfoyMetin(dil)
  const yol = useMusteriYolu()
  const icerik = (
    <>
      <span aria-hidden className="absolute inset-y-0 left-0 w-1.5 bg-tl-yellow transition-all group-hover:w-2.5" />
      <div className="grid gap-3 pl-1.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="line-clamp-2 break-words text-[0.9375rem] font-black leading-snug text-tl-navy" title={m.name}>
              {kisaUnvan(m.name) || t.unvanBos}
            </p>
            {m.segment ? <span className={`mt-1.5 inline-block rounded-lg px-2 py-0.5 text-[0.625rem] font-black ${SEGMENT_RENK[m.segment] ?? "bg-slate-100 text-slate-600"}`}>{m.segment}</span> : null}
          </div>
          <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-tl-navy/5 text-tl-navy transition-colors group-hover:bg-tl-navy group-hover:text-tl-yellow">
            <Building2 aria-hidden className="size-4" />
          </span>
        </div>
        {m.owner ? (
          <p className="flex items-center gap-1.5 truncate text-xs font-bold text-slate-500">
            <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-tl-blue/10 text-[0.5625rem] font-black text-tl-blue">{baslangicHarfleri(m.owner)}</span>
            <span className="truncate">{m.owner}</span>
          </p>
        ) : null}
        <div>
          <p className="mb-1 text-[0.5625rem] font-black uppercase tracking-widest text-slate-400">
            {t.onedeskKayitlar} <span className="font-bold normal-case tracking-normal">· {t.acikKapanan}</span>
          </p>
          <div className="grid grid-cols-3 gap-2">
            <Olcu ad={t.alarm} acik={m.alarm} kapanan={m.alarm_kapanan ?? 0} ton="kirmizi" ipucu={t.acikKapanan} />
            <Olcu ad={t.sikayet} acik={m.sikayet} kapanan={m.sikayet_kapanan ?? 0} ton="amber" ipucu={t.acikKapanan} />
            <Olcu ad={t.talep} acik={m.talep} kapanan={m.talep_kapanan ?? 0} ton="mavi" ipucu={t.acikKapanan} />
          </div>
        </div>
        <div className="flex items-center justify-between gap-3 border-t border-slate-100 pt-2">
          <SkorCubugu skor={m.score} etiket={t.skor} yok={t.skorYok} />
          {m.istirakler.length > 0 ? (
            <span className="shrink-0 rounded-md bg-amber-100 px-2 py-0.5 text-[0.625rem] font-black text-amber-800" title={m.istirakler.map((i) => i.name).join(", ")}>
              {m.istirakler.length} {t.istirak}
            </span>
          ) : null}
        </div>
      </div>
    </>
  )
  const sinif = "group relative block overflow-hidden rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-all"
  return onizleme ? (
    <div className={sinif}>{icerik}</div>
  ) : (
    <a href={`#/${yol}?m=${m.id}`} aria-label={`${t.kartiAc}: ${m.name}`} className={`${sinif} hover:-translate-y-1 hover:border-tl-yellow hover:shadow-xl focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow`}>
      {icerik}
    </a>
  )
}
