import { describe, expect, it } from "vitest"
import { halkalar, KART, MASKOT, TASARIM_Y, YARICAP, YATAY } from "@/components/ui/modul-yayi"

/** Tasarim olcusunde (olcek 1) kart merkezleri; sahne alt orta noktasi (0, 0), yukari eksi y. Olcek tum olculeri orantili degistirir. */
function merkezler(adet: number) {
  const { disAci, icAci } = halkalar(adet)
  const nokta = (r: number, aci: number) => ({ x: YATAY * r * Math.cos((aci * Math.PI) / 180), y: -r * Math.sin((aci * Math.PI) / 180) })
  return [...disAci.map((a) => nokta(YARICAP.dis, a)), ...icAci.map((a) => nokta(YARICAP.ic, a))]
}

describe("ModulYayi dizilimi", () => {
  it.each(Array.from({ length: 12 }, (_, i) => i + 1))("%i kartta hicbir kart digerine binmez ve adet korunur", (adet) => {
    const m = merkezler(adet)
    expect(m).toHaveLength(adet)
    for (let i = 0; i < m.length; i++) {
      for (let j = i + 1; j < m.length; j++) {
        const bosX = Math.abs(m[i]!.x - m[j]!.x) - KART.g
        const bosY = Math.abs(m[i]!.y - m[j]!.y) - KART.y
        expect(bosX >= 6 || bosY >= 6, `${i}. ve ${j}. kart cakisiyor (bosluk ${bosX.toFixed(0)} x ${bosY.toFixed(0)})`).toBe(true)
      }
    }
  })

  it.each(Array.from({ length: 12 }, (_, i) => i + 1))("%i kartta kartlar sahne icinde kalir ve Teknocan kutusuna girmez", (adet) => {
    for (const [i, m] of merkezler(adet).entries()) {
      expect(m.y - KART.y / 2, `${i}. kart sahnenin ustunden tasiyor`).toBeGreaterThanOrEqual(-TASARIM_Y)
      expect(m.y + KART.y / 2, `${i}. kart sahnenin altindan tasiyor`).toBeLessThanOrEqual(0)
      const bosX = Math.abs(m.x) - KART.g / 2 - MASKOT.g / 2
      const bosY = -MASKOT.y - (m.y + KART.y / 2)
      expect(bosX >= 6 || bosY >= 6, `${i}. kart Teknocan kutusuna giriyor (bosluk ${bosX.toFixed(0)} x ${bosY.toFixed(0)})`).toBe(true)
    }
  })
})
