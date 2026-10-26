import { useEffect, useRef, useState } from "react"
import type { ReactNode } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  Bold,
  Copy,
  ImagePlus,
  Italic,
  LayoutTemplate,
  Link2,
  PencilLine,
  List,
  RemoveFormatting,
  RotateCcw,
  Trash2,
  Underline,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

type Mod = "kurumsal" | "serbest" | ""
type Alanlar = { unvan: string; birim: string; sabit: string; eposta: string }
type Imza = {
  mod: Mod
  kayitli: boolean
  alanlar: Alanlar
  kurumsal_html: string
  html: string
  sablon: string
}
type Durum = { tur: "bos" | "calisiyor" | "tamam" | "hata"; metin: string }

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

/** Panoya zengin metin (Outlook imza ayarina yapistirilir); desteklenmezse secip kopyalar. */
async function panoyaKopyala(html: string, duz: string): Promise<boolean> {
  try {
    if (navigator.clipboard && "write" in navigator.clipboard && typeof ClipboardItem !== "undefined") {
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/html": new Blob([html], { type: "text/html" }),
          "text/plain": new Blob([duz], { type: "text/plain" }),
        }),
      ])
      return true
    }
  } catch {
    /* asagidaki yola duser */
  }
  const kutu = document.createElement("div")
  kutu.innerHTML = html
  kutu.style.position = "fixed"
  kutu.style.left = "-9999px"
  document.body.appendChild(kutu)
  const aralik = document.createRange()
  aralik.selectNodeContents(kutu)
  const secim = window.getSelection()
  secim?.removeAllRanges()
  secim?.addRange(aralik)
  const tamam = document.execCommand("copy")
  secim?.removeAllRanges()
  kutu.remove()
  return tamam
}

/** Profil > E-posta imzasi (2026-10-26): iki kip. Kurumsal (varsayilan; masaustundeki imza.html tasarimi, sunucuda uretilir: app.imza.kurumsal)
 *  ve Serbest (Outlook imza editoru gibi). Kaydedilen kip aylik rapor iletisinin imzasidir. */
