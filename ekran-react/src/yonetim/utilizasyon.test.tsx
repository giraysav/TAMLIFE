import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { KriterTablosu, SiralamaSatiri, SkorAgaci, SkorMeta, SkorOnizleme } from "@/yonetim/api"
import { uym } from "@/yonetim/utilizasyon/metin"
import YonetimSayfasi from "@/yonetim/yonetim-sayfasi"
import { TopluAtama } from "@/yonetim/utilizasyon/atama"
import { Kriterler, normal, turCoz, xHucresi } from "@/yonetim/utilizasyon/kriterler"
import { UtilOzet } from "@/yonetim/utilizasyon/ozet"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function sarmala(cocuk: ReactNode) {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={istemci}>{cocuk}</QueryClientProvider>)
}

type Cagri = { yol: string; yontem: string; govde: unknown }

/** fetch'i yola gore cevaplar ({yol parcasi: data}); cagrilarin yontem ve govdesini kaydeder. */
function sahteSunucu(cevaplar: Record<string, unknown>): Cagri[] {
  const cagrilar: Cagri[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn(async (girdi: string, ayar?: RequestInit) => {
      cagrilar.push({ yol: String(girdi), yontem: ayar?.method ?? "GET", govde: typeof ayar?.body === "string" ? JSON.parse(ayar.body) : null })
      const anahtar = Object.keys(cevaplar).find((k) => String(girdi).includes(k))
      return anahtar === undefined
        ? new Response(JSON.stringify({ detail: "yok" }), { status: 404, headers: { "Content-Type": "application/json" } })
        : new Response(JSON.stringify({ status: "success", data: cevaplar[anahtar] }), { status: 200, headers: { "Content-Type": "application/json" } })
    }),
  )
  return cagrilar
}

const META: SkorMeta = {
  kaynak_adlari: { auto_sozlesme: "Ürün-Tutar · fatura bedeli (TL)", auto_segment: "Müşteri kartı · segment", auto_kaynaksiz: "Kaynak yok (başlıktan anlaşılamadı)" },
  tur_ipuclari: [["servis cesit", "servis_cesitliligi"], ["sikayet", "auto_onedesk"], ["segment", "auto_segment"], ["sozlesme", "auto_sozlesme"], ["rapor", "auto_rapor"]],
  varsayilan_kurallar: { auto_sozlesme: { b30: "1-49.999", b100: "1.000.000+" } },
  servis_puanlari: { Cloud: 10, Data: 8 },
  metrikler: { auto_onedesk: "sikayet_talep", auto_segment: "segment", auto_sozlesme: "fatura_bedeli", auto_rapor: "rapor_sayisi", servis_cesitliligi: "servisler" },
  sabit_puan_turleri: ["auto_sozlesme", "auto_rapor"],
  islemler: { say: "SAY", topla: "TOPLA" },
  islecler: { esit: "=" },
  degersiz_islecler: ["dolu", "bos"],
  eslesme_alanlari: { customer_no: "Müşteri No" },
  tur_islemleri: { auto_sozlesme: ["topla"], auto_segment: ["ilk"] },
  partiler: [],
}

const TABLO: KriterTablosu = {
  scope: "parent",
  version: 3,
  varsayilan: false,
  updated_by: "admin",
  updated_at: "2026-10-10T09:00:00Z",
  criteria: [
    { title: "6. Sözleşme", type: "auto_sozlesme", weight: 20, b30: "1-49.999", b50: "", b70: "", b100: "1.000.000+" },
    { title: "5. Segment", type: "auto_segment", weight: 15, b50: "SMB", b70: "MA", b100: "" },
  ],
}

