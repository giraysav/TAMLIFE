import { useEffect, useRef, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { ChevronDown, Pencil, Presentation, Search, Trash2, UserPlus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { baslangicHarfleri, zaman } from "@/lib/bicim"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { metin, yerel } from "@/shell/metin"
import type { Dil } from "@/shell/metin"
import { sunumMetin } from "@/sunum/sunum-metin"

type Rol = { role: string; label: string; editable: boolean; modules: string[]; landing: string; permissions: string[]; saved: boolean }
/** Panelde kaydi olan personel (AD ile giren ya da yoneticinin actigi). `permissions` yalniz kisiye ozel verilenlerdir; rolden gelenler `roles` icindedir. */
type Kisi = { id: number; username: string; display_name: string; first_name?: string; last_name?: string; role: string; auth: string; ad_domain: string; last_login_at: string | null; permissions: string[]; deletable?: boolean; self?: boolean }
type Etiket = { id: string; label: string; label_en?: string }
type Katalog = Etiket & { children: Etiket[] }
/** Eylem yetkisi: duz dilde ne sagladigi ve nerede kullanildigi. Rol kartindaki "Ek yetkiler" kaldirildi (2026-10-11, amaci belirsizdi);
 * yalniz kendi bolumu olan yetkiler (ornek "sunum") Rol Yonetimi'nde duzenlenir. Kayitli yetkiler rol kaydedilince korunur. */
type Yetki = Etiket & { description: string; description_en: string; where: string; where_en: string; area: string }
/** `can_delete_users`/`delete_account`: kullanici silme yalniz tek hesapta (sunucu zorlar); `deletable` kisi basina dugme gosterimi icin. */
type Veri = { roles: Rol[]; catalog: Katalog[]; permission_catalog: Yetki[]; users?: Kisi[]; can_delete_users?: boolean; delete_account?: string }

function YetkiAciklamasi({ yetki, dil }: { yetki: Yetki; dil: Dil }) {
  const t = metin(dil)
  return (
    <dl className="grid gap-0.5 text-xs text-muted-foreground">
      <div>
        <dt className="inline font-medium text-foreground">{t.rolYetkiNe}: </dt>
        <dd className="inline">{yerel(dil, yetki.description, yetki.description_en)}</dd>
      </div>
      <div>
        <dt className="inline font-medium text-foreground">{t.rolYetkiNerede}: </dt>
        <dd className="inline">{yerel(dil, yetki.where, yetki.where_en)}</dd>
      </div>
      <dd>{t.rolYetkiVarsayilan}</dd>
    </dl>
  )
}

/** Roldeki bir personel: ad soyad, AD kullanici adi, hesap turu ve son giris. `onSil` yalniz silme yetkilisi hesapta gelir (hata metni ya da null doner). */
function KisiSatiri({
  kisi,
  dil,
  onSil,
  roller,
  onRol,
  onAd,
}: {
  kisi: Kisi
  dil: Dil
  onSil?: (k: Kisi) => Promise<string | null>
  roller: Rol[]
  onRol: (k: Kisi, rol: string) => Promise<string | null>
  onAd: (k: Kisi, ad: string, soyad: string) => Promise<string | null>
}) {
  const t = metin(dil)
  const [onay, setOnay] = useState(false)
  const [mesgul, setMesgul] = useState(false)
  const [hata, setHata] = useState("")
  const [rolHata, setRolHata] = useState("")
  const [duzen, setDuzen] = useState(false)
  const [ad, setAd] = useState(kisi.first_name ?? "")
  const [soyad, setSoyad] = useState(kisi.last_name ?? "")
  const [adHata, setAdHata] = useState("")

  async function adKaydet(olay: React.FormEvent) {
    olay.preventDefault()
    setMesgul(true)
    setAdHata("")
    const sonuc = await onAd(kisi, ad, soyad)
    setMesgul(false)
    if (sonuc) setAdHata(sonuc)
    else setDuzen(false)
  }

  async function rolDegistir(rol: string) {
    if (rol === kisi.role) return
    setMesgul(true)
    setRolHata("")
    const sonuc = await onRol(kisi, rol)
    setMesgul(false)
    if (sonuc) setRolHata(sonuc)
  }

  async function sil() {
    if (!onSil) return
    setMesgul(true)
    setHata("")
    const sonuc = await onSil(kisi)
    setMesgul(false)
    if (sonuc) setHata(sonuc)
  }

  return (
    <li className="grid gap-2 rounded-lg border bg-background px-3 py-2">
      <div className="flex items-center gap-3">
        <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-tl-navy text-xs font-black text-tl-yellow">
          {baslangicHarfleri(kisi.display_name)}
        </span>
        <span className="grid min-w-0 flex-1">
          <span className="truncate text-sm font-medium">{kisi.display_name}</span>
          <span className="truncate font-mono text-xs text-muted-foreground" title={kisi.ad_domain ? `${kisi.ad_domain}\\${kisi.username}` : kisi.username}>
            {kisi.username}
          </span>
        </span>
        <span className="shrink-0 text-right text-xs text-muted-foreground">
          <span className="block font-medium">{kisi.auth === "AD" ? t.rolAdHesabi : kisi.auth === "Yerel" ? t.rolYerelHesap : "—"}</span>
          <span className="block">{kisi.last_login_at ? `${t.rolSonGiris}: ${zaman(kisi.last_login_at)}` : t.rolHicGirmedi}</span>
        </span>
        <button
          type="button"
          aria-label={t.kisiAdDuzenleAria(kisi.display_name)}
          title={t.kisiAdDuzenle}
          aria-expanded={duzen}
          onClick={() => {
            setAd(kisi.first_name ?? "")
            setSoyad(kisi.last_name ?? "")
            setAdHata("")
            setDuzen((a) => !a)
          }}
          className="grid size-8 shrink-0 place-items-center rounded-md border border-transparent text-muted-foreground transition-colors hover:border-input hover:bg-muted hover:text-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Pencil aria-hidden className="size-4" />
        </button>
        <select
          aria-label={t.kisiRolAria(kisi.display_name)}
          value={kisi.role}
          disabled={mesgul || kisi.self}
          title={kisi.self ? t.kisiRolKendi : undefined}
          onChange={(e) => void rolDegistir(e.target.value)}
          className="h-8 shrink-0 rounded-md border border-input bg-background px-2 text-xs font-medium focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
        >
          {kisi.role !== "TeamMngr" && kisi.role !== "TeamMember" ? (
            <option value={kisi.role} disabled>
              {kisi.role === "Pending" ? t.rolSecin : (t.rolEtiket[kisi.role] ?? kisi.role)}
            </option>
          ) : null}
          {roller
            .filter((r) => r.editable || r.role === "admin") /* 2026-11-12: admin rolu de Rol Yonetimi'nden atanabilir */
            .map((r) => (
              <option key={r.role} value={r.role}>
                {r.label}
              </option>
            ))}
        </select>
        {onSil && kisi.deletable ? (
          <button
            type="button"
            aria-label={t.kisiSilAria(kisi.display_name)}
            title={t.kisiSil}
            aria-expanded={onay}
            onClick={() => {
              setOnay((a) => !a)
              setHata("")
            }}
            className="grid size-8 shrink-0 place-items-center rounded-md border border-transparent text-muted-foreground transition-colors hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Trash2 aria-hidden className="size-4" />
          </button>
        ) : null}
      </div>
      {duzen ? (
        <form onSubmit={(e) => void adKaydet(e)} className="flex flex-wrap items-end gap-2 rounded-md border bg-muted/30 p-2">
          <label className="grid gap-1 text-xs font-medium">
            {t.kisiAdi}
            <input value={ad} onChange={(e) => setAd(e.target.value)} required maxLength={100} className="h-8 w-40 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring" />
          </label>
          <label className="grid gap-1 text-xs font-medium">
            {t.kisiSoyadi}
            <input value={soyad} onChange={(e) => setSoyad(e.target.value)} maxLength={100} className="h-8 w-40 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring" />
          </label>
          <Button type="submit" size="sm" disabled={mesgul || !ad.trim()}>
            {t.kaydet}
          </Button>
          <Button type="button" size="sm" variant="outline" disabled={mesgul} onClick={() => setDuzen(false)}>
            {t.vazgec}
          </Button>
          {adHata ? <p role="alert" className="w-full text-xs font-medium text-destructive">{adHata}</p> : null}
        </form>
      ) : null}
      {rolHata ? (
        <p role="alert" className="text-xs font-medium text-destructive">
          {rolHata}
        </p>
      ) : null}
      {onay ? (
        <div role="alert" className="grid gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs">
          <p className="text-sm font-semibold text-destructive">{t.kisiSilBaslik(kisi.display_name, kisi.username)}</p>
          <p className="text-muted-foreground">{t.kisiSilAciklama}</p>
          {hata ? <p className="font-medium text-destructive">{hata}</p> : null}
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="destructive" disabled={mesgul} onClick={() => void sil()}>
              {t.kisiSilEvet}
            </Button>
            <Button type="button" size="sm" variant="outline" disabled={mesgul} onClick={() => setOnay(false)}>
              {t.vazgec}
            </Button>
          </div>
        </div>
      ) : null}
    </li>
  )
}

/** Acilip kapanan rol kutusu: baslikta rol adi, sayfa ve kisi sayisi; icerik acilinca gorulen sayfalar ve roldeki personel. */
function RolKutusu({
  rol,
  acik,
  onDegis,
  durum,
  sayfaSayisi,
  kisiSayisi,
  dil,
  children,
}: {
  rol: Rol
  acik: boolean
  onDegis: () => void
  durum: string
  sayfaSayisi: number
  kisiSayisi: number
  dil: Dil
  children: ReactNode
}) {
  const t = metin(dil)
  return (
    <section className="overflow-hidden rounded-xl border bg-card text-card-foreground shadow-sm">
      <h3>
        <button
          type="button"
          id={`rol-baslik-${rol.role}`}
          aria-expanded={acik}
          aria-controls={`rol-icerik-${rol.role}`}
          onClick={onDegis}
          className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/50 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className="text-base font-semibold">{rol.label}</span>
          <span className="hidden text-xs text-muted-foreground sm:inline">{durum}</span>
          <span className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
            <span className="rounded-md bg-muted px-2 py-0.5 font-medium">{t.rolSayfaSayisi(sayfaSayisi)}</span>
            <span className="rounded-md bg-muted px-2 py-0.5 font-medium">{t.rolKisiSayisi(kisiSayisi)}</span>
            <ChevronDown aria-hidden className={`size-4 transition-transform ${acik ? "rotate-180" : ""}`} />
          </span>
        </button>
      </h3>
      {acik ? (
        <div id={`rol-icerik-${rol.role}`} role="region" aria-labelledby={`rol-baslik-${rol.role}`} className="grid gap-4 border-t px-4 py-4">
          {children}
        </div>
      ) : null}
    </section>
  )
}

/** Ceyrek Sunum baslinginin yanindaki asagi acilan liste: personel adlarinin yaninda onay kutusu; admin sunumu kimlerin yonetecegini kisi bazinda secer. */
function SunumKisiSecici({
  kisiler,
  roller,
  yetki,
  dil,
  mesgul,
  onDegis,
  bilgi,
}: {
  kisiler: Kisi[]
  roller: Rol[]
  yetki: Yetki
  dil: Dil
  mesgul: boolean
  onDegis: (kisi: Kisi, acik: boolean) => void
  bilgi: string
}) {
  const t = metin(dil)
  const s = sunumMetin(dil)
  const [acik, setAcik] = useState(false)
  const [ara, setAra] = useState("")
  const kutu = useRef<HTMLDivElement>(null)
  const dugme = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!acik) return
    const disariTikla = (olay: MouseEvent) => {
      if (!kutu.current?.contains(olay.target as Node)) setAcik(false)
    }
    const tus = (olay: KeyboardEvent) => {
      if (olay.key === "Escape") {
        setAcik(false)
        dugme.current?.focus()
      }
    }
    document.addEventListener("mousedown", disariTikla)
    document.addEventListener("keydown", tus)
    return () => {
      document.removeEventListener("mousedown", disariTikla)
      document.removeEventListener("keydown", tus)
    }
  }, [acik])

  const roldenMi = (k: Kisi) => roller.find((r) => r.role === k.role)?.permissions.includes(yetki.id) ?? false
  const adminMi = (k: Kisi) => k.role === "admin"
  const etkin = (k: Kisi) => adminMi(k) || roldenMi(k) || k.permissions.includes(yetki.id)
  const yetkiliSayisi = kisiler.filter(etkin).length
  const aranan = ara.trim().toLocaleLowerCase(dil === "en" ? "en" : "tr-TR")
  const gorunen = kisiler.filter((k) => !aranan || `${k.display_name} ${k.username}`.toLocaleLowerCase(dil === "en" ? "en" : "tr-TR").includes(aranan))

  return (
    <div className="relative" ref={kutu}>
      <button
        ref={dugme}
        type="button"
        aria-haspopup="true"
        aria-expanded={acik}
        onClick={() => setAcik((a) => !a)}
        className="inline-flex h-8 items-center gap-2 rounded-md border border-input bg-background px-3 text-xs font-medium shadow-xs transition-colors hover:bg-accent focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
      >
        {s.kisiYetkisi}
        <span className="rounded bg-tl-yellow px-1.5 py-0.5 text-[0.625rem] font-black text-tl-navy">{yetkiliSayisi}</span>
        <ChevronDown aria-hidden className={`size-4 transition-transform ${acik ? "rotate-180" : ""}`} />
      </button>
      {acik ? (
        <div role="group" aria-label={s.kisiYetkisi} className="absolute left-0 top-full z-30 mt-2 grid w-[min(24rem,calc(100vw-3rem))] gap-2 rounded-xl border bg-popover p-3 text-popover-foreground shadow-2xl">
          <p className="text-xs text-muted-foreground">{s.kisiYetkisiAciklama}</p>
          <label className="relative block">
            <span className="sr-only">{s.kisiAra}</span>
            <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              type="search"
              value={ara}
              onChange={(e) => setAra(e.target.value)}
              placeholder={s.kisiAra}
              className="h-8 w-full rounded-md border border-input bg-background pl-8 pr-2 text-xs focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
          <ul className="grid max-h-72 gap-0.5 overflow-y-auto pr-1">
            {gorunen.length === 0 ? <li className="px-2 py-3 text-center text-xs text-muted-foreground">{s.kisiYok}</li> : null}
            {gorunen.map((k) => {
              const kilitli = adminMi(k) || roldenMi(k)
              return (
                <li key={k.id}>
                  <label className={`flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm ${kilitli ? "opacity-80" : "cursor-pointer hover:bg-muted/60"}`}>
                    <input
                      type="checkbox"
                      checked={etkin(k)}
                      disabled={kilitli || mesgul}
                      onChange={(e) => onDegis(k, e.target.checked)}
                      aria-label={k.display_name}
                    />
                    <span className="grid min-w-0 flex-1">
                      <span className="truncate font-medium">{k.display_name}</span>
                      <span className="truncate font-mono text-[0.6875rem] text-muted-foreground">{k.username}</span>
                    </span>
                    {adminMi(k) ? (
                      <span className="shrink-0 text-[0.6875rem] text-muted-foreground">{s.adminHerZaman}</span>
                    ) : roldenMi(k) ? (
                      <span className="shrink-0 text-[0.6875rem] text-muted-foreground">{s.roldenGelir(t.rolEtiket[k.role] ?? k.role)}</span>
                    ) : null}
                  </label>
                </li>
              )
            })}
          </ul>
          <p role="status" className="text-xs text-muted-foreground">
            {bilgi || s.aninda}
          </p>
        </div>
      ) : null}
    </div>
  )
}

