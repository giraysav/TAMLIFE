import { Suspense, lazy, useEffect, useMemo, useRef, useState } from "react"
import { ArrowLeft, ChevronDown, LayoutDashboard } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
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
import logo from "@/assets/tam_life_logo.png"
import { OzetOrbit } from "@/components/ui/ozet-orbit"
import type { Kullanici, MenuOgesi } from "@/lib/oturum"
import { Arama } from "@/shell/arama"
import { IKON } from "@/shell/ikon"
import { KullaniciKarti } from "@/shell/kullanici-karti"
import { metin, yerelMenu } from "@/shell/metin"
import type { Dil } from "@/shell/metin"
import { ModulSayfasi } from "@/shell/modul-sayfasi"
import { ProfilSayfasi } from "@/shell/profil-sayfasi"
import { aktifSayfa, hashParcala } from "@/shell/rota"

/** Modul sayfalari ayri JS parcalaridir: yalniz acildiginda indirilir (Yonetim yalniz admin icin). */
const YonetimSayfasi = lazy(() => import("@/yonetim/yonetim-sayfasi"))
const MusteriSayfasi = lazy(() => import("@/musteri/musteri-sayfasi").then((m) => ({ default: m.MusteriSayfasi })))
const RaporSayfasi = lazy(() => import("@/musteri/rapor-sayfasi").then((m) => ({ default: m.RaporSayfasi })))
const OnedeskSayfasi = lazy(() => import("@/onedesk/onedesk-sayfasi").then((m) => ({ default: m.OnedeskSayfasi })))
const SmsSayfasi = lazy(() => import("@/gelir/sms-sayfasi").then((m) => ({ default: m.SmsSayfasi })))
const ApnSayfasi = lazy(() => import("@/gelir/apn-sayfasi").then((m) => ({ default: m.ApnSayfasi })))
const IzinTakvim = lazy(() => import("@/takvim/izin-takvim").then((m) => ({ default: m.IzinTakvim })))
const TamTakvim = lazy(() => import("@/takvim/tam-takvim").then((m) => ({ default: m.TamTakvim })))
const SunumSayfasi = lazy(() => import("@/sunum/sunum-sayfasi").then((m) => ({ default: m.SunumSayfasi })))
const TalepSayfasi = lazy(() => import("@/talep/talep-sayfasi").then((m) => ({ default: m.TalepSayfasi })))
const RadarSayfasi = lazy(() => import("@/radar/radar-sayfasi").then((m) => ({ default: m.RadarSayfasi })))
const ProjeSayfasi = lazy(() => import("@/proje/proje-sayfasi").then((m) => ({ default: m.ProjeSayfasi })))
const EkipOzeti = lazy(() => import("@/ekip/ekip-ozeti").then((m) => ({ default: m.EkipOzeti })))

/** Eski yonetim adresleri (yer imleri, gecmis) ve Yonetim'e katlanan modul (utilizasyon) tek Yonetim alaninin bolumlerine yonlenir. */
const ESKI_ADRESLER: Record<string, string> = {
  admin: "yonetim/durum",
  utilizasyon: "yonetim/utilizasyon",
  integrations: "yonetim/durum",
  veri: "yonetim/veritabani",
  roller: "yonetim/roller",
  yonetim: "yonetim/durum",
}

/** Yan menu sirasi: Genel, Calisma alanim, Raporlar ve gorunumler. Yonetim kisayolu sol alttaki hesap kartinin menusunde. */
const GRUPLAR = ["genel", "work", "insights"] as const
type Grup = (typeof GRUPLAR)[number]
/** Sol alttaki hesap kartinin menusunde duran, yan menude gosterilmeyen ogeler. */
const YAN_MENU_DISI = new Set(["talep"])
const ANAHTAR = "tamlife.menu"
/** Mavi ust barda (Turkcell mavisi) simge dugmeleri: beyaz, sari odak halkasi. */
const UST_BAR_DUGME = "text-white hover:bg-white/15 hover:text-white focus-visible:ring-tl-yellow"

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

type MenuProps = { kullanici: Kullanici; dil: Dil; secili: string; onSec: (id: string) => void; onDil: (dil: Dil) => void; onCikis: () => void; talepVar: boolean }

function Menu({ kullanici, dil, secili, onSec, onDil, onCikis, talepVar }: MenuProps) {
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
        <a href="#/ozet" aria-label="TAM Life" className="flex min-h-11 items-center rounded-lg px-2 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-sidebar-ring" onClick={() => git("ozet")}>
          <img src={logo} alt="TAM Life" width={459} height={105} className="h-9 w-auto" />
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
      <SidebarFooter className="border-t-0 p-3">
        <KullaniciKarti kullanici={kullanici} dil={dil} onDil={onDil} onGit={git} onCikis={onCikis} talepVar={talepVar} />
      </SidebarFooter>
    </Sidebar>
  )
}

type Props = { kullanici: Kullanici; dil: Dil; onDil: (dil: Dil) => void; onCikis: () => void; onProfilDegisti?: () => void }

