import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { TalepSayfasi } from "@/talep/talep-sayfasi"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function sarmala(cocuk: ReactNode) {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={istemci}>{cocuk}</QueryClientProvider>)
}

type Cagri = { yol: string; yontem: string; govde: unknown }

function sahteSunucu(liste: unknown): Cagri[] {
  const cagrilar: Cagri[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn(async (girdi: string, ayar?: RequestInit) => {
      const yontem = ayar?.method ?? "GET"
      cagrilar.push({ yol: String(girdi), yontem, govde: typeof ayar?.body === "string" ? JSON.parse(ayar.body) : null })
      const veri = yontem === "GET" ? liste : { id: 7, degisen: ["durum"] }
      return new Response(JSON.stringify({ status: "success", data: veri }), { status: 200, headers: { "Content-Type": "application/json" } })
    }),
  )
  return cagrilar
}

const TALEP = {
  id: 7,
  baslik: "Personel süzgeci",
  tur: "iyilestirme",
  oncelik: "yuksek",
  modul: "musteri",
  mevcut_durum: "Yalnız ada göre süzülüyor.",
  beklenen_durum: "TAM'a göre de süzülsün.",
  kabul_olcutu: "",
  durum: "planlandi",
  acik: true,
  talep_eden: "Ayse Test",
  olusturuldu: "2026-10-01T08:00:00Z",
  guncellendi: null,
  hedef_surum: "3.6.0",
  admin_notu: "Sprint 4",
  atanan_id: 2,
  atanan: "Ayse Test",
}

describe("Gelistirme Talepleri sayfasi", () => {
  it("uye: Taleplerim, durum rozeti, yonetim sutunu yok; zorunlu alanlar sunucuya gitmeden uyarir", async () => {
    const cagrilar = sahteSunucu({ yonetebilir: false, silebilir: false, talepler: [TALEP] })
    sarmala(<TalepSayfasi dil="tr" />)
    expect(await screen.findByText("Personel süzgeci")).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Taleplerim" })).toBeInTheDocument()
    expect(screen.getAllByText("Planlandı").some((e) => e.tagName === "SPAN")).toBe(true)  // rozet (secenek degil)
    expect(screen.getAllByText("Müşteri Yönetimi").some((e) => e.tagName === "DIV")).toBe(true)
    expect(screen.queryByRole("columnheader", { name: "Atanan" })).not.toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText("Tek cümleyle ne istiyorsunuz?"), { target: { value: "Yeni rapor" } })
    fireEvent.click(screen.getByRole("button", { name: /Talebi Gönder/ }))
    expect(await screen.findByText(/alanları zorunlu/)).toBeInTheDocument()
    expect(cagrilar.some((c) => c.yontem === "POST")).toBe(false)

    fireEvent.change(screen.getByPlaceholderText("Mevcut davranış veya eksiklik"), { target: { value: "Yok" } })
    fireEvent.change(screen.getByPlaceholderText("Beklediğiniz davranış"), { target: { value: "Olsun" } })
    fireEvent.click(screen.getByRole("button", { name: /Talebi Gönder/ }))
    expect(await screen.findByText(/Talebiniz alındı/)).toBeInTheDocument()
    const post = cagrilar.find((c) => c.yontem === "POST")
    expect(post?.govde).toMatchObject({ baslik: "Yeni rapor", tur: "ozellik", oncelik: "orta", mevcut_durum: "Yok", beklenen_durum: "Olsun" })
  })

  it("yonetici: Is Listesi + acik sayisi, durum degisikligi PATCH ile gider, gecmis acilir, admin silebilir", async () => {
    const liste = {
      yonetebilir: true,
      silebilir: true,
      acik_sayisi: 3,
      kisiler: [{ id: 2, ad: "Ayse Test" }],
      talepler: [{ ...TALEP, gecmis: [{ zaman: "2026-10-02T09:00:00Z", yapan: "Mudur", alan: "durum", eski: "yeni", yeni: "planlandi" }] }],
    }
    const cagrilar = sahteSunucu(liste)
    vi.stubGlobal("confirm", vi.fn(() => true))
    sarmala(<TalepSayfasi dil="tr" />)
    expect(await screen.findByRole("heading", { name: "İş Listesi" })).toBeInTheDocument()
    expect(screen.getByText("3 açık")).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText("Durum: Personel süzgeci"), { target: { value: "yapiliyor" } })
    await waitFor(() => expect(cagrilar.find((c) => c.yontem === "PATCH")?.govde).toEqual({ durum: "yapiliyor" }))
    expect(cagrilar.find((c) => c.yontem === "PATCH")?.yol).toContain("/api/v1/talep/7")
    expect(await screen.findByText("✓ Kaydedildi")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Personel süzgeci: değişiklik geçmişi" }))
    expect(screen.getByRole("listitem").textContent).toMatch(/Mudur · Durum: Yeni → Planlandı/)

    fireEvent.click(screen.getByRole("button", { name: "Sil: Personel süzgeci" }))
    await waitFor(() => expect(cagrilar.some((c) => c.yontem === "DELETE" && c.yol.includes("/api/v1/talep/7"))).toBe(true))
  })
})
