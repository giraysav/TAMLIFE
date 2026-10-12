import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { RollerSayfasi } from "@/shell/roller-sayfasi"
import { SunumSayfasi } from "@/sunum/sunum-sayfasi"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function sarmala(cocuk: ReactNode) {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={istemci}>{cocuk}</QueryClientProvider>)
}

type Cagri = { yol: string; yontem: string; govde: unknown }

/** fetch'i yola gore cevaplar ({yol parcasi: data}, ilk eslesen); cagrilarin yontem ve govdesini kaydeder. */
function sahteSunucu(cevaplar: Record<string, unknown>): Cagri[] {
  const cagrilar: Cagri[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn(async (girdi: string, ayar?: RequestInit) => {
      cagrilar.push({ yol: String(girdi), yontem: ayar?.method ?? "GET", govde: typeof ayar?.body === "string" ? JSON.parse(ayar.body) : null })
      const anahtar = Object.keys(cevaplar).find((k) => String(girdi).includes(k))
      return anahtar === undefined
        ? new Response(JSON.stringify({ detail: "yok" }), { status: 404, headers: { "Content-Type": "application/json" } })
        : new Response(JSON.stringify({ status: "success", data: cevaplar[anahtar] }), { status: 200, headers: { "Content-Type": "application/json" } })
    }),
  )
  return cagrilar
}

const OZET = { durumlar: { yillik_izin: 2 }, online: 1, yuzyuze: 0, kayitli_gun: 2, izin_gun: 2, toplanti: 1 }
const KAYNAKLAR = {
  duzenleyebilir: true,
  kaynaklar: [
    { id: "takvim", ad: "TAM Takvim özeti", ad_en: "TAM Calendar summary", aciklama: "Kişi bazında izin", aciklama_en: "Leave per person", modul: "TAM Takvim", modul_en: "TAM Calendar", anlik: false, acik: true },
    { id: "portfoy", ad: "Müşteri portföy özeti", ad_en: "Customer portfolio summary", aciklama: "Çatı / iştirak", aciklama_en: "Parent / affiliate", modul: "Müşteri Yönetimi", modul_en: "Customer Management", anlik: true, acik: false, grup: "work" },
  ],
}
const DONEM = {
  yil: 2026,
  ceyrek: 4,
  donem: "2026-Q4",
  zaman: "guncel",
  yonetebilir: true,
  ogeler: [
    { kaynak: "takvim", ad: "TAM Takvim özeti", ad_en: "TAM Calendar summary", anlik: false, durum: "canli", gonderen: "", zaman: "2026-10-10T10:00:00Z", veri: { genel: OZET, uyeler: [{ ad: "Ayse Test", ...OZET }] }, kayit_no: "" },
    {
      kaynak: "rapor",
      ad: "Gönderilen aylık rapor durumu",
      ad_en: "Sent monthly report status",
      anlik: false,
      durum: "kayitli",
      gonderen: "",
      zaman: "2026-10-01T08:00:00Z",
      veri: { kpi: [{ ad: "Ekim · atılan", ad_en: "October · sent", deger: 3, birim: "", alt: "/ 5" }], tablo: { sutunlar: [{ ad: "TAM", ad_en: "TAM", birim: "" }, { ad: "Tutar", ad_en: "Amount", birim: "TRY" }], satirlar: [["Ayse Test", 1500]] } },
      kayit_no: "",
    },
    { kaynak: "onedesk", ad: "Onedesk özeti", ad_en: "Onedesk summary", anlik: false, durum: "hata", gonderen: "", zaman: null, veri: null, kayit_no: "ab12cd34" },
    { kaynak: "portfoy", ad: "Müşteri portföy özeti", ad_en: "Customer portfolio summary", anlik: true, durum: "yok", gonderen: "", zaman: null, veri: null, kayit_no: "" },
  ],
}

