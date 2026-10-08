import { useEffect, useState } from "react"
import type { ReactNode } from "react"

/** Hafif SVG/CSS grafikleri (yeni bagimlilik yok). Animasyon yalniz ilk cizimde; `prefers-reduced-motion` ise gecis kapali. */

export type Seri = { anahtar: string; ad: string; renk: string }

/** Ilk cizimde 0'dan buyumek icin: bilesen baglandiktan bir kare sonra true olur. */
function useHazir(): boolean {
  const [hazir, setHazir] = useState(false)
  useEffect(() => {
    const kare = requestAnimationFrame(() => setHazir(true))
    return () => cancelAnimationFrame(kare)
  }, [])
  return hazir
}

export function Lejant({ seriler, sayilar }: { seriler: Seri[]; sayilar?: Record<string, number> }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1">
      {seriler.map((s) => (
        <li key={s.anahtar} className="flex items-center gap-1.5 text-[11px] font-bold text-slate-600">
          <span aria-hidden className="size-2.5 rounded-sm" style={{ background: s.renk }} />
          {s.ad}
          {sayilar ? <span className="font-mono text-slate-400">{(sayilar[s.anahtar] ?? 0).toLocaleString("tr-TR")}</span> : null}
        </li>
      ))}
    </ul>
  )
}

type HalkaDilim = { anahtar: string; ad: string; deger: number; renk: string }

/** Halka (donut) grafik; ortada toplam. Dilimler 0 ise soluk halka gosterilir. */
export function Halka({ dilimler, baslik, alt, boyut = 176, kalinlik = 22 }: { dilimler: HalkaDilim[]; baslik: ReactNode; alt?: ReactNode; boyut?: number; kalinlik?: number }) {
  const hazir = useHazir()
  const yaricap = (boyut - kalinlik) / 2
  const cevre = 2 * Math.PI * yaricap
  const toplam = dilimler.reduce((t, d) => t + d.deger, 0)
  let ilerleme = 0
  return (
    <div className="relative shrink-0" style={{ width: boyut, height: boyut }}>
      <svg width={boyut} height={boyut} viewBox={`0 0 ${boyut} ${boyut}`} role="img" aria-label={dilimler.map((d) => `${d.ad}: ${d.deger}`).join(", ")}>
        <circle cx={boyut / 2} cy={boyut / 2} r={yaricap} fill="none" stroke="#e2e8f0" strokeWidth={kalinlik} />
        {toplam > 0
          ? dilimler
              .filter((d) => d.deger > 0)
              .map((d) => {
                const uzunluk = (d.deger / toplam) * cevre
                const kayma = -ilerleme
                ilerleme += uzunluk
                return (
                  <circle
                    key={d.anahtar}
                    cx={boyut / 2}
                    cy={boyut / 2}
                    r={yaricap}
                    fill="none"
                    stroke={d.renk}
                    strokeWidth={kalinlik}
                    strokeDasharray={`${hazir ? Math.max(uzunluk - 2, 0.5) : 0} ${cevre}`}
                    strokeDashoffset={kayma}
                    transform={`rotate(-90 ${boyut / 2} ${boyut / 2})`}
                    style={{ transition: "stroke-dasharray 900ms cubic-bezier(.22,1,.36,1)" }}
                    className="motion-reduce:transition-none"
                  />
                )
              })
          : null}
      </svg>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
        <div className="font-mono text-2xl font-black leading-none text-tl-navy">{baslik}</div>
        {alt ? <div className="mt-1 max-w-[70%] text-[10px] font-bold uppercase tracking-wide text-slate-400">{alt}</div> : null}
      </div>
    </div>
  )
}

export type CubukSatiri = { anahtar: string | number; etiket: ReactNode; degerler: Record<string, number>; sag?: ReactNode }

/** Yatay yigilmis cubuklar (satir basina bir cubuk). Cubuk uzunlugu en buyuk toplama gore olceklenir. */
export function YatayCubuklar({ satirlar, seriler, yukseklik = 10 }: { satirlar: CubukSatiri[]; seriler: Seri[]; yukseklik?: number }) {
  const hazir = useHazir()
  const toplamlar = satirlar.map((s) => seriler.reduce((t, x) => t + (s.degerler[x.anahtar] ?? 0), 0))
  const enBuyuk = Math.max(1, ...toplamlar)
  return (
    <ul className="grid gap-2.5">
      {satirlar.map((s, i) => (
        <li key={s.anahtar} className="grid gap-1">
          <div className="flex items-baseline justify-between gap-3 text-xs">
            <span className="min-w-0 truncate font-bold text-slate-700">{s.etiket}</span>
            <span className="shrink-0 font-mono font-black text-tl-navy">{s.sag ?? (toplamlar[i] ?? 0).toLocaleString("tr-TR")}</span>
          </div>
          <div className="flex overflow-hidden rounded-full bg-slate-100" style={{ height: yukseklik }} role="img" aria-label={seriler.map((x) => `${x.ad}: ${s.degerler[x.anahtar] ?? 0}`).join(", ")}>
            {seriler.map((x) => {
              const d = s.degerler[x.anahtar] ?? 0
              return d > 0 ? (
                <span
                  key={x.anahtar}
                  title={`${x.ad}: ${d}`}
                  className="h-full motion-reduce:transition-none"
                  style={{ background: x.renk, width: hazir ? `${(d / enBuyuk) * 100}%` : 0, transition: `width 800ms cubic-bezier(.22,1,.36,1) ${i * 40}ms` }}
                />
              ) : null
            })}
          </div>
        </li>
      ))}
    </ul>
  )
}

export type SutunVeri = { etiket: string; degerler: Record<string, number> }

/** Dikey yigilmis sutunlar (ay/yas kovasi gibi sirali kategoriler). */
export function Sutunlar({ sutunlar, seriler, yukseklik = 168 }: { sutunlar: SutunVeri[]; seriler: Seri[]; yukseklik?: number }) {
  const hazir = useHazir()
  const toplam = (s: SutunVeri) => seriler.reduce((t, x) => t + (s.degerler[x.anahtar] ?? 0), 0)
  const enBuyuk = Math.max(1, ...sutunlar.map(toplam))
  return (
    <div className="flex items-end gap-1.5" style={{ height: yukseklik + 24 }} role="img" aria-label={sutunlar.map((s) => `${s.etiket}: ${toplam(s)}`).join(", ")}>
      {sutunlar.map((s, i) => {
        const t = toplam(s)
        return (
          <div key={s.etiket} className="flex min-w-0 flex-1 flex-col items-center justify-end gap-1" title={`${s.etiket}: ${t}`}>
            <span className="font-mono text-[10px] font-black text-slate-500">{t > 0 ? t : ""}</span>
            <div className="flex w-full max-w-9 flex-col-reverse overflow-hidden rounded-t-md bg-slate-50" style={{ height: yukseklik - 16 }}>
              <div className="flex w-full flex-col-reverse motion-reduce:transition-none" style={{ height: hazir ? `${(t / enBuyuk) * 100}%` : 0, transition: `height 800ms cubic-bezier(.22,1,.36,1) ${i * 30}ms` }}>
                {seriler.map((x) => {
                  const d = s.degerler[x.anahtar] ?? 0
                  return d > 0 ? <span key={x.anahtar} className="block w-full" style={{ background: x.renk, height: `${(d / t) * 100}%` }} /> : null
                })}
              </div>
            </div>
            <span className="truncate text-[10px] font-bold text-slate-400">{s.etiket}</span>
          </div>
        )
      })}
    </div>
  )
}
