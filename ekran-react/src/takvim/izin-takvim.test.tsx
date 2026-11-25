import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { IzinTakvim } from "@/takvim/izin-takvim"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  Reflect.deleteProperty(HTMLTextAreaElement.prototype, "scrollHeight")
})

type Cagri = { yol: string; yontem: string; govde: unknown }

const simdi = new Date()
const ay = simdi.getMonth() + 1
const AY_ONEKI = `${simdi.getFullYear()}-${String(ay).padStart(2, "0")}`
const GUN = `${AY_ONEKI}-10`
const OZET = "10:00 - 11:00 XXXXX müşteri ile SD-WAN çözümü üzerine toplantı yapıldı."
const AY_VERISI = {
  yil: simdi.getFullYear(),
  ay,
  gunler: [
    { tarih: GUN, durum: "calisiyor", online: 0, yuzyuze: 0, toplanti_ozeti: OZET },
    { tarih: `${AY_ONEKI}-11`, durum: "yillik_izin", online: 2, yuzyuze: 0, toplanti_ozeti: "" },
  ],
  ozet: { durumlar: {}, online: 0, yuzyuze: 0, kayitli_gun: 1, izin_gun: 0, toplanti: 0 },
  // ustteki sayilar yil toplamidir (sunucu yil_ozet)
  yil_ozet: { durumlar: {}, online: 2, yuzyuze: 0, kayitli_gun: 2, izin_gun: 1, toplanti: 2, is_gunu: 0, ozet_gunu: 1, gorunen: { yillik_izin: 1, calisiyor: 250 } },
}

function sahteSunucu(): Cagri[] {
  const cagrilar: Cagri[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn(async (girdi: string, ayar?: RequestInit) => {
      const yontem = ayar?.method ?? "GET"
      cagrilar.push({ yol: String(girdi), yontem, govde: typeof ayar?.body === "string" ? JSON.parse(ayar.body) : null })
      const data = yontem === "GET" ? AY_VERISI : { tarih: GUN }
      return new Response(JSON.stringify({ status: "success", data }), { status: 200, headers: { "Content-Type": "application/json" } })
    }),
  )
  return cagrilar
}

async function cekmeceyiAc() {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={istemci}>
      <IzinTakvim dil="tr" />
    </QueryClientProvider>,
  )
  fireEvent.click(await screen.findByRole("button", { name: /^10 \S+: Çalışıyor, Toplantı özeti$/ }))
  return await screen.findByRole("textbox", { name: /Toplantı özeti/ })
}

describe("Takvim günü kutusu", () => {
  it("durum etiketini, toplantı sayılarını ve özetin ilk satırlarını gösterir; sıfır sayıyı yazmaz", async () => {
    sahteSunucu()
    const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={istemci}>
        <IzinTakvim dil="tr" />
      </QueryClientProvider>,
    )
    const ozetli = await screen.findByRole("button", { name: /^10 \S+: Çalışıyor, Toplantı özeti$/ })
    expect(within(ozetli).getByText("Çalışıyor")).toBeInTheDocument()
    expect(ozetli).toHaveAttribute("title", OZET) // gun kutusu kucuk: ozet metni ipucunda, kutuda simge
    const izinli = screen.getByRole("button", { name: /^11 \S+: Yıllık İzin, 2\/0$/ })
    expect(within(izinli).getByText("Yıllık İzin")).toBeInTheDocument()
    expect(within(izinli).getByText("2")).toBeInTheDocument()
    expect(within(izinli).queryByText("0")).not.toBeInTheDocument()
  })
})

