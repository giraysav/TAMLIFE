import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { EkipOzeti } from "@/ekip/ekip-ozeti"
import type { EkipOzetVeri, EkipSatiri, ModulKutusu } from "@/ekip/ekip-ozeti"
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
  risk_puani: 16,
  risk_orani: 0.5,
  riskli_utilizasyon: 60.8,
  puanlama_disi: false,
  final_skor: 80,
  agirlik_puani: 40.5,
  online: 2,
  yuzyuze: 1,
  proje_acik: 2,
  onemli_isler: [{ id: 9, baslik: "SD-WAN geçişi", oncelik: "kritik", hedef: "2026-12-31" }],
  cumle: "Ayşe Yılmaz, bugün yıllık izin.",
}

function ciz(veri: EkipOzetVeri, onGit?: (id: string) => void) {
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
}

const TEMEL = {
  tarih: "2026-10-11",
  risk_var: true,
  esikler: { kritik_uyum: 50, yuksek_risk: 16 },
}

const MODULLER: ModulKutusu[] = [
  { id: "musteri", ad: "Müşteri Yönetimi", ikon: "customers", deger: 3, alt: "çatı · 2 iştirak", ton: "mavi" },
  { id: "rapor", ad: "Gönderilen Aylık Rapor", ikon: "file", deger: "1/3", alt: "dönem raporu · %33 uyum", ton: "mavi" },
  { id: "radar", ad: "Müşteri Radar", ikon: "radar", deger: null, alt: "ReportDB verisi henüz yok", ton: "mavi" },
]

describe("Genel Bakis > Ekip Ozeti", () => {
  it("yonetici: ekip karolari + menudeki her modulun karosu, tablo ve kisi ayrintisi yok", async () => {
    const t = ekipMetin("tr")
    const git = vi.fn()
    ciz(
      {
        ...TEMEL,
        kapsam: "ekip",
        cumle: "1 TAM yüksek risk yükü taşıyor.",
        sayilar: { kisi: 2, kritik_uyum: 1, yuksek_risk: 1, acik_proje: 2 },
        satirlar: [SATIR, { ...SATIR, id: 2, ad: "Mehmet", bugun: null, puanlama_disi: true, final_skor: null, agirlik_puani: null, riskli_utilizasyon: null, rapor_atilan: 0, rapor_beklenen: 0, onemli_isler: [], cumle: "Mehmet: kayıt yok." }],
        moduller: MODULLER,
      },
      git,
    )
    expect(await screen.findByText("1 TAM yüksek risk yükü taşıyor.")).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: t.baslik })).toBeInTheDocument()
    expect(screen.getAllByRole("listitem")).toHaveLength(2 + MODULLER.length)
    expect(screen.getByText("60,8")).toBeInTheDocument() // riskli utilizasyon = 40,5 x (1 + 0,5)
    expect(screen.getByText(t.skorRiskAlt("40,5", 50, 40))).toBeInTheDocument()
    expect(screen.getByText("1/3")).toBeInTheDocument()
    expect(screen.getByText("—")).toBeInTheDocument() // veri yok: uydurma sayi yok
    fireEvent.click(screen.getByRole("button", { name: /Müşteri Yönetimi/ }))
    expect(git).toHaveBeenCalledWith("musteri")
    expect(screen.getAllByRole("button")).toHaveLength(MODULLER.length) // ekip karolari tiklanmaz
    expect(screen.queryByText("Bugün izinli")).toBeNull()
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
    expect(screen.queryByText("Ayşe Yılmaz")).not.toBeInTheDocument()
  })

  it("TAM yalniz kendini gorur: ayni karolar kendi degerleriyle, ozet cumlesi dogrudan", async () => {
    const t = ekipMetin("tr")
    ciz({ ...TEMEL, kapsam: "kendi", risk_var: false, cumle: null, sayilar: { kisi: 1, kritik_uyum: 1, yuksek_risk: 0, acik_proje: 2 }, satirlar: [SATIR] })
    expect(await screen.findByText(SATIR.cumle)).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: t.baslikKendi })).toBeInTheDocument()
    expect(screen.getByText("Ayşe Yılmaz")).toBeInTheDocument()
    expect(screen.getByText(t.riskVeriYok)).toBeInTheDocument()
    expect(screen.getByText("40,5")).toBeInTheDocument() // risk verisi yokken yalniz utilizasyon
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
  })
})