export function ImzaEditoru({ dil }: { dil: Dil }) {
  const t = metin(dil).imza
  const q = useQuery({
    queryKey: ["oturum", "imza"],
    queryFn: () => oku<Imza>("/api/v1/session/imza"),
  })
  const [sekme, setSekme] = useState<"kurumsal" | "serbest" | null>(null)
  const [aktarilan, setAktarilan] = useState<string | null>(null)
  const [durum, setDurum] = useState<Durum>({ tur: "bos", metin: "" })
  const istemci = useQueryClient()
  const etkin = sekme ?? (q.data?.mod === "serbest" ? "serbest" : "kurumsal")
  const guncel = (v: Imza) => istemci.setQueryData(["oturum", "imza"], v)

  async function kaldir() {
    if (!window.confirm(t.kaldirOnay)) return
    try {
      guncel(await yaz<Imza>("PUT", "/api/v1/session/imza", { mod: "" }))
      setDurum({ tur: "tamam", metin: t.kaldirildi })
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
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div role="tablist" aria-label={t.baslik} className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5">
            {(["kurumsal", "serbest"] as const).map((k) => (
              <button
                key={k}
                type="button"
                role="tab"
                aria-selected={etkin === k}
                onClick={() => setSekme(k)}
                className={`rounded-md px-3 py-1.5 text-xs font-black ${etkin === k ? "bg-tl-navy text-white shadow-sm" : "text-tl-navy hover:bg-white"}`}
              >
                {k === "kurumsal" ? t.sekmeKurumsal : t.sekmeSerbest}
              </button>
            ))}
          </div>
          {q.data ? (
            <span className="flex items-center gap-2 text-xs font-bold text-slate-500">
              {t.kullanilan[q.data.mod] ?? ""}
              {q.data.kayitli ? (
                <button type="button" onClick={() => void kaldir()} className="rounded-md px-2 py-1 text-rose-600 hover:bg-rose-50">
                  {t.kaldir}
                </button>
              ) : null}
            </span>
          ) : null}
        </div>
        {q.isPending ? <p className="text-sm text-muted-foreground">{t.yukleniyor}</p> : null}
        {q.data && etkin === "kurumsal" ? (
          <KurumsalImza
            dil={dil}
            veri={q.data}
            onKaydedildi={guncel}
            onAktar={(html) => {
              setAktarilan(html)
              setSekme("serbest")
            }}
          />
        ) : null}
        {q.data && etkin === "serbest" ? (
          <SerbestImza key={aktarilan ?? "kayitli"} dil={dil} veri={q.data} baslangic={aktarilan} onKaydedildi={guncel} />
        ) : null}
        {durum.metin ? (
          <span role="status" className={`text-sm ${durum.tur === "hata" ? "text-destructive" : "text-muted-foreground"}`}>
            {durum.metin}
          </span>
        ) : null}
      </CardContent>
    </Card>
  )
}

const ALAN_SIRASI = ["unvan", "birim", "sabit", "eposta"] as const
const BOS_ALANLAR: Partial<Alanlar> = { unvan: "", birim: "", sabit: "", eposta: "" }

/** Kurumsal imza: dort alan + canli onizleme (sunucu uretir; yazdikca 300 ms sonra yenilenir). */
function KurumsalImza({ dil, veri, onKaydedildi, onAktar }: { dil: Dil; veri: Imza; onKaydedildi: (v: Imza) => void; onAktar: (html: string) => void }) {
  const t = metin(dil).imza
  const [alanlar, setAlanlar] = useState<Alanlar>(() => ({ ...BOS_ALANLAR, ...veri.alanlar }) as Alanlar)
  const [onizleme, setOnizleme] = useState(veri.kurumsal_html)
  const [durum, setDurum] = useState<Durum>({ tur: "bos", metin: "" })
  const degisti = ALAN_SIRASI.some((k) => alanlar[k] !== (veri.alanlar?.[k] ?? ""))

  useEffect(() => {
    if (!degisti) {
      setOnizleme(veri.kurumsal_html)
      return
    }
    const zaman = window.setTimeout(() => {
      yaz<{ html: string }>("POST", "/api/v1/session/imza/onizleme", {
        alanlar,
      })
        .then((s) => setOnizleme(s.html))
        .catch(() => undefined) // gecersiz alan: kaydette mesaj gosterilir
    }, 300)
    return () => window.clearTimeout(zaman)
  }, [alanlar, degisti, veri.kurumsal_html])

  async function kaydet() {
    setDurum({ tur: "calisiyor", metin: t.kaydediliyor })
    try {
      const sonuc = await yaz<Imza>("PUT", "/api/v1/session/imza", {
        mod: "kurumsal",
        alanlar,
      })
      onKaydedildi(sonuc)
      setOnizleme(sonuc.kurumsal_html)
      setDurum({ tur: "tamam", metin: t.kurumsalKaydedildi })
    } catch (hata) {
      setDurum({ tur: "hata", metin: hataMesaji(hata, t.hata) })
    }
  }

  async function outlook() {
    const kutu = document.createElement("div")
    kutu.innerHTML = onizleme
    const tamam = await panoyaKopyala(onizleme, kutu.innerText)
    setDurum(tamam ? { tur: "tamam", metin: t.outlookKopyalandi } : { tur: "hata", metin: t.outlookHata })
  }

  const etiket = {
    unvan: t.unvan,
    birim: t.birim,
    sabit: t.sabit,
    eposta: t.eposta,
  }
  const ipucu = {
    unvan: t.unvanIpucu,
    birim: t.birimIpucu,
    sabit: t.sabitIpucu,
    eposta: t.epostaIpucu,
  }
  return (
    <div className="grid gap-3">
      <p className="text-xs text-muted-foreground">{t.kurumsalAciklama}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {ALAN_SIRASI.map((k) => (
          <label key={k} className="grid gap-1.5 text-sm font-medium">
            {etiket[k]}
            <Input
              value={alanlar[k]}
              placeholder={ipucu[k]}
              maxLength={k === "sabit" ? 40 : k === "eposta" ? 200 : 120}
              type={k === "eposta" ? "email" : k === "sabit" ? "tel" : "text"}
              onChange={(e) => {
                setAlanlar((o) => ({ ...o, [k]: e.target.value }))
                setDurum({ tur: "bos", metin: "" })
              }}
            />
          </label>
        ))}
      </div>
      <p className="text-[0.625rem] font-extrabold uppercase tracking-wider text-tl-navy">{t.onizleme}</p>
      <div className="overflow-x-auto rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4">
        {/* Sunucunun urettigi imza: tum metinler kacislanmis, gorsel gomulu (app.imza.kurumsal). */}
        <div aria-label={t.onizleme} className="mx-auto w-max bg-white shadow-sm" dangerouslySetInnerHTML={{ __html: onizleme }} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" onClick={() => void kaydet()} disabled={durum.tur === "calisiyor" || (!degisti && veri.mod === "kurumsal")}>
          {durum.tur === "calisiyor" ? t.kaydediliyor : t.kurumsalKaydet}
        </Button>
        <Button type="button" variant="outline" onClick={() => void outlook()}>
          <Copy aria-hidden className="size-4" />
          {t.outlook}
        </Button>
        <Button type="button" variant="outline" onClick={() => onAktar(onizleme)}>
          <PencilLine aria-hidden className="size-4" />
          {t.serbesteAktar}
        </Button>
        <span role="status" className={`text-sm ${durum.tur === "hata" ? "text-destructive" : "text-muted-foreground"}`}>
          {durum.tur === "calisiyor" ? "" : durum.metin}
        </span>
      </div>
    </div>
  )
}

/** Serbest imza: Outlook imza editoru gibi yazi + gorsel + baglanti; HTML sunucuda izin listesiyle temizlenir (app.imza). */
function SerbestImza({ dil, veri, baslangic, onKaydedildi }: { dil: Dil; veri: Imza; baslangic: string | null; onKaydedildi: (v: Imza) => void }) {
  const t = metin(dil).imza
  const alan = useRef<HTMLDivElement>(null)
  const secici = useRef<HTMLInputElement>(null)
  const [secili, setSecili] = useState<HTMLImageElement | null>(null)
  const [genislik, setGenislik] = useState(96)
  const [degisti, setDegisti] = useState(baslangic !== null)
  const [durum, setDurum] = useState<Durum>({ tur: "bos", metin: "" })

  // Acilista bir kez: kurumsaldan aktarilan, yoksa kayitli serbest imza, o da yoksa kurumsal tasarim (sablon).
  useEffect(() => {
    if (alan.current) alan.current.innerHTML = baslangic ?? (veri.html || veri.sablon)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- yalniz ilk cizimde; sonrasi kullanicinin elinde
  }, [])

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
    if (!alan.current || !window.confirm(t.sablonOnay)) return
    alan.current.innerHTML = veri.sablon
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
      const sonuc = await yaz<Imza>("PUT", "/api/v1/session/imza", {
        mod: "serbest",
        html: alan.current.innerHTML,
      })
      alan.current.innerHTML = sonuc.html || sonuc.sablon // sunucunun temizledigi hal (ne gonderilecekse o gorunsun)
      setDegisti(false)
      setSecili(null)
      setDurum({
        tur: "tamam",
        metin: sonuc.kayitli ? t.kaydedildi : t.silindi,
      })
      onKaydedildi(sonuc)
    } catch (hata) {
      setDurum({ tur: "hata", metin: hataMesaji(hata, t.hata) })
    }
  }

  return (
    <div className="grid gap-3">
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
          <input
            type="color"
            defaultValue="#002855"
            onChange={(e) => uygula("foreColor", e.target.value)}
            className="size-5 cursor-pointer rounded border-0 bg-transparent p-0"
          />
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

      <div
        ref={alan}
        contentEditable
        suppressContentEditableWarning
        role="textbox"
        aria-multiline="true"
        aria-label={t.baslik}
        onInput={elle}
        onClick={(e) => tikla(e.target)}
        className="min-h-36 overflow-x-auto rounded-lg border border-input bg-white p-4 text-[13px] leading-normal text-slate-700 shadow-xs focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring [&_a]:text-tl-blue [&_a]:underline [&_img]:inline-block [&_img]:cursor-pointer [&_ul]:list-disc [&_ul]:pl-5"
      />
      {veri.mod !== "serbest" && !degisti ? <p className="text-xs text-muted-foreground">{t.kayitliDegil}</p> : null}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" onClick={() => void kaydet()} disabled={durum.tur === "calisiyor" || (!degisti && veri.mod === "serbest")}>
          {durum.tur === "calisiyor" ? t.kaydediliyor : t.kaydet}
        </Button>
        <span role="status" className={`text-sm ${durum.tur === "hata" ? "text-destructive" : "text-muted-foreground"}`}>
          {durum.tur === "calisiyor" ? "" : durum.metin}
        </span>
      </div>
    </div>
  )
}
