import { useEffect, useRef, useState } from "react"
import type { ReactNode } from "react"
import { ChevronLeft, ChevronRight, X } from "lucide-react"
import type { sunumMetin } from "@/sunum/sunum-metin"

/**
 * Tam ekran sunum: birbiriyle uyumlu kisa kartlari ayni slayta sigdirir. Tarayicinin tam ekran kipine gecer (Fullscreen API; desteklenmezse sayfayi kaplar).
 * Klavye: sag ok / Page Down / bosluk sonraki, sol ok / Page Up onceki, Home / End ilk / son, Esc cikar.
 */
export function SunumSlayt({ adet, ciz, adlar, baslik, t, onKapat }: { adet: number; ciz: (i: number) => ReactNode; adlar: string[]; baslik: string; t: ReturnType<typeof sunumMetin>; onKapat: () => void }) {
  const kutu = useRef<HTMLDivElement>(null)
  const kapat = useRef(onKapat)
  kapat.current = onKapat
  const [i, setI] = useState(0)
  const git = (n: number) => setI(Math.max(0, Math.min(adet - 1, n)))

  useEffect(() => {
    const el = kutu.current
    el?.focus()
    let tamEkranda = false
    const degisti = () => {
      if (document.fullscreenElement) tamEkranda = true
      else if (tamEkranda) kapat.current() // kullanici Esc ile tarayicinin tam ekranindan cikti
    }
    document.addEventListener("fullscreenchange", degisti)
    if (el && typeof el.requestFullscreen === "function") void el.requestFullscreen().catch(() => undefined)
    return () => {
      document.removeEventListener("fullscreenchange", degisti)
      if (document.fullscreenElement && typeof document.exitFullscreen === "function") void document.exitFullscreen().catch(() => undefined)
    }
  }, [])

  function tus(e: React.KeyboardEvent) {
    if (["ArrowRight", "PageDown", " "].includes(e.key)) git(i + 1)
    else if (["ArrowLeft", "PageUp"].includes(e.key)) git(i - 1)
    else if (e.key === "Home") git(0)
    else if (e.key === "End") git(adet - 1)
    else if (e.key === "Escape") onKapat()
    else return
    e.preventDefault()
  }

  const DUGME = "inline-flex items-center gap-1.5 rounded-xl border border-white/30 px-3 py-2 text-xs font-black text-white transition-colors hover:bg-white/10 disabled:opacity-30 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
  return (
    <div
      ref={kutu}
      role="dialog"
      aria-modal="true"
      aria-label={t.tamEkran}
      tabIndex={-1}
      onKeyDown={tus}
      className="fixed inset-0 z-[100] flex flex-col bg-gradient-to-br from-tl-navy via-[#003a7a] to-tl-blue outline-hidden"
    >
      <header className="flex shrink-0 items-center justify-between gap-4 px-6 py-3 text-white">
        <div className="min-w-0">
          <p className="text-[0.625rem] font-black uppercase tracking-[0.25em] text-tl-yellow">{baslik}</p>
          <h2 className="truncate text-xl font-black">{adlar[i]}</h2>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-sm font-black text-white/80" aria-live="polite">
            {t.slaytNo(i + 1, adet)}
          </span>
          <button type="button" className={DUGME} onClick={onKapat}>
            <X aria-hidden className="size-4" />
            {t.sunumdanCik}
          </button>
        </div>
      </header>
      <main className="flex min-h-0 flex-1 items-stretch justify-center overflow-hidden px-6 pb-4">
        <div className="h-full w-full max-w-7xl overflow-hidden">
          {ciz(i)}
        </div>
      </main>
      <footer className="flex shrink-0 items-center justify-center gap-4 px-6 py-3">
        <button type="button" className={DUGME} disabled={i === 0} onClick={() => git(i - 1)}>
          <ChevronLeft aria-hidden className="size-4" />
          {t.oncekiSlayt}
        </button>
        <div className="flex flex-wrap items-center justify-center gap-1.5">
          {adlar.map((ad, n) => (
            <button key={n} type="button" aria-label={`${n + 1}. ${ad}`} aria-current={n === i ? "step" : undefined} onClick={() => git(n)} className={`h-2 rounded-full transition-all ${n === i ? "w-6 bg-tl-yellow" : "w-2 bg-white/40 hover:bg-white/70"}`} />
          ))}
        </div>
        <button type="button" className={DUGME} disabled={i === adet - 1} onClick={() => git(i + 1)}>
          {t.sonrakiSlayt}
          <ChevronRight aria-hidden className="size-4" />
        </button>
      </footer>
    </div>
  )
}
