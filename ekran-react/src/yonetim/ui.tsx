import { Component } from "react"
import type { ReactNode } from "react"
import { CircleCheck, CircleX, TriangleAlert } from "lucide-react"
import { DUGME, Rozet } from "@/components/sayfa-ui"
import type { Durum3 } from "@/yonetim/api"
import type { YM } from "@/yonetim/metin"

/** Yonetime ozgu ogeler; ortak olanlar components/sayfa-ui'da. */

const TON_SINIF = {
  ok: "border-l-emerald-500",
  uyari: "border-l-amber-500",
  hata: "border-l-rose-500",
  notr: "border-l-tl-blue",
} as const

/** Tek degerli gosterge karti; `href` verilirse ilgili bolume gider. Renk tek basina anlam tasimaz (metin + deger de var). */
export function Gosterge({ etiket, deger, alt, ton = "notr", href }: { etiket: string; deger: ReactNode; alt?: ReactNode; ton?: keyof typeof TON_SINIF; href?: string }) {
  const govde = (
    <div className={`h-full rounded-xl border border-l-4 border-slate-200 bg-white p-3 shadow-sm ${TON_SINIF[ton]} ${href ? "transition-colors hover:bg-slate-50" : ""}`}>
      <div className="text-[0.625rem] font-black uppercase tracking-wide text-slate-400">{etiket}</div>
      <div className="mt-0.5 font-mono text-2xl font-black leading-tight text-tl-navy">{deger}</div>
      {alt ? <div className="mt-1 text-[0.6875rem] font-bold text-slate-500">{alt}</div> : null}
    </div>
  )
  return href ? (
    <a href={href} className="block rounded-xl focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow">
      {govde}
    </a>
  ) : (
    govde
  )
}

const DURUM_IKON = { ok: CircleCheck, uyari: TriangleAlert, hata: CircleX } as const
const DURUM_TON = { ok: "yesil", uyari: "amber", hata: "kirmizi" } as const

/** Renk + ikon + metin: renk koru de anlasilir. */
export function DurumRozeti({ durum, t }: { durum: Durum3; t: YM }) {
  const Ikon = DURUM_IKON[durum]
  return (
    <Rozet ton={DURUM_TON[durum]}>
      <span className="inline-flex items-center gap-1">
        <Ikon aria-hidden className="size-3" />
        {t.durumEtiket[durum]}
      </span>
    </Rozet>
  )
}

export function Sayfalama({ t, sayfa, adet, toplam, onSayfa }: { t: YM; sayfa: number; adet: number; toplam: number; onSayfa: (sayfa: number) => void }) {
  const son = Math.max(1, Math.ceil(toplam / adet))
  if (toplam <= adet) return null
  return (
    <nav aria-label={t.sayfaBilgi(sayfa, son, toplam)} className="flex items-center justify-between gap-2 text-xs font-bold text-slate-500">
      <span>{t.sayfaBilgi(sayfa, son, toplam)}</span>
      <span className="flex gap-2">
        <button type="button" className={DUGME} disabled={sayfa <= 1} onClick={() => onSayfa(sayfa - 1)}>
          {t.onceki}
        </button>
        <button type="button" className={DUGME} disabled={sayfa >= son} onClick={() => onSayfa(sayfa + 1)}>
          {t.sonraki}
        </button>
      </span>
    </nav>
  )
}

/** Yuklenen alt bolum cokerse (ag, eski onbellek) tum uygulama dusmesin. */
export class HataSiniri extends Component<{ children: ReactNode; mesaj: string }, { hata: boolean }> {
  state = { hata: false }
  static getDerivedStateFromError() {
    return { hata: true }
  }
  render() {
    return this.state.hata ? (
      <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs font-bold text-rose-700">
        {this.props.mesaj}
      </p>
    ) : (
      this.props.children
    )
  }
}
