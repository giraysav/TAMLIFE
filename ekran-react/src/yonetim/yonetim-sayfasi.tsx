import { lazy, Suspense } from "react"
import type { ComponentType, ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import { Activity, ChartColumn, Database, Network, ShieldCheck, TriangleAlert } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import type { MenuOgesi } from "@/lib/oturum"
import type { Dil } from "@/shell/metin"
import { ANAHTAR } from "@/yonetim/api"
import { oku } from "@/lib/sorgu"
import type { Ozet } from "@/yonetim/api"
import { ym } from "@/yonetim/metin"
import { DisBetikAlani, HataSiniri } from "@/yonetim/ui"
import { Yukleniyor } from "@/components/sayfa-ui"

/** Her bolum ayri JS parcasidir: Yonetim yalniz admin acinca indirilir, diger kullanicilarin ilk yuklemesini sismirmez. */
const Tampon = lazy(() => import("@/yonetim/bolumler/tampon"))
const UrunTutar = lazy(() => import("@/yonetim/utilizasyon/urun-tutar").then((m) => ({ default: m.UrunTutar })))
const Arizalar = lazy(() => import("@/yonetim/bolumler/arizalar"))
const Gunlukler = lazy(() => import("@/yonetim/bolumler/gunlukler"))

/** Birlesik bolumde ikinci alt bolum: ayirici cizgi + baslik. */
function AltBolum({ baslik, children }: { baslik: string; children: ReactNode }) {
  return (
    <section className="grid gap-3 border-t border-slate-200 pt-6">
      <h2 className="text-base font-black text-tl-navy">{baslik}</h2>
      {children}
    </section>
  )
}

/** Veri Kaynaklari (2026-11-21): Veri Ozeti (public/veri-ozeti.js) + Urun-Tutar yuklemeleri, altta Veri Girisi (tampon, analiz, dagitim). */
function VeriKaynaklari({ dil }: { dil: Dil }) {
  const t = ym(dil)
  return (
    <div className="grid gap-8">
      <div className="grid gap-6">
        <DisBetikAlani betik="TamlifeVeriOzeti" dil={dil} yuklenemedi={t.disBilesenYuklenemedi} />
        <section className="grid gap-3">
          <h2 className="text-base font-black text-tl-navy">{t.urunTutarYuklemeleri}</h2>
          <UrunTutar dil={dil} />
        </section>
      </div>
      <AltBolum baslik={t.veriGirisiBaslik}>
        <Tampon dil={dil} />
      </AltBolum>
    </div>
  )
}

/** Kayitlar (2026-11-21): Arizalar, altta Gunlukler. */
function Kayitlar({ dil }: { dil: Dil }) {
  const t = ym(dil)
  return (
    <div className="grid gap-8">
      <Arizalar dil={dil} />
      <AltBolum baslik={t.bolumler.gunlukler}>
        <Gunlukler dil={dil} />
      </AltBolum>
    </div>
  )
}

const BOLUMLER = {
  durum: { ikon: Activity, bilesen: lazy(() => import("@/yonetim/bolumler/durum")) },
  utilizasyon: { ikon: ChartColumn, bilesen: lazy(() => import("@/yonetim/bolumler/utilizasyon")) },
  veri: { ikon: Database, bilesen: VeriKaynaklari },
  kurum: { ikon: Network, bilesen: lazy(() => import("@/yonetim/bolumler/kurum")) },
  veritabani: { ikon: Database, bilesen: lazy(() => import("@/yonetim/bolumler/veritabani")) },
  roller: { ikon: ShieldCheck, bilesen: lazy(() => import("@/yonetim/bolumler/roller")) },
  arizalar: { ikon: TriangleAlert, bilesen: Kayitlar },
} satisfies Record<string, { ikon: LucideIcon; bilesen: ComponentType<{ dil: Dil }> }>

export type BolumKimligi = keyof typeof BOLUMLER
const SIRA = Object.keys(BOLUMLER) as BolumKimligi[]
/** Birlesen bolumlerin eski adresleri (#/yonetim/tampon, #/yonetim/gunlukler) birlesik bolume acilir. */
const ESKI_BOLUM: Record<string, BolumKimligi> = { tampon: "veri", gunlukler: "arizalar" }

export function bolumMu(deger: string): deger is BolumKimligi {
  return deger in BOLUMLER
}

/** Yonetim: tek giris, yedi bolum. Adres #/yonetim/<bolum>; bolum yoksa (ya da izinli degilse) ilk izinli bolum, o da yoksa Genel Durum.
 *  `izinli` (admin olmayan, orn. yalniz TAM Utilizasyon yetkili rol) verilirse sekmelerde yalniz o bolumler listelenir; admin icin hepsi. */
export default function YonetimSayfasi({ dil, bolum, digerleri, izinli }: { dil: Dil; bolum: string; digerleri: MenuOgesi[]; izinli?: string[] }) {
  const t = ym(dil)
  const istenen = ESKI_BOLUM[bolum] ?? bolum
  const liste = izinli ? SIRA.filter((id) => izinli.includes(id)) : SIRA
  const aktif: BolumKimligi = bolumMu(istenen) && liste.includes(istenen) ? istenen : (liste[0] ?? "durum")
  const Bilesen = BOLUMLER[aktif].bilesen
  // Sekme rozeti: acik ariza sayisi (Genel Durum ile ayni onbellek girdisi; ek istek yok).
  const ozet = useQuery({ queryKey: ANAHTAR.ozet, queryFn: () => oku<Ozet>("/api/v1/yonetim/ozet"), refetchInterval: 60_000 })
  const acikAriza = ozet.data?.gostergeler.ariza.acik ?? 0

  return (
    <div className="grid gap-4">
      <nav aria-label={t.bolumNav} className="-mx-1 overflow-x-auto px-1 pb-1">
        <ul className="flex min-w-max gap-1.5">
          {liste.map((id) => {
            const { ikon: Ikon } = BOLUMLER[id]
            const secili = id === aktif
            return (
              <li key={id}>
                <a
                  href={`#/yonetim/${id}`}
                  aria-current={secili ? "page" : undefined}
                  className={`inline-flex min-h-9 items-center gap-1.5 rounded-lg border px-3 text-xs font-black transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow ${
                    secili ? "border-tl-navy bg-tl-navy text-white shadow-sm" : "border-slate-200 bg-white text-tl-navy hover:bg-slate-50"
                  }`}
                >
                  <Ikon aria-hidden className="size-3.5" />
                  {t.bolumler[id]}
                  {id === "arizalar" && acikAriza > 0 ? (
                    <span className="rounded-full bg-rose-500 px-1.5 text-[0.625rem] leading-4 text-white" aria-label={`${acikAriza} ${t.durumlar.open}`}>
                      {acikAriza}
                    </span>
                  ) : null}
                </a>
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="min-w-0">
        <h2 className="text-base font-black text-tl-navy">{t.bolumler[aktif]}</h2>
        <p className="mt-0.5 text-xs font-bold text-slate-500">{t.bolumAciklama[aktif]}</p>
      </div>

      <HataSiniri key={aktif} mesaj={t.panelHatasi}>
        <Suspense fallback={<Yukleniyor metin={t.yukleniyor} iskelet />}>
          <Bilesen dil={dil} />
        </Suspense>
      </HataSiniri>

      {digerleri.length > 0 ? (
        <p className="text-[0.6875rem] font-bold text-slate-400">
          {t.digerAlanlar}:{" "}
          {digerleri.map((o, i) => (
            <span key={o.id}>
              {i > 0 ? " · " : ""}
              <a className="text-tl-blue underline-offset-2 hover:underline" href={`#/${o.id}`}>
                {o.label}
              </a>
            </span>
          ))}
        </p>
      ) : null}
    </div>
  )
}
