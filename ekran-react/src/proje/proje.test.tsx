import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ProjeSayfasi } from "@/proje/proje-sayfasi"

beforeEach(() => window.localStorage.clear())
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

type Cagri = { yol: string; yontem: string; govde: unknown }

const EKRAN = {
  yonetici: true,
  kendi_id: 1,
  genel_toplam: 2,
  tamlar: [
    { id: 1, ad: "Mudur" },
    { id: 2, ad: "Ayse Test" },
  ],
  ozet: [{ tam: "Ayse Test", proje: 1, calisma: 0, ddos: 1, dc_tasima: 0, topoloji: 0, kapanan: 1, devam_eden: 1, toplam: 2 }],
  kalemler: [
    {
      id: 5,
      tam_id: 2,
      tam: "Ayse Test",
      kategori: "ddos",
      baslik: "DDoS eşik ayarı",
      aciklama: "",
      durum: "kapandi",
      oncelik: "kritik",
      baslangic: null,
      hedef: "2026-12-31",
      kapanis: "2026-10-10",
      aksiyonlar: [{ id: 1, metin: "Proje kaydı oluşturuldu.", yapan: "Mudur", zaman: "2026-10-01T08:00:00Z" }],
    },
  ],
}
const CALISMA = {
  musteriler: [
    { id: 1, ad: "Alfa A.Ş.", tam: "Ayse Test", tam_id: 2, istirak: false },
    { id: 2, ad: "Alfa İştirak", tam: "Ayse Test", tam_id: 2, istirak: true },
    { id: 3, ad: "Beta Ltd", tam: "Mudur", tam_id: 1, istirak: false },
  ],
  isaretler: { "2": { ddos: { yapildi: true, detay: "Eşik 2 Gbps", guncelleyen: "Ayse Test", zaman: "2026-10-02T08:00:00Z" } } },
}

function kur(yazabilir = true): Cagri[] {
  const cagrilar: Cagri[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn(async (girdi: string, ayar?: RequestInit) => {
      const yontem = ayar?.method ?? "GET"
      const yol = String(girdi)
      cagrilar.push({ yol, yontem, govde: typeof ayar?.body === "string" ? JSON.parse(ayar.body) : null })
      const veri = yontem !== "GET" ? { id: 5, zaman: "2026-10-10T10:00:00Z" } : yol.includes("/proje/musteri") ? CALISMA : EKRAN
      return new Response(JSON.stringify({ status: "success", data: veri }), { status: 200, headers: { "Content-Type": "application/json" } })
    }),
  )
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={istemci}>
      <ProjeSayfasi dil="tr" yazabilir={yazabilir} />
    </QueryClientProvider>,
  )
  return cagrilar
}

describe("Takip Edilen Projeler sayfasi", () => {
  it("ozet, proje durumu PATCH, aksiyon ekleme ve yeni proje formu", async () => {
    const cagrilar = kur()
    expect(await screen.findByText("DDoS eşik ayarı")).toBeInTheDocument()
    expect(screen.getByText("GENEL TOPLAM")).toBeInTheDocument()
    expect(screen.getByText("🎯 31.12.2026")).toBeInTheDocument()
    expect(screen.getByText("Proje kaydı oluşturuldu.")).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText("Durum: DDoS eşik ayarı"), { target: { value: "devam" } })
    await waitFor(() => expect(cagrilar.find((c) => c.yontem === "PATCH")?.govde).toEqual({ status: "devam" }))

    fireEvent.change(screen.getByLabelText("Aksiyon/not ekle... DDoS eşik ayarı"), { target: { value: "Test yapıldı" } })
    fireEvent.click(screen.getByRole("button", { name: "Ekle" }))
    await waitFor(() => expect(cagrilar.find((c) => c.yol.includes("/kalem/5/aksiyon"))?.govde).toEqual({ metin: "Test yapıldı" }))

    fireEvent.click(screen.getByRole("button", { name: "+ Yeni Proje" }))
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }))
    expect(await screen.findByText("Proje başlığı zorunlu.")).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText("Sorumlu TAM"), { target: { value: "2" } })
    fireEvent.change(screen.getByLabelText("Proje Başlığı"), { target: { value: "SD-WAN" } })
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }))
    await waitFor(() => expect(cagrilar.find((c) => c.yol.endsWith("/proje/kalem") && c.yontem === "POST")?.govde).toMatchObject({ owner_id: 2, category: "proje", priority: "orta", title: "SD-WAN", target_date: null }))
  })

  it("admin olmayan kullanici proje kalemini yalniz okur: ekle, sil, durum ve aksiyon yok; musteri calismasi isareti acik kalir", async () => {
    kur(false)
    expect(await screen.findByText("DDoS eşik ayarı")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "+ Yeni Proje" })).not.toBeInTheDocument()
    expect(screen.queryByLabelText("Durum: DDoS eşik ayarı")).not.toBeInTheDocument()
    expect(screen.queryByLabelText("Öncelik: DDoS eşik ayarı")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Sil: DDoS eşik ayarı" })).not.toBeInTheDocument()
    expect(screen.queryByLabelText("Aksiyon/not ekle... DDoS eşik ayarı")).not.toBeInTheDocument()
    expect(await screen.findByLabelText("Beta Ltd: Proje")).toBeEnabled()
  })

  it("musteri bazli calismalar: isaret aninda kaydedilir, TAM suzgeci istiraki catisiyla tutar, Excel baglantisi suzgeci tasir", async () => {
    const cagrilar = kur()
    expect(await screen.findByText("↳ Alfa İştirak")).toBeInTheDocument()
    expect(screen.getByLabelText("Alfa İştirak: Ddos Optimizasyonu")).toBeChecked()

    fireEvent.click(screen.getByLabelText("Beta Ltd: Proje"))
    await waitFor(() => expect(cagrilar.find((c) => c.yontem === "PUT")).toMatchObject({ govde: { yapildi: true, detay: "" } }))
    expect(cagrilar.find((c) => c.yontem === "PUT")?.yol).toContain("/api/v1/proje/musteri/3/proje")
    expect(await screen.findByText(/✓ Kaydedildi/)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText("TAM", { selector: "select" }), { target: { value: "2" } })
    expect(screen.queryByText("Beta Ltd")).not.toBeInTheDocument()
    expect(screen.getByText("↳ Alfa İştirak")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Excel/ })).toHaveAttribute("href", expect.stringContaining("/api/v1/proje/rapor.xlsx?tam_id=2"))
  })
})
