import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import { RaporSayfasi } from "@/musteri/rapor-sayfasi"
import { oku } from "@/lib/sorgu"

vi.mock("@/lib/sorgu", async (gercek) => ({ sorguMetni: (await gercek<typeof import("@/lib/sorgu")>()).sorguMetni, oku: vi.fn() }))
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function sar({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
}

const DURUM = { yil: 2026, ay: 9, satirlar: [{ id: 2, ad: "Ayse Test", musteri: 4, atilan: 3, bekleyen: 1, muaf: 2 }], toplam: { musteri: 4, atilan: 3, bekleyen: 1, muaf: 2 } }
const GONDERIM = { id: 5, customer_id: 1, musteri: "Alfa A.Ş.", yil: 2026, ay: 9, gonderen: "ayse", zaman: "2026-10-03T09:00:00Z", konu: "Eylül raporu", durum: "sent" }

describe("gonderilen aylik rapor (2026-10-31: APN duzeni, ay/yil filtresi)", () => {
  it("varsayilan donem sunucudan gelir; oran halkada, muaflar ayri sutunda; ay secimi durumu ve gecmisi o donemle sorgular", async () => {
    vi.mocked(oku).mockImplementation(async (url: string) => {
      if (url.includes("/durum")) return url.includes("ay=8") ? { ...DURUM, ay: 8, toplam: { ...DURUM.toplam, atilan: 1, bekleyen: 3 } } : DURUM
      return url.includes("ay=9") ? [GONDERIM] : []
    })
    render(<RaporSayfasi dil="tr" />, { wrapper: sar })
    expect(await screen.findAllByText("%75")).toHaveLength(2) // halka + KPI
    expect(screen.getByRole("img", { name: "Atılan: 3, Bekleyen: 1" })).toBeInTheDocument()
    expect(screen.getByRole("columnheader", { name: "Rapor atılmıyor" })).toBeInTheDocument()
    expect(screen.getByLabelText("Ay")).toHaveValue("9")
    expect(screen.getByLabelText("Yıl")).toHaveValue("2026")
    expect(await screen.findByText("Alfa A.Ş.")).toBeInTheDocument()
    expect(vi.mocked(oku)).toHaveBeenCalledWith("/api/v1/rapor/durum")
    expect(vi.mocked(oku)).toHaveBeenCalledWith("/api/v1/rapor/gonderilenler?yil=2026&ay=9")

    fireEvent.change(screen.getByLabelText("Ay"), { target: { value: "8" } })
    expect(await screen.findAllByText("%25")).toHaveLength(2)
    expect(vi.mocked(oku)).toHaveBeenCalledWith("/api/v1/rapor/durum?yil=2026&ay=8")
    await waitFor(() => expect(vi.mocked(oku)).toHaveBeenCalledWith("/api/v1/rapor/gonderilenler?yil=2026&ay=8"))
    expect(await screen.findByText("Henüz gönderim yok.")).toBeInTheDocument()
  })
})
