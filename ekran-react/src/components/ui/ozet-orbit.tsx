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
  ShieldCheck,
  TrendingUp,
  Truck,
  Users,
  Wifi,
} from "lucide-react"
import CommunityOrbit from "@/components/ui/community-orbit"
import type { OrbitItem, OrbitStat, OrbitTag } from "@/components/ui/community-orbit"

type Kart = { key: string; title: string }

const IKON: Record<string, LucideIcon> = {
  ekip: Users,
  takvim_ozet: CalendarDays,
  takvim: CalendarDays,
  sunum: Presentation,
  radar: Radar,
  musteri: Briefcase,
  rapor: FileText,
  proje: FolderKanban,
  onedesk: LifeBuoy,
  toptan: Truck,
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

async function getir<T>(yol: string): Promise<T | null> {
  try {
    const cevap = await fetch(yol, { credentials: "same-origin" })
    if (!cevap.ok) return null
    return ((await cevap.json()) as { data: T }).data
  } catch {
    return null
  }
}

type Props = {
  dil: "tr" | "en"
  admin: boolean
  onGit: (id: string) => void
}

export function OzetOrbit({ dil, admin, onGit }: Props) {
  const [kartlar, setKartlar] = useState<Kart[]>([])
  const [sayilar, setSayilar] = useState({ modul: 0, tablo: 0, kaynak: 0 })

  useEffect(() => {
    let iptal = false
    void Promise.all([
      getir<Kart[]>("/api/v1/home"),
      getir<{ modules: number; tables: number; external_sources: number }>("/api/v1/summary"),
    ]).then(([home, ozet]) => {
      if (iptal) return
      setKartlar(home ?? [])
      setSayilar({
        modul: ozet?.modules ?? 0,
        tablo: ozet?.tables ?? 0,
        kaynak: ozet?.external_sources ?? 0,
      })
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
  const stats: OrbitStat[] = [
    { value: String(sayilar.modul), label: tr ? "Modül" : "Modules" },
    { value: String(kartlar.length), label: tr ? "Ana sayfa kartı" : "Home cards" },
    { value: String(sayilar.tablo), label: tr ? "Panel tablosu" : "Panel tables" },
    { value: String(sayilar.kaynak), label: tr ? "Dış kaynak" : "External sources" },
  ]
  const tags: OrbitTag[] = admin
    ? [
        { icon: <ShieldCheck aria-hidden />, label: tr ? "Yönetim" : "Admin", onClick: () => onGit("admin") },
        { icon: <Users aria-hidden />, label: tr ? "Rol yönetimi" : "Roles", onClick: () => onGit("rol") },
      ]
    : []

  return (
    <CommunityOrbit
      items={items}
      stats={stats}
      tags={tags}
      headline={tr ? "TAM Life tek panelde, tüm modüller bir arada." : "TAM Life in one panel, every module together."}
    />
  )
}
