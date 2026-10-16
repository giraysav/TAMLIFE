import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { TamTakvim } from "@/takvim/tam-takvim"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const ozet = (online: number) => ({ durumlar: { yillik_izin: 1 }, online, yuzyuze: 0, kayitli_gun: 1, is_gunu: 0, izin_gun: 1, toplanti: online })
const ekip = (ceyrek: number, online: number) => ({
  yil: 2026,
  ceyrek,
  donem: ceyrek ? `2026-Q${ceyrek}` : "2026",
  uyeler: [{ id: 2, ad: "Ayse Test", kullanici: "ayse", rol: "TeamMember", son_giris: null, ...ozet(online) }],
  genel: ozet(online),
  sunumda: null,
  sunuma_gonderebilir: false,
})

describe("TAM Takvim grafigi", () => {
  it("grafik secilen ceyrek degil yilin tamamini gosterir", async () => {
    const yollar: string[] = []
    vi.stubGlobal(
      "fetch",
      vi.fn(async (girdi: string) => {
        yollar.push(String(girdi))
        const veri = String(girdi).includes("ceyrek=0") ? ekip(0, 37) : ekip(4, 5)
        return new Response(JSON.stringify({ status: "success", data: veri }), { status: 200, headers: { "Content-Type": "application/json" } })
      }),
    )
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <TamTakvim dil="tr" />
      </QueryClientProvider>,
    )
    fireEvent.click(await screen.findByRole("button", { name: /Grafik oluştur/ }))
    await waitFor(() => expect(yollar.some((y) => y.includes("ceyrek=0"))).toBe(true))
    expect(await screen.findByText(/2026 · Tüm yıl · tüm personelin toplamı/)).toBeInTheDocument()
    expect(await screen.findAllByText("37")).not.toHaveLength(0) // yillik toplam (ceyrek 5 degil)
  })
})

describe("TAM Takvim yillik ve admin kayitlari", () => {
  it("varsayilan donem tum yil; admin kisinin girdigi kayitlari metinleriyle gorur", async () => {
    const yollar: string[] = []
    const gunler = {
      uye: "Ayse Test",
      gunler: [
        { tarih: "2026-10-05", durum: "calisiyor", online: 2, yuzyuze: 1, toplanti_ozeti: "Alfa ile SD-WAN toplantisi", yapilan_isler: "Kurulum bitti" },
        { tarih: "2026-10-28", durum: "arife_tatili", durum2: "sirket_izni", online: 0, yuzyuze: 0, kurum: { durum: "arife_tatili" }, toplanti_ozeti: "", yapilan_isler: "" },
      ],
    }
    vi.stubGlobal(
      "fetch",
      vi.fn(async (girdi: string) => {
        yollar.push(String(girdi))
        const veri = String(girdi).includes("/ekip/2") ? gunler : ekip(0, 3)
        return new Response(JSON.stringify({ status: "success", data: veri }), { status: 200, headers: { "Content-Type": "application/json" } })
      }),
    )
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <TamTakvim dil="tr" />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(yollar[0]).toContain("ceyrek=0"))
    // 2026-10-15: tablo sutunlari kullanicinin sirasiyla; is girilen gun, calisiyor, toplanti, izin gunu yok
    const basliklar = (await screen.findAllByRole("columnheader")).map((h) => h.textContent?.trim())
    expect(basliklar.slice(1, 7)).toEqual(["Online", "Yüzyüze", "Yıllık izin", "Şirket izni", "Yarım gün", "Resmi tatil"])
    expect(basliklar).not.toContain("Çalışıyor")
    expect(screen.getByText("TAM sayısı")).toBeInTheDocument()
    expect(screen.queryByText("Toplam izin günü")).toBeNull()
    fireEvent.click(await screen.findByRole("button", { name: /Ayse Test/ }))
    expect(await screen.findByText("Alfa ile SD-WAN toplantisi")).toBeInTheDocument()
    expect(screen.getByText("Kurulum bitti")).toBeInTheDocument()
    expect(screen.getByText("Girilen kayıtlar")).toBeInTheDocument()
    expect(screen.getAllByRole("row").filter((r) => r.textContent?.includes("28.10.2026"))).toHaveLength(0) // kurum gunu kayit degil
  })
})