describe("Gün düzenle: toplantı özeti", () => {
  it("kutu Kaydet düğmesinin altında, kayıtlı özeti gösterir ve Kaydet gövdeye özeti ekler", async () => {
    const cagrilar = sahteSunucu()
    const kutu = await cekmeceyiAc()
    expect(kutu).toHaveValue(OZET)
    expect(kutu).toHaveAttribute("placeholder", expect.stringContaining("SD-WAN"))
    const kaydet = screen.getByRole("button", { name: "Kaydet" })
    expect(kaydet.compareDocumentPosition(kutu) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    fireEvent.change(kutu, { target: { value: `${OZET}\n14:00 - 14:30 YYYYY ile fiyat görüşüldü.` } })
    fireEvent.click(kaydet)
    await waitFor(() => expect(cagrilar.some((c) => c.yontem === "PUT")).toBe(true))
    expect(cagrilar.find((c) => c.yontem === "PUT")?.govde).toEqual({
      tarih: GUN,
      durum: "calisiyor",
      durum2: null,
      online: 0,
      yuzyuze: 0,
      toplanti_ozeti: `${OZET}\n14:00 - 14:30 YYYYY ile fiyat görüşüldü.`,
      yapilan_isler: "",
    })
  })

  it("her satırla kutu aşağı doğru uzar", async () => {
    sahteSunucu()
    Object.defineProperty(HTMLTextAreaElement.prototype, "scrollHeight", { configurable: true, get: function (this: HTMLTextAreaElement) { return 20 * this.value.split("\n").length } })
    const kutu = await cekmeceyiAc()
    expect(kutu.style.height).toBe("20px")
    fireEvent.change(kutu, { target: { value: "bir\niki\nüç\ndört" } })
    expect(kutu.style.height).toBe("80px")
  })

  it("Varsayılana dön özeti de temizler", async () => {
    const cagrilar = sahteSunucu()
    await cekmeceyiAc()
    fireEvent.click(screen.getByRole("button", { name: "Varsayılana dön" }))
    await waitFor(() => expect(cagrilar.some((c) => c.yontem === "PUT")).toBe(true))
    expect(cagrilar.find((c) => c.yontem === "PUT")?.govde).toEqual({ tarih: GUN, durum: "calisiyor", durum2: null, online: 0, yuzyuze: 0, toplanti_ozeti: "", yapilan_isler: "" })
  })
})

describe("Turkcell'li Takvimi (kurum günü)", () => {
  it("kurum gününün adını gösterir; Varsayılana dön kurum durumuna döner", async () => {
    const cagrilar: Cagri[] = []
    const kurumGunu = { tarih: `${AY_ONEKI}-12`, durum: "resmi_tatil", online: 0, yuzyuze: 0, kurum: { durum: "resmi_tatil", aciklama: "Cumhuriyet Bayramı" } }
    vi.stubGlobal(
      "fetch",
      vi.fn(async (girdi: string, ayar?: RequestInit) => {
        const yontem = ayar?.method ?? "GET"
        cagrilar.push({ yol: String(girdi), yontem, govde: typeof ayar?.body === "string" ? JSON.parse(ayar.body) : null })
        const data = yontem === "GET" ? { ...AY_VERISI, gunler: [kurumGunu] } : kurumGunu
        return new Response(JSON.stringify({ status: "success", data }), { status: 200, headers: { "Content-Type": "application/json" } })
      }),
    )
    const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={istemci}>
        <IzinTakvim dil="tr" />
      </QueryClientProvider>,
    )
    const hucre = await screen.findByRole("button", { name: /^12 \S+: Resmi Tatil \(Cumhuriyet Bayramı\)$/ })
    expect(within(hucre).getByText("Cumhuriyet Bayramı")).toBeInTheDocument()
    fireEvent.click(hucre)
    fireEvent.click(await screen.findByRole("button", { name: "Varsayılana dön" }))
    await waitFor(() => expect(cagrilar.some((c) => c.yontem === "PUT")).toBe(true))
    expect(cagrilar.find((c) => c.yontem === "PUT")?.govde).toMatchObject({ tarih: `${AY_ONEKI}-12`, durum: "resmi_tatil" })
  })
})

