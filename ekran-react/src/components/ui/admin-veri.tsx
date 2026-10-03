import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import type { Dil } from "@/components/ui/app-1-utils/app-1-data"
import { API_KOK } from "@/lib/api"

type Slot = {
  id: string
  ad: string
  host: string
  port: number
  service: string
  user: string
  parola: string
  parola_var: boolean
}

type IceKayit = {
  id: number
  ad: string
  yol: string
  zaman: string
  satir: number
}

type Form = {
  host: string
  port: string
  service: string
  user: string
  password: string
}

const YAZI = {
  tr: {
    baslik: "Veri al\u0131m\u0131",
    aciklama: "\u0130ki ba\u011flant\u0131 yuvas\u0131 ve CSV i\u00e7eri alma. Parola yan\u0131tta d\u00f6nmez.",
    host: "Host",
    port: "Port",
    service: "Servis",
    user: "Kullan\u0131c\u0131",
    parola: "Parola",
    parolaIpucu: "Bo\u015f b\u0131rak\u0131l\u0131rsa kay\u0131tl\u0131 parola durur.",
    parolaVar: "Parola kay\u0131tl\u0131",
    parolaYok: "Parola yok",
    kaydet: "Kaydet",
    dene: "Ba\u011flant\u0131y\u0131 dene",
    ulasti: "TCP ula\u015ft\u0131",
    ulasmadi: "TCP ula\u015fmad\u0131",
    iceBaslik: "\u0130\u00e7eri alma",
    iceAciklama: "CSV dosyas\u0131 veri/gelen alt\u0131na yaz\u0131l\u0131r ve ice_aktarim tablosuna i\u015flenir.",
    ice: "\u0130\u00e7eri alma",
    yukleniyor: "Y\u00fckleniyor",
    hata: "\u0130\u015flem yap\u0131lamad\u0131.",
    kaydedildi: "Kaydedildi.",
    satir: "sat\u0131r",
    sqlite: "SQLite",
    dosya: "CSV dosyas\u0131",
  },
  en: {
    baslik: "Data intake",
    aciklama: "Two connection slots and CSV intake. The password is never returned.",
    host: "Host",
    port: "Port",
    service: "Service",
    user: "User",
    parola: "Password",
    parolaIpucu: "Leave blank to keep the saved password.",
    parolaVar: "Password saved",
    parolaYok: "No password",
    kaydet: "Save",
    dene: "Test connection",
    ulasti: "TCP reachable",
    ulasmadi: "TCP unreachable",
    iceBaslik: "Import",
    iceAciklama: "The CSV is stored under veri/gelen and a row is written to ice_aktarim.",
    ice: "Import",
    yukleniyor: "Loading",
    hata: "The request failed.",
    kaydedildi: "Saved.",
    satir: "rows",
    sqlite: "SQLite",
    dosya: "CSV file",
  },
} as const

function formYap(slot: Slot): Form {
  return {
    host: slot.host,
    port: String(slot.port),
    service: slot.service,
    user: slot.user,
    password: "",
  }
}

