import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { buyukHarfIzle } from "@/lib/buyuk-harf"
import { RaporOnizleme } from "@/musteri/rapor-onizleme"

afterEach(cleanup)

describe("aylik rapor PDF onizlemesi (2026-10-31)", () => {
  it("ekranin BUYUK HARF kuralindan korunur: icerik taslaktaki gibi Turkce harflerle, basliklar Turkce buyuk harfle", () => {
    const birak = buyukHarfIzle()
    try {
      render(
        <RaporOnizleme
          musteriAdi="2N Medya Anonim Şirketi"
          donem="Eylül 2026"
          dil="tr"
          alanlar={{ olumlu: "Bu dönem için ayrıca kayda değer bir olumlu gelişme raporlanmamıştır." }}
          grafikler={[]}
          ekler={[]}
        />,
      )
      expect(screen.getByTestId("rapor-pdf")).toHaveAttribute("data-harf-koru")
      expect(screen.getByText("Bu dönem için ayrıca kayda değer bir olumlu gelişme raporlanmamıştır.")).toBeInTheDocument()
      expect(screen.getByRole("heading", { name: "2N Medya Anonim Şirketi", level: 1 })).toBeInTheDocument()
      expect(screen.getByRole("heading", { name: "OLUMLU GELİŞMELER" })).toBeInTheDocument() // CSS text-transform degil: html2canvas I/İ'yi bozardi
      expect(screen.getByText("TAM AYLIK RAPOR - EYLÜL 2026")).toBeInTheDocument()
    } finally {
      birak()
    }
  })

  it("sayfa sayfa bolumler (2026-11-24): bilgilendirmeler, grafik bolumleri ve oneriler zorunlu sayfa sonuyla (data-pdf-sayfa) baslar", () => {
    const g = (anahtar: string) => ({ anahtar, baslik: anahtar, gorsel: "data:image/png;base64,AA==" })
    render(
      <RaporOnizleme
        musteriAdi="X"
        donem="Ekim 2026"
        dil="tr"
        alanlar={{ bilgi: "Bilgi metni", oneri: "Öneri metni" }}
        grafikler={[g("sla-1"), g("sla-2")]}
        ekler={[g("trafik-1")]}
        loe={[g("devre-1")]}
      />,
    )
    const sayfalar = [...screen.getByTestId("rapor-pdf").querySelectorAll("[data-pdf-sayfa]")]
    expect(sayfalar.map((s) => s.querySelector("h3")?.textContent)).toEqual([
      "BİLGİLENDİRMELER",
      "ALARM, TALEP VE ŞİKAYET",
      "AYLIK TRAFİK KULLANIMI",
      "DEVRE PERFORMANSI",
      "ÖNERİLER",
    ])
    expect(sayfalar[1]?.querySelectorAll("figure")).toHaveLength(2)
    expect(sayfalar[3]?.querySelector("figcaption")).toHaveTextContent("devre-1")
    expect(screen.getByText("Technical Account Manager")).toBeInTheDocument()
    expect(screen.getByText("TURKCELL SUPERONLINE")).toBeInTheDocument()
  })

  it("grafik yoksa grafik bolumleri cizilmez", () => {
    render(<RaporOnizleme musteriAdi="X" donem="Ekim 2026" dil="en" alanlar={{}} grafikler={[]} ekler={[]} />)
    const basliklar = [...screen.getByTestId("rapor-pdf").querySelectorAll("h3")].map((h) => h.textContent)
    expect(basliklar).toEqual(["POSITIVE DEVELOPMENTS", "ONGOING WORK", "CRITICAL ISSUES", "INFORMATION", "SUGGESTIONS"])
  })
})
