import { Suspense, lazy, useEffect, useMemo, useState } from "react"
import { ArrowLeft, ChevronDown, LayoutDashboard } from "lucide-react"
import { Button } from "@/components/ui/button"
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
} from "@/components/ui/sidebar"
import { OzetOrbit } from "@/components/ui/ozet-orbit"
import type { Kullanici, MenuOgesi } from "@/lib/oturum"
import { Arama } from "@/shell/arama"
import { IKON } from "@/shell/ikon"
import { KullaniciMenu } from "@/shell/kullanici-menu"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"
import { ModulSayfasi } from "@/shell/modul-sayfasi"
import { MusteriSayfasi } from "@/musteri/musteri-sayfasi"
import { ProfilSayfasi } from "@/shell/profil-sayfasi"
import { RaporSayfasi } from "@/musteri/rapor-sayfasi"
import { RollerSayfasi } from "@/shell/roller-sayfasi"
import { hashParcala } from "@/shell/rota"

/** Yonetim yalniz admin icin: ayri JS parcasi (diger kullanicilar indirmez). */
const YonetimSayfasi = lazy(() => import("@/yonetim/yonetim-sayfasi"))

/** Eski yonetim adresleri (yer imleri, gecmis) tek Yonetim alaninin bolumlerine yonlenir. */
const ESKI_ADRESLER: Record<string, string> = {
  admin: "yonetim/durum",
  integrations: "yonetim/durum",
  veri: "yonetim/veritabani",
  roller: "yonetim/roller",
  yonetim: "yonetim/durum",
}

/** Yan menu sirasi: Genel, Calisma alanim, Raporlar ve gorunumler. Yonetim yalniz sag ustteki kullanici menusunde. */
const GRUPLAR = ["genel", "work", "insights"] as const
type Grup = (typeof GRUPLAR)[number]
/** Sag ustteki kullanici menusunde duran, yan menude gosterilmeyen ogeler. */
const YAN_MENU_DISI = new Set(["talep"])
const ANAHTAR = "tamlife.menu"

function hashId(): string {
  return hashParcala().yol
}

function kapaliOku(): Record<string, boolean> {
  try {
    const ham = JSON.parse(window.localStorage.getItem(ANAHTAR) ?? "{}") as unknown
    return ham && typeof ham === "object" ? (ham as Record<string, boolean>) : {}
  } catch {
    return {}
  }
}

type MenuProps = { kullanici: Kullanici; dil: Dil; secili: string; onSec: (id: string) => void }

