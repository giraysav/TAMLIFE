import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { KriterTablosu, SiralamaSatiri, SkorAgaci, SkorMeta } from "@/yonetim/api"
import { ym } from "@/yonetim/metin"
import YonetimSayfasi from "@/yonetim/yonetim-sayfasi"
import { Kriterler, normal, turCoz, xHucresi } from "@/yonetim/utilizasyon/kriterler"
import { UtilOzet } from "@/yonetim/utilizasyon/ozet"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function sarmala(cocuk: ReactNode) {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={istemci}>{cocuk}</QueryClientProvider>)
}

type Cagri = { yol: string; yontem: string; govde: unknown }

/** fetch'i yola gore cevaplar ({yol parcasi: data}); cagrilarin yontem ve govdesini kaydeder. */
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

const META: SkorMeta = {
  kaynak_adlari: { auto_sozlesme: "Ürün-Tutar · fatura bedeli (TL)", auto_segment: "Müşteri kartı · segment", auto_kaynaksiz: "Kaynak yok (başlıktan anlaşılamadı)" },
  tur_ipuclari: [["servis cesit", "servis_cesitliligi"], ["sikayet", "auto_onedesk"], ["segment", "auto_segment"], ["sozlesme", "auto_sozlesme"], ["rapor", "auto_rapor"]],
  varsayilan_kurallar: { auto_sozlesme: { b30: "1-49.999", b100: "1.000.000+" } },
  servis_puanlari: { Cloud: 10, Data: 8 },
  metrikler: { auto_onedesk: "sikayet_talep", auto_segment: "segment", auto_sozlesme: "fatura_bedeli", auto_rapor: "rapor_sayisi", servis_cesitliligi: "servisler" },
  sabit_puan_turleri: ["auto_sozlesme", "auto_rapor"],
  islemler: { say: "SAY", topla: "TOPLA" },
  islecler: { esit: "=" },
  degersiz_islecler: ["dolu", "bos"],
  eslesme_alanlari: { customer_no: "Müşteri No" },
  tur_islemleri: { auto_sozlesme: ["topla"], auto_segment: ["ilk"] },
  partiler: [],
}

const TABLO: KriterTablosu = {
  scope: "parent",
  version: 3,
  varsayilan: false,
  updated_by: "admin",
  updated_at: "2026-10-10T09:00:00Z",
  criteria: [
    { title: "6. Sözleşme", type: "auto_sozlesme", weight: 20, b30: "1-49.999", b50: "", b70: "", b100: "1.000.000+" },
    { title: "5. Segment", type: "auto_segment", weight: 15, b50: "SMB", b70: "MA", b100: "" },
  ],
}

