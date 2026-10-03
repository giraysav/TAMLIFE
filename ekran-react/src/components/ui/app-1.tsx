"use client"

import { useEffect, useState, type FormEvent } from "react"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"
import { Bell, Search } from "lucide-react"

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import { Progress } from "@/components/ui/progress"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/app-1-utils/sidebar"
import {
  app1Activity,
  app1Chart,
  app1Nav,
  app1Projects,
  arayuz,
  chartConfig,
  dilOku,
  DIL_ANAHTARI,
  type ArayuzMetin,
  type Dil,
} from "@/components/ui/app-1-utils/app-1-data"
import { App1Sidebar } from "@/components/ui/app-1-utils/app-1-sidebar"
import { Input } from "@/components/ui/input"
import { AdminVeri } from "@/components/ui/admin-veri"
import { API_KOK } from "@/lib/api"
import { OzetOrbit } from "@/components/ui/ozet-orbit"
import { csrfBasliklari } from "@/lib/http"

type Yetki = {
  oturum: boolean
  admin: boolean
  moduller: string[]
  menu: { rol: boolean; admin: boolean }
}

const BOS_YETKI: Yetki = {
  oturum: false,
  admin: false,
  moduller: ["ozet"],
  menu: { rol: false, admin: false },
}

const STATUS_VARIANT = {
  progress: "default",
  review: "secondary",
  planning: "outline",
} as const


const ROL_ADLARI = ["admin", "TeamMngr", "TeamMember"] as const

type RolAdi = (typeof ROL_ADLARI)[number]

type RolCevap = { roller?: Partial<Record<RolAdi, string[]>> }