export function AdminVeri({ dil }: { dil: Dil }) {
  const yazi = YAZI[dil]
  const [sqlite, setSqlite] = useState("")
  const [slotlar, setSlotlar] = useState<Slot[] | null>(null)
  const [formlar, setFormlar] = useState<Record<string, Form>>({})
  const [kayitlar, setKayitlar] = useState<IceKayit[]>([])
  const [hata, setHata] = useState<string | null>(null)
  const [bilgi, setBilgi] = useState<string | null>(null)
  const [sonuc, setSonuc] = useState<Record<string, string>>({})
  const [mesgul, setMesgul] = useState(false)
  const [dosya, setDosya] = useState<File | null>(null)

  function uygula(govde: { sqlite?: string; baglantilar?: Slot[] }) {
    const liste = Array.isArray(govde.baglantilar) ? govde.baglantilar : []
    setSqlite(govde.sqlite || "")
    setSlotlar(liste)
    setFormlar((eski) => {
      const sonraki: Record<string, Form> = {}
      for (const slot of liste) {
        const onceki = eski[slot.id]
        sonraki[slot.id] = onceki
          ? { ...formYap(slot), password: onceki.password }
          : formYap(slot)
      }
      return sonraki
    })
  }

  useEffect(() => {
    let iptal = false
    Promise.all([
      fetch(`${API_KOK}/api/admin/baglantilar`, { credentials: "include" }),
      fetch(`${API_KOK}/api/admin/ice-aktar`, { credentials: "include" }),
    ])
      .then(async ([baglanti, ice]) => {
        if (!baglanti.ok || !ice.ok) throw new Error(String(baglanti.status))
        const bagGovde = (await baglanti.json()) as { sqlite?: string; baglantilar?: Slot[] }
        const iceGovde = (await ice.json()) as { kayitlar?: IceKayit[] }
        if (iptal) return
        uygula(bagGovde)
        setKayitlar(Array.isArray(iceGovde.kayitlar) ? iceGovde.kayitlar : [])
      })
      .catch(() => {
        if (!iptal) setHata(yazi.hata)
      })
    return () => {
      iptal = true
    }
  }, [yazi.hata])

  function alan(id: string, ad: keyof Form, deger: string) {
    setFormlar((eski) => ({ ...eski, [id]: { ...eski[id], [ad]: deger } }))
    setBilgi(null)
  }

  function kaydet(id: string) {
    const form = formlar[id]
    if (!form) return
    setMesgul(true)
    setHata(null)
    setBilgi(null)
    const govde: Record<string, string | number> = {
      host: form.host,
      port: Number(form.port),
      service: form.service,
      user: form.user,
    }
    if (form.password) govde.password = form.password
    fetch(`${API_KOK}/api/admin/baglantilar/${id}`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(govde),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(String(response.status))
        uygula((await response.json()) as { sqlite?: string; baglantilar?: Slot[] })
        setFormlar((eski) => ({ ...eski, [id]: { ...eski[id], password: "" } }))
        setBilgi(yazi.kaydedildi)
      })
      .catch(() => setHata(yazi.hata))
      .finally(() => setMesgul(false))
  }

  function dene(id: string) {
    setMesgul(true)
    setHata(null)
    fetch(`${API_KOK}/api/admin/baglantilar/${id}/dene`, { method: "POST", credentials: "include" })
      .then(async (response) => {
        if (!response.ok) throw new Error(String(response.status))
        const govde = (await response.json()) as { sonuc?: { ulasti?: boolean; neden?: string } }
        const ulasti = Boolean(govde.sonuc?.ulasti)
        const neden = govde.sonuc?.neden ? ` (${govde.sonuc.neden})` : ""
        setSonuc((eski) => ({ ...eski, [id]: (ulasti ? yazi.ulasti : yazi.ulasmadi) + neden }))
      })
      .catch(() => setHata(yazi.hata))
      .finally(() => setMesgul(false))
  }

  function iceAl() {
    if (!dosya) return
    setMesgul(true)
    setHata(null)
    setBilgi(null)
    const paket = new FormData()
    paket.append("dosya", dosya)
    fetch(`${API_KOK}/api/admin/ice-aktar`, { method: "POST", credentials: "include", body: paket })
      .then(async (response) => {
        if (!response.ok) throw new Error(String(response.status))
        const liste = await fetch(`${API_KOK}/api/admin/ice-aktar`, { credentials: "include" })
        if (!liste.ok) throw new Error(String(liste.status))
        const govde = (await liste.json()) as { kayitlar?: IceKayit[] }
        setKayitlar(Array.isArray(govde.kayitlar) ? govde.kayitlar : [])
        setDosya(null)
        setBilgi(yazi.kaydedildi)
      })
      .catch(() => setHata(yazi.hata))
      .finally(() => setMesgul(false))
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>{yazi.baslik}</CardTitle>
          <CardDescription>{yazi.aciklama}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {hata ? <p className="text-sm text-destructive">{hata}</p> : null}
          {sqlite ? (
            <p className="text-xs text-muted-foreground">
              {yazi.sqlite}: {sqlite}
            </p>
          ) : null}
          {!slotlar ? <p className="text-sm text-muted-foreground">{yazi.yukleniyor}</p> : null}
        </CardContent>
      </Card>

      {slotlar?.map((slot) => {
        const form = formlar[slot.id]
        if (!form) return null
        return (
          <Card key={slot.id}>
            <CardHeader>
              <CardTitle>{slot.ad}</CardTitle>
              <CardDescription>{slot.parola_var ? yazi.parolaVar : yazi.parolaYok}</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-muted-foreground">{yazi.host}</span>
                <Input value={form.host} onChange={(event) => alan(slot.id, "host", event.target.value)} />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-muted-foreground">{yazi.port}</span>
                <Input value={form.port} inputMode="numeric" onChange={(event) => alan(slot.id, "port", event.target.value)} />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-muted-foreground">{yazi.service}</span>
                <Input value={form.service} onChange={(event) => alan(slot.id, "service", event.target.value)} />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-muted-foreground">{yazi.user}</span>
                <Input value={form.user} onChange={(event) => alan(slot.id, "user", event.target.value)} />
              </label>
              <label className="flex flex-col gap-1 text-sm sm:col-span-2">
                <span className="text-muted-foreground">{yazi.parola}</span>
                <Input
                  type="password"
                  autoComplete="new-password"
                  value={form.password}
                  placeholder={slot.parola || yazi.parolaIpucu}
                  onChange={(event) => alan(slot.id, "password", event.target.value)}
                />
                <span className="text-xs text-muted-foreground">{yazi.parolaIpucu}</span>
              </label>
              <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
                <Button type="button" onClick={() => kaydet(slot.id)} disabled={mesgul}>
                  {yazi.kaydet}
                </Button>
                <Button type="button" variant="outline" onClick={() => dene(slot.id)} disabled={mesgul}>
                  {yazi.dene}
                </Button>
                {sonuc[slot.id] ? <p className="text-sm text-muted-foreground">{sonuc[slot.id]}</p> : null}
                {bilgi ? <p className="text-sm text-muted-foreground">{bilgi}</p> : null}
              </div>
            </CardContent>
          </Card>
        )
      })}

      <Card>
        <CardHeader>
          <CardTitle>{yazi.iceBaslik}</CardTitle>
          <CardDescription>{yazi.iceAciklama}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">{yazi.dosya}</span>
            <Input
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => setDosya(event.target.files?.[0] ?? null)}
            />
          </label>
          <div>
            <Button type="button" onClick={iceAl} disabled={mesgul || !dosya}>
              {yazi.ice}
            </Button>
          </div>
          <ul className="flex flex-col gap-2">
            {kayitlar.map((kayit) => (
              <li key={kayit.id} className="text-sm">
                <span className="font-medium">{kayit.ad}</span>
                <span className="text-muted-foreground">
                  {" "}
                  {kayit.zaman} · {kayit.satir} {yazi.satir}
                </span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
