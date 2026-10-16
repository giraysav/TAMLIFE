import { useQuery } from "@tanstack/react-query"
import type { LucideIcon } from "lucide-react"
import { Circle, Gauge, Users } from "lucide-react"
import type { ReactNode } from "react"
import { HataKutu, Panel, Yukleniyor } from "@/components/sayfa-ui"
import { hataMesaji, oku } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"
import { IKON } from "@/shell/ikon"
import { ekipMetin } from "@/ekip/ekip-metin"

type OnemliIs = { id: number; baslik: string; oncelik: string; hedef: string | null }
export type EkipSatiri = {
  id: number
  ad: string
  bugun: string | null
  bugun_ad: string
  musteri: number
  rapor_atilan: number
  rapor_beklenen: number
  uyum: number
  risk: number
  risk_puani: number
  risk_orani: number
  riskli_utilizasyon: number | null
  puanlama_disi: boolean
  final_skor: number | null
  agirlik_puani: number | null
  online: number
  yuzyuze: number
  proje_acik: number
  onemli_isler: OnemliIs[]
  cumle: string
}
export type Ton = "mavi" | "sari" | "kirmizi" | "yesil" | "amber" | "gri"
/** Menudeki bir modulun ozet kutusu (sunucu ekip/moduller.py): ana sayi + kisa alt satir; deger null = veri yok. */
export type ModulKutusu = { id: string; ad: string; ikon: string; deger: number | string | null; alt: string; ton: Ton }
export type EkipOzetVeri = {
  tarih: string
  kapsam: "ekip" | "kendi"
  risk_var: boolean
  cumle: string | null
  sayilar: { kisi: number; kritik_uyum: number; yuksek_risk: number; acik_proje: number }
  satirlar: EkipSatiri[]
  moduller?: ModulKutusu[]
  esikler: { kritik_uyum: number; yuksek_risk: number }
}

const sayiYaz = (n: number) => String(Math.round(n * 10) / 10).replace(".", ",")
const topla = (satirlar: EkipSatiri[], al: (s: EkipSatiri) => number) => satirlar.reduce((t, s) => t + al(s), 0)

const TON: Record<Ton, string> = {
  mavi: "border-l-tl-blue",
  sari: "border-l-tl-yellow",
  kirmizi: "border-l-rose-500",
  yesil: "border-l-emerald-500",
  amber: "border-l-amber-500",
  gri: "border-l-slate-300",
}
const IKON_TON: Record<Ton, string> = {
  mavi: "bg-tl-blue/10 text-tl-blue",
  sari: "bg-tl-yellow/30 text-tl-navy",
  kirmizi: "bg-rose-500/10 text-rose-600",
  yesil: "bg-emerald-500/10 text-emerald-600",
  amber: "bg-amber-500/15 text-amber-700",
  gri: "bg-slate-200/60 text-slate-600",
}

/** Kucuk ozet karosu: ikon + etiket ustte, deger, tek satir alt bilgi (tasarsa ucu kesilir, tamami ipucunda). Tiklanirsa modul acilir. */
function Karo({ etiket, deger, alt, ikon: Ikon, ton, sans, ipucu, onClick }: { etiket: string; deger: ReactNode; alt?: string; ikon: LucideIcon; ton: Ton; sans?: boolean; ipucu?: string; onClick?: () => void }) {
  const uzun = typeof deger === "string" && deger.length > 8
  const icerik = (
    <>
      <span className="flex min-w-0 items-center gap-1.5">
        <span aria-hidden className={`grid size-5 shrink-0 place-items-center rounded-md ${IKON_TON[ton]}`}>
          <Ikon className="size-3" />
        </span>
        <span className="truncate text-[0.6875rem] font-extrabold text-slate-600">{etiket}</span>
      </span>
      <span className={`mt-1 block truncate font-black leading-tight text-tl-navy ${sans ? "font-sans" : "font-mono"} ${uzun ? "text-base" : "text-xl"}`}>{deger}</span>
      {alt ? <span className="mt-0.5 block truncate text-[0.625rem] font-bold text-slate-500">{alt}</span> : null}
    </>
  )
  const sinif = `block w-full min-w-0 rounded-xl border border-l-4 border-slate-200 bg-white px-2.5 py-1.5 text-left shadow-sm ${TON[ton]}`
  const baslik = ipucu ?? (alt ? `${etiket}: ${alt}` : etiket)
  return onClick ? (
    <button type="button" title={baslik} onClick={onClick} className={`${sinif} transition hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow`}>
      {icerik}
    </button>
  ) : (
    <div title={baslik} className={sinif}>
      {icerik}
    </div>
  )
}

