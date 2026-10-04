import { useEffect, useMemo, useState } from "react"
import { ChevronDown, LayoutDashboard } from "lucide-react"
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
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
import { AnaKartlar } from "@/shell/ana-kartlar"
import { Arama } from "@/shell/arama"
import { EntegrasyonSayfasi } from "@/shell/entegrasyon-sayfasi"
import { IKON } from "@/shell/ikon"
import { KullaniciMenu } from "@/shell/kullanici-menu"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"
import { ModulSayfasi } from "@/shell/modul-sayfasi"
import { ProfilSayfasi } from "@/shell/profil-sayfasi"
import { VeriSayfasi } from "@/shell/veri-sayfasi"
import { YonetimSayfasi } from "@/shell/yonetim-sayfasi"

/** Yan menu sirasi: Genel, Calisma alanim, Raporlar ve gorunumler, Yonetim alanlari. */
const GRUPLAR = ["genel", "work", "insights", "admin"] as const
type Grup = (typeof GRUPLAR)[number]
/** Sag ustteki kullanici menusunde duran, yan menude gosterilmeyen ogeler. */
const YAN_MENU_DISI = new Set(["talep"])
const ANAHTAR = "tamlife.menu"

function hashId(): string {
  return decodeURIComponent(window.location.hash.replace(/^#\/?/, "")) || "ozet"
}

function kapaliOku(): Record<string, boolean> {
  try {
    const ham = JSON.parse(window.localStorage.getItem(ANAHTAR) ?? "{}") as unknown
    return ham && typeof ham === "object" ? (ham as Record<string, boolean>) : {}
  } catch {
    return {}
  }
}

type MenuProps = {
  kullanici: Kullanici
  dil: Dil
  secili: string
  onSec: (id: string) => void
}

function Menu({ kullanici, dil, secili, onSec }: MenuProps) {
  const t = metin(dil)
  const { setOpenMobile } = useSidebar()
  const [kapali, setKapali] = useState<Record<string, boolean>>(kapaliOku)

  const gruplu = useMemo(() => {
    const yan = kullanici.navigation.filter((o) => !YAN_MENU_DISI.has(o.id))
    return GRUPLAR.map((grup) => ({
      grup,
      satirlar: grup === "genel" ? [] : yan.filter((o) => o.group === grup),
    })).filter((g) => g.grup === "genel" || g.satirlar.length > 0)
  }, [kullanici.navigation])

  function ac(grup: Grup) {
    setKapali((onceki) => {
      const sonraki = { ...onceki, [grup]: !onceki[grup] }
      try {
        window.localStorage.setItem(ANAHTAR, JSON.stringify(sonraki))
      } catch {
        /* tarayici kaydedemiyor */
      }
      return sonraki
    })
  }

  function git(id: string) {
    onSec(id)
    setOpenMobile(false)
  }

  function oge(o: { id: string; label: string; icon: string; ready?: boolean }) {
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
          {o.ready === false ? <span className="ml-auto size-1.5 rounded-full bg-muted-foreground/50" title={t.hazirlaniyor} /> : null}
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
          {gruplu.map(({ grup, satirlar }) => {
            const acik = !kapali[grup]
            const kimlik = `menu-${grup}`
            return (
              <SidebarGroup key={grup}>
                <button
                  type="button"
                  aria-expanded={acik}
                  aria-controls={kimlik}
                  onClick={() => ac(grup)}
                  className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-xs font-medium text-sidebar-foreground/70 hover:text-sidebar-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-sidebar-ring"
                >
                  {t.gruplar[grup]}
                  <ChevronDown aria-hidden className={`size-4 transition-transform ${acik ? "" : "-rotate-90"}`} />
                </button>
                {acik ? (
                  <SidebarGroupContent id={kimlik}>
                    <SidebarMenu>
                      {grup === "genel"
                        ? oge({ id: "ozet", label: t.genelBakis, icon: "ozet" })
                        : satirlar.map((o: MenuOgesi) => oge(o))}
                    </SidebarMenu>
                  </SidebarGroupContent>
                ) : null}
              </SidebarGroup>
            )
          })}
        </nav>
      </SidebarContent>
    </Sidebar>
  )
}

type Props = {
  kullanici: Kullanici
  dil: Dil
  onDil: (dil: Dil) => void
  onCikis: () => void
}

export function Panel({ kullanici, dil, onDil, onCikis }: Props) {
  const t = metin(dil)
  const [secili, setSecili] = useState(hashId)
  const yonetimOgeleri = useMemo(() => kullanici.navigation.filter((o) => o.group === "admin"), [kullanici.navigation])
  const izinli = useMemo(() => {
    const kume = new Set(["ozet", "profil", ...kullanici.navigation.map((o) => o.id)])
    if (kullanici.is_admin) kume.add("yonetim")
    return kume
  }, [kullanici.navigation, kullanici.is_admin])
  const aktif = izinli.has(secili) ? secili : "ozet"
  const oge = kullanici.navigation.find((o) => o.id === aktif)
  const baslik = aktif === "ozet" ? t.hosgeldin(kullanici.username) : aktif === "profil" ? t.profil : aktif === "yonetim" ? t.yonetim : oge?.label

  useEffect(() => {
    const degisti = () => setSecili(hashId())
    window.addEventListener("hashchange", degisti)
    return () => window.removeEventListener("hashchange", degisti)
  }, [])

  useEffect(() => {
    document.documentElement.lang = dil
    document.title = `${aktif === "ozet" ? t.genelBakis : (baslik ?? "")} · TAM Life`
  }, [dil, aktif, baslik, t.genelBakis])

  function sec(id: string) {
    window.location.hash = `#/${id}`
    setSecili(id)
  }

  return (
    <SidebarProvider>
      <Menu kullanici={kullanici} dil={dil} secili={aktif} onSec={sec} />
      <SidebarInset className="min-w-0">
        <header className="sticky top-0 z-10 flex h-16 items-center gap-3 border-b bg-background px-4 sm:px-6">
          <SidebarTrigger aria-label={t.menu} />
          <h1 className="truncate text-lg font-semibold">{baslik}</h1>
          <div className="ml-auto flex items-center gap-2">
            <Arama ogeler={kullanici.navigation} dil={dil} onGit={sec} />
            <KullaniciMenu
              kullanici={kullanici}
              dil={dil}
              onDil={onDil}
              onGit={sec}
              onCikis={onCikis}
              talepVar={kullanici.navigation.some((o) => o.id === "talep")}
            />
          </div>
        </header>
        <main className="flex flex-1 flex-col gap-6 p-4 sm:p-6">
          {aktif === "ozet" ? (
            <>
              <OzetOrbit dil={dil} admin={kullanici.is_admin} onGit={sec} />
              <AnaKartlar ogeler={kullanici.navigation} dil={dil} onGit={sec} />
            </>
          ) : aktif === "profil" ? (
            <ProfilSayfasi kullanici={kullanici} dil={dil} />
          ) : aktif === "yonetim" ? (
            <YonetimSayfasi ogeler={yonetimOgeleri} dil={dil} onGit={sec} />
          ) : aktif === "admin" ? (
            <AdminSayfasi dil={dil} />
          ) : aktif === "integrations" ? (
            <EntegrasyonSayfasi dil={dil} />
          ) : aktif === "veri" ? (
            <VeriSayfasi dil={dil} />
          ) : oge ? (
            <ModulSayfasi oge={oge} dil={dil} />
          ) : null}
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
