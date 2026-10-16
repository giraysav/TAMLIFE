import type { LucideIcon } from "lucide-react"
import {
  BarChart3,
  CalendarDays,
  Database,
  FileText,
  Inbox,
  Layers,
  Link2,
  MessageSquare,
  Network,
  Presentation,
  Radar,
  Settings,
  ShieldCheck,
  Store,
  Users,
} from "lucide-react"

/** Sunucunun menu ogesine verdigi ikon adi -> bilesen. */
export const IKON: Record<string, LucideIcon> = {
  customers: Users,
  team: Users,
  calendar: CalendarDays,
  inbox: Inbox,
  chart: BarChart3,
  shield: ShieldCheck,
  message: MessageSquare,
  file: FileText,
  layers: Layers,
  network: Network,
  presentation: Presentation,
  radar: Radar,
  link: Link2,
  database: Database,
  settings: Settings,
  store: Store,
}
