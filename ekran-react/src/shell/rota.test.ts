import { describe, expect, it } from "vitest"
import { aktifSayfa } from "@/shell/rota"

describe("aktifSayfa", () => {
  const izinli = new Set(["ozet", "musteri", "yonetim", "yonetim/durum"])

  it("menudeki sayfa acilir, olmayan genel bakisa doner", () => {
    expect(aktifSayfa("musteri", izinli, false)).toBe("musteri")
    expect(aktifSayfa("radar", izinli, false)).toBe("ozet")
  })

  it("admin: sunucu listesinde olmayan Yonetim bolumu (orn. eski API'de kurum) ana sayfaya atmaz", () => {
    expect(aktifSayfa("yonetim/kurum", izinli, true)).toBe("yonetim/kurum")
    expect(aktifSayfa("yonetim/kurum", izinli, false)).toBe("ozet")
    expect(aktifSayfa("yonetimx", izinli, true)).toBe("ozet")
  })
})
