import { apiYolu } from "@/lib/http"

/**
 * Aylik rapor PDF'i (uretim customer_detail.html raporPdfOlustur): sablon html2canvas ile tek resim alinir, jsPDF ile
 * A4 sayfalara BOLUNUR. Kesim bos (beyaz) bir piksel satirina cekilir; grafik kutusu ve ust/alt bant bolunmez.
 * Kutuphaneler (html2canvas 1.4.1, jsPDF 4.2.1; MIT) public/ altinda durur ve yalniz PDF istendiginde yuklenir:
 * yeni npm bagimliligi yok, ana paket buyumez.
 */

type Html2Canvas = (el: HTMLElement, secenek: Record<string, unknown>) => Promise<HTMLCanvasElement>
type JsPdf = {
  internal: { pageSize: { getWidth(): number; getHeight(): number } }
  addPage(): void
  addImage(veri: string, tur: string, x: number, y: number, g: number, y2: number): void
  output(tur: "blob"): Blob
  output(tur: "datauristring"): string
}
type Pencere = Window & { html2canvas?: Html2Canvas; jspdf?: { jsPDF: new (yon: string, birim: string, boyut: string) => JsPdf } }

const BETIKLER = ["html2canvas-1.4.1.min.js", "jspdf-4.2.1.umd.min.js"]
const UST_KENAR_MM = 12 // 2. ve sonraki sayfalar (1. sayfada sablonun kendi boslugu var)
const ALT_KENAR_MM = 10
const yuklenen = new Map<string, Promise<void>>()

function betikYukle(ad: string): Promise<void> {
  const var_ = yuklenen.get(ad)
  if (var_) return var_
  const soz = new Promise<void>((coz, reddet) => {
    const betik = document.createElement("script")
    betik.src = apiYolu(`/${ad}`)
    betik.async = true
    betik.onload = () => coz()
    betik.onerror = () => {
      yuklenen.delete(ad)
      reddet(new Error(ad))
    }
    document.head.appendChild(betik)
  })
  yuklenen.set(ad, soz)
  return soz
}

function satirBos(veri: Uint8ClampedArray, y: number, genislik: number): boolean {
  for (let i = y * genislik * 4; i < (y + 1) * genislik * 4; i += 4) {
    if (veri[i] < 245 || veri[i + 1] < 245 || veri[i + 2] < 245) return false
  }
  return true
}

/** [enAz, alt] araliginda asagidan yukari tamamen beyaz bir satir; yoksa alt. */
function bosSatiraCek(ctx: CanvasRenderingContext2D, genislik: number, enAz: number, alt: number): number {
  const veri = ctx.getImageData(0, enAz, genislik, alt - enAz).data
  for (let y = alt - enAz - 1; y > 0; y--) if (satirBos(veri, y, genislik)) return enAz + y
  return alt
}

/** En alttaki beyaz olmayan satir (256 satirlik bloklarla). */
function sonDoluSatir(ctx: CanvasRenderingContext2D, genislik: number, yukseklik: number): number {
  for (let alt = yukseklik; alt > 0; alt -= 256) {
    const ust = Math.max(0, alt - 256)
    const veri = ctx.getImageData(0, ust, genislik, alt - ust).data
    for (let y = alt - ust - 1; y >= 0; y--) if (!satirBos(veri, y, genislik)) return ust + y
  }
  return yukseklik
}

/** Sayfa kesiminin icinden gecmemesi gereken bloklar (canvas pikseli). */
function bolunmezBloklar(el: HTMLElement, canvas: HTMLCanvasElement): [number, number][] {
  const kokUst = el.getBoundingClientRect().top
  const olcek = canvas.height / el.offsetHeight
  return [...el.querySelectorAll<HTMLElement>("figure, [data-pdf-blok]")]
    .filter((b) => b.offsetHeight > 0)
    .map((b) => {
      const k = b.getBoundingClientRect()
      return [Math.floor((k.top - kokUst) * olcek), Math.ceil((k.bottom - kokUst) * olcek)] as [number, number]
    })
    .sort((a, b) => a[0] - b[0])
}

