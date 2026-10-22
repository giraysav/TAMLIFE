import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import { AylikRapor } from "@/musteri/aylik-rapor"
import { oku, yaz } from "@/lib/sorgu"
import { dosyaIndir } from "@/musteri/rapor-pdf"

vi.mock("@/lib/sorgu", () => ({ oku: vi.fn(), yaz: vi.fn(), hataMesaji: (_h: unknown, text: string) => text, ApiHata: class extends Error {} }))
vi.mock("@/musteri/rapor-pdf", () => ({
  blobBase64: vi.fn(async () => "cGRm"),
  dosyaIndir: vi.fn(),
  raporPdfOlustur: vi.fn(async () => new Blob(["pdf"])),
  seriGrafigi: vi.fn(() => null),
}))
afterEach(() => { cleanup(); vi.clearAllMocks() })

function sar({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
}

function sunucu(kip: "eml" | "smtp") {
  const taslak = { yil: 2026, ay: 9, birim: true, alanlar: {}, varsayilanlar: { tr: {}, en: {} }, kayitli: false, guncelleyen: null, zaman: null,
    alicilar: { kime: "musteri@example.com", bilgi: "" }, gonderim: null, gonderim_kipi: kip }
  vi.mocked(oku).mockImplementation(async (url: string) => {
    if (url.endsWith("/cacti")) return { baglantilar: [], hazir: false, duzenleyebilir: false, kilitli: false, yil: 2026, ay: 9 }
    if (url.endsWith("/taslak")) return taslak
    if (url.endsWith("/gecmis")) return []
    return { dosyalar: [], ekler: [] }
  })
}

describe("aylik rapor gonderim kipi (2026-10-22)", () => {
  it("smtp: .eml inmez, gonderildi mesaji ve TAMLIFE notu gorunur", async () => {
    sunucu("smtp")
    vi.mocked(yaz).mockResolvedValue({ kip: "smtp", reddedilen: [] })
    vi.spyOn(window, "confirm").mockReturnValue(true)
    render(<AylikRapor musteriId={1} musteriAdi="Test" dil="tr" geriAlabilir={false} />, { wrapper: sar })
    await waitFor(() => expect(screen.getByText(/TAMLIFE@turkcell.com.tr adresinden panel tarafından gönderilir/)).toBeInTheDocument())
    const dugme = screen.getByRole("button", { name: "Raporu gönder" })
    await waitFor(() => expect(dugme).toBeEnabled())
    fireEvent.click(dugme)
    await waitFor(() => expect(screen.getByText("Rapor e-posta ile gönderildi.")).toBeInTheDocument())
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("geri çağrılamaz"))
    expect(yaz).toHaveBeenCalledWith("POST", "/api/v1/musteri/1/rapor/gonder", expect.objectContaining({ onay: true, pdf_base64: "cGRm" }))
    expect(dosyaIndir).toHaveBeenCalledTimes(0)
  })
  it("eml (varsayilan): Outlook taslagi iner", async () => {
    sunucu("eml")
    vi.mocked(yaz).mockResolvedValue({ kip: "eml", eml_adi: "r.eml", eml_base64: "eA==" })
    vi.spyOn(window, "confirm").mockReturnValue(true)
    render(<AylikRapor musteriId={1} musteriAdi="Test" dil="tr" geriAlabilir={false} />, { wrapper: sar })
    const dugme = await screen.findByRole("button", { name: "Raporu gönder" })
    await waitFor(() => expect(dugme).toBeEnabled())
    fireEvent.click(dugme)
    await waitFor(() => expect(dosyaIndir).toHaveBeenCalledWith(expect.any(Blob), "r.eml"))
    expect(screen.getByText(/Outlook taslağı \(\.eml\) indirildi/)).toBeInTheDocument()
  })
})
