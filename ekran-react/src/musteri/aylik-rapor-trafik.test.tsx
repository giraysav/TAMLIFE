import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import { AylikRapor } from "@/musteri/aylik-rapor"
import { oku, yaz } from "@/lib/sorgu"

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
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  delete window.TamlifeTrafik
})

function sar({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
}

function sunucu() {
  const taslak = { yil: 2026, ay: 10, birim: true, alanlar: {}, varsayilanlar: { tr: {}, en: {} }, kayitli: false, guncelleyen: null, zaman: null,
    alicilar: { kime: "", bilgi: "" }, gonderim: null }  // prettier-ignore
  vi.mocked(oku).mockImplementation(async (url: string) => {
    if (url.endsWith("/taslak")) return taslak
    if (url.endsWith("/gecmis")) return []
    return { dosyalar: [], ekler: [] }
  })
}

describe("aylik rapor devre performansi grafikleri (public/rapor-trafik.js koprusu, 2026-11-20)", () => {
  it("betik varsa grafikler PDF sablonunda 'Devre Performansi' sayfasina girer; devre kutusu rapor adresleriyle cizilir", async () => {
    sunucu()
    const gorseller = vi.fn(async () => [{ anahtar: "d1", baslik: "Devre 1", gorsel: "data:image/png;base64,AA==" }])
    const devreKutusu = vi.fn()
    window.TamlifeTrafik = { gorseller, bekliyor: () => false, devreKutusu }
    render(<AylikRapor musteriId={1} musteriAdi="Test" dil="tr" geriAlabilir={false} />, { wrapper: sar })
    const sablon = await screen.findByTestId("rapor-pdf")
    await waitFor(() => expect(within(sablon).getByText("DEVRE PERFORMANSI")).toBeInTheDocument())
    // onizleme kapaliyken sablon ekran disinda ve aria-hidden
    expect(within(sablon).getByRole("img", { name: "Devre 1", hidden: true })).toBeInTheDocument()
    expect(gorseller).toHaveBeenCalledWith(oku, "/api/v1/musteri/1/rapor/trafik", "tr")
    expect(devreKutusu).toHaveBeenCalledWith(
      expect.any(HTMLDivElement),
      expect.objectContaining({ taban: "/api/v1/musteri/1/rapor", adres: "/api/v1/musteri/1/rapor/trafik", dil: "tr", getir: oku, istek: yaz }),
    )
  })

  it("betik yoksa rapor onsuz calisir (devre performansi sayfasi yok)", async () => {
    sunucu()
    render(<AylikRapor musteriId={1} musteriAdi="Test" dil="tr" geriAlabilir={false} />, { wrapper: sar })
    const sablon = await screen.findByTestId("rapor-pdf")
    await screen.findByRole("button", { name: "Raporu gönder" })
    expect(within(sablon).queryByText("DEVRE PERFORMANSI")).toBeNull()
  })
})
