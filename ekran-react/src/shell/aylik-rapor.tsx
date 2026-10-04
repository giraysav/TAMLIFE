import { useCallback, useEffect, useState } from "react"
import type { FormEvent, ReactNode } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiOku, apiYaz } from "@/lib/api-yaz"
import type { Dil } from "@/shell/metin"
import { musteriMetin } from "@/shell/musteri-metin"

type Gonderim = { id: number; yil: number; ay: number; gonderen: string; zaman: string; konu: string; durum: string; pdf: boolean; geri_alan: string | null }
type Taslak = {
  yil: number
  ay: number
  birim: boolean
  alanlar: Record<string, string>
  kayitli: boolean
  guncelleyen: string | null
  zaman: string | null
  alicilar: { kime: string; bilgi: string }
  gonderim: Gonderim | null
}

const METINLER = ["olumlu", "devam", "kritik", "bilgi", "oneri"] as const

function Blok({ baslik, children }: { baslik: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{baslik}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">{children}</CardContent>
    </Card>
  )
}

function dosyaOku(dosya: File): Promise<string> {
  return new Promise((coz, reddet) => {
    const okuyucu = new FileReader()
    okuyucu.onload = () => coz(String(okuyucu.result))
    okuyucu.onerror = () => reddet(new Error("okunamadi"))
    okuyucu.readAsDataURL(dosya)
  })
}