/**
 * Genel Bakis > Ekip Ozeti (uretim 'TAM Ozet'; ayri modul degil). Ilk iki karo ekibin kendisi (TAM, riskli utilizasyon), ardindan
 * kullanicinin menusundeki modullerin ozet karosu (menu sirasi, sunucu ekip/moduller.OZETTE_YOK haric; tiklaninca modul acilir). Kisi bazli satir ve tablo yoktur.
 * Karo sayisi arttikca ust bolumdeki Teknocan gorseli kalan yuksekligi doldurdugu icin kendiliginden kuculur (sayfa kaymaz).
 */
export function EkipOzeti({ dil, onGit }: { dil: Dil; onGit?: (id: string) => void }) {
  const t = ekipMetin(dil)
  const q = useQuery({ queryKey: ["ekip-ozet"], queryFn: () => oku<EkipOzetVeri>("/api/v1/ekip/ozet") })

  if (q.isPending) return <Panel baslik={t.baslik}><Yukleniyor metin={t.yukleniyor} /></Panel>
  if (q.isError) return <Panel baslik={t.baslik}><HataKutu metin={hataMesaji(q.error, t.yuklenemedi)} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} /></Panel>

  const v = q.data
  const kendi = v.kapsam === "kendi"
  const { sayilar, esikler, satirlar } = v
  const puanli = satirlar.filter((s) => !s.puanlama_disi && s.agirlik_puani !== null)
  const utilizasyon = puanli.length ? topla(puanli, (s) => s.agirlik_puani ?? 0) / puanli.length : null
  // Risk + utilizasyon tek kutu (2026-10-14): riskli utilizasyon = U x (1 + p), p = R / (R + E) (sunucu ekip/servis.py); ekipte ortalama
  const riskli = puanli.filter((s) => s.riskli_utilizasyon !== null)
  const riskliOrt = riskli.length ? topla(riskli, (s) => s.riskli_utilizasyon ?? 0) / riskli.length : null
  const riskOrani = riskli.length ? topla(riskli, (s) => s.risk_orani) / riskli.length : 0
  const cumle = kendi ? satirlar[0]?.cumle : v.cumle
  return (
    <Panel baslik={kendi ? t.baslikKendi : t.baslik} aciklama={kendi ? t.aciklamaKendi : t.aciklama} sinif="w-full shrink-0" govdeSinif="grid gap-2 p-2.5">
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-5" aria-label={t.kutularEtiket}>
        <li>
          <Karo sans={kendi} etiket={t.kisi} deger={kendi ? (satirlar[0]?.ad ?? "—") : sayilar.kisi} ikon={Users} ton="mavi" alt={kendi ? undefined : t.kisiAlt} />
        </li>
        <li>
          <Karo
            etiket={t.kolSkorRisk}
            deger={v.risk_var ? (riskliOrt === null ? "—" : sayiYaz(riskliOrt)) : utilizasyon === null ? "—" : sayiYaz(utilizasyon)}
            ikon={Gauge}
            ton={v.risk_var && sayilar.yuksek_risk ? "kirmizi" : "mavi"}
            alt={v.risk_var ? t.skorRiskAlt(utilizasyon === null ? "—" : sayiYaz(utilizasyon), Math.round(riskOrani * 100), topla(satirlar, (s) => s.risk)) : t.riskVeriYok}
            ipucu={t.formul(esikler.yuksek_risk)}
          />
        </li>
        {(v.moduller ?? []).map((k) => (
          <li key={k.id}>
            <Karo
              etiket={k.ad}
              deger={k.deger === null ? "—" : k.deger}
              alt={k.alt}
              ikon={IKON[k.ikon] ?? Circle}
              ton={k.ton}
              onClick={onGit ? () => onGit(k.id) : undefined}
            />
          </li>
        ))}
      </ul>
      {cumle ? <p className="hidden rounded-xl bg-tl-blue/5 px-3 py-1.5 text-xs font-bold text-tl-navy [@media(min-height:900px)]:block">{cumle}</p> : null}
    </Panel>
  )
}
