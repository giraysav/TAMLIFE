import { useCallback, useEffect, useRef, useState } from "react"
import type { ReactNode } from "react"
import { ChevronDown, Presentation, Search, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { baslangicHarfleri, zaman } from "@/lib/bicim"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { metin, yerel } from "@/shell/metin"
import type { Dil } from "@/shell/metin"
import { SunumKaynaklari } from "@/sunum/sunum-kaynaklari"
import { sunumMetin } from "@/sunum/sunum-metin"

type Rol = { role: string; label: string; editable: boolean; modules: string[]; landing: string; permissions: string[]; saved: boolean }
/** Panelde kaydi olan personel (AD ile giren ya da yoneticinin actigi). `permissions` yalniz kisiye ozel verilenlerdir; rolden gelenler `roles` icindedir. */
type Kisi = { id: number; username: string; display_name: string; role: string; auth: string; ad_domain: string; last_login_at: string | null; permissions: string[]; deletable?: boolean }
type Etiket = { id: string; label: string; label_en?: string }
type Katalog = Etiket & { children: Etiket[] }
/** Eylem yetkisi: duz dilde ne sagladigi ve nerede kullanildigi. Rol kartindaki "Ek yetkiler" kaldirildi (2026-10-11, amaci belirsizdi);
 * yalniz kendi bolumu olan yetkiler (ornek "sunum") Rol Yonetimi'nde duzenlenir. Kayitli yetkiler rol kaydedilince korunur. */
type Yetki = Etiket & { description: string; description_en: string; where: string; where_en: string; area: string }
/** `can_delete_users`/`delete_account`: kullanici silme yalniz tek hesapta (sunucu zorlar); `deletable` kisi basina dugme gosterimi icin. */
type Veri = { roles: Rol[]; catalog: Katalog[]; permission_catalog: Yetki[]; users?: Kisi[]; can_delete_users?: boolean; delete_account?: string }
type Taslak = { modules: Set<string>; landing: string; permissions: Set<string> }

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
function KisiSatiri({ kisi, dil, onSil }: { kisi: Kisi; dil: Dil; onSil?: (k: Kisi) => Promise<string | null> }) {
  const t = metin(dil)
  const [onay, setOnay] = useState(false)
  const [mesgul, setMesgul] = useState(false)
  const [hata, setHata] = useState("")

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

/** Acilip kapanan rol kutusu: baslikta rol adi, sayfa ve kisi sayisi; icerik acilinca sayfa secimi, giris sayfasi ve roldeki personel. */
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

/** Ceyrek Bazli Sunum baslinginin yanindaki asagi acilan liste: personel adlarinin yaninda onay kutusu; admin sunumu kimlerin yonetecegini kisi bazinda secer. */
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

/** Rol Yonetimi: admin her rolun gorecegi sayfalari ve giris sayfasini belirler. Sunucu da ayni kurali zorlar. */
export function RollerSayfasi({ dil }: { dil: Dil }) {
  const t = metin(dil)
  const s = sunumMetin(dil)
  const [veri, setVeri] = useState<Veri | null | undefined>(undefined)
  const [taslak, setTaslak] = useState<Record<string, Taslak>>({})
  const [bilgi, setBilgi] = useState<Record<string, string>>({})
  const [alanBilgi, setAlanBilgi] = useState({ bekliyor: false, metin: "" })
  const [acik, setAcik] = useState<Record<string, boolean>>({})
  const [silBilgi, setSilBilgi] = useState("")

  const yukle = useCallback(async () => {
    const govde = await oku<Veri>("/api/v1/roller").catch(() => null)
    setVeri(govde)
    if (govde) {
      setTaslak(Object.fromEntries(govde.roles.map((r) => [r.role, { modules: new Set(r.modules), landing: r.landing, permissions: new Set(r.permissions) }])))
    }
  }, [])

  useEffect(() => {
    void yukle()
  }, [yukle])

  if (veri === undefined) return <p className="text-sm text-muted-foreground">{t.yukleniyor}</p>
  if (veri === null) return <p role="alert" className="text-sm text-destructive">{t.yuklenemedi}</p>

  const kisiler = veri.users ?? []

  function degistir(rol: string, kimlik: string, secili: boolean) {
    setTaslak((onceki) => {
      const mevcut = onceki[rol]
      const kume = new Set(mevcut.modules)
      if (secili) kume.add(kimlik)
      else kume.delete(kimlik)
      const landing = mevcut.landing !== "ozet" && !kume.has(mevcut.landing) ? "ozet" : mevcut.landing
      return { ...onceki, [rol]: { ...mevcut, modules: kume, landing } }
    })
  }

  async function kaydet(rol: string) {
    const t1 = taslak[rol]
    setBilgi((b) => ({ ...b, [rol]: "" }))
    try {
      await yaz("PUT", `/api/v1/roller/${rol}`, { modules: [...t1.modules], landing: t1.landing, permissions: [...t1.permissions] })
      setBilgi((b) => ({ ...b, [rol]: t.rolKaydedildi }))
      await yukle()
    } catch {
      setBilgi((b) => ({ ...b, [rol]: t.rolKaydedilemedi }))
    }
  }

  /** Bolumdeki (ornek Ceyrek Bazli Sunum) rol yetkisi aninda kaydedilir: rolun KAYITLI sayfalari korunur, karttaki kaydedilmemis taslak gonderilmez. */
  async function alanYetkisiKaydet(r: Rol, yetki: string, secili: boolean) {
    const kume = new Set(r.permissions)
    if (secili) kume.add(yetki)
    else kume.delete(yetki)
    setAlanBilgi({ bekliyor: true, metin: "" })
    try {
      const sonuc = await yaz<{ permissions: string[] }>("PUT", `/api/v1/roller/${r.role}`, { modules: r.modules, landing: r.landing, permissions: [...kume] })
      setVeri((v) => v && { ...v, roles: v.roles.map((x) => (x.role === r.role ? { ...x, permissions: sonuc.permissions, saved: true } : x)) })
      setTaslak((o) => (o[r.role] ? { ...o, [r.role]: { ...o[r.role], permissions: new Set(sonuc.permissions) } } : o))
      setAlanBilgi({ bekliyor: false, metin: t.rolKaydedildi })
    } catch {
      setAlanBilgi({ bekliyor: false, metin: t.rolKaydedilemedi })
    }
  }

  /** Kullanici silme (yalniz silme yetkilisi hesap; sunucu zorlar). Hata metnini doner, basarida null: satir yerelde listeden dusurulur,
   * boylece rol kutularindaki kaydedilmemis sayfa secimleri bozulmaz. */
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
  const sunumYetkisi = veri.permission_catalog.find((y) => y.area === "sunum")

  return (
    <div className="grid gap-4">
      <p className="text-sm text-muted-foreground">{t.rolAciklama}</p>
      {veri.can_delete_users === false && veri.delete_account ? <p className="text-xs text-muted-foreground">{t.kisiSilSadece(veri.delete_account)}</p> : null}
      {silBilgi ? (
        <p role="status" className="text-sm font-medium text-foreground">
          {silBilgi}
        </p>
      ) : null}
      <div className="grid gap-3">
        {veri.roles.map((r) => {
          const tas = taslak[r.role]
          const secili = kimlikler.filter((k) => tas?.modules.has(k))
          const rolKisileri = kisiler.filter((k) => k.role === r.role)
          return (
            <RolKutusu
              key={r.role}
              rol={r}
              acik={!!acik[r.role]}
              onDegis={() => setAcik((o) => ({ ...o, [r.role]: !o[r.role] }))}
              durum={r.editable ? (r.saved ? t.rolKayitli : t.rolVarsayilan) : t.rolAdminSabit}
              sayfaSayisi={r.editable ? secili.length : r.modules.length}
              kisiSayisi={rolKisileri.length}
              dil={dil}
            >
              {r.editable ? (
                <>
                  <fieldset className="grid gap-2">
                    <legend className="mb-1 text-xs font-medium text-muted-foreground">{t.rolGorecegiSayfalar}</legend>
                    <div className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
                      {veri.catalog.map((m) => (
                        <div key={m.id} className="grid content-start gap-1">
                          <label className="flex items-center gap-2 text-sm font-medium">
                            <input type="checkbox" checked={!!tas?.modules.has(m.id)} onChange={(e) => degistir(r.role, m.id, e.target.checked)} />
                            {ad(m)}
                          </label>
                          {m.children.map((c) => (
                            <label key={c.id} className="ml-6 flex items-center gap-2 text-sm">
                              <input type="checkbox" checked={!!tas?.modules.has(c.id)} onChange={(e) => degistir(r.role, c.id, e.target.checked)} />
                              {ad(c)}
                            </label>
                          ))}
                        </div>
                      ))}
                    </div>
                  </fieldset>
                  <div className="flex flex-wrap items-end gap-4">
                    <label className="grid gap-1 text-sm">
                      <span className="text-xs font-medium text-muted-foreground">{t.rolGirisSayfasi}</span>
                      <select
                        className="h-9 min-w-56 rounded-md border bg-background px-2"
                        value={tas?.landing ?? "ozet"}
                        onChange={(e) => setTaslak((o) => (o[r.role] ? { ...o, [r.role]: { ...o[r.role], landing: e.target.value } } : o))}
                      >
                        <option value="ozet">{t.genelBakis}</option>
                        {secili.map((k) => (
                          <option key={k} value={k}>
                            {etiket(k)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="flex items-center gap-3">
                      <Button type="button" size="sm" onClick={() => void kaydet(r.role)}>
                        {t.kaydet}
                      </Button>
                      {bilgi[r.role] ? (
                        <span role="status" className="text-sm text-muted-foreground">
                          {bilgi[r.role]}
                        </span>
                      ) : null}
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
                      <KisiSatiri key={k.id} kisi={k} dil={dil} onSil={veri.can_delete_users ? kisiSil : undefined} />
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
              {s.baslik}
            </CardTitle>
            {sunumYetkisi ? (
              <SunumKisiSecici kisiler={kisiler} roller={veri.roles} yetki={sunumYetkisi} dil={dil} mesgul={alanBilgi.bekliyor} onDegis={(k, secili) => void kisiYetkisiKaydet(k, sunumYetkisi.id, secili)} bilgi={alanBilgi.metin} />
            ) : null}
          </div>
          <CardDescription>{s.alanAciklama}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
          <section className="grid content-start gap-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">1 · {s.kimYonetir}</h3>
            {veri.permission_catalog
              .filter((y) => y.area === "sunum")
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
          <section className="grid content-start gap-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">2 · {s.kaynaklarBaslik}</h3>
            <SunumKaynaklari dil={dil} />
          </section>
        </CardContent>
      </Card>
    </div>
  )
}
