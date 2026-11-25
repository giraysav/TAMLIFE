import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ApnSayfasi } from "@/gelir/apn-sayfasi"
import { SmsSayfasi } from "@/gelir/sms-sayfasi"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

type Cagri = { yol: string; yontem: string; govde: unknown }

/** fetch'i yola gore cevaplar ({yol parcasi: data}, ilk eslesen); cagrilarin yontem ve govdesini kaydeder. */
function sahteSunucu(cevaplar: Record<string, unknown>): Cagri[] {
  const cagrilar: Cagri[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn(async (girdi: string, ayar?: RequestInit) => {
      cagrilar.push({ yol: String(girdi), yontem: ayar?.method ?? "GET", govde: typeof ayar?.body === "string" ? JSON.parse(ayar.body) : null })
      const anahtar = Object.keys(cevaplar).find((k) => String(girdi).includes(k))
      return anahtar === undefined
        ? new Response(JSON.stringify({ detail: "yok" }), { status: 404, headers: { "Content-Type": "application/json" } })
        : new Response(JSON.stringify({ status: "success", data: cevaplar[anahtar] }), { status: 200, headers: { "Content-Type": "application/json" } })
    }),
  )
  return cagrilar
}

function sarmala(cocuk: React.ReactNode) {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={istemci}>{cocuk}</QueryClientProvider>)
}

const SMS = { items: [{ id: 1, musteri: "Beta Test Ltd", proje: "OTP", tutar: 1500, para_birimi: "TRY", tam: "Ayse Test", yil: 2026, ay: 3 }], toplam: { TRY: 1500 }, yillar: [2026] }
const KURULUM = { items: [{ id: 5, musteri: "Beta Test Ltd", apn_adi: "x", talep_tarihi: "2026-02-01", teslim_tarihi: null, tutar: 800, tam: "" }], toplam: 800, teslim_edilen: 0, bekleyen: 1 }

describe("ICT SMS / APN: kayit TAM'i personel listesinden secilir", () => {
  it("SMS: TAM sutunu gorunur, secenekler /gelir/tamlar'dan gelir, secim govdeye yazilir", async () => {
    const cagrilar = sahteSunucu({ "/gelir/tamlar": ["Ayse Test", "Derya Acar"], "/gelir/musteri-adlari": ["Beta Test Ltd"], "/gelir/sms/": { id: 2 }, "/gelir/sms": SMS })
    sarmala(<SmsSayfasi dil="tr" yazabilir />)
    expect(await screen.findByRole("columnheader", { name: "TAM" })).toBeInTheDocument()
    expect(await screen.findByText("Ayse Test")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Satır ekle" }))
    const secici = await screen.findByRole("combobox", { name: "TAM" })
    await waitFor(() => expect(within(secici).getAllByRole("option").map((o) => o.textContent)).toEqual(["Müşterinin TAM'i", "Ayse Test", "Derya Acar"])) // admin listede yok
    fireEvent.change(screen.getByLabelText("Müşteri adı"), { target: { value: "Beta Test Ltd" } })
    fireEvent.change(screen.getByLabelText("Proje bilgisi"), { target: { value: "Kampanya" } })
    fireEvent.change(secici, { target: { value: "Derya Acar" } })
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }))
    await waitFor(() => expect(cagrilar.some((c) => c.yontem === "POST")).toBe(true))
    expect(cagrilar.find((c) => c.yontem === "POST")?.govde).toMatchObject({ musteri: "Beta Test Ltd", proje: "Kampanya", tam: "Derya Acar" })
  })

  it("APN kurulum: TAM'i bos kayit tire gorunur; secim yapilmazsa govde tam'i bos (null) yollar, sunucu musteriden turetir", async () => {
    const cagrilar = sahteSunucu({ "/gelir/tamlar": ["Ayse Test"], "/gelir/musteri-adlari": ["Beta Test Ltd"], "/gelir/apn/kurulum/": { id: 5 }, "/gelir/apn/kurulum": KURULUM })
    sarmala(<ApnSayfasi dil="tr" yazabilir />)
    expect(await screen.findByRole("columnheader", { name: "TAM" })).toBeInTheDocument()
    expect(await screen.findByText("Beta Test Ltd")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Düzenle" }))
    fireEvent.click(await screen.findByRole("button", { name: "Kaydet" }))
    await waitFor(() => expect(cagrilar.some((c) => c.yontem === "PUT")).toBe(true))
    expect(cagrilar.find((c) => c.yontem === "PUT")?.govde).toMatchObject({ tam: null })
  })
})