function RolSayfasi({ dil, metin }: { dil: Dil; metin: ArayuzMetin }) {
  const [harita, setHarita] = useState<Record<RolAdi, string[]> | null>(null)
  const [hata, setHata] = useState<string | null>(null)
  const [bilgi, setBilgi] = useState<string | null>(null)
  const [kaydediyor, setKaydediyor] = useState(false)

  useEffect(() => {
    let iptal = false
    fetch(`${API_KOK}/api/roller`, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) throw new Error(String(response.status))
        return (await response.json()) as RolCevap
      })
      .then((govde) => {
        if (iptal) return
        const roller = govde.roller ?? {}
        const sonraki = {} as Record<RolAdi, string[]>
        for (const rol of ROL_ADLARI) {
          const liste = Array.isArray(roller[rol]) ? roller[rol] : []
          sonraki[rol] = rol === "admin" ? app1Nav.map((item) => item.id) : Array.from(new Set(["ozet", ...liste]))
        }
        setHarita(sonraki)
      })
      .catch(() => {
        if (!iptal) setHata(metin.rolHata)
      })
    return () => {
      iptal = true
    }
  }, [metin.rolHata])

  function degistir(rol: RolAdi, modulId: string, acik: boolean) {
    if (rol === "admin" || modulId === "ozet") return
    setHarita((eski) => {
      if (!eski) return eski
      const secili = new Set(eski[rol])
      if (acik) secili.add(modulId)
      else secili.delete(modulId)
      secili.add("ozet")
      return { ...eski, [rol]: app1Nav.map((item) => item.id).filter((id) => secili.has(id)) }
    })
    setBilgi(null)
  }

  function kaydet() {
    if (!harita) return
    setKaydediyor(true)
    setHata(null)
    setBilgi(null)
    fetch(`${API_KOK}/api/roller`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        roller: {
          TeamMngr: harita.TeamMngr,
          TeamMember: harita.TeamMember,
        },
      }),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(String(response.status))
        const govde = (await response.json()) as RolCevap
        const roller = govde.roller ?? {}
        setHarita((eski) => {
          if (!eski) return eski
          const sonraki = { ...eski }
          for (const rol of ["TeamMngr", "TeamMember"] as const) {
            if (Array.isArray(roller[rol])) sonraki[rol] = roller[rol] as string[]
          }
          sonraki.admin = app1Nav.map((item) => item.id)
          return sonraki
        })
        setBilgi(metin.rolKaydedildi)
      })
      .catch(() => setHata(metin.rolHata))
      .finally(() => setKaydediyor(false))
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{metin.rol}</CardTitle>
        <CardDescription>{metin.rolAciklama}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {hata ? <p className="text-sm text-destructive">{hata}</p> : null}
        {!harita ? (
          <p className="text-sm text-muted-foreground">{metin.rolYukleniyor}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="py-2 pr-3 font-medium">{metin.rolModul}</th>
                  {ROL_ADLARI.map((rol) => (
                    <th key={rol} className="px-2 py-2 font-medium">
                      {rol}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {app1Nav.map((item) => (
                  <tr key={item.id} className="border-b last:border-0">
                    <td className="py-2 pr-3">{item.ad[dil]}</td>
                    {ROL_ADLARI.map((rol) => {
                      const kilit = rol === "admin" || item.id === "ozet"
                      const acik = rol === "admin" || harita[rol].includes(item.id)
                      return (
                        <td key={rol} className="px-2 py-2">
                          <input
                            type="checkbox"
                            className="size-4 accent-primary"
                            checked={acik}
                            disabled={kilit}
                            aria-label={`${rol} ${item.ad[dil]}`}
                            onChange={(event) => degistir(rol, item.id, event.target.checked)}
                          />
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="flex items-center gap-3">
          <Button type="button" onClick={kaydet} disabled={!harita || kaydediyor}>
            {metin.rolKaydet}
          </Button>
          {bilgi ? <p className="text-sm text-muted-foreground">{bilgi}</p> : null}
        </div>
      </CardContent>
    </Card>
  )
}

export function App1() {
  const [dil, setDil] = useState<Dil>(dilOku)
  const [yetki, setYetki] = useState<Yetki>({
    oturum: false,
    admin: false,
    moduller: ["ozet"],
    menu: { rol: false, admin: false },
  })
  const [oturumKontrol, setOturumKontrol] = useState(true)
  const [kullanici, setKullanici] = useState({ name: "", initials: "", email: "" })
  const [selectedId, setSelectedId] = useState("ozet")
  const [girisAd, setGirisAd] = useState("")
  const [girisParola, setGirisParola] = useState("")
  const [girisHata, setGirisHata] = useState<string | null>(null)
  const [girisBekliyor, setGirisBekliyor] = useState(false)
  const metin = arayuz(dil)
  const navIdleri = app1Nav.map((item) => item.id)
  const gorunen = yetki.moduller.filter((id) => id === "ozet" || navIdleri.includes(id))
  const menuRol = yetki.admin && yetki.menu.rol
  const menuAdmin = yetki.admin && yetki.menu.admin

  function kullaniciAyarla(ad?: string) {
    const name = ad?.trim() ?? ""
    setKullanici({ name, initials: name.slice(0, 2).toUpperCase(), email: "" })
  }

  useEffect(() => {
    document.documentElement.lang = dil
  }, [dil])

  useEffect(() => {
    let iptal = false
    fetch("/api/v1/session/me", { credentials: "same-origin" })
      .then((response) => {
        if (!response.ok) throw new Error(String(response.status))
        return response.json()
      })
      .then((govde: { data?: { is_admin?: boolean; username?: string } }) => {
        if (iptal) return
        kullaniciAyarla(govde.data?.username)
        const admin = Boolean(govde.data?.is_admin)
        setYetki({
          oturum: true,
          admin,
          moduller: navIdleri,
          menu: {
            rol: admin,
            admin,
          },
        })
      })
      .catch(() => {
        if (!iptal) setYetki((eski) => ({ ...eski, oturum: false }))
      })
      .finally(() => {
        if (!iptal) setOturumKontrol(false)
      })
    return () => {
      iptal = true
    }
  }, [])

  useEffect(() => {
    const izinli =
      gorunen.includes(selectedId) ||
      (selectedId === "admin" && menuAdmin) ||
      (selectedId === "rol" && menuRol)
    if (!izinli) setSelectedId("ozet")
  }, [gorunen, menuAdmin, menuRol, selectedId])

  function girisYap(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setGirisHata(null)
    setGirisBekliyor(true)
    fetch("/api/v1/session/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: girisAd, password: girisParola }),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(String(response.status))
        let admin = false
        try {
          const yetkiCevap = await fetch("/api/v1/session/me", { credentials: "same-origin" })
          if (yetkiCevap.ok) {
            const govde = (await yetkiCevap.json()) as { data?: { is_admin?: boolean; username?: string } }
            admin = Boolean(govde.data?.is_admin)
            kullaniciAyarla(govde.data?.username)
          }
        } catch {
          admin = false
        }
        setYetki({
          oturum: true,
          admin,
          moduller: navIdleri,
          menu: {
            rol: admin,
            admin,
          },
        })
        setGirisParola("")
      })
      .catch((hata: Error) => {
        const kilit = hata.message === "429"
        setGirisHata(
          kilit
            ? dil === "en" ? "Too many attempts. Try again later." : "Cok fazla deneme. Biraz bekleyin."
            : dil === "en" ? "Sign-in was not accepted." : "Giris onaylanmadi.",
        )
      })
      .finally(() => setGirisBekliyor(false))
  }

  function cikisYap() {
    fetch("/api/v1/session/logout", { method: "POST", credentials: "same-origin", headers: csrfBasliklari() })
      .then((response) => {
        if (!response.ok) throw new Error(String(response.status))
        setYetki(BOS_YETKI)
        setSelectedId("ozet")
        setGirisAd("")
        setGirisParola("")
        setGirisHata(null)
      })
      .catch(() => {
        setGirisHata(dil === "en" ? "Sign-out failed." : "Cikis yapilamadi.")
      })
  }

  function dilSec(sonraki: Dil) {
    setDil(sonraki)
    try {
      localStorage.setItem(DIL_ANAHTARI, sonraki)
    } catch {
      /* bu tarayici kaydedemez */
    }
  }

  const grafik = app1Chart.map((row) => ({ ...row, week: metin.hafta(row.week) }))
  const secili = app1Nav.find((item) => item.id === selectedId)
  const bosBaslik = selectedId === "rol" ? metin.rol : selectedId === "admin" ? metin.admin : secili?.ad[dil]

  if (oturumKontrol) return null

  if (!yetki.oturum) {
    return (
      <div className="flex h-full min-h-dvh w-full items-center justify-center bg-background p-4">
        <form
          onSubmit={girisYap}
          className="flex w-full max-w-sm flex-col gap-4 rounded-xl border bg-card p-6 shadow-xs"
          aria-label={dil === "en" ? "Sign in" : "Giris"}
        >
          <h1 className="text-xl font-semibold">{dil === "en" ? "Sign in" : "Giris"}</h1>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">{dil === "en" ? "Username" : "Kullanici adi"}</span>
            <Input
              name="username"
              autoComplete="username"
              value={girisAd}
              onChange={(event) => setGirisAd(event.target.value)}
              required
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">{dil === "en" ? "Password" : "Parola"}</span>
            <Input
              name="password"
              type="password"
              autoComplete="current-password"
              value={girisParola}
              onChange={(event) => setGirisParola(event.target.value)}
              required
            />
          </label>
          {girisHata ? <p className="text-sm text-destructive">{girisHata}</p> : null}
          <Button type="submit" disabled={girisBekliyor} className="w-full">
            {dil === "en" ? "Sign in" : "Giris"}
          </Button>
        </form>
      </div>
    )
  }

  return (
    <SidebarProvider>
      <App1Sidebar
        dil={dil}
        metin={metin}
        gorunen={gorunen}
        menuRol={menuRol}
        menuAdmin={menuAdmin}
        oturum={yetki.oturum}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onCikis={cikisYap}
        kullanici={kullanici}
      />
      <SidebarInset className="min-w-0">
        <header className="sticky top-0 z-10 flex h-16 items-center gap-3 border-b bg-background px-4 sm:px-6">
          <SidebarTrigger aria-label={metin.menu} />
          <h1 className="truncate text-lg font-semibold">{metin.hosgeldin(kullanici.name)}</h1>
          <div className="ml-auto flex items-center gap-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mr-1 h-8 border border-border px-3"
              onClick={cikisYap}
            >
            {metin.cikis}
            </Button>
            <div className="mr-1 flex items-center rounded-md border" role="group" aria-label={metin.dil}>
              <Button
                type="button"
                size="sm"
                variant={dil === "tr" ? "default" : "ghost"}
                className="h-8 rounded-r-none px-2"
                aria-pressed={dil === "tr"}
                onClick={() => dilSec("tr")}
              >
                TR
              </Button>
              <Button
                type="button"
                size="sm"
                variant={dil === "en" ? "default" : "ghost"}
                className="h-8 rounded-l-none px-2"
                aria-pressed={dil === "en"}
                onClick={() => dilSec("en")}
              >
                EN
              </Button>
            </div>
            <Button variant="ghost" size="icon" aria-label={metin.ara}>
              <Search />
            </Button>
            <Button variant="ghost" size="icon" aria-label={metin.bildirim}>
              <Bell />
            </Button>
            <Avatar className="ml-1 size-8">
              <AvatarFallback>{kullanici.initials}</AvatarFallback>
            </Avatar>
          </div>
        </header>

        <main className="flex flex-1 flex-col gap-6 p-4 sm:p-6">

          {selectedId === "ozet" ? (
            <>
              <OzetOrbit dil={dil} admin={menuAdmin} onGit={setSelectedId} />

              <Card>
                <CardHeader>
                  <CardTitle>{metin.grafikBaslik}</CardTitle>
                  <CardDescription>{metin.grafikAciklama}</CardDescription>
                </CardHeader>
                <CardContent>
                  <ChartContainer config={chartConfig(dil)} className="h-64 w-full">
                    <AreaChart data={grafik} margin={{ left: 4, right: 4, top: 8 }} accessibilityLayer>
                      <defs>
                        <linearGradient id="app1Completed" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="var(--color-completed)" stopOpacity={0.25} />
                          <stop offset="100%" stopColor="var(--color-completed)" stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid vertical={false} strokeDasharray="3 3" />
                      <XAxis dataKey="week" tickLine={false} axisLine={false} tickMargin={8} />
                      <YAxis tickLine={false} axisLine={false} width={32} />
                      <ChartTooltip content={<ChartTooltipContent />} />
                      <ChartLegend content={<ChartLegendContent />} />
                      <Area
                        dataKey="opened"
                        type="monotone"
                        stroke="var(--color-opened)"
                        strokeDasharray="4 4"
                        fill="none"
                        strokeWidth={2}
                      />
                      <Area
                        dataKey="completed"
                        type="monotone"
                        stroke="var(--color-completed)"
                        fill="url(#app1Completed)"
                        strokeWidth={2}
                      />
                    </AreaChart>
                  </ChartContainer>
                </CardContent>
              </Card>

              <div className="grid gap-6 lg:grid-cols-2">
                <Card>
                  <CardHeader>
                    <CardTitle>{metin.aktifProjeler}</CardTitle>
                    <CardDescription>{metin.aktifProjelerAciklama}</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-5">
                    {app1Projects.map((project) => (
                      <div key={project.id} className="flex flex-col gap-2">
                        <div className="flex items-center justify-between gap-2">
                          <h3 className="truncate text-sm font-medium">{project.name[dil]}</h3>
                          <Badge variant={STATUS_VARIANT[project.status]}>{metin.durum[project.status]}</Badge>
                        </div>
                        <p className="text-xs text-muted-foreground">{project.description[dil]}</p>
                        <div className="flex items-center gap-3">
                          <Progress value={project.progress} aria-label={`${project.name[dil]} ${metin.ilerleme}`} />
                          <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{project.progress}%</span>
                        </div>
                        <div className="flex items-center justify-between gap-2">
                          <span className="flex items-center gap-1">
                            {project.team.map((member) => (
                              <Avatar key={member.name} className="size-6">
                                <AvatarImage src={member.avatar} alt={member.name} className="object-[50%_15%]" />
                                <AvatarFallback className="text-[10px]">{member.initials}</AvatarFallback>
                              </Avatar>
                            ))}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {metin.sonTarih} {project.due[dil]}
                          </span>
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>{metin.sonHareket}</CardTitle>
                    <CardDescription>{metin.sonHareketAciklama}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ol className="flex flex-col gap-4">
                      {app1Activity.map((entry) => (
                        <li key={entry.id} className="flex items-start gap-3">
                          <Avatar className="size-8">
                            <AvatarImage src={entry.person.avatar} alt={entry.person.name} className="object-[50%_15%]" />
                            <AvatarFallback className="text-xs">{entry.person.initials}</AvatarFallback>
                          </Avatar>
                          <div className="min-w-0 flex-1">
                            <p className="text-sm leading-snug">
                              <span className="font-medium">{entry.person.name}</span>{" "}
                              <span className="text-muted-foreground">{entry.action[dil]}</span>
                            </p>
                            <p className="text-xs text-muted-foreground">{entry.time[dil]}</p>
                          </div>
                        </li>
                      ))}
                    </ol>
                  </CardContent>
                </Card>
              </div>
            </>
          ) : selectedId === "admin" && menuAdmin ? (
            <AdminVeri dil={dil} />
          ) : selectedId === "rol" && menuRol ? (
            <RolSayfasi dil={dil} metin={metin} />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>{bosBaslik}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col items-start gap-2">
                <p className="text-sm text-muted-foreground">{metin.bosModul}</p>
                <Button type="button" variant="link" onClick={() => setSelectedId("ozet")}>
                  {metin.anaSayfa}
                </Button>
              </CardContent>
            </Card>
          )}
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

export default App1
