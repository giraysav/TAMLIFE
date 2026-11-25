import { describe, expect, it } from "vitest"
import { dilUygula, elleYazilanlar, ozetiYerlestir } from "@/musteri/aylik-rapor"
import { yzBol } from "@/musteri/sla-analizi"

const varsayilanlar = {
  tr: { konu: "TAM Aylık Rapor - Eylül 2026", olumlu: "Olumlu gelişme yok.", oneri: "Öneri yok." },
  en: { konu: "TAM Monthly Report - September 2026", olumlu: "No positive developments.", oneri: "No suggestions." },
}

describe("rapor dili", () => {
  it("hazir ve bos metinleri karsiligiyla degistirir, personelin yazdigina dokunmaz", () => {
    const alanlar = { dil: "tr", konu: varsayilanlar.tr.konu, olumlu: "Yeni hat devreye alındı.", oneri: "" }
    const en = dilUygula(alanlar, varsayilanlar, "en")
    expect(en).toEqual({ dil: "en", konu: varsayilanlar.en.konu, olumlu: "Yeni hat devreye alındı.", oneri: "No suggestions." })
    expect(dilUygula(en, varsayilanlar, "tr")).toEqual({ dil: "tr", konu: varsayilanlar.tr.konu, olumlu: "Yeni hat devreye alındı.", oneri: "Öneri yok." })
    expect(dilUygula(en, varsayilanlar, "en")).toBe(en)
  })
})

describe("ceviri", () => {
  it("yalniz elle yazilmis dolu alanlari cevirir; hazir metin ve dil alani gitmez", () => {
    const alanlar = { dil: "en", konu: varsayilanlar.en.konu, olumlu: "Yeni hat devreye alındı.", oneri: "", kritik: varsayilanlar.tr.olumlu }
    expect(elleYazilanlar(alanlar, varsayilanlar)).toEqual({ olumlu: "Yeni hat devreye alındı.", kritik: varsayilanlar.tr.olumlu })
  })
})

describe("SLA ozeti", () => {
  it("hazir metnin yerine gecer, tekrar basinca cogalmaz, elle yazilanin altina eklenir", () => {
    expect(ozetiYerlestir("Hazır metin", "• A", undefined, ["Hazır metin"])).toBe("• A")
    expect(ozetiYerlestir("• A", "• B", "• A", [])).toBe("• B")
    expect(ozetiYerlestir("Elle yazılan", "• A", undefined, [])).toBe("Elle yazılan\n\n• A")
    expect(ozetiYerlestir("Elle yazılan\n\n• A", "• A", "• A", [])).toBe("Elle yazılan\n\n• A")
  })

  it("YZ yanitini iki basliga ayirir", () => {
    expect(yzBol("Bilgilendirme:\n• 7 kayıt\n\n• 2 CI\n\n**Devam eden çalışmalar:**\n• 4 numaralı kayıt açık")).toEqual({ bilgi: "• 7 kayıt\n\n• 2 CI", devam: "• 4 numaralı kayıt açık" })
    expect(yzBol("• Yalnız bilgi")).toEqual({ bilgi: "• Yalnız bilgi", devam: "" })
    expect(yzBol("Information:\n• x\nOngoing work:\n• y")).toEqual({ bilgi: "• x", devam: "• y" })
  })
})
