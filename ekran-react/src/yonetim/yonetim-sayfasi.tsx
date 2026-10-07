import { Suspense, lazy } from "react"
import { useQuery } from "@tanstack/react-query"
import { Activity, ArrowDownToLine, Database, ScrollText, ShieldCheck, TriangleAlert } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import type { MenuOgesi } from "@/lib/oturum"
import type { Dil } from "@/shell/metin"
import { ANAHTAR, oku } from "@/yonetim/api"
import type { Ozet } from "@/yonetim/api"
import { ym } from "@/yonetim/metin"
import { HataSiniri, SayfaBasligi, Yukleniyor } from "@/yonetim/ui"

/** Her bolum ayri JS parcasidir: Yonetim yalniz admin acinca indirilir, diger kullanicilarin ilk yuklemesini sismirmez. */
const BOLUMLER = {
  durum: { ikon: Activity, bilesen: lazy(() => import("@/yonetim/bolumler/durum")) },
  tampon: { ikon: ArrowDownToLine, bilesen: lazy(() => import("@/yonetim/bolumler/tampon")) },
  veritabani: { ikon: Database, bilesen: lazy(() => import("@/yonetim/bolumler/veritabani")) },
  roller: { ikon: ShieldCheck, bilesen: lazy(() => import("@/yonetim/bolumler/roller")) },
  arizalar: { ikon: TriangleAlert, bilesen: lazy(() => import("@/yonetim/bolumler/arizalar")) },
  gunlukler: { ikon: ScrollText, bilesen: lazy(() => import("@/yonetim/bolumler/gunlukler")) },
} satisfies Record<string, { ikon: LucideIcon; bilesen: ReturnType<typeof lazy> }>

export type BolumKimligi = keyof typeof BOLUMLER
const SIRA = Object.keys(BOLUMLER) as BolumKimligi[]

export function bolumMu(deger: string): deger is BolumKimligi {
  return deger in BOLUMLER
}

/** Yonetim (yalniz admin): tek giris, alti bolum. Adres #/yonetim/<bolum>; bolum yoksa Genel Durum. */
export default function YonetimSayfasi({ dil, bolum, digerleri }: { dil: Dil; bolum: string; digerleri: MenuOgesi[] }) {
  const t = ym(dil)
  const aktif: BolumKimligi = bolumMu(bolum) ? bolum : "durum"
  const Bilesen = BOLUMLER[aktif].bilesen
  // Sekme rozeti: acik ariza sayisi (Genel Durum ile ayni onbellek girdisi; ek istek yok).
  const ozet = useQuery({ queryKey: ANAHTAR.ozet, queryFn: () => oku<Ozet>("/api/v1/yonetim/ozet"), refetchInterval: 60_000 })
  const acikAriza = ozet.data?.gostergeler.ariza.acik ?? 0

  return (
    <div className="grid gap-4">
      <nav aria-label={t.bolumNav} className="-mx-1 overflow-x-auto px-1 pb-1">
        <ul className="flex min-w-max gap-1.5">
          {SIRA.map((id) => {
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
                    <span className="rounded-full bg-rose-500 px-1.5 text-[10px] leading-4 text-white" aria-label={`${acikAriza} ${t.durumlar.open}`}>
                      {acikAriza}
                    </span>
                  ) : null}
                </a>
              </li>
            )
          })}
        </ul>
      </nav>

      <SayfaBasligi baslik={t.bolumler[aktif]} aciklama={t.bolumAciklama[aktif]} />

      <HataSiniri key={aktif} mesaj={t.panelHatasi}>
        <Suspense fallback={<Yukleniyor t={t} />}>
          <Bilesen dil={dil} />
        </Suspense>
      </HataSiniri>

      {digerleri.length > 0 ? (
        <p className="text-[11px] font-bold text-slate-400">
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
