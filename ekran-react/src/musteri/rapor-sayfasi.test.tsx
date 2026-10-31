import { cleanup, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import { RaporSayfasi } from "@/musteri/rapor-sayfasi"
import { oku } from "@/lib/sorgu"

vi.mock("@/lib/sorgu", () => ({ oku: vi.fn() }))
afterEach(() => { cleanup(); vi.clearAllMocks() })

function sar({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
}

describe("gonderilen aylik rapor ozeti (2026-10-31)", () => {
  it("gonderim oranini halkada, raporu atilmayanlari ayri sutunda gosterir", async () => {
    vi.mocked(oku).mockImplementation(async (url: string) =>
      url.endsWith("/durum")
        ? { yil: 2026, ay: 9, satirlar: [{ id: 2, ad: "Ayse Test", musteri: 4, atilan: 3, bekleyen: 1, muaf: 2 }], toplam: { musteri: 4, atilan: 3, bekleyen: 1, muaf: 2 } }
        : [],
    )
    render(<RaporSayfasi dil="tr" />, { wrapper: sar })
    expect(await screen.findByText("%75")).toBeInTheDocument()
    expect(screen.getByRole("img", { name: "Atılan: 3, Bekleyen: 1" })).toBeInTheDocument()
    expect(screen.getByRole("columnheader", { name: "Rapor atılmıyor" })).toBeInTheDocument()
  })
})