/** Musteri kartinin arkasindaki aylik rapor: taslak (hazir metinlerle), alicilar, ONAYLI ayda tek gonderim, gecmis. */
export function AylikRapor({ musteriId, dil, geriAlabilir }: { musteriId: number; dil: Dil; geriAlabilir: boolean }) {
  const t = musteriMetin(dil)
  const taban = `/api/v1/musteri/${musteriId}/rapor`
  const [taslak, setTaslak] = useState<Taslak | null | undefined>(undefined)
  const [alanlar, setAlanlar] = useState<Record<string, string>>({})
  const [alici, setAlici] = useState({ kime: "", bilgi: "" })
  const [gecmis, setGecmis] = useState<Gonderim[]>([])
  const [pdf, setPdf] = useState<File | null>(null)
  const [mesaj, setMesaj] = useState<Record<string, string>>({})

  const yukle = useCallback(async () => {
    const [t1, g1] = await Promise.all([apiOku<Taslak>(`${taban}/taslak`), apiOku<Gonderim[]>(`${taban}/gecmis`)])
    setTaslak(t1.ok ? t1.veri : null)
    if (t1.veri) {
      setAlanlar(t1.veri.alanlar)
      setAlici({ kime: t1.veri.alicilar.kime, bilgi: t1.veri.alicilar.bilgi })
    }
    setGecmis(g1.ok && g1.veri ? g1.veri : [])
  }, [taban])

  useEffect(() => {
    void yukle()
  }, [yukle])

  const bildir = (anahtar: string, metin: string) => setMesaj((m) => ({ ...m, [anahtar]: metin }))

  if (taslak === undefined) return <p className="text-sm text-muted-foreground">…</p>
  if (taslak === null) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t.yuklenemedi}
      </p>
    )
  }
  const kilitli = taslak.gonderim !== null

  async function taslagiKaydet(olay: FormEvent) {
    olay.preventDefault()
    const sonuc = await apiYaz("PUT", `${taban}/taslak`, { alanlar })
    bildir("taslak", sonuc.ok ? t.kaydedildi : sonuc.durum === 409 ? t.gonderimKilitli : `${t.kaydedilemedi}: ${sonuc.hata}`)
    if (sonuc.ok) await yukle()
  }

  async function alicilariKaydet(olay: FormEvent) {
    olay.preventDefault()
    const sonuc = await apiYaz("PUT", `${taban}/alicilar`, alici)
    bildir("alici", sonuc.ok ? t.kaydedildi : `${t.kaydedilemedi}: ${sonuc.hata}`)
  }

  async function gonder() {
    if (!window.confirm(t.gonderOnay)) return
    let pdfVeri: string | undefined
    if (pdf) {
      try {
        pdfVeri = await dosyaOku(pdf)
      } catch {
        bildir("gonder", t.kaydedilemedi)
        return
      }
    }
    const sonuc = await apiYaz("POST", `${taban}/gonder`, { onay: true, subject: alanlar.konu, ...(pdfVeri ? { pdf_base64: pdfVeri } : {}) })
    bildir("gonder", sonuc.ok ? t.gonderildi : sonuc.durum === 409 ? t.gonderimKilitli : `${t.kaydedilemedi}: ${sonuc.hata}`)
    setPdf(null)
    await yukle()
  }

  async function geriAl(id: number) {
    if (!window.confirm(t.geriAlOnay)) return
    const sonuc = await apiYaz("POST", `/api/v1/rapor/gonderim/${id}/geri-al`)
    bildir("gecmis", sonuc.ok ? "" : `${t.kaydedilemedi}: ${sonuc.hata}`)
    await yukle()
  }

  const yaz = (anahtar: string, deger: string) => setAlanlar((a) => ({ ...a, [anahtar]: deger }))
  const metinAlani = (anahtar: string, etiket: string, satir = 4, uzun = 10000) => (
    <div className="grid gap-1.5" key={anahtar}>
      <Label htmlFor={`r-${anahtar}`}>{etiket}</Label>
      <textarea
        id={`r-${anahtar}`}
        rows={satir}
        maxLength={uzun}
        disabled={kilitli}
        value={alanlar[anahtar] ?? ""}
        onChange={(ev) => yaz(anahtar, ev.target.value)}
        className="min-h-9 w-full rounded-md border bg-background px-3 py-2 text-sm disabled:opacity-60"
      />
    </div>
  )

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">
          {t.donem}: {String(taslak.ay).padStart(2, "0")}.{taslak.yil}
        </span>
        {kilitli ? <Badge>{t.gonderildi}</Badge> : taslak.kayitli ? <Badge variant="secondary">{t.taslak}</Badge> : null}
        {taslak.guncelleyen ? <span className="text-muted-foreground">{taslak.guncelleyen}</span> : null}
      </div>
      {!taslak.birim ? <p className="rounded-md border bg-muted/40 p-3 text-sm">{t.rapordaBirimDegil}</p> : null}
      {kilitli ? (
        <p role="status" className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm">
          {t.gonderimKilitli}
        </p>
      ) : null}

      <form onSubmit={taslagiKaydet} className="grid gap-4" aria-label={t.sekmeRapor}>
        <Blok baslik={t.taslak}>
          <div className="grid gap-1.5 sm:max-w-xs">
            <Label htmlFor="r-dil">{t.dil}</Label>
            <select id="r-dil" disabled={kilitli} value={alanlar.dil ?? "tr"} onChange={(ev) => yaz("dil", ev.target.value)} className="h-9 rounded-md border bg-background px-2 text-sm">
              <option value="tr">{t.tr}</option>
              <option value="en">{t.en}</option>
            </select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="r-konu">{t.konu}</Label>
            <Input id="r-konu" disabled={kilitli} maxLength={200} value={alanlar.konu ?? ""} onChange={(ev) => yaz("konu", ev.target.value)} />
          </div>
          {metinAlani("govde", t.govde, 8)}
          {metinAlani("imza", t.imza, 3, 2000)}
          {METINLER.map((a) => metinAlani(a, t[a], a === "bilgi" || a === "oneri" ? 7 : 3, a === "bilgi" || a === "oneri" ? 20000 : 10000))}
          {!kilitli ? (
            <div className="flex items-center gap-3">
              <Button type="submit">{t.taslagiKaydet}</Button>
              {mesaj.taslak ? <span role="status" className="text-sm text-muted-foreground">{mesaj.taslak}</span> : null}
            </div>
          ) : null}
        </Blok>
      </form>

      <Blok baslik={t.alicilar}>
        <form onSubmit={alicilariKaydet} className="grid gap-3" aria-label={t.alicilar}>
          <div className="grid gap-1.5">
            <Label htmlFor="r-kime">{t.kime}</Label>
            <Input id="r-kime" value={alici.kime} maxLength={5000} onChange={(ev) => setAlici({ ...alici, kime: ev.target.value })} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="r-cc">{t.bilgiCc}</Label>
            <Input id="r-cc" value={alici.bilgi} maxLength={5000} onChange={(ev) => setAlici({ ...alici, bilgi: ev.target.value })} />
          </div>
          <p className="text-xs text-muted-foreground">{t.alicilarAyrac}</p>
          <div className="flex items-center gap-3">
            <Button type="submit" variant="outline">
              {t.alicilariKaydet}
            </Button>
            {mesaj.alici ? <span role="status" className="text-sm text-muted-foreground">{mesaj.alici}</span> : null}
          </div>
        </form>
      </Blok>

      {!kilitli ? (
        <Blok baslik={t.gonder}>
          <div className="grid gap-1.5 sm:max-w-sm">
            <Label htmlFor="r-pdf">{t.pdfEkle}</Label>
            <Input id="r-pdf" type="file" accept="application/pdf" onChange={(ev) => setPdf(ev.target.files?.[0] ?? null)} />
          </div>
          <p className="text-xs text-muted-foreground">{t.emlNot}</p>
          <div className="flex items-center gap-3">
            <Button type="button" onClick={() => void gonder()}>
              {t.gonder}
            </Button>
            {mesaj.gonder ? <span role="status" className="text-sm text-muted-foreground">{mesaj.gonder}</span> : null}
          </div>
        </Blok>
      ) : null}

      <Blok baslik={t.gecmis}>
        {gecmis.length === 0 ? <p className="text-sm text-muted-foreground">{t.gecmisYok}</p> : null}
        <ul className="grid gap-2 text-sm">
          {gecmis.map((g) => (
            <li key={g.id} className="flex flex-wrap items-center gap-2 border-b pb-2 last:border-0">
              <span className="tabular-nums">
                {String(g.ay).padStart(2, "0")}.{g.yil}
              </span>
              <span className="flex-1">{g.konu}</span>
              <span className="text-muted-foreground">
                {g.gonderen} · {g.zaman.slice(0, 16).replace("T", " ")}
              </span>
              {g.durum === "reverted" ? <Badge variant="secondary">{t.geriAlindi}</Badge> : null}
              {g.durum === "sent" && geriAlabilir ? (
                <Button type="button" size="sm" variant="outline" onClick={() => void geriAl(g.id)}>
                  {t.geriAl}
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
        {mesaj.gecmis ? <p role="alert" className="text-sm text-destructive">{mesaj.gecmis}</p> : null}
      </Blok>
    </div>
  )
}
