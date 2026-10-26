import { useEffect, useRef, useState } from "react"
import type { ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  Bold,
  ImagePlus,
  Italic,
  LayoutTemplate,
  Link2,
  List,
  RemoveFormatting,
  RotateCcw,
  Trash2,
  Underline,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

type Imza = { html: string; sablon: string; kayitli: boolean }

const AZAMI_GORSEL_KB = 600 // sunucu siniri (app.imza.AZAMI_GORSEL)
const GORSEL_TURLERI = ["image/png", "image/jpeg", "image/gif"]

/** Tarayicinin zengin metin komutu (Outlook imza editoru gibi; secili metne uygulanir). execCommand eski ama tum tarayicilarda calisir. */
function komut(ad: string, deger?: string) {
  document.execCommand(ad, false, deger)
}

function dosyaVeriUrl(dosya: File): Promise<string> {
  return new Promise((coz, reddet) => {
    const okuyucu = new FileReader()
    okuyucu.onload = () => coz(String(okuyucu.result))
    okuyucu.onerror = () => reddet(okuyucu.error)
    okuyucu.readAsDataURL(dosya)
  })
}

function AracDugmesi({ etiket, onClick, children }: { etiket: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      title={etiket}
      aria-label={etiket}
      // odak editorde kalsin: secim kaybolmadan komut uygulanir
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      className="inline-flex size-8 items-center justify-center rounded-md text-slate-600 hover:bg-slate-100 hover:text-tl-navy focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
    >
      {children}
    </button>
  )
}

/** Profil > E-posta imzasi (2026-10-26): Outlook imza editoru gibi yazi + gorsel + baglanti. Kaydedilen HTML sunucuda izin listesiyle
 *  temizlenir (app.imza) ve aylik rapor iletisinin imzasi olur. Kayit yoksa hazir sablon (Teknocan + ad / unvan / iletisim) acilir. */
export function ImzaEditoru({ dil }: { dil: Dil }) {
  const t = metin(dil).imza
  const alan = useRef<HTMLDivElement>(null)
  const secici = useRef<HTMLInputElement>(null)
  const q = useQuery({ queryKey: ["oturum", "imza"], queryFn: () => oku<Imza>("/api/v1/session/imza") })
  const [secili, setSecili] = useState<HTMLImageElement | null>(null)
  const [genislik, setGenislik] = useState(96)
  const [degisti, setDegisti] = useState(false)
  const [durum, setDurum] = useState<{ tur: "bos" | "calisiyor" | "tamam" | "hata"; metin: string }>({ tur: "bos", metin: "" })

  // Sunucudan gelen (temiz) imza editore bir kez yazilir; sonrasi kullanicinin elinde.
  useEffect(() => {
    if (q.data && alan.current && !degisti) alan.current.innerHTML = q.data.html || q.data.sablon
  }, [q.data, degisti])

  function elle() {
    setDegisti(true)
    setDurum({ tur: "bos", metin: "" })
  }

  function uygula(ad: string, deger?: string) {
    alan.current?.focus()
    komut(ad, deger)
    elle()
  }

  function baglanti() {
    const adres = window.prompt(t.baglantiSor, "https://")?.trim()
    if (adres && /^(https?:\/\/|mailto:|tel:)/i.test(adres)) uygula("createLink", adres)
  }

  async function gorselEkle(dosya: File | undefined) {
    if (!dosya) return
    if (!GORSEL_TURLERI.includes(dosya.type)) return setDurum({ tur: "hata", metin: t.gorselTur })
    if (dosya.size > AZAMI_GORSEL_KB * 1024) return setDurum({ tur: "hata", metin: t.gorselBuyuk(AZAMI_GORSEL_KB) })
    const url = await dosyaVeriUrl(dosya)
    alan.current?.focus()
    komut("insertHTML", `<img src="${url}" width="96" alt="">`)
    elle()
  }

  /** Outlook'taki klasik duzen: solda gorsel (Teknocan), sagda yazi. Gorsel sonradan secilip degistirilebilir. */
  function duzenEkle() {
    const gorsel = alan.current?.querySelector("img")?.getAttribute("src") ?? ""
    const yazi = t.duzenYazi
      .split("\n")
      .map((s, i) => (i === 0 ? `<b>${s}</b>` : s))
      .join("<br>")
    const sol = gorsel ? `<td valign="middle" style="padding-right:16px"><img src="${gorsel}" width="96" alt=""></td>` : ""
    alan.current?.focus()
    komut("insertHTML", `<table cellpadding="0" cellspacing="0" border="0"><tbody><tr>${sol}<td valign="middle">${yazi}</td></tr></tbody></table><p><br></p>`)
    elle()
  }

  function sablonaDon() {
    if (!q.data || !alan.current || !window.confirm(t.sablonOnay)) return
    alan.current.innerHTML = q.data.sablon
    setSecili(null)
    elle()
  }

  function tikla(hedef: EventTarget) {
    if (hedef instanceof HTMLImageElement) {
      setSecili(hedef)
      setGenislik(hedef.width || 96)
    } else setSecili(null)
  }

  function genislikYaz(px: number) {
    if (!secili) return
    setGenislik(px)
    secili.setAttribute("width", String(px))
    secili.removeAttribute("height") // oran korunsun
    elle()
  }

  function gorselSil() {
    secili?.remove()
    setSecili(null)
    elle()
  }

  async function kaydet() {
    if (!alan.current) return
    setDurum({ tur: "calisiyor", metin: t.kaydediliyor })
    try {
      const sonuc = await yaz<Imza>("PUT", "/api/v1/session/imza", { html: alan.current.innerHTML })
      alan.current.innerHTML = sonuc.html || sonuc.sablon // sunucunun temizledigi hal (ne gonderilecekse o gorunsun)
      setDegisti(false)
      setSecili(null)
      setDurum({ tur: "tamam", metin: sonuc.kayitli ? t.kaydedildi : t.silindi })
      void q.refetch()
    } catch (hata) {
      setDurum({ tur: "hata", metin: hataMesaji(hata, t.hata) })
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t.baslik}</CardTitle>
        <CardDescription>{t.aciklama}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div role="toolbar" aria-label={t.baslik} className="flex flex-wrap items-center gap-0.5 rounded-lg border border-slate-200 bg-slate-50 p-1">
          <AracDugmesi etiket={t.kalin} onClick={() => uygula("bold")}>
            <Bold aria-hidden className="size-4" />
          </AracDugmesi>
          <AracDugmesi etiket={t.italik} onClick={() => uygula("italic")}>
            <Italic aria-hidden className="size-4" />
          </AracDugmesi>
          <AracDugmesi etiket={t.alti} onClick={() => uygula("underline")}>
            <Underline aria-hidden className="size-4" />
          </AracDugmesi>
          <select
            aria-label={t.boyut}
            title={t.boyut}
            defaultValue=""
            onChange={(e) => {
              if (e.target.value) uygula("fontSize", e.target.value)
              e.target.value = ""
            }}
            className="h-8 rounded-md border border-slate-200 bg-white px-1.5 text-xs font-bold text-slate-600"
          >
            <option value="">{t.boyut}</option>
            {Object.entries(t.boyutlar).map(([k, ad]) => (
              <option key={k} value={k}>
                {ad}
              </option>
            ))}
          </select>
          <label title={t.renk} className="inline-flex size-8 cursor-pointer items-center justify-center rounded-md hover:bg-slate-100">
            <span className="sr-only">{t.renk}</span>
            <input type="color" defaultValue="#002855" onChange={(e) => uygula("foreColor", e.target.value)} className="size-5 cursor-pointer rounded border-0 bg-transparent p-0" />
          </label>
          <AracDugmesi etiket={t.baglanti} onClick={baglanti}>
            <Link2 aria-hidden className="size-4" />
          </AracDugmesi>
          <span aria-hidden className="mx-1 h-5 w-px bg-slate-200" />
          <AracDugmesi etiket={t.sola} onClick={() => uygula("justifyLeft")}>
            <AlignLeft aria-hidden className="size-4" />
          </AracDugmesi>
          <AracDugmesi etiket={t.ortala} onClick={() => uygula("justifyCenter")}>
            <AlignCenter aria-hidden className="size-4" />
          </AracDugmesi>
          <AracDugmesi etiket={t.saga} onClick={() => uygula("justifyRight")}>
            <AlignRight aria-hidden className="size-4" />
          </AracDugmesi>
          <AracDugmesi etiket={t.liste} onClick={() => uygula("insertUnorderedList")}>
            <List aria-hidden className="size-4" />
          </AracDugmesi>
          <span aria-hidden className="mx-1 h-5 w-px bg-slate-200" />
          <AracDugmesi etiket={t.gorsel} onClick={() => secici.current?.click()}>
            <ImagePlus aria-hidden className="size-4" />
          </AracDugmesi>
          <AracDugmesi etiket={t.duzen} onClick={duzenEkle}>
            <LayoutTemplate aria-hidden className="size-4" />
          </AracDugmesi>
          <AracDugmesi etiket={t.temizle} onClick={() => uygula("removeFormat")}>
            <RemoveFormatting aria-hidden className="size-4" />
          </AracDugmesi>
          <AracDugmesi etiket={t.sablon} onClick={sablonaDon}>
            <RotateCcw aria-hidden className="size-4" />
          </AracDugmesi>
          <input
            ref={secici}
            type="file"
            accept={GORSEL_TURLERI.join(",")}
            className="hidden"
            onChange={(e) => {
              void gorselEkle(e.target.files?.[0])
              e.target.value = ""
            }}
          />
        </div>

        {secili ? (
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-tl-blue/30 bg-sky-50 px-3 py-2 text-xs font-bold text-tl-navy">
            <label className="flex items-center gap-2">
              {t.gorselGenislik}
              <input type="range" aria-label={t.gorselGenislik} min={32} max={320} value={genislik} onChange={(e) => genislikYaz(Number(e.target.value))} />
              <span className="w-12 font-mono">{genislik} px</span>
            </label>
            <button type="button" onClick={gorselSil} className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-rose-600 hover:bg-rose-50">
              <Trash2 aria-hidden className="size-3.5" />
              {t.gorselSil}
            </button>
          </div>
        ) : null}

        {q.isPending ? <p className="text-sm text-muted-foreground">{t.yukleniyor}</p> : null}
        <div
          ref={alan}
          contentEditable={!q.isPending}
          suppressContentEditableWarning
          role="textbox"
          aria-multiline="true"
          aria-label={t.baslik}
          onInput={elle}
          onClick={(e) => tikla(e.target)}
          className="min-h-36 overflow-x-auto rounded-lg border border-input bg-white p-4 text-[13px] leading-normal text-slate-700 shadow-xs focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring [&_a]:text-tl-blue [&_a]:underline [&_img]:inline-block [&_img]:cursor-pointer [&_ul]:list-disc [&_ul]:pl-5"
        />
        {q.data && !q.data.kayitli && !degisti ? <p className="text-xs text-muted-foreground">{t.kayitliDegil}</p> : null}
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" onClick={() => void kaydet()} disabled={durum.tur === "calisiyor" || q.isPending || (!degisti && !!q.data?.kayitli)}>
            {durum.tur === "calisiyor" ? t.kaydediliyor : t.kaydet}
          </Button>
          <span role="status" className={`text-sm ${durum.tur === "hata" ? "text-destructive" : "text-muted-foreground"}`}>
            {durum.tur === "calisiyor" ? "" : durum.metin}
          </span>
        </div>
      </CardContent>
    </Card>
  )
}
