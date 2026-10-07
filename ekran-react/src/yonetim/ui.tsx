import { Component } from "react"
import type { ReactNode } from "react"
import { CircleCheck, CircleX, TriangleAlert } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { DUGME, Rozet } from "@/components/kart-ui"
import type { Durum3 } from "@/yonetim/api"
import type { YM } from "@/yonetim/metin"

/** Yonetim bolumlerinin ortak ogeleri. Gorsel dil: Musteri Karti ile ayni (kart-ui: lacivert baslik, sari vurgu). */

export function SayfaBasligi({ baslik, aciklama, children }: { baslik: string; aciklama?: string; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-base font-black text-tl-navy">{baslik}</h2>
        {aciklama ? <p className="mt-0.5 text-xs font-bold text-slate-500">{aciklama}</p> : null}
      </div>
      {children ? <div className="flex flex-wrap items-center gap-2">{children}</div> : null}
    </div>
  )
}

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
      <div className="text-[10px] font-black uppercase tracking-wide text-slate-400">{etiket}</div>
      <div className="mt-0.5 font-mono text-2xl font-black leading-tight text-tl-navy">{deger}</div>
      {alt ? <div className="mt-1 text-[11px] font-bold text-slate-500">{alt}</div> : null}
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

export type Kolon<T> = { baslik: string; hucre: (satir: T) => ReactNode; sinif?: string }

/** Basit, erisilebilir tablo (caption sr-only, th scope=col). Satir secimi icin hucreye gercek bir buton/baglanti koyun. */
export function VeriTablosu<T>({
  baslik,
  kolonlar,
  satirlar,
  anahtar,
  vurgulu,
  bos,
}: {
  baslik: string
  kolonlar: Kolon<T>[]
  satirlar: T[]
  anahtar: (satir: T) => string | number
  vurgulu?: (satir: T) => boolean
  bos?: ReactNode
}) {
  if (satirlar.length === 0 && bos) return <>{bos}</>
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full text-left text-xs">
        <caption className="sr-only">{baslik}</caption>
        <thead className="bg-tl-navy text-white">
          <tr>
            {kolonlar.map((k) => (
              <th key={k.baslik} scope="col" className={`whitespace-nowrap px-3 py-2 font-black ${k.sinif ?? ""}`}>
                {k.baslik}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {satirlar.map((s) => (
            <tr key={anahtar(s)} className={vurgulu?.(s) ? "bg-tl-yellow/15" : "hover:bg-slate-50"}>
              {kolonlar.map((k) => (
                <td key={k.baslik} className={`px-3 py-2 font-bold text-slate-700 ${k.sinif ?? ""}`}>
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

export function Yukleniyor({ t }: { t: YM }) {
  return (
    <div role="status" aria-label={t.yukleniyor} className="grid gap-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-20 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-40 rounded-xl" />
    </div>
  )
}

export function HataKutusu({ t, mesaj, onTekrar }: { t: YM; mesaj?: string; onTekrar?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs font-bold text-rose-700">
      <span>{mesaj || t.yuklenemedi}</span>
      {onTekrar ? (
        <button type="button" onClick={onTekrar} className={DUGME}>
          {t.tekrarDene}
        </button>
      ) : null}
    </div>
  )
}

export function Bilgi({ children, ton = "gri" }: { children: ReactNode; ton?: "gri" | "amber" | "yesil" }) {
  const sinif = { gri: "border-slate-200 bg-slate-50 text-slate-600", amber: "border-amber-200 bg-amber-50 text-amber-800", yesil: "border-emerald-200 bg-emerald-50 text-emerald-700" }[ton]
  return (
    <p role="status" className={`rounded-lg border px-3 py-2 text-xs font-bold ${sinif}`}>
      {children}
    </p>
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

/** Etiketli form alani (etiket + kontrol ayni <label> icinde: tiklama ve ekran okuyucu baglantisi). */
export function Alan({ etiket, children, sinif = "" }: { etiket: string; children: ReactNode; sinif?: string }) {
  return (
    <label className={`grid gap-1 ${sinif}`}>
      <span className="text-[10px] font-black uppercase tracking-wide text-slate-400">{etiket}</span>
      {children}
    </label>
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

// --- bicimleyiciler ----------------------------------------------------------------------------------------------------
export function bayt(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—"
  if (n < 1024) return `${n} B`
  const birimler = ["KB", "MB", "GB", "TB"]
  let deger = n / 1024
  let i = 0
  while (deger >= 1024 && i < birimler.length - 1) {
    deger /= 1024
    i += 1
  }
  return `${deger.toLocaleString("tr-TR", { maximumFractionDigits: deger < 10 ? 1 : 0 })} ${birimler[i]}`
}

/** ISO (UTC, 'Z') -> yerel "07.10.2026 14:05". */
export function zamanYaz(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })
}

export function sureYaz(sn: number): string {
  if (sn < 90) return `${sn} sn`
  if (sn < 5400) return `${Math.round(sn / 60)} dk`
  return `${(sn / 3600).toLocaleString("tr-TR", { maximumFractionDigits: 1 })} sa`
}

export function sayi(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : n.toLocaleString("tr-TR")
}
