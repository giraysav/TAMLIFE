import { describe, expect, it } from "vitest"
import { BASLIK_USTU, halkalar, HALKA, KALKIS, KART, LOGO, MASKOT, TASARIM_Y } from "@/components/ui/modul-yayi"

/** Tasarim olcusunde (olcek 1) kart merkezleri; sahne alt orta noktasi (0, 0), yukari eksi y. Olcek tum olculeri orantili degistirir. */
function merkezler(adet: number) {
  const { disAci, icAci } = halkalar(adet)
  const nokta = (h: { rx: number; ry: number }, aci: number) => ({ x: h.rx * Math.cos((aci * Math.PI) / 180), y: -(KALKIS + h.ry * Math.sin((aci * Math.PI) / 180)) })
  return [...disAci.map((a) => nokta(HALKA.dis, a)), ...icAci.map((a) => nokta(HALKA.ic, a))]
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

  it.each(Array.from({ length: 12 }, (_, i) => i + 1))("%i kartta kartlar sahne icinde kalir ve maskot bandina girmez", (adet) => {
    for (const [i, m] of merkezler(adet).entries()) {
      expect(m.y - KART.y / 2, `${i}. kart sahnenin ustunden tasiyor`).toBeGreaterThanOrEqual(-TASARIM_Y)
      expect(-(m.y + KART.y / 2), `${i}. kart gorseldeki baslik yazisini kapatiyor`).toBeGreaterThanOrEqual(BASLIK_USTU)
      const bosX = Math.abs(m.x) - KART.g / 2 - MASKOT.yarim
      expect(bosX, `${i}. kart maskot bandina giriyor (bosluk ${bosX.toFixed(0)})`).toBeGreaterThanOrEqual(6)
    }
  })

  it.each(Array.from({ length: 12 }, (_, i) => i + 1))("%i kartta sol ustteki logo kapanmaz", (adet) => {
    for (const [i, m] of merkezler(adet).entries()) {
      const logoda = 545 + m.x - KART.g / 2 < LOGO.sag && -(m.y - KART.y / 2) > LOGO.alt
      expect(logoda, `${i}. kart gorseldeki logoyu kapatiyor`).toBe(false)
    }
  })

  it("kartlar iki yana esit dagilir: tepe (maskotun ustu) bos kalir", () => {
    const sol = merkezler(12).filter((m) => m.x < 0).length
    expect(sol).toBe(6)
    expect(merkezler(7).filter((m) => m.x < 0).length).toBeGreaterThanOrEqual(3)
  })
})
