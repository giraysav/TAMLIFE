import { afterEach, describe, expect, it } from "vitest"
import { buyukHarf, buyukHarfIzle } from "@/lib/buyuk-harf"

let birak: (() => void) | null = null
afterEach(() => {
  birak?.()
  birak = null
  document.body.innerHTML = ""
})

const bekle = () => new Promise((r) => setTimeout(r, 0)) // MutationObserver mikro gorevde calisir

describe("buyukHarf", () => {
  it("Turkce ve aksanli harfleri duz buyuk Latin harfe indirir", () => {
    expect(buyukHarf("GİRAY SAV")).toBe("GIRAY SAV")
    expect(buyukHarf("Giray Sav")).toBe("GIRAY SAV")
    expect(buyukHarf("çağrı şık ılık iğne öğün üzüm")).toBe("CAGRI SIK ILIK IGNE OGUN UZUM")
    expect(buyukHarf("ÇAĞRI ŞIK İĞNE ÖĞÜN ÜZÜM Â")).toBe("CAGRI SIK IGNE OGUN UZUM A")
    expect(buyukHarf("Alfa Teknoloji A.Ş. · 1.500,50 ₺ · tac@alfa.com.tr")).toBe("ALFA TEKNOLOJI A.S. · 1.500,50 ₺ · TAC@ALFA.COM.TR")
  })
})

describe("buyukHarfIzle", () => {
  it("var olan ve sonradan gelen metni cevirir; yan menu, giris alani ve korunan oge disarida kalir", async () => {
    document.body.innerHTML = `
      <div data-yan-menu><span id="menu">Müşteri Yönetimi</span><span id="kart">Giray Sav</span></div>
      <main><h2 id="baslik">Müşteri Detayı</h2><input id="girdi" value="Alfa Ş.">
      <textarea id="not">toplantı özeti</textarea><code id="kod" data-harf-koru>şifre-örneği</code></main>`
    birak = buyukHarfIzle(document.body)
    const al = (id: string) => document.getElementById(id)!
    expect(al("baslik").textContent).toBe("MUSTERI DETAYI")
    expect(al("menu").textContent).toBe("Müşteri Yönetimi")
    expect(al("kart").textContent).toBe("Giray Sav")
    expect((al("girdi") as HTMLInputElement).value).toBe("Alfa Ş.")
    expect((al("not") as HTMLTextAreaElement).value).toBe("toplantı özeti")
    expect(al("kod").textContent).toBe("şifre-örneği")

    const yeni = document.createElement("p")
    yeni.innerHTML = "Personel: <b>Ayşe Çelik</b>"
    document.querySelector("main")!.append(yeni)
    al("baslik").firstChild!.nodeValue = "İştirak listesi" // React'in metin dugumunu guncellemesi
    await bekle()
    expect(yeni.textContent).toBe("PERSONEL: AYSE CELIK")
    expect(al("baslik").textContent).toBe("ISTIRAK LISTESI")
  })

  it("birakilinca yeni metne dokunmaz", async () => {
    document.body.innerHTML = "<main id='m'></main>"
    buyukHarfIzle(document.body)()
    document.getElementById("m")!.textContent = "Giray Sav"
    await bekle()
    expect(document.getElementById("m")!.textContent).toBe("Giray Sav")
  })
})
