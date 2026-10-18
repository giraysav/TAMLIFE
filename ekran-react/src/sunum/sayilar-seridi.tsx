import type { LucideIcon } from "lucide-react"
import { BadgeDollarSign, BriefcaseBusiness, Gauge, TrendingUp, UserRoundCheck, Users } from "lucide-react"
import { sayi } from "@/lib/bicim"
import { yerel } from "@/shell/metin"
import type { Dil } from "@/shell/metin"
import { sunumMetin } from "@/sunum/sunum-metin"
import type { GenelVeri } from "@/sunum/sunum-tipleri"
import { kpiAlt } from "@/sunum/sunum-kartlari"

const IKON: Record<string, LucideIcon> = {
  gelir: BadgeDollarSign,
  yillik_gelir: TrendingUp,
  fayda: BriefcaseBusiness,
  musteri: Users,
  utilizasyon: Gauge,
  tam: UserRoundCheck,
}

/**
 * Sayilarla TAM Ekibi: gelir faydasi, musteri, utilizasyon ve ekip buyuklugunu tek bakista gosteren ust yonetim ozeti.
 * Kaynak onceki donem degeri verirse tamamlanmis ceyrekte fark da gosterilir.
 */
export function SayilarSeridi({ veri, dil, oncekiEtiket, farkli }: { veri: GenelVeri; dil: Dil; oncekiEtiket: string; farkli: boolean }) {
  const t = sunumMetin(dil)
  return (
    <ul className="grid grid-cols-3 gap-x-2 gap-y-5 py-1 sm:grid-cols-4 sm:gap-x-3 sm:gap-y-6 xl:grid-cols-7">
      {veri.kpi.map((k) => {
        const Ikon = (k.kod ? IKON[k.kod] : undefined) ?? Gauge
        const deger = sayi(k.deger)
        const alt = kpiAlt(k, dil)
        const fark = farkli && k.deger !== null && k.onceki !== null && k.onceki !== undefined ? k.deger - k.onceki : 0
        return (
          <li key={k.kod || k.ad} className="flex min-w-0 flex-col items-center gap-1.5 text-center">
            <div className="relative">
              <div className="rounded-full bg-gradient-to-br from-tl-navy via-tl-blue to-tl-accent p-1 shadow-md">
                <div className="grid size-20 place-items-center rounded-full bg-white sm:size-24">
                  <span className={`font-black leading-none tabular-nums text-tl-navy ${deger.length > 4 ? "text-xl sm:text-2xl" : "text-2xl sm:text-3xl"}`}>{deger}</span>
                </div>
              </div>
              <span aria-hidden className="absolute -right-1 -top-1 grid size-7 place-items-center rounded-full bg-tl-yellow text-tl-navy shadow sm:size-8">
                <Ikon className="size-3.5 sm:size-4" />
              </span>
            </div>
            <span className="text-[0.6875rem] font-black uppercase tracking-wide text-tl-blue">{yerel(dil, k.ad, k.ad_en)}</span>
            {alt ? <span className="text-[0.625rem] font-bold text-slate-500">{alt}</span> : null}
            {k.onceki !== null && k.onceki !== undefined ? (
              <span className="flex flex-wrap items-center justify-center gap-x-1.5 text-[0.625rem] font-bold text-slate-400">
                <span>
                  {oncekiEtiket}: <span className="tabular-nums">{sayi(k.onceki)}</span>
                </span>
                {fark !== 0 ? (
                  <span className="font-black tabular-nums text-tl-navy" title={t.fark(fark > 0, sayi(Math.abs(fark)))}>
                    {fark > 0 ? "▲" : "▼"} {sayi(Math.abs(fark))}
                  </span>
                ) : null}
              </span>
            ) : null}
          </li>
        )
      })}
    </ul>
  )
}
