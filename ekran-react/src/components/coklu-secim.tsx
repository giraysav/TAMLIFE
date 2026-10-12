import { useEffect, useRef, useState } from "react"
import { Check, ChevronDown, Users } from "lucide-react"
import { DUGME } from "@/components/sayfa-ui"

export type SecimOgesi = { deger: string; etiket: string; sayi?: number }

/**
 * Onay kutulu coklu secim acilir listesi (filtre). Hicbiri secili degilse filtre yok demektir (hepsi gorunur).
 * Esc ve disari tik kapatir; dugme ozetler ("Tum personel", tek ad ya da "N kisi").
 */
export function CokluSecim({
  etiket,
  tumuEtiketi,
  secimOzeti,
  temizleEtiketi,
  ogeler,
  secili,
  onDegis,
}: {
  etiket: string
  tumuEtiketi: string
  secimOzeti: (n: number) => string
  temizleEtiketi: string
  ogeler: SecimOgesi[]
  secili: ReadonlySet<string>
  onDegis: (yeni: Set<string>) => void
}) {
  const [acik, setAcik] = useState(false)
  const kutu = useRef<HTMLDivElement>(null)
  const dugme = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!acik) return
    const disariTikla = (olay: MouseEvent) => {
      if (!kutu.current?.contains(olay.target as Node)) setAcik(false)
    }
    const tus = (olay: KeyboardEvent) => {
      if (olay.key === "Escape") {
        setAcik(false)
        dugme.current?.focus()
      }
    }
    document.addEventListener("mousedown", disariTikla)
    document.addEventListener("keydown", tus)
    return () => {
      document.removeEventListener("mousedown", disariTikla)
      document.removeEventListener("keydown", tus)
    }
  }, [acik])

  function degistir(deger: string, isaretli: boolean) {
    const yeni = new Set(secili)
    if (isaretli) yeni.add(deger)
    else yeni.delete(deger)
    onDegis(yeni)
  }

  const ozet = secili.size === 0 ? tumuEtiketi : secili.size === 1 ? (ogeler.find((o) => secili.has(o.deger))?.etiket ?? secimOzeti(1)) : secimOzeti(secili.size)

  return (
    <div className="relative" ref={kutu}>
      <button
        ref={dugme}
        type="button"
        aria-haspopup="true"
        aria-expanded={acik}
        aria-label={`${etiket}: ${ozet}`}
        onClick={() => setAcik((a) => !a)}
        className={`${DUGME} ${secili.size > 0 ? "!border-tl-yellow !bg-tl-yellow/20" : ""}`}
      >
        <Users aria-hidden className="size-4 text-tl-blue" />
        <span className="text-slate-500">{etiket}:</span>
        <span className="max-w-48 truncate">{ozet}</span>
        <ChevronDown aria-hidden className={`size-4 text-tl-navy/60 transition-transform ${acik ? "rotate-180" : ""}`} />
      </button>
      {acik ? (
        <div role="group" aria-label={etiket} className="absolute left-0 top-full z-30 mt-1.5 w-72 max-w-[85vw] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl shadow-tl-navy/20">
          <div className="flex items-center justify-between gap-2 border-b border-slate-100 bg-tl-blue/5 px-3 py-2">
            <span className="text-[0.6875rem] font-black uppercase tracking-widest text-tl-navy">{etiket}</span>
            <button type="button" className="text-xs font-bold text-tl-blue hover:underline disabled:text-slate-300 disabled:no-underline" disabled={secili.size === 0} onClick={() => onDegis(new Set())}>
              {temizleEtiketi}
            </button>
          </div>
          <ul className="max-h-72 overflow-auto p-1">
            {ogeler.map((o) => {
              const isaretli = secili.has(o.deger)
              return (
                <li key={o.deger}>
                  <label className={`flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-xs font-bold hover:bg-slate-100 ${isaretli ? "bg-tl-yellow/15 text-tl-navy" : "text-slate-700"}`}>
                    <input type="checkbox" className="size-4 accent-tl-blue" checked={isaretli} onChange={(e) => degistir(o.deger, e.target.checked)} />
                    <span className="min-w-0 flex-1 truncate">{o.etiket}</span>
                    {o.sayi !== undefined ? <span className="font-mono text-[0.6875rem] text-slate-400">{o.sayi}</span> : null}
                    {isaretli ? <Check aria-hidden className="size-3.5 text-tl-blue" /> : null}
                  </label>
                </li>
              )
            })}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
