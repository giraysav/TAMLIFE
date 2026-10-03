import { useEffect, useMemo, useState } from "react"
import type { LucideIcon } from "lucide-react"
import {
  BarChart3,
  CalendarDays,
  Database,
  FileText,
  Inbox,
  Layers,
  Link2,
  LayoutDashboard,
  MessageSquare,
  Network,
  Presentation,
  Radar,
  Settings,
  ShieldCheck,
  Users,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/app-1-utils/sidebar"
import { OzetOrbit } from "@/components/ui/ozet-orbit"
import type { Kullanici, MenuOgesi } from "@/lib/oturum"
import { AdminSayfasi } from "@/shell/admin-sayfasi"
import { Arama } from "@/shell/arama"
import { EntegrasyonSayfasi } from "@/shell/entegrasyon-sayfasi"
import { VeriSayfasi } from "@/shell/veri-sayfasi"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"
import { ModulSayfasi } from "@/shell/modul-sayfasi"

const IKON: Record<string, LucideIcon> = {
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
}

const GRUPLAR = ["work", "insights", "admin"] as const

function hashId(): string {
  return decodeURIComponent(window.location.hash.replace(/^#\/?/, "")) || "ozet"
}

type Props = {
  kullanici: Kullanici
  dil: Dil
  onDil: (dil: Dil) => void
  onCikis: () => void
}

function Menu({ kullanici, dil, secili, onSec, onCikis }: Props & { secili: string; onSec: (id: string) => void }) {
  const t = metin(dil)
  const { setOpenMobile } = useSidebar()
  const gruplu = useMemo(
    () =>
      GRUPLAR.map((grup) => ({ grup, satirlar: kullanici.navigation.filter((o) => o.group === grup) })).filter(
        (g) => g.satirlar.length > 0,
      ),
    [kullanici.navigation],
  )

  function git(id: string) {
    onSec(id)
    setOpenMobile(false)
  }

  function oge(o: MenuOgesi) {
    const Ikon = IKON[o.icon] ?? LayoutDashboard
    const aktif = secili === o.id
    return (
      <SidebarMenuItem key={o.id}>
        <SidebarMenuButton
          isActive={aktif}
          render={<a href={`#/${o.id}`} aria-current={aktif ? "page" : undefined} onClick={() => git(o.id)} />}
        >
          <Ikon aria-hidden />
          <span>{o.label}</span>
          {!o.ready ? <span className="ml-auto size-1.5 rounded-full bg-muted-foreground/50" title={t.hazirlaniyor} /> : null}
        </SidebarMenuButton>
      </SidebarMenuItem>
    )
  }

  return (
    <Sidebar>
      <SidebarHeader>
        <a href="#/ozet" className="flex min-h-11 items-center gap-2 rounded-lg px-2 font-semibold" onClick={() => git("ozet")}>
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-sm text-primary-foreground">T</span>
          TAM Life
        </a>
      </SidebarHeader>
      <SidebarContent>
        <nav aria-label="TAM Life">
          <SidebarGroup>
            <SidebarGroupLabel>{t.genel}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    isActive={secili === "ozet"}
                    render={<a href="#/ozet" aria-current={secili === "ozet" ? "page" : undefined} onClick={() => git("ozet")} />}
                  >
                    <LayoutDashboard aria-hidden />
                    <span>{t.genelBakis}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
          {gruplu.map(({ grup, satirlar }) => (
            <SidebarGroup key={grup}>
              <SidebarGroupLabel>{t.gruplar[grup]}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>{satirlar.map(oge)}</SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          ))}
        </nav>
      </SidebarContent>
      <SidebarFooter>
        <div className="flex items-center gap-2 px-2 py-1">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium">
            {kullanici.username.slice(0, 2).toUpperCase()}
          </span>
          <span className="min-w-0 flex-1 truncate text-sm font-medium">{kullanici.username}</span>
          <Button type="button" variant="outline" size="sm" onClick={onCikis}>
            {t.cikis}
          </Button>
        </div>
      </SidebarFooter>
    </Sidebar>
  )
}

export function Panel({ kullanici, dil, onDil, onCikis }: Props) {
  const t = metin(dil)
  const [secili, setSecili] = useState(hashId)
  const izinli = useMemo(() => new Set(["ozet", ...kullanici.navigation.map((o) => o.id)]), [kullanici.navigation])
  const aktif = izinli.has(secili) ? secili : "ozet"
  const oge = kullanici.navigation.find((o) => o.id === aktif)

  useEffect(() => {
    const degisti = () => setSecili(hashId())
    window.addEventListener("hashchange", degisti)
    return () => window.removeEventListener("hashchange", degisti)
  }, [])

  useEffect(() => {
    document.documentElement.lang = dil
    document.title = `${oge?.label ?? t.genelBakis} · TAM Life`
  }, [dil, oge, t.genelBakis])

  function sec(id: string) {
    window.location.hash = `#/${id}`
    setSecili(id)
  }

  return (
    <SidebarProvider>
      <Menu kullanici={kullanici} dil={dil} onDil={onDil} onCikis={onCikis} secili={aktif} onSec={sec} />
      <SidebarInset className="min-w-0">
        <header className="sticky top-0 z-10 flex h-16 items-center gap-3 border-b bg-background px-4 sm:px-6">
          <SidebarTrigger aria-label={t.menu} />
          <h1 className="truncate text-lg font-semibold">{aktif === "ozet" ? t.hosgeldin(kullanici.username) : oge?.label}</h1>
          <div className="ml-auto flex items-center gap-2">
            <div className="flex items-center rounded-md border" role="group" aria-label={t.dil}>
              {(["tr", "en"] as const).map((d) => (
                <Button
                  key={d}
                  type="button"
                  size="sm"
                  variant={dil === d ? "default" : "ghost"}
                  className="h-8 px-2 first:rounded-r-none last:rounded-l-none"
                  aria-pressed={dil === d}
                  onClick={() => onDil(d)}
                >
                  {d.toUpperCase()}
                </Button>
              ))}
            </div>
            <Arama ogeler={kullanici.navigation} dil={dil} onGit={sec} />
            <Button type="button" variant="outline" size="sm" onClick={onCikis}>
              {t.cikis}
            </Button>
          </div>
        </header>
        <main className="flex flex-1 flex-col gap-6 p-4 sm:p-6">
          {aktif === "ozet" ? (
            <OzetOrbit dil={dil} admin={kullanici.is_admin} onGit={sec} />
          ) : aktif === "admin" ? (
            <AdminSayfasi dil={dil} />
          ) : aktif === "veri" ? (
            <VeriSayfasi dil={dil} />
          ) : aktif === "integrations" ? (
            <EntegrasyonSayfasi dil={dil} />
          ) : oge ? (
            <ModulSayfasi oge={oge} dil={dil} />
          ) : null}
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
