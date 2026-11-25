import { describe, expect, it } from "vitest"
import { ILK_YIL, varsayilanYil, yilSecenekleri } from "@/lib/yillar"

describe("yil secenekleri", () => {
  it("2026'dan baslar ve ileri gider; 2024/2025 yok", () => {
    expect(yilSecenekleri(2, new Date(2026, 9, 11))).toEqual([2026, 2027, 2028])
    expect(yilSecenekleri(2, new Date(2027, 0, 5))).toEqual([2026, 2027, 2028, 2029])
    expect(yilSecenekleri(2, new Date(2025, 5, 1))[0]).toBe(ILK_YIL)
    expect(varsayilanYil(new Date(2025, 5, 1))).toBe(2026)
  })
})
