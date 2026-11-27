import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ProjeIceAktar } from "@/proje/ice-aktar"
import { yukle } from "@/lib/sorgu"

vi.mock("@/lib/sorgu", async (gercek) => ({
  sorguMetni: (await gercek<typeof import("@/lib/sorgu")>()).sorguMetni,
  hataMesaji: (_h: unknown, metin: string) => metin,
  yukle: vi.fn(),
}))
const atamalar = (cagri: number) => JSON.parse(new URLSearchParams(String(vi.mocked(yukle).mock.calls[cagri][0]).split("?")[1]).get("atamalar") ?? "{}")
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const ONIZLEME = {
  dosya: "Proje calisma 2026.xlsm",
  yil: 2026,
  plan: { toplam: 3, yeni: 2, var: 0, tekrar: 0, tam_yok: 1 },
  eslesmeyen: [{ ad: "Sevil Yenihan", anahtar: "sevil yenihan", kayit: 1 }],
  kisiler: [{ id: 7, ad: "Ayse Test" }],
  satirlar: [
    { satir: 4, ceyrek: "Q1", tam: "AYSE", sahip: "Ayse Test", kategori: "proje", baslik: "Alfa: SD-WAN geçişi", durum: "yeni" },
    { satir: 4, ceyrek: "Q1", tam: "AYSE", sahip: "Ayse Test", kategori: "ddos", baslik: "Alfa", durum: "yeni" },
    { satir: 6, ceyrek: "Q1", tam: "Sevil Yenihan", sahip: "", kategori: "calisma", baslik: "Delta: topoloji", durum: "tam_yok" },
  ],
}

describe("proje Excel ice aktarma (2026-10-31)", () => {
  it("onizler, eslesmeyen TAM'a kisi secimiyle yeniden onizler, yalniz yenileri ekler", async () => {
    vi.mocked(yukle).mockImplementation(async (yol: string) => {
      if (yol.includes("/uygula")) return { ...ONIZLEME.plan, yeni: 3, tam_yok: 0, eklendi: 3 }
      return yol.includes("atamalar")
        ? { ...ONIZLEME, plan: { ...ONIZLEME.plan, yeni: 3, tam_yok: 0 }, eslesmeyen: [], satirlar: ONIZLEME.satirlar.map((s) => ({ ...s, durum: "yeni" })) }
        : ONIZLEME
    })
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ProjeIceAktar dil="tr" onKapat={() => {}} />
      </QueryClientProvider>,
    )
    const dosya = new File(["x"], "Proje calisma 2026.xlsm")
    fireEvent.change(screen.getByLabelText("Excel dosyası seç"), { target: { files: [dosya] } })
    expect(await screen.findByText("Alfa: SD-WAN geçişi")).toBeInTheDocument()
    expect(vi.mocked(yukle).mock.calls[0][0]).toBe("/api/v1/proje/ice-al/onizleme?dosya=Proje+calisma+2026.xlsm")
    expect(screen.getByRole("button", { name: "2 yeni kaydı ekle" })).toBeEnabled()

    fireEvent.change(screen.getByLabelText("Sevil Yenihan (1 kayıt) için kişi"), { target: { value: "7" } })
    expect(await screen.findByRole("button", { name: "3 yeni kaydı ekle" })).toBeInTheDocument()
    expect(atamalar(1)).toEqual({ "sevil yenihan": 7 })
    expect(screen.getByLabelText("Sevil Yenihan (1 kayıt) için kişi")).toBeInTheDocument()  // secim geri alinabilir

    fireEvent.click(screen.getByRole("button", { name: "3 yeni kaydı ekle" }))
    await waitFor(() => expect(screen.getByText(/3 kayıt eklendi/)).toBeInTheDocument())
    expect(vi.mocked(yukle).mock.calls[2][0]).toContain("/uygula?")
    expect(atamalar(2)).toEqual({ "sevil yenihan": 7 })
  })
})