describe("Yarım gün ve renkler", () => {
  it("Ctrl ile ikinci durum seçilir, kutu iki renge bölünür; dolu gün üst bardaki renkle boyanır", async () => {
    const cagrilar: Cagri[] = []
    const yarim = { tarih: `${AY_ONEKI}-13`, durum: "arife_tatili", durum2: "sirket_izni", online: 1, yuzyuze: 0 }
    vi.stubGlobal(
      "fetch",
      vi.fn(async (girdi: string, ayar?: RequestInit) => {
        const yontem = ayar?.method ?? "GET"
        cagrilar.push({ yol: String(girdi), yontem, govde: typeof ayar?.body === "string" ? JSON.parse(ayar.body) : null })
        const data = yontem === "GET" ? { ...AY_VERISI, gunler: [...AY_VERISI.gunler, yarim] } : yarim
        return new Response(JSON.stringify({ status: "success", data }), { status: 200, headers: { "Content-Type": "application/json" } })
      }),
    )
    const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={istemci}>
        <IzinTakvim dil="tr" />
      </QueryClientProvider>,
    )
    const bolunmus = await screen.findByRole("button", { name: /^13 \S+: Arife \(Yarım Gün\) \/ Şirket İzni, 1\/0$/ })
    expect(bolunmus.style.background).toContain("linear-gradient")
    const izinli = screen.getByRole("button", { name: /^11 \S+: Yıllık İzin/ })
    expect(izinli.style.background).toMatch(/rgb\(14, 165, 233\)|#0ea5e9/) // ust bardaki Yillik Izin rengi
    // gun duzenle: Ctrl ile ikinci yari
    fireEvent.click(screen.getByRole("button", { name: /^10 \S+: Çalışıyor/ }))
    fireEvent.click(await screen.findByRole("button", { name: "Raporlu" }))
    fireEvent.click(screen.getByRole("button", { name: "Çalışıyor" }), { ctrlKey: true })
    expect(screen.getByRole("button", { name: /Raporlu/ })).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("button", { name: /^Çalışıyor/ })).toHaveAttribute("aria-pressed", "true")
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }))
    await waitFor(() => expect(cagrilar.some((c) => c.yontem === "PUT")).toBe(true))
    expect(cagrilar.find((c) => c.yontem === "PUT")?.govde).toMatchObject({ durum: "raporlu", durum2: "calisiyor" })
  })
})

describe("Tek ekran ve kişiye özel takvim", () => {
  it("kişi seçici yok, kayıtlı gün yok; gösterim kutusu üstte; yapılan işler kaydedilir", async () => {
    const cagrilar = sahteSunucu()
    const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={istemci}>
        <IzinTakvim dil="tr" />
      </QueryClientProvider>,
    )
    const gosterim = await screen.findByRole("region", { name: "Gösterim" })
    expect(within(gosterim).getByText("Yapılan işler")).toBeInTheDocument()
    // gosterim kutucuklari: veri girilen her alanin bu aydaki adedi (gun durumu ekranda gorunen haliyle)
    expect(await within(gosterim).findByRole("group", { name: "Toplantı özeti: 1" })).toBeInTheDocument()
    expect(within(gosterim).getByRole("group", { name: "Yıllık İzin: 1" })).toBeInTheDocument()
    expect(within(gosterim).getByRole("group", { name: "Yapılan işler: 0" })).toBeInTheDocument()
    expect(within(gosterim).getAllByRole("group")).toHaveLength(12)
    expect(screen.queryByRole("combobox")).toBeNull()
    expect(screen.queryByText("Kayıtlı gün")).toBeNull()
    expect(cagrilar.some((c) => c.yol.includes("/takvim/kisiler"))).toBe(false)
    fireEvent.click(await screen.findByRole("button", { name: /^10 \S+: Çalışıyor, Toplantı özeti$/ }))
    const kutu = await screen.findByRole("textbox", { name: /Toplantı özeti/ })
    const isler = screen.getByRole("textbox", { name: /Yapılan işler/ })
    expect(kutu).toHaveValue(OZET)
    fireEvent.change(isler, { target: { value: "Alfa SD-WAN kurulumu" } })
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }))
    await waitFor(() => expect(cagrilar.some((c) => c.yontem === "PUT")).toBe(true))
    expect(cagrilar.find((c) => c.yontem === "PUT")?.govde).toMatchObject({ tarih: GUN, yapilan_isler: "Alfa SD-WAN kurulumu", toplanti_ozeti: OZET })
  })
})
