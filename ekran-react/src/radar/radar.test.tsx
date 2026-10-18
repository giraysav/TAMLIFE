import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { RadarSayfasi } from "@/radar/radar-sayfasi"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function sunucu(veri: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ status: "success", data: veri }), { status: 200, headers: { "Content-Type": "application/json" } })),
  )
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={istemci}>
      <RadarSayfasi dil="tr" />
    </QueryClientProvider>,
  )
}

describe("Musteri Radar sayfasi", () => {
  it("adaylar: sira, unvan, alarm acik/kapanan, toplam; bayat veri uyarisi ve veri zamani", async () => {
    sunucu({ var: true, taze: false, veri_zamani: "2026-10-06 12:30:00", satirlar: [{ sira: 1, musteri_no: "10000004", unvan: "BETA ENERJI", aktif: 30, kapanan: 1200, toplam: 1230 }] })
    expect(await screen.findByText("BETA ENERJI")).toBeInTheDocument()
    expect(screen.getByText("30 / 1.200")).toBeInTheDocument()
    expect(screen.getByText("1.230")).toBeInTheDocument()
    expect(screen.getByText(/güncel değil/)).toBeInTheDocument()
    expect(screen.getByText(/Veri zamanı: 2026-10-06 12:30:00/)).toBeInTheDocument()
    expect(screen.getAllByTitle("OneDesk bilet şeması erişimi bekleniyor")).toHaveLength(2)
  })

  it("TEMIP kayit kipi: ticketli/son kayit, kart adayi rozeti, ozet; Kayitlar dugmesi musterinin kayitlarini acar", async () => {
    const radar = {
      var: true, taze: true, veri_zamani: "2026-10-17T18:00:00Z", kaynak: "kayit", toplam_musteri: 1, toplam_kayit: 73, sayfa: 1, adet: 50,
      satirlar: [{ sira: 1, musteri_no: "23659267", unvan: "VODAFONE NET", aktif: 3, kapanan: 70, toplam: 73, ticketli: 60, son_kayit: "2026-10-17T16:46:00Z", kart_adayi: { id: 9, ad: "VODAFONE" } }],
    }
    const kayit = {
      musteri_no: "23659267", unvan: "VODAFONE NET", toplam: 1, sayfa: 1, adet: 50,
      kayitlar: [{ kimlik: "43601244", ticket: "10134785623", ci: "nw_li_cust_x", baslik: "AVAILABILITY", durum: "closed", ayrinti: "Closed/atm", acilis: "2026-10-17T16:46:00Z", kapanis: "2026-10-17T17:57:00Z" }],
    }
    const fetchSahte = vi.fn(async (url: string) =>
      new Response(JSON.stringify({ status: "success", data: url.includes("/kayitlar") ? kayit : radar }), { status: 200, headers: { "Content-Type": "application/json" } }),
    )
    vi.stubGlobal("fetch", fetchSahte)
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RadarSayfasi dil="tr" />
      </QueryClientProvider>,
    )
    expect(await screen.findByText("VODAFONE NET")).toBeInTheDocument()
    expect(screen.getByText(/1 müşteri · 73 kayıt/)).toBeInTheDocument()
    expect(screen.getByText(/Aynı ünvanlı kart var: VODAFONE/)).toBeInTheDocument()
    expect(screen.getByText("60")).toBeInTheDocument()
    expect(String(fetchSahte.mock.calls[0][0])).toContain("adet=50")
    fireEvent.click(screen.getByRole("button", { name: "Kayıtlar" }))
    expect(await screen.findByText("10134785623")).toBeInTheDocument()
    expect(screen.getByText("Closed/atm")).toBeInTheDocument()
    expect(String(fetchSahte.mock.calls.at(-1)?.[0])).toContain("/api/v1/radar/23659267/kayitlar")
  })

  it("ReportDB verisi yoksa aciklama", async () => {
    sunucu({ var: false, taze: false, veri_zamani: null, satirlar: [] })
    expect(await screen.findByText(/ReportDB verisi henüz alınmadı/)).toBeInTheDocument()
  })
})
