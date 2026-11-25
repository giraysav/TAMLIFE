import { Gauge, ListChecks, Network } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Sekmeler } from "@/components/sayfa-ui"
import type { SekmeSecenegi } from "@/components/sayfa-ui"
import { sorguAyarla, useHashSorgu } from "@/shell/rota"
import { DisBetikAlani } from "@/yonetim/ui"
import { Kriterler } from "@/yonetim/utilizasyon/kriterler"
import { MusteriListesi } from "@/yonetim/utilizasyon/musteri-listesi"
import { UtilOzet } from "@/yonetim/utilizasyon/ozet"
import { uym } from "@/yonetim/utilizasyon/metin"

const SEKMELER = ["ozet", "kriterler", "puanlama"] as const
type Sekme = (typeof SEKMELER)[number]

/** 2026-11-21 sadelestirme: Musteri Listesi, Toplu atama, Skor agaci, Iptal ve Onay talepleri tek "Puanlama"da; eski adresler oraya acilir. */
const ESKI_SEKME: Record<string, Sekme> = { musteriler: "puanlama", atama: "puanlama", agac: "puanlama", iptal: "puanlama", talepler: "puanlama" }

/** TAM Utilizasyon: Ozet, Kriterler, Puanlama. Secili alt sekme adreste: #/yonetim/utilizasyon?sekme=kriterler.
 *  Puanlama (personele gore gruplu liste, kriter dokumu) public/util-puanlama.js'tir; musteri ekle/sil altta katlanir bolumde. */
export default function Utilizasyon({ dil }: { dil: Dil }) {
  const t = uym(dil)
  const u = t.util
  const sorgu = useHashSorgu()
  const ham = sorgu.get("sekme") ?? ""
  const sekme: Sekme = (SEKMELER as readonly string[]).includes(ham) ? (ham as Sekme) : (ESKI_SEKME[ham] ?? "ozet")

  const secenekler: SekmeSecenegi<Sekme>[] = [
    { id: "ozet", etiket: u.sekme.ozet, ikon: Gauge },
    { id: "kriterler", etiket: u.sekme.kriterler, ikon: ListChecks },
    { id: "puanlama", etiket: u.sekme.puanlama, ikon: Network },
  ]

  return (
    <div className="grid gap-4">
      <Sekmeler etiket={u.sekmeNav} secenekler={secenekler} deger={sekme} onDegis={(id) => sorguAyarla("yonetim/utilizasyon", { sekme: id === "ozet" ? null : id })} />
      {sekme === "ozet" ? (
        <UtilOzet dil={dil} />
      ) : sekme === "kriterler" ? (
        <Kriterler dil={dil} />
      ) : (
        <div className="grid gap-4">
          <DisBetikAlani betik="TamlifeUtilPuanlama" dil={dil} yuklenemedi={t.disBilesenYuklenemedi} />
          <details className="rounded-xl border border-slate-200 bg-white p-4">
            <summary className="cursor-pointer text-sm font-black text-tl-navy">{u.musteriEkleSil}</summary>
            <div className="mt-3">
              <MusteriListesi dil={dil} />
            </div>
          </details>
        </div>
      )}
    </div>
  )
}