const ROLLER = ["roller"] as const

/** Giris yapmasi beklenen kisiyi onceden acar: kullanici adi + rol (+ istenirse Ceyrek Sunum yetkisi). Kisi ilk AD girisinde hazir gelir. */
function KisiEkle({ roller, sunumYetki, dil, onEklendi }: { roller: Rol[]; sunumYetki?: Yetki; dil: Dil; onEklendi: (k: Kisi) => void }) {
  const t = metin(dil)
  const duzenlenebilir = roller.filter((r) => r.editable || r.role === "admin")
  const [ad, setAd] = useState("")
  const [rol, setRol] = useState("TeamMember")
  const [sunum, setSunum] = useState(false)
  const [mesgul, setMesgul] = useState(false)
  const [bilgi, setBilgi] = useState({ hata: false, metin: "" })

  async function ekle(olay: React.FormEvent) {
    olay.preventDefault()
    setMesgul(true)
    setBilgi({ hata: false, metin: "" })
    try {
      const yetkiler = sunum && sunumYetki ? [sunumYetki.id] : []
      const k = await yaz<{ id: number; username: string; display_name: string; role: string; permissions: string[] }>("POST", "/api/v1/roller/kisiler", { username: ad, role: rol, permissions: yetkiler })
      onEklendi({ ...k, auth: "AD", ad_domain: "", last_login_at: null, deletable: false })
      setAd("")
      setSunum(false)
      setBilgi({ hata: false, metin: t.kisiEklendi(k.display_name, t.rolEtiket[k.role] ?? k.role) })
    } catch (hata) {
      setBilgi({ hata: true, metin: hataMesaji(hata, t.kisiEkleHata) })
    } finally {
      setMesgul(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <UserPlus aria-hidden className="size-4" />
          {t.kisiEkleBaslik}
        </CardTitle>
        <CardDescription>{t.kisiEkleAciklama}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={(e) => void ekle(e)} className="flex flex-wrap items-end gap-3">
          <label className="grid gap-1 text-xs font-medium">
            {t.kisiEkleKullanici}
            <input
              value={ad}
              onChange={(e) => setAd(e.target.value)}
              required
              maxLength={80}
              autoComplete="off"
              placeholder="tc12345"
              className="h-9 w-56 rounded-md border border-input bg-background px-2 font-mono text-sm focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
          <label className="grid gap-1 text-xs font-medium">
            {t.kisiEkleRol}
            <select value={rol} onChange={(e) => setRol(e.target.value)} className="h-9 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring">
              {duzenlenebilir.map((r) => (
                <option key={r.role} value={r.role}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
          {sunumYetki ? (
            <label className="flex h-9 items-center gap-2 text-sm font-medium">
              <input type="checkbox" checked={sunum} onChange={(e) => setSunum(e.target.checked)} />
              {yerel(dil, sunumYetki.label, sunumYetki.label_en)}
            </label>
          ) : null}
          <Button type="submit" disabled={mesgul || !ad.trim()}>
            {t.kisiEkleDugme}
          </Button>
        </form>
        {bilgi.metin ? (
          <p role={bilgi.hata ? "alert" : "status"} className={`mt-3 text-sm font-medium ${bilgi.hata ? "text-destructive" : "text-foreground"}`}>
            {bilgi.metin}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}

/** Rol Yonetimi: Yonetim disindaki her modul herkese acik (2026-10-14); admin yalniz sunum yetkisini verir; giris sayfasi secimi yok (herkes Genel Bakis'la acar). Sunucu da ayni kurali zorlar. */
export function RollerSayfasi({ dil }: { dil: Dil }) {
  const t = metin(dil)
  const s = sunumMetin(dil)
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ROLLER, queryFn: () => oku<Veri>("/api/v1/roller") })
  const veri = q.isError ? null : q.data
  /** Yazma sonucu onbellege islenir; once yoldaki yenileme iptal edilir: yazmadan once baslamis (eski veriyi tasiyan) bir yenileme
   * sonradan donup kaydedilen yetkiyi geri almasin (yuk-render.test.tsx). */
  const setVeri = (f: (v: Veri | undefined) => Veri | undefined) => {
    void qc.cancelQueries({ queryKey: ROLLER })
    qc.setQueryData<Veri>(ROLLER, f)
  }
  const [alanBilgi, setAlanBilgi] = useState({ bekliyor: false, metin: "" })
  const [acik, setAcik] = useState<Record<string, boolean>>({})
  const [silBilgi, setSilBilgi] = useState("")

  if (veri === undefined) return <p className="text-sm text-muted-foreground">{t.yukleniyor}</p>
  if (veri === null) return <p role="alert" className="text-sm text-destructive">{t.yuklenemedi}</p>

  const kisiler = veri.users ?? []
  const bekleyenler = kisiler.filter((k) => !veri.roles.some((r) => r.role === k.role))

  /** Bolumdeki (ornek Ceyrek Sunum) rol yetkisi aninda kaydedilir. Giris sayfasi secimi 2026-10-14'te kalkti: herkes Genel Bakis'la acar. */
  async function alanYetkisiKaydet(r: Rol, yetki: string, secili: boolean) {
    const kume = new Set(r.permissions)
    if (secili) kume.add(yetki)
    else kume.delete(yetki)
    setAlanBilgi({ bekliyor: true, metin: "" })
    try {
      const sonuc = await yaz<{ permissions: string[] }>("PUT", `/api/v1/roller/${r.role}`, { permissions: [...kume] })
      setVeri((v) => v && { ...v, roles: v.roles.map((x) => (x.role === r.role ? { ...x, permissions: sonuc.permissions, saved: true } : x)) })
      setAlanBilgi({ bekliyor: false, metin: t.rolKaydedildi })
    } catch {
      setAlanBilgi({ bekliyor: false, metin: t.rolKaydedilemedi })
    }
  }

  /** Kullanici silme (yalniz silme yetkilisi hesap; sunucu zorlar). Hata metnini doner, basarida null: satir yerelde listeden dusurulur,
   * boylece sayfa yeniden yuklenmez. */
  async function kisiSil(k: Kisi): Promise<string | null> {
    try {
      const sonuc = await yaz<{ devredilen: number }>("DELETE", `/api/v1/roller/kisiler/${k.id}`)
      setVeri((v) => v && { ...v, users: (v.users ?? []).filter((x) => x.id !== k.id) })
      setSilBilgi(t.kisiSilSilindi(k.display_name, sonuc.devredilen))
      return null
    } catch (hata) {
      return hataMesaji(hata, t.kisiSilHata)
    }
  }

  /** Admin kisinin ad ve soyadini duzeltir; basarida listedeki gorunen ad guncellenir. */
  async function kisiAdiKaydet(k: Kisi, ad: string, soyad: string): Promise<string | null> {
    try {
      const sonuc = await yaz<{ display_name: string; first_name: string; last_name: string }>("PUT", `/api/v1/roller/kisiler/${k.id}/ad`, { first_name: ad, last_name: soyad })
      setVeri((v) => v && { ...v, users: (v.users ?? []).map((x) => (x.id === k.id ? { ...x, display_name: sonuc.display_name, first_name: sonuc.first_name, last_name: sonuc.last_name } : x)) })
      setSilBilgi(t.kisiAdiKaydedildi(sonuc.display_name))
      return null
    } catch (hata) {
      return hataMesaji(hata, t.kisiAdiHata)
    }
  }

  /** Kisinin rolu degisir (yalniz admin; sunucu zorlar). Basarida satir yeni rolun kutusuna tasinir; hata metnini doner, basarida null. */
  async function kisiRoluKaydet(k: Kisi, rol: string): Promise<string | null> {
    try {
      await yaz<{ role: string }>("PUT", `/api/v1/roller/kisiler/${k.id}/rol`, { role: rol })
      setVeri((v) => v && { ...v, users: (v.users ?? []).map((x) => (x.id === k.id ? { ...x, role: rol } : x)) })
      setSilBilgi(t.kisiRolBilgi(k.display_name, t.rolEtiket[rol] ?? rol))
      return null
    } catch (hata) {
      return hataMesaji(hata, t.kisiRolHata)
    }
  }

  /** Kisiye ozel yetki aninda kaydedilir: yalniz o kisinin ek yetki listesi degisir, rolun yetkileri ve sayfalari ayni kalir. */
  async function kisiYetkisiKaydet(k: Kisi, yetki: string, secili: boolean) {
    const kume = new Set(k.permissions)
    if (secili) kume.add(yetki)
    else kume.delete(yetki)
    setAlanBilgi({ bekliyor: true, metin: "" })
    try {
      const sonuc = await yaz<{ permissions: string[] }>("PUT", `/api/v1/roller/kisiler/${k.id}`, { permissions: [...kume] })
      setVeri((v) => v && { ...v, users: (v.users ?? []).map((x) => (x.id === k.id ? { ...x, permissions: sonuc.permissions } : x)) })
      setAlanBilgi({ bekliyor: false, metin: t.rolKaydedildi })
    } catch {
      setAlanBilgi({ bekliyor: false, metin: t.rolKaydedilemedi })
    }
  }

  /** Rolun gorecegi moduller aninda kaydedilir: sunucuda RoleView.modules tablosuna yazilir, kullanicilarin sol menusune yansir. */
  async function modulYetkisiKaydet(r: Rol, kimlik: string, secili: boolean) {
    const kume = new Set(r.modules)
    if (secili) kume.add(kimlik)
    else kume.delete(kimlik)
    const yeniModuller = [...kume]
    setAlanBilgi({ bekliyor: true, metin: "" })
    try {
      const sonuc = await yaz<{ modules: string[]; permissions: string[] }>("PUT", `/api/v1/roller/${r.role}`, {
        modules: yeniModuller,
        permissions: r.permissions,
      })
      setVeri((v) =>
        v && {
          ...v,
          roles: v.roles.map((x) => (x.role === r.role ? { ...x, modules: sonuc.modules, saved: true } : x)),
        }
      )
      setAlanBilgi({ bekliyor: false, metin: t.rolKaydedildi })
    } catch {
      setAlanBilgi({ bekliyor: false, metin: t.rolKaydedilemedi })
    }
  }

  /** Bir roldeki tum modulleri tek seferde acar ya da kapatir. */
  async function tumModulleriAyarla(r: Rol, secili: boolean) {
    const yeniModuller = secili ? kimlikler : []
    setAlanBilgi({ bekliyor: true, metin: "" })
    try {
      const sonuc = await yaz<{ modules: string[]; permissions: string[] }>("PUT", `/api/v1/roller/${r.role}`, {
        modules: yeniModuller,
        permissions: r.permissions,
      })
      setVeri((v) =>
        v && {
          ...v,
          roles: v.roles.map((x) => (x.role === r.role ? { ...x, modules: sonuc.modules, saved: true } : x)),
        }
      )
      setAlanBilgi({ bekliyor: false, metin: t.rolKaydedildi })
    } catch {
      setAlanBilgi({ bekliyor: false, metin: t.rolKaydedilemedi })
    }
  }

  const kimlikler = veri.catalog.flatMap((m) => [m.id, ...m.children.map((c) => c.id)])
  const ad = (o: Etiket) => yerel(dil, o.label, o.label_en)
  const etiket = (kimlik: string) => {
    for (const m of veri.catalog) {
      if (m.id === kimlik) return ad(m)
      const c = m.children.find((x) => x.id === kimlik)
      if (c) return `${ad(m)} › ${ad(c)}`
    }
    return kimlik
  }
  const erisimYetkisi = veri.permission_catalog.find((y) => y.area === "utilizasyon")

  return (
    <div className="grid gap-4">
      <p className="text-sm text-muted-foreground">{t.rolAciklama}</p>
      <p className="text-xs text-muted-foreground">{t.kisiRolYeni}</p>
      {veri.can_delete_users === false && veri.delete_account ? <p className="text-xs text-muted-foreground">{t.kisiSilSadece(veri.delete_account)}</p> : null}
      {silBilgi ? (
        <p role="status" className="text-sm font-medium text-foreground">
          {silBilgi}
        </p>
      ) : null}
      <KisiEkle
        roller={veri.roles}
        sunumYetki={erisimYetkisi}
        dil={dil}
        onEklendi={(k) => setVeri((v) => v && { ...v, users: [...(v.users ?? []), k] })}
      />
      {bekleyenler.length > 0 ? (
        <section className="grid gap-2 rounded-xl border-2 border-tl-yellow bg-tl-yellow/10 p-4">
          <h3 className="text-sm font-semibold">
            {t.rolBekleyenler} ({bekleyenler.length})
          </h3>
          <p className="text-xs text-muted-foreground">{t.rolBekleyenAciklama}</p>
          <ul className="grid items-start gap-2 sm:grid-cols-2">
            {bekleyenler.map((k) => (
              <KisiSatiri key={k.id} kisi={k} dil={dil} onSil={veri.can_delete_users ? kisiSil : undefined} roller={veri.roles} onRol={kisiRoluKaydet} onAd={kisiAdiKaydet} />
            ))}
          </ul>
        </section>
      ) : null}
      <div className="grid gap-3">
        {veri.roles.map((r) => {
          const rolKisileri = kisiler.filter((k) => k.role === r.role)
          return (
            <RolKutusu
              key={r.role}
              rol={r}
              acik={!!acik[r.role]}
              onDegis={() => setAcik((o) => ({ ...o, [r.role]: !o[r.role] }))}
              durum={r.editable ? (r.saved ? t.rolKayitli : t.rolVarsayilan) : t.rolAdminSabit}
              sayfaSayisi={r.modules.length}
              kisiSayisi={rolKisileri.length}
              dil={dil}
            >
              {r.editable ? (
                <>
                  <div className="grid gap-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h4 className="text-xs font-medium text-muted-foreground">
                        {t.rolGorecegiSayfalar} ({r.modules.length}/{kimlikler.length})
                      </h4>
                      <div className="flex items-center gap-2">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-7 text-xs px-2.5"
                          disabled={alanBilgi.bekliyor}
                          onClick={() => void tumModulleriAyarla(r, true)}
                        >
                          {t.tumunuSec}
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-7 text-xs px-2.5 text-destructive hover:bg-destructive/10 hover:text-destructive"
                          disabled={alanBilgi.bekliyor}
                          onClick={() => void tumModulleriAyarla(r, false)}
                        >
                          {t.tumunuTemizle}
                        </Button>
                      </div>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-3">
                      {kimlikler.map((k) => {
                        const secili = r.modules.includes(k)
                        return (
                          <label
                            key={k}
                            className={`flex items-center gap-2 rounded-lg border p-2.5 text-xs font-medium transition-colors cursor-pointer select-none ${
                              secili
                                ? "border-primary/40 bg-primary/5 text-foreground"
                                : "border-border/60 bg-muted/20 text-muted-foreground opacity-60 hover:opacity-90"
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={secili}
                              disabled={alanBilgi.bekliyor}
                              onChange={(e) => void modulYetkisiKaydet(r, k, e.target.checked)}
                              className="size-4 rounded border-input text-primary focus:ring-primary"
                            />
                            <span className="truncate">{etiket(k)}</span>
                          </label>
                        )
                      })}
                    </div>
                  </div>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">{t.rolAdminAciklama}</p>
              )}
              <div className="grid gap-2">
                <h4 className="text-xs font-medium text-muted-foreground">
                  {t.rolKisiler} ({rolKisileri.length})
                </h4>
                {rolKisileri.length === 0 ? (
                  <p className="text-sm text-muted-foreground">{t.rolKisiYok}</p>
                ) : (
                  <ul className="grid items-start gap-2 sm:grid-cols-2">
                    {rolKisileri.map((k) => (
                      <KisiSatiri key={k.id} kisi={k} dil={dil} onSil={veri.can_delete_users ? kisiSil : undefined} roller={veri.roles} onRol={kisiRoluKaydet} onAd={kisiAdiKaydet} />
                    ))}
                  </ul>
                )}
              </div>
            </RolKutusu>
          )
        })}
      </div>
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center gap-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Presentation aria-hidden className="size-4" />
              {t.utilErisimBaslik}
            </CardTitle>
            {erisimYetkisi ? (
              <SunumKisiSecici kisiler={kisiler} roller={veri.roles} yetki={erisimYetkisi} dil={dil} mesgul={alanBilgi.bekliyor} onDegis={(k, secili) => void kisiYetkisiKaydet(k, erisimYetkisi.id, secili)} bilgi={alanBilgi.metin} />
            ) : null}
          </div>
          <CardDescription>{t.utilErisimAciklama}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <section className="grid content-start gap-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t.utilErisimKim}</h3>
            {veri.permission_catalog
              .filter((y) => y.area === "utilizasyon")
              .map((y) => (
                <div key={y.id} className="grid gap-2 rounded-lg border border-tl-yellow/60 bg-tl-yellow/10 p-3">
                  <p className="text-sm font-medium">{ad(y)}</p>
                  <YetkiAciklamasi yetki={y} dil={dil} />
                  <div className="flex flex-wrap gap-x-4 gap-y-1.5 pt-1">
                    {veri.roles.map((r) => (
                      <label key={r.role} className="flex items-center gap-2 text-sm font-medium">
                        <input
                          type="checkbox"
                          checked={!r.editable || r.permissions.includes(y.id)}
                          disabled={!r.editable || alanBilgi.bekliyor}
                          onChange={(e) => void alanYetkisiKaydet(r, y.id, e.target.checked)}
                        />
                        {r.label}
                        {r.editable ? null : <span className="text-xs font-normal text-muted-foreground">({s.herZaman})</span>}
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            <p role="status" className="text-xs text-muted-foreground">
              {alanBilgi.metin || s.aninda}
            </p>
          </section>
        </CardContent>
      </Card>
    </div>
  )
}