describe("TAM Utilizasyon", () => {
  it("tur basliktan cozulur; X yalniz Sozlesme / Raporlama satirinda ve tek hucrede gecerli (sunucu kuraliyla ayni)", () => {
    expect(normal("  İŞLEM   Çağrı ")).toBe("islem cagri")
    expect(turCoz({ title: "6. Sözleşme", weight: 20 }, META)).toBe("auto_sozlesme")
    expect(turCoz({ title: "Bilinmeyen", weight: 1 }, META)).toBe("auto_kaynaksiz")
    expect(turCoz({ title: "Aylık takip", type: "auto_rapor", weight: 1 }, META)).toBe("auto_rapor")
    expect(xHucresi({ title: "Sözleşme", weight: 1, b70: "x" }, "auto_sozlesme", META)).toBe("b70")
    expect(xHucresi({ title: "Sözleşme", weight: 1, b30: "X", b70: "x" }, "auto_sozlesme", META)).toBeNull()
    expect(xHucresi({ title: "Segment", weight: 1, b100: "X" }, "auto_segment", META)).toBeNull()
  })

  it("kriter tablosu: X yazilinca diger hucreler kilitlenir; kaydet tum satirlari sunucuya gonderir", async () => {
    const u = ym("tr").util
    const cagrilar = sahteSunucu({ "/api/v1/skor/kriterler/parent": TABLO, "/api/v1/skor/meta": META })
    sarmala(<Kriterler dil="tr" />)
    const b70 = await screen.findByLabelText("6. Sözleşme 70")
    fireEvent.change(b70, { target: { value: "x" } })
    expect(b70).toHaveValue("X")
    expect(screen.getByLabelText("6. Sözleşme 30")).toBeDisabled()
    expect(screen.getByLabelText("6. Sözleşme 100")).toBeDisabled()
    expect(screen.getByLabelText("5. Segment 50")).not.toBeDisabled()
    expect(screen.getByText(u.kaydedilmedi)).toBeInTheDocument()
    expect(screen.getByText(u.toplamAgirlik(35))).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText("5. Segment 100"), { target: { value: "x" } })
    expect(screen.getByLabelText("5. Segment 100")).toHaveValue("x") // segment satirinda X sabit puan degil
    fireEvent.click(screen.getByRole("button", { name: /Kaydet/ }))
    expect(await screen.findByText(u.kaydedildi(3))).toBeInTheDocument()
    const put = cagrilar.find((c) => c.yontem === "PUT")
    expect(put?.yol).toContain("/api/v1/skor/kriterler/parent")
    const govde = put?.govde as { criteria: { title: string; b70?: string; weight: number }[] }
    expect(govde.criteria.map((k) => [k.title, k.b70, k.weight])).toEqual([
      ["6. Sözleşme", "X", 20],
      ["5. Segment", "MA", 15],
    ])
  })

  it("ozet: siralama, personel agirlik tablosu ve veri kaynaklari cizilir", async () => {
    const u = ym("tr").util
    const agac: SkorAgaci = {
      kaynaklar: [
        { ad: "Panel (kart + aylık rapor)", metrikler: ["sikayet_talep"], hazir: true, neden: "" },
        { ad: "ReportDB", metrikler: ["sikayet_talep"], hazir: false, neden: "ReportDB: bağlantı tanımlı değil" },
      ],
      kriterler: [],
      uyarilar: ["ornek uyari"],
      personel: [],
      atanmamis: [],
      tum_personel: [],
      ozet: { toplam: 3, cati: 3, hazir: 1, istirak: 1, istirak_dahil: 0 },
      dagilim: {
        satirlar: [{ id: 2, ad: "ORNEK TAM Bir", sira: 1, musteri_sayisi: 2, istirakli_musteri: 1, skorlu_musteri: 1, toplam_puan: 80, agirlik_puani: 40, hedef_fark: 20, dengeleme_musteri: 0.5 }],
        ozet: { tam_sayisi: 2, musteri_sayisi: 3, toplam_puan: 120, hedef_agirlik: 60, ortalama_musteri_puani: 40, skorlu_musteri: 2 },
      },
    }
    const siralama: SiralamaSatiri[] = [{ id: 2, full_name: "ORNEK TAM Bir", customer_count: 2, avg_score: 80, rank: 1, bar_pct: 100 }]
    sahteSunucu({ "/api/v1/skor/agac": agac, "/api/v1/skor/siralama": siralama })
    sarmala(<UtilOzet dil="tr" />)
    expect(await screen.findByText("1/3")).toBeInTheDocument()
    expect(screen.getByText(u.hedefAlt(2, 40))).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(u.musteriAdet(2), { exact: false })).toBeInTheDocument())
    expect(screen.getAllByText("ORNEK TAM Bir").length).toBeGreaterThan(0)
    expect(screen.getByText("+20")).toBeInTheDocument()
    expect(screen.getByText("ReportDB: bağlantı tanımlı değil")).toBeInTheDocument()
    expect(screen.getByText(/ornek uyari/)).toBeInTheDocument()
  })

  it("Yonetim sekmeleri: TAM Utilizasyon, Genel Durum ile Veri Girisi arasinda", () => {
    sahteSunucu({})
    sarmala(<YonetimSayfasi dil="tr" bolum="durum" digerleri={[]} />)
    const t = ym("tr")
    const nav = screen.getByRole("navigation", { name: t.bolumNav })
    const yollar = Array.from(nav.querySelectorAll("a")).map((a) => a.getAttribute("href"))
    expect(yollar.slice(0, 3)).toEqual(["#/yonetim/durum", "#/yonetim/utilizasyon", "#/yonetim/tampon"])
    expect(t.bolumler.utilizasyon).toBe("TAM Utilizasyon")
    expect(ym("en").util.sekme.atama).toBe("Bulk assignment")
  })
})
