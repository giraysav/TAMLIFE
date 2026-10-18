import { useQuery } from "@tanstack/react-query"
import { BellRing, Calculator, FileSpreadsheet, Gauge, ListChecks, Network, Users } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Sekmeler } from "@/components/sayfa-ui"
import type { SekmeSecenegi } from "@/components/sayfa-ui"
import { sorguAyarla, useHashSorgu } from "@/shell/rota"
import { ANAHTAR } from "@/yonetim/api"
import type { SkorTalebi } from "@/yonetim/api"
import { oku } from "@/lib/sorgu"
import { SkorAgaciBolumu } from "@/yonetim/utilizasyon/agac"
import { TopluAtama } from "@/yonetim/utilizasyon/atama"
import { Kriterler } from "@/yonetim/utilizasyon/kriterler"
import { MusteriListesi } from "@/yonetim/utilizasyon/musteri-listesi"
import { UtilOzet } from "@/yonetim/utilizasyon/ozet"
import { Talepler } from "@/yonetim/utilizasyon/talepler"
import { UrunTutar } from "@/yonetim/utilizasyon/urun-tutar"
import { uym } from "@/yonetim/utilizasyon/metin"

const SEKMELER = ["ozet", "kriterler", "atama", "agac", "talepler", "veri", "musteriler"] as const
type Sekme = (typeof SEKMELER)[number]

/** TAM Utilizasyon (uretim Final Skoru Atama + Veri Yonlendirici kriter/agac ekranlari). Secili alt sekme adreste: #/yonetim/utilizasyon?sekme=kriterler. */
export default function Utilizasyon({ dil }: { dil: Dil }) {
  const u = uym(dil).util
  const sorgu = useHashSorgu()
  const ham = sorgu.get("sekme") ?? ""
  const sekme: Sekme = (SEKMELER as readonly string[]).includes(ham) ? (ham as Sekme) : "ozet"
  const talepler = useQuery({ queryKey: ANAHTAR.skorTalepler, queryFn: () => oku<{ count: number; requests: SkorTalebi[] }>("/api/v1/skor/talepler") })
  const bekleyen = talepler.data?.count ?? 0

  const secenekler: SekmeSecenegi<Sekme>[] = [
    { id: "ozet", etiket: u.sekme.ozet, ikon: Gauge },
    { id: "kriterler", etiket: u.sekme.kriterler, ikon: ListChecks },
    { id: "atama", etiket: u.sekme.atama, ikon: Calculator },
    { id: "agac", etiket: u.sekme.agac, ikon: Network },
    { id: "talepler", etiket: u.sekme.talepler, ikon: BellRing, sayi: bekleyen > 0 ? bekleyen : undefined },
    { id: "veri", etiket: u.sekme.veri, ikon: FileSpreadsheet },
    { id: "musteriler", etiket: u.sekme.musteriler, ikon: Users },
  ]

  return (
    <div className="grid gap-4">
      <Sekmeler etiket={u.sekmeNav} secenekler={secenekler} deger={sekme} onDegis={(id) => sorguAyarla("yonetim/utilizasyon", { sekme: id === "ozet" ? null : id })} />
      {sekme === "ozet" ? (
        <UtilOzet dil={dil} />
      ) : sekme === "kriterler" ? (
        <Kriterler dil={dil} />
      ) : sekme === "atama" ? (
        <TopluAtama dil={dil} />
      ) : sekme === "agac" ? (
        <SkorAgaciBolumu dil={dil} />
      ) : sekme === "talepler" ? (
        <Talepler dil={dil} />
      ) : sekme === "musteriler" ? (
        <MusteriListesi dil={dil} />
      ) : (
        <UrunTutar dil={dil} />
      )}
    </div>
  )
}
