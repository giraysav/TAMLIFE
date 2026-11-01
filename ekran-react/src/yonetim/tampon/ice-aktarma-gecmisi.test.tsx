import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import { IceAktarmaGecmisi } from "@/yonetim/tampon/ice-aktarma-gecmisi"
import { oku, yaz } from "@/lib/sorgu"

vi.mock("@/lib/sorgu", () => ({
  hataMesaji: (_h: unknown, metin: string) => metin,
  oku: vi.fn(),
  yaz: vi.fn(),
}))
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.restoreAllMocks()
})

describe("ice aktarma gecmisi (2026-11-01)", () => {
  it("elle yuklenen dosyalar listelenir; geri alinmamis olan onayla geri alinir, geri alinmis olan rozetle gorunur", async () => {
    vi.mocked(oku).mockResolvedValue([
      { id: 3, tur: "urun_tutar", dosya: "urun.xlsx", zaman: "2026-11-01T09:00:00Z", kullanici: "admin", ozet: { musteri: "Alfa Holding", kart: 2 }, geri_alinan: null },
      { id: 2, tur: "proje", dosya: "proje.xlsm", zaman: "2026-10-31T09:00:00Z", kullanici: "admin", ozet: { eklendi: 272 }, geri_alinan: { zaman: "2026-11-01T08:00:00Z", kullanici: "admin" } },
    ])
    vi.mocked(yaz).mockResolvedValue({ geri_alinan: 1, korunan: 1 })
    vi.spyOn(window, "confirm").mockReturnValue(true)
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <IceAktarmaGecmisi dil="tr" />
      </QueryClientProvider>,
    )
    expect(await screen.findByText("Alfa Holding · 2 kart")).toBeInTheDocument()
    expect(screen.getByText("272 kayıt eklendi")).toBeInTheDocument()
    expect(screen.getByText("Geri alındı")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Geri al: proje.xlsm" })).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "Geri al: urun.xlsx" }))
    expect(await screen.findByText("1 kayıt geri alındı, 1 kayıt sonradan değiştiği için korundu.")).toBeInTheDocument()
    expect(vi.mocked(yaz)).toHaveBeenCalledWith("POST", "/api/v1/tampon/ice-aktarmalar/3/geri-al")
  })
})