function Menu({ kullanici, dil, secili, onSec }: MenuProps) {
  const t = metin(dil)
  const { setOpenMobile } = useSidebar()
  const [kapali, setKapali] = useState<Record<string, boolean>>(kapaliOku)
  const [altKapali, setAltKapali] = useState<Record<string, boolean>>({})

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

  function satir(o: MenuOgesi) {
    const Ikon = IKON[o.icon] ?? LayoutDashboard
    const aktif = secili === o.id
    const altlar = o.children ?? []
    const altAktif = altlar.some((c) => c.id === secili)
    const altAcik = altlar.length > 0 && (altAktif || !altKapali[o.id])
    return (
      <SidebarMenuItem key={o.id}>
        <div className="flex items-center">
          <SidebarMenuButton
            className="flex-1"
            isActive={aktif}
            render={<a href={`#/${o.id}`} aria-current={aktif ? "page" : undefined} onClick={() => git(o.id)} />}
          >
            <Ikon aria-hidden />
            <span>{o.label}</span>
            {!o.ready ? <span className="ml-auto size-1.5 rounded-full bg-muted-foreground/50" title={t.hazirlaniyor} /> : null}
          </SidebarMenuButton>
          {altlar.length > 0 ? (
            <button
              type="button"
              aria-label={`${o.label}: ${t.altModuller}`}
              aria-expanded={altAcik}
              onClick={() => setAltKapali((a) => ({ ...a, [o.id]: altAcik }))}
              className="ml-1 rounded-md p-1.5 text-sidebar-foreground/70 hover:text-sidebar-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-sidebar-ring"
            >
              <ChevronDown aria-hidden className={`size-4 transition-transform ${altAcik ? "" : "-rotate-90"}`} />
            </button>
          ) : null}
        </div>
        {altAcik ? (
          <ul className="ml-6 mt-1 grid gap-0.5 border-l pl-2">
            {altlar.map((c) => (
              <li key={c.id}>
                <a
                  href={`#/${c.id}`}
                  aria-current={secili === c.id ? "page" : undefined}
                  onClick={() => git(c.id)}
                  className={`flex min-h-8 items-center rounded-md px-2 text-sm hover:bg-sidebar-accent focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-sidebar-ring ${
                    secili === c.id ? "bg-sidebar-accent font-medium" : ""
                  }`}
                >
                  {c.label}
                  {!c.ready ? <span className="ml-auto size-1.5 rounded-full bg-muted-foreground/50" title={t.hazirlaniyor} /> : null}
                </a>
              </li>
            ))}
          </ul>
        ) : null}
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
                        ? satir({ id: "ozet", label: t.genelBakis, description: "", group: "work", icon: "ozet", ready: true, children: [] })
                        : satirlar.map(satir)}
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

type Props = { kullanici: Kullanici; dil: Dil; onDil: (dil: Dil) => void; onCikis: () => void }

export function Panel({ kullanici, dil, onDil, onCikis }: Props) {
  const t = metin(dil)
  const [secili, setSecili] = useState(() => hashId() || "ozet")
  /** Yonetim disindaki admin alanlari (orn. TAM Utilizasyon): Yonetim sayfasinin altinda baglanti olarak gorunur. */
  const digerYonetim = useMemo(() => kullanici.navigation.filter((o) => o.group === "admin" && o.id !== "yonetim"), [kullanici.navigation])
  const izinli = useMemo(() => {
    const kume = new Set(["ozet", "profil"])
    for (const o of kullanici.navigation) {
      kume.add(o.id)
      for (const c of o.children ?? []) kume.add(c.id)
    }
    return kume
  }, [kullanici.navigation])
  // Admin icin eski adresler (admin, veri, integrations, roller) yeni Yonetim bolumune cevrilir.
  const normal = kullanici.is_admin ? (ESKI_ADRESLER[secili] ?? secili) : secili
  const aktif = izinli.has(normal) ? normal : "ozet"
  const [ustId, altId] = aktif.split("/")
  const oge = kullanici.navigation.find((o) => o.id === ustId)
  const alt = altId ? oge?.children?.find((c) => c.id === aktif) : undefined
  const baslik =
    aktif === "ozet"
      ? t.hosgeldin(kullanici.username)
      : aktif === "profil"
        ? t.profil
        : ustId === "yonetim"
          ? `${t.yonetim}${alt ? ` › ${alt.label}` : ""}`
          : (alt?.label ?? oge?.label)
  const aramaOgeleri = useMemo(
    () => kullanici.navigation.flatMap((o) => [o, ...(o.children ?? []).map((c) => ({ ...o, id: c.id, label: `${o.label} › ${c.label}`, description: c.description, children: [] }))]),
    [kullanici.navigation],
  )

  // Eski adresten gelindiyse adres cubugunu da yeni adrese cevir (gecmise kayit eklemeden).
  useEffect(() => {
    if (kullanici.is_admin && ESKI_ADRESLER[secili]) {
      window.location.replace(`#/${ESKI_ADRESLER[secili]}`)
      setSecili(ESKI_ADRESLER[secili])
    }
  }, [kullanici.is_admin, secili])

  // Rol bazli giris sayfasi: adres bos acildiysa rolun giris sayfasina git (gecmise yeni kayit eklemeden).
  useEffect(() => {
    if (hashId() === "" && kullanici.landing && kullanici.landing !== "ozet" && izinli.has(kullanici.landing)) {
      window.location.replace(`#/${kullanici.landing}`)
      setSecili(kullanici.landing)
    }
  }, [kullanici.landing, izinli])

  useEffect(() => {
    const degisti = () => setSecili(hashId() || "ozet")
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

  /** Geri: onceki sayfaya doner; gecmis yoksa ust sayfaya (alt modulde ana modul, digerlerinde genel bakis). */
  function geri() {
    if (window.history.length > 1) window.history.back()
    else sec(altId ? ustId : "ozet")
  }

  return (
    <SidebarProvider>
      <Menu kullanici={kullanici} dil={dil} secili={aktif} onSec={sec} />
      <SidebarInset className="min-w-0">
        <header className="sticky top-0 z-10 flex h-16 items-center gap-3 border-b bg-background px-4 sm:px-6">
          <SidebarTrigger aria-label={t.menu} />
          {aktif !== "ozet" ? (
            <Button type="button" variant="ghost" size="icon" aria-label={t.geri} title={t.geri} onClick={geri}>
              <ArrowLeft aria-hidden />
            </Button>
          ) : null}
          <h1 className="truncate text-lg font-semibold">{baslik}</h1>
          <div className="ml-auto flex items-center gap-2">
            <Arama ogeler={aramaOgeleri} dil={dil} onGit={sec} />
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
            <OzetOrbit dil={dil} />
          ) : aktif === "profil" ? (
            <ProfilSayfasi kullanici={kullanici} dil={dil} />
          ) : ustId === "yonetim" && kullanici.is_admin ? (
            <Suspense fallback={<p className="text-sm text-muted-foreground">{t.yukleniyor}</p>}>
              <YonetimSayfasi dil={dil} bolum={altId ?? ""} digerleri={digerYonetim} />
            </Suspense>
          ) : aktif === "musteri" ? (
            <MusteriSayfasi dil={dil} />
          ) : aktif === "rapor" ? (
            <RaporSayfasi dil={dil} />
          ) : aktif === "roller" ? (
            <RollerSayfasi dil={dil} saltOkunur={!kullanici.is_admin} />
          ) : alt && oge ? (
            <ModulSayfasi baslik={alt.label} aciklama={alt.description} hazir={alt.ready} ust={oge.label} dil={dil} onGit={sec} />
          ) : oge ? (
            <ModulSayfasi baslik={oge.label} aciklama={oge.description} hazir={oge.ready} altlar={oge.children ?? []} dil={dil} onGit={sec} />
          ) : null}
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
