import { describe, expect, it } from "vitest"
import { ANA_SAYFA_KARTLARI } from "./home-cards"

describe("ana sayfa kartlari", () => {
  it("12 kart (Toptan ve TAM Ozet kaldirildi) ve prod sirasi", () => {
    expect(ANA_SAYFA_KARTLARI).toHaveLength(12)
    expect(ANA_SAYFA_KARTLARI[0].cardId).toBe("dash-card-takvim")
    expect(ANA_SAYFA_KARTLARI.at(-1)?.cardId).toBe("dash-card-baglantili")
  })
  it("kart kimlikleri benzersiz", () => {
    const ids = ANA_SAYFA_KARTLARI.map((k) => k.cardId)
    expect(new Set(ids).size).toBe(ids.length)
  })
})
