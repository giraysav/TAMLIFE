import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { EkipOzeti } from "@/ekip/ekip-ozeti"
import type { EkipOzetVeri, EkipSatiri } from "@/ekip/ekip-ozeti"
import { ekipMetin } from "@/ekip/ekip-metin"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const SATIR: EkipSatiri = {
  id: 1,
  ad: "Ayşe Yılmaz",
  bugun: "yillik_izin",
  bugun_ad: "Yıllık İzin",
  musteri: 2,
  rapor_atilan: 1,
  rapor_beklenen: 3,
  uyum: 33,
  risk: 20,
  puanlama_disi: false,
  final_skor: 80,
  agirlik_puani: 40.5,
  online: 2,
  yuzyuze: 1,
  proje_acik: 2,
  onemli_isler: [{ id: 9, baslik: "SD-WAN geçişi", oncelik: "kritik", hedef: "2026-12-31" }],
  cumle: "Ayşe Yılmaz, bugün yıllık izin.",
}

function ciz(veri: EkipOzetVeri, onGit = vi.fn()) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ status: "success", data: veri }), { status: 200, headers: { "Content-Type": "application/json" } })),
  )
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={istemci}>
      <EkipOzeti dil="tr" onGit={onGit} />
    </QueryClientProvider>,
  )
  return onGit
}

const TEMEL = {
  tarih: "2026-10-11",
  risk_var: true,
  esikler: { kritik_uyum: 50, yuksek_risk: 16 },
}

describe("Genel Bakis > Ekip Ozeti", () => {
  it("yonetici: sayilar, ekip cumlesi, satir; ayrinti kisinin ozetini ve onemli projeleri acar", async () => {
    const t = ekipMetin("tr")
    const onGit = ciz({
      ...TEMEL,
      kapsam: "ekip",
      cumle: "1 TAM yüksek risk yükü taşıyor.",
      sayilar: { kisi: 2, kritik_uyum: 1, yuksek_risk: 1, acik_proje: 2, bugun_izinli: 1 },
      satirlar: [SATIR, { ...SATIR, id: 2, ad: "Mehmet", bugun: null, puanlama_disi: true, final_skor: null, agirlik_puani: null, rapor_beklenen: 0, onemli_isler: [], cumle: "Mehmet: kayıt yok." }],
    })
    expect(await screen.findByText("1 TAM yüksek risk yükü taşıyor.")).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: t.baslik })).toBeInTheDocument()
    expect(screen.getByText(t.bugunIzinli(1))).toBeInTheDocument()
    expect(screen.getByText("%33")).toBeInTheDocument()
    expect(screen.getByText("40,5")).toBeInTheDocument()
    expect(screen.getByText(t.puanlamaDisi)).toBeInTheDocument()
    expect(screen.getByText(t.kayitYok)).toBeInTheDocument()
    expect(screen.queryByText(SATIR.cumle)).not.toBeInTheDocument()
    fireEvent.click(screen.getAllByRole("button", { name: t.ayrinti })[0])
    expect(screen.getByText(SATIR.cumle)).toBeInTheDocument()
    expect(screen.getByText("SD-WAN geçişi")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: t.projelereGit }))
    expect(onGit).toHaveBeenCalledWith("proje")
  })

  it("TAM yalniz kendini gorur: sayi kutulari ve ayrinti dugmesi yok, ozet cumlesi dogrudan", async () => {
    const t = ekipMetin("tr")
    ciz({ ...TEMEL, kapsam: "kendi", risk_var: false, cumle: null, sayilar: { kisi: 1, kritik_uyum: 1, yuksek_risk: 0, acik_proje: 2, bugun_izinli: 1 }, satirlar: [SATIR] })
    expect(await screen.findByText(SATIR.cumle)).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: t.baslikKendi })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: t.ayrinti })).not.toBeInTheDocument()
    expect(screen.queryByText(t.kritikUyum)).not.toBeInTheDocument()
    expect(screen.getByTitle(t.riskVeriYok)).toBeInTheDocument()
  })
})