describe("TAM Utilizasyon", () => {
  it("tur basliktan cozulur; X yalniz Sozlesme / Raporlama satirinda ve tek hucrede gecerli (sunucu kuraliyla ayni)", () => {
    expect(normal("  İŞLEM   Çağrı ")).toBe("islem cagri")
    expect(turCoz({ title: "6. Sözleşme", weight: 20 }, META)).toBe("auto_sozlesme")
    expect(turCoz({ title: "Bilinmeyen", weight: 1 }, META)).toBe("auto_kaynaksiz")
    expect(turCoz({ title: "Aylık takip", type: "auto_rapor", weight: 1 }, META)).toBe("auto_rapor")
    expect(xHucresi({ title: "Sözleşme", weight: 1, b70: "x" }, "auto_sozlesme", META)).toBe("b70")
    expect(xHucresi({ title: "Sözleşme", weight: 1, b30: "X", b70: "x" }, "auto_sozlesme", META)).toBeNull()
    expect(xHucresi({ title: "Segment", weight: 1, b100: "X" }, "auto_segment", META)).toBeNull()
  })

  it("kriter tablosu: X yazilinca diger hucreler kilitlenir; kaydet tum satirlari sunucuya gonderir", async () => {
    const u = uym("tr").util
    const cagrilar = sahteSunucu({ "/api/v1/skor/kriterler/parent": TABLO, "/api/v1/skor/meta": META })
    sarmala(<Kriterler dil="tr" />)
    const b70 = await screen.findByLabelText("6. Sözleşme 70")
    fireEvent.change(b70, { target: { value: "x" } })
    expect(b70).toHaveValue("X")
    expect(screen.getByLabelText("6. Sözleşme 30")).toBeDisabled()
    expect(screen.getByLabelText("6. Sözleşme 100")).toBeDisabled()
    expect(screen.getByLabelText("5. Segment 50")).not.toBeDisabled()
    expect(screen.getByText(u.kaydedilmedi)).toBeInTheDocument()
    expect(screen.getByText(u.toplamAgirlik(35))).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText("5. Segment 100"), { target: { value: "x" } })
    expect(screen.getByLabelText("5. Segment 100")).toHaveValue("x") // segment satirinda X sabit puan degil
    fireEvent.click(screen.getByRole("button", { name: /Kaydet/ }))
    expect(await screen.findByText(u.kaydedildi(3))).toBeInTheDocument()
    const put = cagrilar.find((c) => c.yontem === "PUT")
    expect(put?.yol).toContain("/api/v1/skor/kriterler/parent")
    const govde = put?.govde as { criteria: { title: string; b70?: string; weight: number }[] }
    expect(govde.criteria.map((k) => [k.title, k.b70, k.weight])).toEqual([
      ["6. Sözleşme", "X", 20],
      ["5. Segment", "MA", 15],
    ])
  })

  it("ozet: siralama, personel agirlik tablosu (ortalama final skor) ve veri kaynaklari cizilir", async () => {
    const u = uym("tr").util
    const agac: SkorAgaci = {
      kaynaklar: [
        { ad: "Panel (kart + aylık rapor)", metrikler: ["sikayet_talep"], hazir: true, neden: "" },
        { ad: "ReportDB", metrikler: ["sikayet_talep"], hazir: false, neden: "ReportDB: bağlantı tanımlı değil" },
      ],
      kriterler: [],
      uyarilar: ["ornek uyari"],
      personel: [],
      atanmamis: [],
      tum_personel: [],
      ozet: { toplam: 3, cati: 3, hazir: 1, istirak: 1, istirak_dahil: 0 },
      dagilim: {
        satirlar: [{ id: 2, ad: "ORNEK TAM Bir", sira: 1, musteri_sayisi: 2, istirakli_musteri: 1, skorlu_musteri: 1, toplam_puan: 80, agirlik_puani: 40, hedef_fark: 20, dengeleme_musteri: 0.5 }],
        ozet: { tam_sayisi: 2, musteri_sayisi: 3, toplam_puan: 120, hedef_agirlik: 60, ortalama_musteri_puani: 40, skorlu_musteri: 2 },
      },
    }
    const siralama: SiralamaSatiri[] = [{ id: 2, full_name: "ORNEK TAM Bir", customer_count: 2, avg_score: 80, rank: 1, bar_pct: 100 }]
    sahteSunucu({ "/api/v1/skor/agac": agac, "/api/v1/skor/siralama": siralama })
    sarmala(<UtilOzet dil="tr" />)
    expect(await screen.findByText("1/3")).toBeInTheDocument()
    expect(screen.getByText(u.hedefAlt(2, 40))).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(u.musteriAdet(2), { exact: false })).toBeInTheDocument())
    expect(screen.getAllByText("ORNEK TAM Bir").length).toBeGreaterThan(0)
    expect(screen.queryByText("+20")).toBeNull() // hedef farki / dengeleme / toplam puan kolonlari kalkti (2026-11-21)
    expect(screen.queryByText(u.hedefFarki)).toBeNull()
    expect(screen.getByText("ReportDB: bağlantı tanımlı değil")).toBeInTheDocument()
    expect(screen.getByText(/ornek uyari/)).toBeInTheDocument()
  })

  it("alt sekmeler: Ozet, Kriterler, Puanlama; eski sekme adresi Puanlama'ya acilir, puanlama public/util-puanlama.js ile kurulur (2026-11-21)", async () => {
    sahteSunucu({})
    const kur = vi.fn((kok: HTMLElement) => {
      kok.textContent = "PUANLAMA BETIGI"
    })
    const kaldir = vi.fn()
    window.TamlifeUtilPuanlama = { kur, kaldir }
    window.location.hash = "#/yonetim/utilizasyon?sekme=iptal"
    const { default: Utilizasyon } = await import("@/yonetim/bolumler/utilizasyon")
    const { unmount } = sarmala(<Utilizasyon dil="tr" />)
    const t = uym("tr").util
    const s = t.sekme
    expect(screen.getAllByRole("tab").map((x) => x.textContent)).toEqual([s.ozet, s.kriterler, s.puanlama])
    expect(screen.getByRole("tab", { name: s.puanlama })).toHaveAttribute("aria-selected", "true")
    expect(screen.getByText("PUANLAMA BETIGI")).toBeInTheDocument()
    expect(kur).toHaveBeenCalledWith(expect.any(HTMLElement), { dil: "tr" })
    expect(screen.getByText(t.musteriEkleSil).tagName).toBe("SUMMARY")
    unmount()
    expect(kaldir).toHaveBeenCalledTimes(1)
    delete window.TamlifeUtilPuanlama
    window.location.hash = ""
  })

  it("Puanlama: betik yuklenmemisse alanda uyari metni kalir", async () => {
    sahteSunucu({})
    window.location.hash = "#/yonetim/utilizasyon?sekme=puanlama"
    const { default: Utilizasyon } = await import("@/yonetim/bolumler/utilizasyon")
    sarmala(<Utilizasyon dil="en" />)
    expect(screen.getByText(uym("en").disBilesenYuklenemedi)).toBeInTheDocument()
    window.location.hash = ""
  })

  it("Yonetim sekmeleri: Veri Kaynaklari (Veri Girisi dahil) ve Kayitlar (Gunlukler dahil) birlesik; eski adres birlesik bolume acilir", () => {
    sahteSunucu({})
    sarmala(<YonetimSayfasi dil="tr" bolum="gunlukler" digerleri={[]} />)
    const t = uym("tr")
    const nav = screen.getByRole("navigation", { name: t.bolumNav })
    const yollar = Array.from(nav.querySelectorAll("a")).map((a) => a.getAttribute("href"))
    expect(yollar).toEqual([
      "#/yonetim/durum",
      "#/yonetim/utilizasyon",
      "#/yonetim/veri",
      "#/yonetim/kurum",
      "#/yonetim/veritabani",
      "#/yonetim/roller",
      "#/yonetim/arizalar",
    ])
    expect(screen.getByRole("link", { name: t.bolumler.arizalar })).toHaveAttribute("aria-current", "page")
    expect(t.bolumler.utilizasyon).toBe("TAM Utilizasyon")
    expect(uym("en").bolumler.arizalar).toBe("Records")
  })

  it("Yonetim: izinli bolum listesi verilirse (admin olmayan) yalniz o bolumler; izinsiz adres ilk izinliye acilir", () => {
    sahteSunucu({})
    sarmala(<YonetimSayfasi dil="tr" bolum="kurum" digerleri={[]} izinli={["utilizasyon"]} />)
    const t = uym("tr")
    const nav = screen.getByRole("navigation", { name: t.bolumNav })
    expect(Array.from(nav.querySelectorAll("a")).map((a) => a.getAttribute("href"))).toEqual(["#/yonetim/utilizasyon"])
    expect(screen.getByRole("heading", { name: t.bolumler.utilizasyon })).toBeInTheDocument()
  })

  it("kriter metin hucreleri yazdikca uzayan cok satirli alan (textarea); Enter yeni satir acmaz", async () => {
    sahteSunucu({ "/api/v1/skor/kriterler/parent": TABLO, "/api/v1/skor/meta": META })
    sarmala(<Kriterler dil="tr" />)
    const b30 = await screen.findByLabelText("6. Sözleşme 30")
    expect(b30.tagName).toBe("TEXTAREA")
    fireEvent.change(b30, { target: { value: "1-\n49.999" } })
    expect(b30).toHaveValue("1- 49.999")
    expect(screen.getAllByLabelText(uym("tr").util.metrik)[0].tagName).toBe("TEXTAREA")
  })

  it("toplu atama: satir kutusu tiklaninca secilir / birakilir (eksik kriterli musteri de); uygula secilenleri gonderir", async () => {
    const u = uym("tr").util
    const musteri = (id: number, ad: string, tamam: boolean) => ({
      id, ad, tam: "ORNEK TAM", tam_id: 2, mevcut: null, yeni: 40, fark: null, tamam, eksik: tamam ? [] : ["6. Sözleşme"], kriterler: [], son_atama: null,
    })
    const onizleme: SkorOnizleme = { kaynaklar: [], uyarilar: [], kriterler: [], musteriler: [musteri(1, "ORNEK A", true), musteri(2, "ORNEK B", false)], ozet: { toplam: 2, hazir: 1 } }
    const cagrilar = sahteSunucu({
      "/api/v1/skor/toplu/onizleme": onizleme,
      "/api/v1/skor/toplu/uygula": { uygulanan: [], atlanan: [{ id: 2, ad: "ORNEK B", neden: "eksik kriter: 6. Sözleşme" }], degismeyen: 0 },
      "/api/v1/skor/agac": { tum_personel: [] },
    })
    vi.stubGlobal("confirm", () => true)
    sarmala(<TopluAtama dil="tr" />)
    const kutu = (await screen.findByLabelText(u.secMusteri("ORNEK B"))) as HTMLInputElement
    expect(kutu).not.toBeDisabled()
    fireEvent.click(kutu)
    expect(kutu).toBeChecked()
    expect(screen.getByRole("button", { name: u.seciliUygula(1) })).not.toBeDisabled()
    fireEvent.click(kutu)
    expect(kutu).not.toBeChecked()
    expect(screen.getByRole("button", { name: u.seciliUygula(0) })).toBeDisabled()
    fireEvent.click(screen.getByLabelText(u.secMusteri("ORNEK A")))
    fireEvent.click(kutu)
    fireEvent.click(screen.getByRole("button", { name: u.seciliUygula(2) }))
    expect(await screen.findByText(/ORNEK B: eksik kriter/)).toBeInTheDocument()
    expect(cagrilar.find((c) => c.yol.includes("/toplu/uygula"))?.govde).toEqual({ customer_ids: [1, 2] })
  })

  it("manuel puanlama: kriter dokumunde her kriter secilir, kaydet secimleri sunucuya gonderir (X sabit satir secilmez)", async () => {
    const u = uym("tr").util
    const secenekler = [{ puan: 50, etiket: "SMB" }, { puan: 70, etiket: "MA" }, { puan: 100, etiket: "SA" }]
    const kriter = (baslik: string, ek: object) => ({ baslik, tur: "auto_segment", agirlik: 50, puan: 0, katki: 0, durum: "eksik" as const, kaynak: null, deger: null, varsayilan_kural: false, ...ek })
    const onizleme: SkorOnizleme = {
      manuel: true,
      kaynaklar: [],
      uyarilar: [],
      kriterler: [],
      musteriler: [
        {
          id: 1, ad: "ORNEK A", tam: "ORNEK TAM", tam_id: 2, mevcut: null, yeni: 25, fark: null, tamam: false, eksik: ["5. Segment"], son_atama: null,
          kriterler: [kriter("5. Segment", { secenekler }), kriter("7. Raporlama", { tur: "auto_rapor", puan: 50, durum: "otomatik", kaynak: "Sabit puan (X işareti)" })],
        },
      ],
      ozet: { toplam: 1, hazir: 0 },
    } // fmt: skip
    const cagrilar = sahteSunucu({
      "/api/v1/skor/toplu/onizleme": onizleme,
      "/api/v1/skor/toplu/manuel/1": { id: 1, ad: "ORNEK A", eski: null, yeni: 85 },
      "/api/v1/skor/agac": { tum_personel: [] },
    })
    sarmala(<TopluAtama dil="tr" />)
    expect(await screen.findByText(u.manuelBilgi)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "ORNEK A" }))
    const kaydet = screen.getByRole("button", { name: u.manuelKaydet })
    expect(kaydet).not.toBeDisabled() // eksik kriterde de kaydedilir (ara skor, 2026-11-21); uyari kalir
    expect(screen.getByText(u.manuelEksik(1))).toBeInTheDocument()
    expect(screen.queryByLabelText(u.puanSecEtiket("7. Raporlama"))).toBeNull()
    fireEvent.change(screen.getByLabelText(u.puanSecEtiket("5. Segment")), { target: { value: "70" } })
    expect(kaydet).not.toBeDisabled()
    fireEvent.click(kaydet)
    expect(await screen.findByText(u.manuelKaydedildi("ORNEK A", "%85.0"))).toBeInTheDocument()
    const put = cagrilar.find((c) => c.yontem === "PUT")
    expect(put?.yol).toContain("/api/v1/skor/toplu/manuel/1")
    expect(put?.govde).toEqual({ secimler: { "5. Segment": 70 } })
  })

  it("servis cesitliligi: satir acilir, alinan servislerin puan toplami bareme gore kriter puani olur; servis puani dokumde degistirilemez", async () => {
    const u = uym("tr").util
    const onizleme: SkorOnizleme = {
      manuel: true,
      kaynaklar: [],
      uyarilar: [],
      kriterler: [],
      musteriler: [
        {
          id: 1, ad: "ORNEK A", tam: "ORNEK TAM", tam_id: 2, mevcut: null, yeni: 0, fark: null, tamam: false, eksik: ["2. Servis Çeşitliliği"], son_atama: null,
          kriterler: [
            {
              baslik: "2. Servis Çeşitliliği", tur: "servis_cesitliligi", agirlik: 20, puan: 0, katki: 0, durum: "eksik", kaynak: null, deger: null, varsayilan_kural: false,
              servisler: [{ ad: "Cloud", puan: 10 }, { ad: "Data", puan: 30 }],
              kurallar: [{ alt: 1, ust: 19, puan: 30 }, { alt: 20, ust: 39, puan: 70 }, { alt: 40, ust: null, puan: 100 }],
            },
          ],
        },
      ],
      ozet: { toplam: 1, hazir: 0 },
    } // fmt: skip
    const cagrilar = sahteSunucu({
      "/api/v1/skor/toplu/onizleme": onizleme,
      "/api/v1/skor/toplu/manuel/1": { id: 1, ad: "ORNEK A", eski: null, yeni: 70 },
      "/api/v1/skor/agac": { tum_personel: [] },
    })
    sarmala(<TopluAtama dil="tr" />)
    fireEvent.click(await screen.findByRole("button", { name: "ORNEK A" }))
    expect(screen.queryByLabelText(u.servisAlinir("Data"))).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "2. Servis Çeşitliliği" }))
    expect(screen.getByText(u.servisOzet("0", "0"))).toBeInTheDocument() // acmak = secim basladi (hic servis yok, baremde yok)
    expect(screen.queryByRole("spinbutton")).toBeNull() // servis puani Kriterler tablosunda degisir
    fireEvent.click(screen.getByLabelText(u.servisAlinir("Data")))
    expect(screen.getByText(u.servisOzet("30", "70"))).toBeInTheDocument()
    expect(screen.getByText("14")).toBeInTheDocument() // katki: 20 x %70
    fireEvent.click(screen.getByLabelText(u.servisAlinir("Cloud")))
    expect(screen.getByText(u.servisOzet("40", "100"))).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText(u.servisAlinir("Cloud")))
    fireEvent.click(screen.getByRole("button", { name: u.manuelKaydet }))
    expect(await screen.findByText(u.manuelKaydedildi("ORNEK A", "%70.0"))).toBeInTheDocument()
    expect(cagrilar.find((c) => c.yontem === "PUT")?.govde).toEqual({ secimler: { "2. Servis Çeşitliliği": ["Data"] } })
  })

  it("sozlesme alt kriterleri: Fatura veriden (Urun-Tutar) otomatik, Kritik Madde / SLA elle; kayitli secimle acilir, puan toplami en fazla 100", async () => {
    const u = uym("tr").util
    const onizleme: SkorOnizleme = {
      manuel: true,
      kaynaklar: [],
      uyarilar: [],
      kriterler: [],
      musteriler: [
        {
          id: 1, ad: "ORNEK A", tam: "ORNEK TAM", tam_id: 2, mevcut: null, yeni: 0, fark: null, tamam: true, eksik: [], son_atama: null,
          kriterler: [
            {
              baslik: "6. Sözleşme", tur: "auto_sozlesme", agirlik: 20, puan: 85, katki: 17, durum: "manuel", kaynak: null, deger: null, varsayilan_kural: false,
              alt_kriterler: [
                { ad: "Fatura", puan: 70, oto: true, saglandi: true, fatura_bedeli: 1500000 },
                { ad: "Kritik Madde", puan: 15, oto: false, saglandi: false },
                { ad: "SLA", puan: 15, oto: false, saglandi: false },
              ],
              secim: ["SLA"],
            },
          ],
        },
      ],
      ozet: { toplam: 1, hazir: 1 },
    } // fmt: skip
    const cagrilar = sahteSunucu({
      "/api/v1/skor/toplu/onizleme": onizleme,
      "/api/v1/skor/toplu/manuel/1": { id: 1, ad: "ORNEK A", eski: null, yeni: 100 },
      "/api/v1/skor/agac": { tum_personel: [] },
    })
    sarmala(<TopluAtama dil="tr" />)
    fireEvent.click(await screen.findByRole("button", { name: "ORNEK A" }))
    fireEvent.click(screen.getByRole("button", { name: "6. Sözleşme" }))
    const fatura = screen.getByLabelText(u.altKriterSaglanir("Fatura"))
    expect(fatura).toBeChecked()
    expect(fatura).toBeDisabled()
    expect(screen.getByText(u.faturaOto((1500000).toLocaleString("tr-TR", { maximumFractionDigits: 0 })))).toBeInTheDocument()
    expect(screen.getByLabelText(u.altKriterSaglanir("SLA"))).toBeChecked() // kayitli secim
    expect(screen.getAllByText("+15")).toHaveLength(2) // ilk alt kriter taban puan, digerleri ek
    expect(screen.getByText(u.sozlesmeNot)).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText(u.altKriterSaglanir("Kritik Madde")))
    expect(screen.getByText("Fatura, Kritik Madde, SLA")).toBeInTheDocument() // deger: saglanan alt kriterler
    expect(screen.getAllByText("20")).toHaveLength(2) // agirlik 20 ve katki: 20 x %100
    fireEvent.click(screen.getByRole("button", { name: u.manuelKaydet }))
    await screen.findByText(u.manuelKaydedildi("ORNEK A", "%100.0"))
    expect(cagrilar.find((c) => c.yontem === "PUT")?.govde).toEqual({ secimler: { "6. Sözleşme": ["SLA", "Kritik Madde"] } })
  })

  it("kriter tablosu: veri kaynagi salt okunur etiket; Servis Cesitliligi servis puani tabloda degisir ve kaydedilir", async () => {
    const u = uym("tr").util
    const tablo: KriterTablosu = { ...TABLO, criteria: [...TABLO.criteria, { title: "2. Servis Çeşitliliği", type: "servis_cesitliligi", weight: 10 }] }
    const cagrilar = sahteSunucu({ "/api/v1/skor/kriterler/parent": tablo, "/api/v1/skor/meta": META })
    sarmala(<Kriterler dil="tr" />)
    const etiket = await screen.findByText(META.kaynak_adlari.auto_segment)
    expect(etiket.tagName).toBe("SPAN")
    expect(etiket).toHaveAttribute("title", u.kaynakSabit)
    fireEvent.click(screen.getByRole("button", { name: `${u.servisler}: ${u.servisTumu}` }))
    expect(screen.getByText(u.servisPuanNot)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(`Cloud ${u.puan}`), { target: { value: "150" } })
    expect(screen.getByLabelText(`Cloud ${u.puan}`)).toHaveValue(100) // 0-100 arasina kirpilir
    fireEvent.click(screen.getByRole("button", { name: /Kaydet/ }))
    await screen.findByText(u.kaydedildi(3))
    const govde = cagrilar.find((c) => c.yontem === "PUT")?.govde as { criteria: { title: string; servis_puanlari?: Record<string, number> }[] }
    expect(govde.criteria[2].servis_puanlari).toEqual({ Cloud: 100, Data: 8 })
  })
})