describe("Ceyrek Bazli Sunum sayfasi", () => {
  it("kaynak basina kart: canli/donmus rozet, genel KPI + tablo, hata ve kaydi olmayan anlik kaynak", async () => {
    const cagrilar = sahteSunucu({ "/api/v1/sunum/donem": DONEM, "/api/v1/sunum/gonder": { sunumda: null }, "/api/v1/sunum/kaynaklar": KAYNAKLAR })
    sarmala(<SunumSayfasi dil="tr" />)
    expect(await screen.findByRole("heading", { name: "Gönderilen aylık rapor durumu" })).toBeInTheDocument()
    expect(screen.getByText("Canlı")).toBeInTheDocument()
    expect(screen.getByText("Donduruldu")).toBeInTheDocument()
    expect(screen.getByText("Ekim · atılan")).toBeInTheDocument()
    expect(screen.getByText("/ 5")).toBeInTheDocument()
    expect(screen.getByText("1.500,00 ₺")).toBeInTheDocument()
    expect(screen.getByText(/kayıt ab12cd34/)).toBeInTheDocument()
    expect(screen.getByText(/dondurulmuş kaydı olmayan anlık kaynaklar: Müşteri portföy özeti/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Sunuma sabitle/ })).toBeInTheDocument()
    expect(screen.getByText("Sunuma akan kaynaklar")).toBeInTheDocument() // yetkiliye kaynak secimi

    fireEvent.click(screen.getByRole("button", { name: /Kaldır/ }))
    await waitFor(() => expect(cagrilar.some((c) => c.yontem === "POST" && c.yol.includes("/sunum/gonder"))).toBe(true))
    expect(cagrilar.find((c) => c.yontem === "POST")?.govde).toEqual({ kaynak: "rapor", yil: new Date().getFullYear(), ceyrek: Math.floor(new Date().getMonth() / 3) + 1, gonder: false })

    fireEvent.click(screen.getByRole("button", { name: "Ç1" }))
    await waitFor(() => expect(cagrilar.some((c) => c.yol.includes("ceyrek=1"))).toBe(true))
  })

  it("English iken kaynak ve KPI adlari EN; yetkisiz kullanici islem dugmesi gormez", async () => {
    sahteSunucu({ "/api/v1/sunum/donem": { ...DONEM, yonetebilir: false } })
    sarmala(<SunumSayfasi dil="en" />)
    expect(await screen.findByRole("heading", { name: "Sent monthly report status" })).toBeInTheDocument()
    expect(screen.getByText("October · sent")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Pin to presentation|Remove|Update/ })).not.toBeInTheDocument()
    expect(screen.queryByText("Sources flowing into the presentation")).not.toBeInTheDocument()
  })
})

describe("Rol Yonetimi: ek yetkiler ve Ceyrek Bazli Sunum bolumu", () => {
  const ROLLER = {
    catalog: [{ id: "sunum", label: "Çeyrek Bazlı Sunum", label_en: "Quarterly Presentation", admin_only: false, children: [] }],
    permission_catalog: [
      {
        id: "sunum.gonder",
        label: "Çeyrek bazlı sunumu yönet",
        label_en: "Manage the quarterly presentation",
        description: "Sunuma öğe gönderebilir",
        description_en: "Can send items",
        where: "TAM Takvim › grafik",
        where_en: "TAM Calendar › chart",
        area: "sunum",
      },
    ],
    roles: [
      { role: "admin", label: "Admin", editable: false, modules: ["sunum"], landing: "ozet", permissions: ["sunum.gonder"], saved: false },
      { role: "TeamMngr", label: "Manager", editable: true, modules: ["sunum"], landing: "ozet", permissions: [], saved: true },
    ],
  }

  it("yetki duz dilde anlatilir; rol isareti aninda kaydedilir ve rol kartina yansir; kaynak isareti listeyi gonderir", async () => {
    const cagrilar = sahteSunucu({
      "/api/v1/roller/TeamMngr": { role: "TeamMngr", modules: ["sunum"], landing: "ozet", permissions: ["sunum.gonder"] },
      "/api/v1/roller": ROLLER,
      "/api/v1/sunum/kaynaklar": KAYNAKLAR,
    })
    sarmala(<RollerSayfasi dil="tr" />)
    expect(await screen.findByText("1 · Sunumu yönetebilecek roller")).toBeInTheDocument()
    expect(screen.getAllByText("Ne sağlar:").length).toBeGreaterThan(0)
    expect(screen.getByText("Sunuma öğe gönderebilir")).toBeInTheDocument()
    expect(screen.queryByText("Ek yetkiler")).toBeNull() // rol kartindaki "Ek yetkiler" kaldirildi

    const alan = screen.getByText("1 · Sunumu yönetebilecek roller").closest("section") as HTMLElement
    const admin = within(alan).getByRole("checkbox", { name: /Admin/ })
    expect(admin).toBeChecked()
    expect(admin).toBeDisabled()
    fireEvent.click(within(alan).getByRole("checkbox", { name: /Manager/ }))
    await waitFor(() => expect(within(alan).getByRole("checkbox", { name: /Manager/ })).toBeChecked())
    expect(cagrilar.find((c) => c.yontem === "PUT" && c.yol.includes("/roller/TeamMngr"))?.govde).toEqual({ modules: ["sunum"], landing: "ozet", permissions: ["sunum.gonder"] })

    fireEvent.click(await screen.findByRole("checkbox", { name: /Müşteri portföy özeti/ }))
    await waitFor(() => expect(cagrilar.some((c) => c.yontem === "PUT" && c.yol.includes("/sunum/kaynaklar"))).toBe(true))
    expect(cagrilar.find((c) => c.yontem === "PUT" && c.yol.includes("/sunum/kaynaklar"))?.govde).toEqual({ kaynaklar: ["takvim", "portfoy"] })
    expect(screen.getByRole("region", { name: "Benim Yerim" })).toBeInTheDocument() // kaynaklar menu bolumune gore gruplu
  })
})
