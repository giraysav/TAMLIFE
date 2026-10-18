import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { TopoMaker, yerlesim } from "@/topoloji/topo-maker"
import type { Analiz, Dugum, Kenar } from "@/topoloji/topo-maker"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const d = (id: string, tur: Dugum["tur"], lokasyon = "Merkez", etiket = ""): Dugum => ({ id, tur, etiket, lokasyon, il: "İstanbul" })
let kenarNo = 0
const k = (kaynak: string, hedef: string, altyapi = "SOL Fiber", yedek = false): Kenar => ({ id: `K${++kenarNo}`, kaynak, hedef, altyapi, etiket: "", yedek, devre: `D${kenarNo}`, renk: "#1A6FA6" })

const DUGUMLER = [d("ISP_CLOUD", "bulut"), d("R1", "router", "Merkez", "192.168.1.1"), d("SW1", "switch", "Merkez", "10.0.0.1"), d("SW2", "switch"), d("R2", "router"), d("R3", "router", "Şube")]
const KENARLAR = [k("ISP_CLOUD", "SW1"), k("SW1", "R1", "LAN"), k("ISP_CLOUD", "SW2", "TT Fiber"), k("SW2", "R1", "LAN"), k("ISP_CLOUD", "R2", "4.5G", true), k("ISP_CLOUD", "R3", "xDSL", true)]

const ANALIZ: Analiz = {
  spof: true,
  spof_noktalari: [{ lokasyon: "Merkez", bb: "ist-bb-01", altyapilar: ["SOL Fiber", "TT Fiber"], neden: "ortak_bb", devreler: ["D1", "D2"] }],
  dugumler: DUGUMLER,
  kenarlar: KENARLAR,
  sehirler: [{ il: "İSTANBUL", adet: 5, enlem: 41.0082, boylam: 28.9784 }],
  konumsuz_iller: ["Bilecik"],
  kolonlar: { loc: "Lokasyon_Adi", il: "Il" },
  satir: 6,
  lokasyon: 2,
  degerlendirme: "riskli",
  uyarilar: [],
  renkler: { "SOL Fiber": "#1A6FA6", "TT Fiber": "#B03A2E", "4.5G": "#6C3483", xDSL: "#E67E22", LAN: "#7F8C8D" },
}

describe("TopoMaker yerlesimi", () => {
  it("lokasyon bloklari, switch altinda router; ortak router ilk switch'te, bulut ortada", () => {
    const y = yerlesim(DUGUMLER, KENARLAR)
    expect(y.lokasyonlar.map((l) => l.ad)).toEqual(["Merkez", "Şube"])
    expect(y.konum.R1.x).toBe(y.konum.SW1.x)
    expect(y.konum.R1.y).toBeGreaterThan(y.konum.SW1.y)
    expect(y.konum.SW2.y).toBe(y.konum.SW1.y)
    expect(y.konum.R2.y).toBe(y.konum.SW1.y) // 4.5G router dogrudan bulut altinda
    expect(y.konum.R3.x).toBeGreaterThan(y.lokasyonlar[0].x2)
    expect(y.konum.ISP_CLOUD.x).toBe(y.genislik / 2)
  })
})

describe("TopoMaker ekrani", () => {
  it("dosya secilmeden uyarir; analizde SPoF, sayilar, cizim ve harita sekmesi", async () => {
    const fetchSahte = vi.fn(async (yol: RequestInfo | URL, _ayar?: RequestInit) => new Response(JSON.stringify({ status: "success", data: String(yol).includes("/musteri/7") ? { kimlik: { unvan: "Test Müşteri" } } : ANALIZ }), { status: 200, headers: { "Content-Type": "application/json" } }))
    vi.stubGlobal("fetch", fetchSahte)
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <TopoMaker dil="tr" musteriId={7} />
      </QueryClientProvider>,
    )
    expect(screen.getByText("Envanter Yüklenmesi Bekleniyor")).toBeInTheDocument()
    await screen.findByText("Test Müşteri")
    fireEvent.click(screen.getByRole("button", { name: /Analizi Başlat/ }))
    expect(screen.getByText(/Önce bir CSV veya XLSX/)).toBeInTheDocument()
    expect(fetchSahte.mock.calls.filter((c) => String(c[0]).includes("/topoloji/"))).toHaveLength(0)

    const girdi = container.querySelector("input[type=file]") as HTMLInputElement
    fireEvent.change(girdi, { target: { files: [new File(["a;b"], "envanter.csv", { type: "text/csv" })] } })
    fireEvent.click(screen.getByRole("button", { name: /Analizi Başlat/ }))
    expect(await screen.findByText(/TEKİL HATA NOKTASI/)).toBeInTheDocument()
    expect(fetchSahte.mock.calls.some((c) => String(c[0]).includes("/api/v1/topoloji/analiz?musteri=7&dosya=envanter.csv"))).toBe(true)
    expect(screen.getByText(/Merkez: ortak BB router/)).toBeInTheDocument()
    expect(container.querySelectorAll("[data-tur=switch]")).toHaveLength(2)
    expect(container.querySelectorAll("[data-tur=router]")).toHaveLength(3)
    expect(container.querySelectorAll("path[stroke-dasharray]")).toHaveLength(2) // iki yedek devre
    expect(screen.getByText(/Lokasyon_Adi, Il/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole("tab", { name: /Coğrafi Harita/ }))
    expect(container.querySelector("[data-il='İSTANBUL']")?.textContent).toContain("5")
    expect(screen.getByText(/Koordinatı tanımlı olmayan iller: Bilecik/)).toBeInTheDocument()
  })

  it("sunucu hatasi mesaji gosterilir", async () => {
    vi.stubGlobal("fetch", vi.fn(async (yol: RequestInfo | URL) => String(yol).includes("/musteri/7")
      ? new Response(JSON.stringify({ status: "success", data: { kimlik: { unvan: "Test Müşteri" } } }), { status: 200, headers: { "Content-Type": "application/json" } })
      : new Response(JSON.stringify({ detail: "Lokasyon kolonu bulunamadı." }), { status: 400, headers: { "Content-Type": "application/json" } })))
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <TopoMaker dil="tr" musteriId={7} />
      </QueryClientProvider>,
    )
    await screen.findByText("Test Müşteri")
    fireEvent.change(container.querySelector("input[type=file]") as HTMLInputElement, { target: { files: [new File(["x"], "a.xlsx")] } })
    fireEvent.click(screen.getByRole("button", { name: /Analizi Başlat/ }))
    expect(await screen.findByText("Lokasyon kolonu bulunamadı.")).toBeInTheDocument()
  })
})
