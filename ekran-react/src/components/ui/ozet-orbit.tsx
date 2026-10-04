import { useEffect, useState } from "react"
import type { LucideIcon } from "lucide-react"
import {
  Briefcase,
  CalendarDays,
  Circle,
  FileText,
  FolderKanban,
  LifeBuoy,
  Link2,
  MessageSquare,
  Presentation,
  Radar,
  TrendingUp,
  Wifi,
} from "lucide-react"
import { apiGet } from "@/lib/oturum"
import CommunityOrbit from "@/components/ui/community-orbit"
import type { OrbitItem } from "@/components/ui/community-orbit"

type Kart = { key: string; title: string }

const IKON: Record<string, LucideIcon> = {
  takvim_ozet: CalendarDays,
  takvim: CalendarDays,
  sunum: Presentation,
  radar: Radar,
  musteri: Briefcase,
  rapor: FileText,
  proje: FolderKanban,
  onedesk: LifeBuoy,
  tamsms: MessageSquare,
  tamapn: Wifi,
  gelir_uretim: TrendingUp,
  baglantili: Link2,
}

const DIS = [
  { ring: "outer", angle: 156 },
  { ring: "outer", angle: 138 },
  { ring: "outer", angle: 120 },
  { ring: "outer", angle: 102 },
  { ring: "outer", angle: 84 },
  { ring: "outer", angle: 66 },
  { ring: "outer", angle: 48 },
  { ring: "outer", angle: 30 },
] as const

const IC = [
  { ring: "inner", angle: 148 },
  { ring: "inner", angle: 124 },
  { ring: "inner", angle: 100 },
  { ring: "inner", angle: 76 },
  { ring: "inner", angle: 52 },
  { ring: "inner", angle: 32 },
] as const

const YER = [...DIS, ...IC]

/** Genel Bakis: tek parca. Yaydaki modul adlari rolun gorebildigi ana sayfa kartlaridir (/home). */
export function OzetOrbit({ dil }: { dil: "tr" | "en" }) {
  const [kartlar, setKartlar] = useState<Kart[]>([])

  useEffect(() => {
    let iptal = false
    void apiGet<Kart[]>("/api/v1/home").then((home) => {
      if (!iptal) setKartlar(home ?? [])
    })
    return () => {
      iptal = true
    }
  }, [])

  const tr = dil === "tr"
  const items: OrbitItem[] = kartlar.slice(0, YER.length).map((kart, i) => {
    const Ikon = IKON[kart.key] ?? Circle
    return { kind: "pill", icon: <Ikon aria-hidden />, label: kart.title, ...YER[i] }
  })

  return (
    <CommunityOrbit
      items={items}
      stats={[]}
      headline={tr ? "TAM Life tek panelde, tüm modüller bir arada." : "TAM Life in one panel, every module together."}
    />
  )
}
