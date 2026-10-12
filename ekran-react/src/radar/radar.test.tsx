import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen } from "@testing-library/react"
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

  it("ReportDB verisi yoksa aciklama", async () => {
    sunucu({ var: false, taze: false, veri_zamani: null, satirlar: [] })
    expect(await screen.findByText(/ReportDB verisi henüz alınmadı/)).toBeInTheDocument()
  })
})
