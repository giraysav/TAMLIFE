import { describe, expect, it } from "vitest"
import { adaGoreSirala } from "@/lib/bicim"

describe("adaGoreSirala", () => {
  it("musteri ve personel adlarini Turkce alfabe duzeninde siralar ve kaynak diziyi degistirmez", () => {
    const kaynak = [{ ad: "Zeynep" }, { ad: "İpek" }, { ad: "Çınar" }, { ad: "Cem" }, { ad: "Işık" }, { ad: "Ayşe" }]

    expect(adaGoreSirala(kaynak, (k) => k.ad).map((k) => k.ad)).toEqual(["Ayşe", "Cem", "Çınar", "Işık", "İpek", "Zeynep"])
    expect(kaynak.map((k) => k.ad)).toEqual(["Zeynep", "İpek", "Çınar", "Cem", "Işık", "Ayşe"])
  })
})
