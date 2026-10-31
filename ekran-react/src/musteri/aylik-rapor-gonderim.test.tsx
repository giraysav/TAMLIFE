import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import { AylikRapor } from "@/musteri/aylik-rapor"
import { oku, yaz } from "@/lib/sorgu"
import { dosyaIndir } from "@/musteri/rapor-pdf"

vi.mock("@/lib/sorgu", async (gercek) => ({
  sorguMetni: (await gercek<typeof import("@/lib/sorgu")>()).sorguMetni,
  oku: vi.fn(),
  yaz: vi.fn(),
  hataMesaji: (_h: unknown, text: string) => text,
  ApiHata: class extends Error {},
}))
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

function sunucu() {
  const taslak = { yil: 2026, ay: 9, birim: true, alanlar: {}, varsayilanlar: { tr: {}, en: {} }, kayitli: false, guncelleyen: null, zaman: null,
    alicilar: { kime: "musteri@example.com", bilgi: "" }, gonderim: null }
  vi.mocked(oku).mockImplementation(async (url: string) => {
    if (url.endsWith("/taslak")) return taslak
    if (url.endsWith("/gecmis")) return []
    return { dosyalar: [], ekler: [] }
  })
}

describe("aylik rapor gonderimi (2026-10-31: SMTP kaldirildi, yalniz Outlook taslagi)", () => {
  it("Outlook taslagi iner, TAMLIFE@ adresi gecmez", async () => {
    sunucu()
    vi.mocked(yaz).mockResolvedValue({ eml_adi: "r.eml", eml_base64: "eA==" })
    vi.spyOn(window, "confirm").mockReturnValue(true)
    render(<AylikRapor musteriId={1} musteriAdi="Test" dil="tr" geriAlabilir={false} />, { wrapper: sar })
    const dugme = await screen.findByRole("button", { name: "Raporu gönder" })
    await waitFor(() => expect(dugme).toBeEnabled())
    fireEvent.click(dugme)
    await waitFor(() => expect(dosyaIndir).toHaveBeenCalledWith(expect.any(Blob), "r.eml"))
    expect(screen.getByText(/Outlook taslağı \(\.eml\) indirildi/)).toBeInTheDocument()
    expect(yaz).toHaveBeenCalledWith("POST", "/api/v1/musteri/1/rapor/gonder", expect.objectContaining({ onay: true, pdf_base64: "cGRm" }))
    expect(document.body.textContent).not.toContain("TAMLIFE@")
  })
})
