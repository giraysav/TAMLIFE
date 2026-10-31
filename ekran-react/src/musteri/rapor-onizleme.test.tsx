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
})
