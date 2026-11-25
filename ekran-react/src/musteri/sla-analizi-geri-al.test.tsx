import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
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
afterEach(() => { cleanup(); vi.clearAllMocks() })

function sar({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
}

describe("SLA analizini geri alma", () => {
  it("analiz alanlari yazar, geri al analizden onceki metni dondurur", async () => {
    const taslak = { yil: 2026, ay: 9, birim: true, alanlar: { bilgi: "ELLE YAZILAN", devam: "" }, varsayilanlar: { tr: {}, en: {} }, kayitli: false,
      guncelleyen: null, zaman: null, alicilar: { kime: "musteri@example.com", bilgi: "" }, gonderim: null }
    const sla = { yil: 2026, ay: 9, ozet: { dosya: "sla.xlsx", boyut: 1, zaman: null, yukleyen: null, grafik: 0, ek_gorsel: 0, ek_dosya: 0 }, analiz: null,
      ekler: [], dosyalar: [], araclar: { ceviri: { hazir: false, kaynak: null }, yz: false } }
    vi.mocked(oku).mockImplementation(async (url: string) => {
      if (url.includes("/taslak")) return taslak
      if (url.endsWith("/gecmis")) return []
      return sla
    })
    vi.mocked(yaz).mockImplementation(async (_m: string, url: string) => {
      if (url.includes("/sla/analiz")) return { analiz: { toplam: 3, ci_sayisi: 1, dil: "tr" }, ozet: { bilgi: "• YENI OZET", devam: "" }, yz: { hazir: false, yorum: null, neden: "" } }
      return {}
    })
    render(<AylikRapor musteriId={1} musteriAdi="Test" dil="tr" geriAlabilir={false} />, { wrapper: sar })
    expect(screen.queryByRole("button", { name: "Analizi geri al" })).toBeNull()
    fireEvent.click(await screen.findByRole("button", { name: "Özet çıkar" }))
    const geriAl = await screen.findByRole("button", { name: "Analizi geri al" })
    await waitFor(() => expect((screen.getAllByRole("textbox") as HTMLTextAreaElement[]).some((k) => k.value.includes("YENI OZET"))).toBe(true))
    fireEvent.click(geriAl)
    await waitFor(() => expect((screen.getAllByRole("textbox") as HTMLTextAreaElement[]).some((k) => k.value === "ELLE YAZILAN")).toBe(true))
    expect((screen.getAllByRole("textbox") as HTMLTextAreaElement[]).some((k) => k.value.includes("YENI OZET"))).toBe(false)
    expect(screen.queryByRole("button", { name: "Analizi geri al" })).toBeNull()
  })
})
