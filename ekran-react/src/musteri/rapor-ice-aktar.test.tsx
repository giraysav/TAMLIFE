import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import { RaporIceAktar } from "@/musteri/rapor-ice-aktar"
import { oku, yukle } from "@/lib/sorgu"

vi.mock("@/lib/sorgu", async (gercek) => ({
  sorguMetni: (await gercek<typeof import("@/lib/sorgu")>()).sorguMetni,
  hataMesaji: (_h: unknown, metin: string) => metin,
  oku: vi.fn(),
  yukle: vi.fn(),
}))
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe("gecmis rapor ice aktarma (2026-10-31)", () => {
  it("ay/yil secimine gore yalniz kullanicinin musterileri; raporu olan secilemez; Outlook dosyasi o donem olarak aktarilir", async () => {
    vi.mocked(oku).mockImplementation(async (url: string) =>
      url.includes("ay=8")
        ? [{ id: 1, ad: "Alfa A.Ş.", gonderildi: false }, { id: 2, ad: "Beta Ltd", gonderildi: false }]
        : [{ id: 1, ad: "Alfa A.Ş.", gonderildi: true }, { id: 2, ad: "Beta Ltd", gonderildi: false }],
    )
    vi.mocked(yukle).mockResolvedValue({ id: 9 })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RaporIceAktar dil="tr" yil={2026} ay={9} onKapat={() => {}} />
      </QueryClientProvider>,
    )
    expect(await screen.findByRole("option", { name: "Alfa A.Ş. · raporu var" })).toBeDisabled()
    expect(vi.mocked(oku)).toHaveBeenCalledWith("/api/v1/rapor/ice-al/musteriler?yil=2026&ay=9")

    fireEvent.change(screen.getByLabelText("Ay"), { target: { value: "8" } })
    expect(await screen.findByRole("option", { name: "Alfa A.Ş." })).toBeEnabled()
    const dugme = screen.getByRole("button", { name: /İçe aktar$/ })
    expect(dugme).toBeDisabled()

    fireEvent.change(screen.getByLabelText(/Rapor dosyası seç/), { target: { files: [new File(["x"], "rapor.docx")] } })
    expect(screen.getByText("Yalnız .msg, .eml ya da .pdf dosyası seçilebilir.")).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/Rapor dosyası seç/), { target: { files: [new File(["x"], "Alfa Agustos.msg")] } })
    fireEvent.change(screen.getByLabelText(/^Müşteri/), { target: { value: "1" } })
    fireEvent.click(dugme)
    expect(await screen.findByText("Alfa A.Ş. · Ağustos 2026 raporu kaydedildi.")).toBeInTheDocument()
    await waitFor(() => expect(vi.mocked(yukle)).toHaveBeenCalledTimes(1))
    expect(vi.mocked(yukle).mock.calls[0][0]).toBe("/api/v1/rapor/ice-al?musteri_id=1&yil=2026&ay=8&dosya=Alfa+Agustos.msg")
  })
})
