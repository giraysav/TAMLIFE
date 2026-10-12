import { useQuery } from "@tanstack/react-query"
import type { LucideIcon } from "lucide-react"
import { Briefcase, CalendarCheck, CalendarDays, Circle, FileText, FolderKanban, LifeBuoy, Link2, MessageSquare, Presentation, Radar, TrendingUp, Wifi } from "lucide-react"
import teknocan from "@/assets/teknocan.png"
import { oku } from "@/lib/sorgu"
import { ModulYayi } from "@/components/ui/modul-yayi"
import type { YayOgesi } from "@/components/ui/modul-yayi"

type Kart = { key: string; title: string; title_en?: string }

const IKON: Record<string, LucideIcon> = {
  takvim_ozet: CalendarCheck,
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

/** Modul rengi: [acik, koyu] gradyan. Renk tek basina anlam tasimaz (etiket her zaman gorunur). */
const RENK: Record<string, readonly [string, string]> = {
  takvim_ozet: ["#34d399", "#059669"],
  takvim: ["#2dd4bf", "#0d9488"],
  sunum: ["#818cf8", "#4f46e5"],
  radar: ["#a78bfa", "#7c3aed"],
  musteri: ["#3b82f6", "#0055a5"],
  rapor: ["#38bdf8", "#0284c7"],
  proje: ["#5eead4", "#0f766e"],
  onedesk: ["#fb7185", "#e11d48"],
  tamsms: ["#fbbf24", "#d97706"],
  tamapn: ["#22d3ee", "#0891b2"],
  gelir_uretim: ["#facc15", "#ca8a04"],
  baglantili: ["#94a3b8", "#475569"],
}
const VARSAYILAN_RENK: readonly [string, string] = ["#64748b", "#334155"]

/** Genel Bakis: yaydaki kartlar rolun gorebildigi ana sayfa kartlaridir (/home); kart tiklaninca ilgili module gider. */
export function OzetOrbit({ dil, onGit }: { dil: "tr" | "en"; onGit: (id: string) => void }) {
  const { data: kartlar = [] } = useQuery({ queryKey: ["home"], queryFn: () => oku<Kart[]>("/api/v1/home") })

  const ogeler: YayOgesi[] = kartlar.slice(0, 12).map((kart) => {
    const Ikon = IKON[kart.key] ?? Circle
    const etiket = dil === "en" ? kart.title_en || kart.title : kart.title
    return { anahtar: kart.key, etiket, ikon: <Ikon aria-hidden />, renk: RENK[kart.key] ?? VARSAYILAN_RENK, onClick: () => onGit(kart.key) }
  })

  return (
    <ModulYayi
      ogeler={ogeler}
      alt={
        <div className="relative flex h-full w-full items-end justify-center">
          <span aria-hidden className="absolute inset-x-[-18%] bottom-[-3%] h-[9%] rounded-[50%] bg-tl-navy/15 blur-[3px]" />
          <img
            src={teknocan}
            alt="Teknocan"
            draggable={false}
            className="relative h-full w-auto max-w-full select-none object-contain drop-shadow-[0_8px_10px_rgba(0,40,85,0.2)]"
          />
        </div>
      }
    />
  )
}