/** Sablon elemanindan cok sayfali A4 PDF. */
export async function raporPdfOlustur(el: HTMLElement, olcek = 2, kalite = 0.95): Promise<Blob> {
  for (const ad of BETIKLER) await betikYukle(ad)
  const w = window as Pencere
  if (!w.html2canvas || !w.jspdf) throw new Error("pdf")
  const [eskiX, eskiY] = [window.scrollX, window.scrollY]
  window.scrollTo(0, 0) // kaydirilmis sayfada html2canvas sablonun ustunu kirpabiliyor
  let canvas: HTMLCanvasElement
  try {
    canvas = await w.html2canvas(el, {
      scale: olcek,
      useCORS: true,
      backgroundColor: "#ffffff",
      logging: false,
      // Kopyada stil dosyalari kaldirilir: html2canvas Tailwind v4'un oklch renklerini okuyamaz. Sablon yalniz satir ici
      // (hex) stil kullanir, bu yuzden gorunum degismez.
      onclone: (kopya: Document) => kopya.querySelectorAll('style, link[rel="stylesheet"]').forEach((e) => e.remove()),
    })
  } finally {
    window.scrollTo(eskiX, eskiY)
  }
  const pdf = new w.jspdf.jsPDF("p", "mm", "a4")
  const sayfaG = pdf.internal.pageSize.getWidth()
  const sayfaY = pdf.internal.pageSize.getHeight()
  const mmPiksel = canvas.width / sayfaG
  const ctx = canvas.getContext("2d")
  if (!ctx) throw new Error("pdf")
  const bitis = Math.min(canvas.height, sonDoluSatir(ctx, canvas.width, canvas.height) + Math.round(5 * mmPiksel))
  const bloklar = bolunmezBloklar(el, canvas)
  let ust = 0
  for (let sayfa = 0; ust < bitis; sayfa++) {
    const ustMm = sayfa === 0 ? 0 : UST_KENAR_MM
    const sigan = Math.floor((sayfaY - ustMm - ALT_KENAR_MM) * mmPiksel)
    const kalanSigar = bitis - ust <= Math.floor((sayfaY - ustMm + 4) * mmPiksel)
    let alt = kalanSigar ? bitis : Math.min(ust + sigan, bitis)
    if (alt < bitis) {
      const bolunen = bloklar.find(([bUst, bAlt]) => bUst > ust + 2 && bUst < alt && bAlt > alt)
      alt = bolunen ? bolunen[0] - 2 : bosSatiraCek(ctx, canvas.width, ust + Math.floor(sigan * 0.6), alt)
    }
    const parca = document.createElement("canvas")
    parca.width = canvas.width
    parca.height = alt - ust
    const pctx = parca.getContext("2d")
    if (!pctx) throw new Error("pdf")
    pctx.fillStyle = "#ffffff"
    pctx.fillRect(0, 0, parca.width, parca.height)
    pctx.drawImage(canvas, 0, ust, canvas.width, parca.height, 0, 0, canvas.width, parca.height)
    if (sayfa > 0) pdf.addPage()
    pdf.addImage(parca.toDataURL("image/jpeg", kalite), "JPEG", 0, ustMm, sayfaG, parca.height / mmPiksel)
    ust = alt
  }
  return pdf.output("blob")
}

export function blobBase64(blob: Blob): Promise<string> {
  return new Promise((coz, reddet) => {
    const okuyucu = new FileReader()
    okuyucu.onload = () => coz(String(okuyucu.result))
    okuyucu.onerror = () => reddet(new Error("okunamadi"))
    okuyucu.readAsDataURL(blob)
  })
}

export function dosyaIndir(blob: Blob, ad: string) {
  const adres = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = adres
  a.download = ad
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(adres), 10_000) // erken birakilirsa Chromium dosya adini kaybedebiliyor
}

// --- seri grafikleri (SLA pivot serilerinden; Excel gorselleri kullanilmaz) ---------------------------------
/** Uretim grafik dili (referans mail): adet = turuncu sutun + deger etiketi; sure = sari (ilk mudahale) + mor (cozum) cizgi. */
const RENK = { adet: "#ED7D31", ilk: "#FFC000", cozum: "#7C6FAF", yazi: "#1A1A1A", izgara: "#D9D9D9" }

export type SeriGrafik = { tur: string; aylar: string[]; seriler: Record<string, (number | null)[]> }