export function Panel({ kullanici: oturum, dil, onDil, onCikis, onProfilDegisti }: Props) {
  const t = metin(dil)
  /** Sunucu etiketleri (modul adi, aciklama) bir kez dile cevrilir; asagidaki her kullanim bu listeyi gorur. */
  const kullanici = useMemo(() => ({ ...oturum, navigation: yerelMenu(oturum.navigation, dil) }), [oturum, dil])
  const [secili, setSecili] = useState(() => hashId() || "ozet")
  const icerik = useRef<HTMLElement>(null)
  /** Yonetim disindaki admin alanlari: Yonetim sayfasinin altinda baglanti olarak gorunur (Yonetim bolumune katlananlar, orn. TAM Utilizasyon, haric). */
  const digerYonetim = useMemo(() => kullanici.navigation.filter((o) => o.group === "admin" && o.id !== "yonetim" && !ESKI_ADRESLER[o.id]), [kullanici.navigation])
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
  const aktif = aktifSayfa(normal, izinli, kullanici.is_admin)
  const [ustId, altId] = aktif.split("/")
  const oge = kullanici.navigation.find((o) => o.id === ustId)
  const alt = altId ? oge?.children?.find((c) => c.id === aktif) : undefined
  const baslik =
    aktif === "ozet"
      ? t.hosgeldin(kullanici.profile?.first_name || kullanici.display_name || kullanici.username)
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

  // Sayfa degisince icerik alani basa doner (onceki sayfanin kaydirma konumu tasinmasin).
  useEffect(() => {
    icerik.current?.scrollTo(0, 0)
  }, [aktif])

  useEffect(() => {
    document.title = `${aktif === "ozet" ? t.genelBakis : (baslik ?? "")} · TAM Life`
  }, [aktif, baslik, t.genelBakis])

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
      <Menu kullanici={kullanici} dil={dil} secili={aktif} onSec={sec} onDil={onDil} onCikis={onCikis} talepVar={kullanici.navigation.some((o) => o.id === "talep")} />
      <SidebarInset ref={icerik} className="min-w-0">
        <header className="sticky top-0 z-10 flex h-16 items-center gap-3 border-b-[3px] border-tl-yellow bg-gradient-to-r from-tl-navy via-[#003a7a] to-tl-blue px-4 text-white shadow-md sm:px-6">
          <SidebarTrigger aria-label={t.menu} className={UST_BAR_DUGME} />
          {aktif !== "ozet" ? (
            <Button type="button" variant="ghost" size="icon" aria-label={t.geri} title={t.geri} onClick={geri} className={UST_BAR_DUGME}>
              <ArrowLeft aria-hidden />
            </Button>
          ) : null}
          <h1 className="truncate text-lg font-black tracking-tight">{baslik}</h1>
          <div className="ml-auto flex items-center gap-2">
            <Arama ogeler={aramaOgeleri} dil={dil} onGit={sec} dugmeSinifi={UST_BAR_DUGME} />
          </div>
        </header>
        <main className={`flex flex-1 flex-col gap-6 p-4 sm:p-6 ${aktif === "ozet" ? "min-h-0 !gap-0 !py-3" : ""}`}>
          <Suspense fallback={<p className="text-sm text-muted-foreground">{t.yukleniyor}</p>}>
          {aktif === "ozet" ? (
            <div className="mx-auto flex min-h-0 w-full max-w-[87.5rem] flex-1 flex-col justify-center-safe gap-3">
              <OzetOrbit dil={dil} onGit={sec} />
              <Suspense fallback={null}>
                <EkipOzeti dil={dil} onGit={sec} sikisik />
              </Suspense>
            </div>
          ) : aktif === "profil" ? (
            <ProfilSayfasi kullanici={kullanici} dil={dil} onKaydedildi={onProfilDegisti} />
          ) : ustId === "yonetim" && kullanici.is_admin ? (
            <YonetimSayfasi dil={dil} bolum={altId ?? ""} digerleri={digerYonetim} />
          ) : aktif === "musteri" ? (
            <MusteriSayfasi dil={dil} yazabilir={kullanici.is_admin} />
          ) : aktif === "onedesk" ? (
            <OnedeskSayfasi dil={dil} admin={kullanici.is_admin} />
          ) : aktif === "takvim" ? (
            <IzinTakvim dil={dil} />
          ) : aktif === "takvim_ozet" ? (
            <TamTakvim dil={dil} />
          ) : aktif === "sunum" ? (
            <SunumSayfasi dil={dil} />
          ) : aktif === "talep" ? (
            <TalepSayfasi dil={dil} />
          ) : aktif === "radar" ? (
            <RadarSayfasi dil={dil} />
          ) : aktif === "proje" ? (
            <ProjeSayfasi dil={dil} yazabilir={kullanici.is_admin} />
          ) : aktif === "tamsms" ? (
            <SmsSayfasi dil={dil} yazabilir={kullanici.is_admin} />
          ) : aktif === "tamapn" ? (
            <ApnSayfasi dil={dil} yazabilir={kullanici.is_admin} />
          ) : aktif === "rapor" ? (
            <RaporSayfasi dil={dil} />
          ) : alt && oge ? (
            <ModulSayfasi baslik={alt.label} aciklama={alt.description} hazir={alt.ready} ust={oge.label} dil={dil} onGit={sec} />
          ) : oge ? (
            <ModulSayfasi baslik={oge.label} aciklama={oge.description} hazir={oge.ready} altlar={oge.children ?? []} dil={dil} onGit={sec} />
          ) : null}
          </Suspense>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
