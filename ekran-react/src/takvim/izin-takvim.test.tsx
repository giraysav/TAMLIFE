import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
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
const GUN = `${simdi.getFullYear()}-${String(ay).padStart(2, "0")}-10`
const OZET = "10:00 - 11:00 XXXXX müşteri ile SD-WAN çözümü üzerine toplantı yapıldı."
const AY_VERISI = {
  yil: simdi.getFullYear(),
  ay,
  gunler: [{ tarih: GUN, durum: "calisiyor", online: 0, yuzyuze: 0, toplanti_ozeti: OZET }],
  ozet: { durumlar: {}, online: 0, yuzyuze: 0, kayitli_gun: 1, izin_gun: 0, toplanti: 0 },
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
      online: 0,
      yuzyuze: 0,
      toplanti_ozeti: `${OZET}\n14:00 - 14:30 YYYYY ile fiyat görüşüldü.`,
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
    expect(cagrilar.find((c) => c.yontem === "PUT")?.govde).toEqual({ tarih: GUN, durum: "calisiyor", online: 0, yuzyuze: 0, toplanti_ozeti: "" })
  })
})