/** Seriyi tuvale cizer, PNG veri adresi dondurur. Tuval yoksa (test ortami) null. */
export function seriGrafigi(g: SeriGrafik, lejant: { ilk: string; cozum: string }): string | null {
  const tuval = document.createElement("canvas")
  const [G, Y, olcek] = [640, 340, 2]
  tuval.width = G * olcek
  tuval.height = Y * olcek
  let ctx: CanvasRenderingContext2D | null = null
  try {
    ctx = tuval.getContext("2d")
  } catch {
    return null
  }
  if (!ctx) return null
  ctx.scale(olcek, olcek)
  ctx.fillStyle = "#ffffff"
  ctx.fillRect(0, 0, G, Y)
  const sure = g.tur === "sure"
  const seriler = sure ? (["ilk", "cozum"] as const).filter((k) => (g.seriler[k] ?? []).length) : (["adet"] as const)
  const degerler = seriler.flatMap((k) => (g.seriler[k] ?? []).filter((d): d is number => typeof d === "number"))
  const tavan = Math.max(1, ...degerler) * 1.18
  const [sol, sag, ust, alt] = [44, 12, 14, sure ? 92 : 64]
  const cizG = G - sol - sag
  const cizY = Y - ust - alt
  const yKonum = (d: number) => ust + cizY - (d / tavan) * cizY
  ctx.font = "11px Arial, sans-serif"
  ctx.strokeStyle = RENK.izgara
  ctx.fillStyle = "#555"
  ctx.lineWidth = 1
  for (let i = 0; i <= 4; i++) {
    const d = (tavan / 4) * i
    const y = yKonum(d)
    ctx.beginPath()
    ctx.moveTo(sol, y)
    ctx.lineTo(G - sag, y)
    ctx.stroke()
    ctx.textAlign = "right"
    ctx.fillText(String(Math.round(d)), sol - 6, y + 4)
  }
  const n = Math.max(1, g.aylar.length)
  const adim = cizG / n
  const xOrta = (i: number) => sol + adim * i + adim / 2
  g.aylar.forEach((ay, i) => {
    ctx.save()
    ctx.translate(xOrta(i), ust + cizY + 10)
    ctx.rotate(-Math.PI / 4)
    ctx.textAlign = "right"
    ctx.fillStyle = "#555"
    ctx.fillText(ay, 0, 0)
    ctx.restore()
  })
  if (!sure) {
    const veri = g.seriler.adet ?? []
    ctx.textAlign = "center"
    veri.forEach((d, i) => {
      const deger = typeof d === "number" ? d : 0
      const y = yKonum(deger)
      ctx.fillStyle = RENK.adet
      ctx.fillRect(xOrta(i) - adim * 0.31, y, adim * 0.62, ust + cizY - y)
      ctx.fillStyle = RENK.yazi
      ctx.fillText(typeof d === "number" ? String(d) : "–", xOrta(i), y - 4)
    })
    return tuval.toDataURL("image/png")
  }
  for (const k of seriler) {
    const veri = g.seriler[k] ?? []
    ctx.strokeStyle = RENK[k]
    ctx.fillStyle = RENK[k]
    ctx.lineWidth = 2
    ctx.beginPath()
    let acik = false
    veri.forEach((d, i) => {
      if (typeof d !== "number") {
        acik = false // verisi olmayan ay bosluk kalir, sifira dusmez
        return
      }
      if (acik) ctx.lineTo(xOrta(i), yKonum(d))
      else ctx.moveTo(xOrta(i), yKonum(d))
      acik = true
    })
    ctx.stroke()
    veri.forEach((d, i) => {
      if (typeof d !== "number") return
      ctx.beginPath()
      ctx.arc(xOrta(i), yKonum(d), 3, 0, Math.PI * 2)
      ctx.fill()
    })
  }
  ctx.textAlign = "left"
  let x = sol
  for (const k of seriler) {
    if (k === "adet") continue
    ctx.fillStyle = RENK[k]
    ctx.fillRect(x, Y - 18, 14, 4)
    ctx.fillStyle = RENK.yazi
    ctx.fillText(lejant[k], x + 18, Y - 13)
    x += ctx.measureText(lejant[k]).width + 40
  }
  return tuval.toDataURL("image/png")
}
