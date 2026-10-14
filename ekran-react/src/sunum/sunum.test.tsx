import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { RollerSayfasi } from "@/shell/roller-sayfasi"
import { SunumSayfasi } from "@/sunum/sunum-sayfasi"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function sarmala(cocuk: ReactNode) {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={istemci}>{cocuk}</QueryClientProvider>)
}

type Cagri = { yol: string; yontem: string; govde: unknown }

/** fetch'i yola gore cevaplar ({yol parcasi: data}, ilk eslesen); cagrilarin yontem ve govdesini kaydeder. */
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

const OZET = { durumlar: { yillik_izin: 2 }, online: 1, yuzyuze: 0, kayitli_gun: 2, izin_gun: 2, toplanti: 1 }
const KAYNAKLAR = {
  duzenleyebilir: true,
  kaynaklar: [
    { id: "takvim", ad: "TAM Takvim özeti", ad_en: "TAM Calendar summary", aciklama: "Kişi bazında izin", aciklama_en: "Leave per person", modul: "TAM Takvim", modul_en: "TAM Calendar", anlik: false, acik: true },
    { id: "portfoy", ad: "Müşteri portföy özeti", ad_en: "Customer portfolio summary", aciklama: "Çatı / iştirak", aciklama_en: "Parent / affiliate", modul: "Müşteri Yönetimi", modul_en: "Customer Management", anlik: true, acik: false, grup: "work" },
  ],
}
const DONEM = {
  yil: 2026,
  ceyrek: 4,
  donem: "2026-Q4",
  zaman: "guncel",
  yonetebilir: true,
  ogeler: [
    { kaynak: "takvim", ad: "TAM Takvim özeti", ad_en: "TAM Calendar summary", anlik: false, durum: "canli", gonderen: "", zaman: "2026-10-10T10:00:00Z", veri: { genel: OZET, uyeler: [{ ad: "Ayse Test", ...OZET }] }, kayit_no: "" },
    {
      kaynak: "rapor",
      ad: "Gönderilen aylık rapor durumu",
      ad_en: "Sent monthly report status",
      anlik: false,
      durum: "kayitli",
      gonderen: "",
      zaman: "2026-10-01T08:00:00Z",
      veri: { kpi: [{ ad: "Ekim · atılan", ad_en: "October · sent", deger: 3, birim: "", alt: "/ 5" }], tablo: { sutunlar: [{ ad: "TAM", ad_en: "TAM", birim: "" }, { ad: "Tutar", ad_en: "Amount", birim: "TRY" }], satirlar: [["Ayse Test", 1500]] } },
      kayit_no: "",
    },
    { kaynak: "onedesk", ad: "Onedesk özeti", ad_en: "Onedesk summary", anlik: false, durum: "hata", gonderen: "", zaman: null, veri: null, kayit_no: "ab12cd34" },
    { kaynak: "portfoy", ad: "Müşteri portföy özeti", ad_en: "Customer portfolio summary", anlik: true, durum: "yok", gonderen: "", zaman: null, veri: null, kayit_no: "" },
  ],
}

describe("Ceyrek Bazli Sunum sayfasi", () => {
  it("kaynak basina kart: canli/donmus rozet, genel KPI + tablo, hata ve kaydi olmayan anlik kaynak", async () => {
    const cagrilar = sahteSunucu({ "/api/v1/sunum/donem": DONEM, "/api/v1/sunum/gonder": { sunumda: null }, "/api/v1/sunum/kaynaklar": KAYNAKLAR })
    sarmala(<SunumSayfasi dil="tr" />)
    expect(await screen.findByRole("heading", { name: "Gönderilen aylık rapor durumu" })).toBeInTheDocument()
    expect(screen.getByText("Canlı")).toBeInTheDocument()
    expect(screen.getByText("Donduruldu")).toBeInTheDocument()
    expect(screen.getByText("Ekim · atılan")).toBeInTheDocument()
    expect(screen.getByText("/ 5")).toBeInTheDocument()
    expect(screen.queryByText("1.500,00 ₺")).not.toBeInTheDocument() // tablo kisa kartta kapali, Ayrinti altinda
    fireEvent.click(screen.getByRole("button", { name: /Ayrıntı · 1 satır/ }))
    expect(screen.getByText("1.500,00 ₺")).toBeInTheDocument()
    expect(screen.getByText(/kayıt ab12cd34/)).toBeInTheDocument()
    expect(screen.getByText(/dondurulmuş kaydı olmayan anlık kaynaklar: Müşteri portföy özeti/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Sunuma sabitle/ })).toBeInTheDocument()
    expect(screen.getByText("Sunuma akan kaynaklar")).toBeInTheDocument() // yetkiliye kaynak secimi

    fireEvent.click(screen.getByRole("button", { name: /Kaldır/ }))
    await waitFor(() => expect(cagrilar.some((c) => c.yontem === "POST" && c.yol.includes("/sunum/gonder"))).toBe(true))
    expect(cagrilar.find((c) => c.yontem === "POST")?.govde).toEqual({ kaynak: "rapor", yil: new Date().getFullYear(), ceyrek: Math.floor(new Date().getMonth() / 3) + 1, gonder: false })

    fireEvent.click(screen.getByRole("button", { name: "Ç1" }))
    await waitFor(() => expect(cagrilar.some((c) => c.yol.includes("ceyrek=1"))).toBe(true))
  })

  it("English iken kaynak ve KPI adlari EN; yetkisiz kullanici islem dugmesi gormez", async () => {
    sahteSunucu({ "/api/v1/sunum/donem": { ...DONEM, yonetebilir: false } })
    sarmala(<SunumSayfasi dil="en" />)
    expect(await screen.findByRole("heading", { name: "Sent monthly report status" })).toBeInTheDocument()
    expect(screen.getByText("October · sent")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Pin to presentation|Remove|Update/ })).not.toBeInTheDocument()
    expect(screen.queryByText("Sources flowing into the presentation")).not.toBeInTheDocument()
  })
})

/** Kisa ozet duzeni icin yeni bicimli kaynaklar (sunucu: app/sunum/servis.py). */
const kpi = (ad: string, ad_en: string, deger: number | null, ek: Record<string, unknown> = {}) => ({ ad, ad_en, deger, birim: "", alt: "", alt_en: "", onceki: null, kod: "", ...ek })
const sutun = (ad: string, ad_en = ad) => ({ ad, ad_en, birim: "" })
const oge = (kaynak: string, ad: string, ad_en: string, veri: unknown, ek: Record<string, unknown> = {}) => ({ kaynak, ad, ad_en, anlik: false, durum: "canli", gonderen: "", zaman: "2026-10-10T10:00:00Z", veri, kayit_no: "", ...ek })
const donem = (ogeler: unknown[], ek: Record<string, unknown> = {}) => ({ yil: 2026, ceyrek: 4, donem: "2026-Q4", zaman: "guncel", yonetebilir: false, ogeler, ...ek })

const ONEDESK = oge("onedesk", "Onedesk özeti", "Onedesk summary", {
  kpi: [kpi("Alarm", "Alarms", 12), kpi("Talep", "Requests", 5)],
  tablo: {
    sutunlar: [sutun("Sıra", "Rank"), sutun("Müşteri", "Customer"), sutun("Alarm", "Alarms"), sutun("Talep", "Requests"), sutun("Şikayet", "Complaints"), sutun("Toplam", "Total"), sutun("Lokasyon", "Location")],
    satirlar: [
      [1, "Alfa A.Ş.", 8, 2, 1, 11, "Gebze"],
      [2, "Beta Ltd", 4, 3, 0, 7, "Ankara"],
      [3, "Gama Holding", 2, 0, 0, 2, "İzmir"],
      [4, "Delta Lojistik", 1, 0, 0, 1, "Bursa"],
    ],
    onizleme: { adet: 3, sira: 0, etiket: 1, deger: 5 },
  },
})
const SAYILAR = oge("sayilar", "Sayılarla TAM Ekibi", "TAM Team in Numbers", {
  stil: "sayilar",
  kpi: [
    kpi("Proje", "Projects", 23, { alt: "5 açıldı · 3 kapandı", alt_en: "5 opened · 3 closed", onceki: 20, kod: "proje" }),
    kpi("Yüz yüze buluşma", "Face-to-face meetings", 112, { onceki: 88, kod: "yuz_yuze" }),
    kpi("Online toplantı", "Online meetings", 900, { onceki: 924, kod: "online" }),
  ],
  tablo: { sutunlar: [sutun("TAM"), sutun("Proje", "Projects"), sutun("Toplam", "Total")], satirlar: [["Ayse Test", 23, 23]] },
})
const TANITIM = oge(
  "tanitim",
  "TAM Life tanıtımı",
  "TAM Life introduction",
  {
    stil: "tanitim",
    kpi: [kpi("Satır kod", "Lines of code", 39502, { kod: "satir" })],
    olcum: "2026-10-13T17:13:50Z",
    amac: { tr: "Tek ekranda toplamak.", en: "Bring it into one screen." },
    kapsam: [
      { ad: "Müşteri Yönetimi", ad_en: "Customer Management" },
      { ad: "Onedesk", ad_en: "Onedesk" },
    ],
    fayda: [{ ad: "Tek kaynak", ad_en: "One source", aciklama: "Aynı veri, aynı ekran.", aciklama_en: "Same data, same screen." }],
    kod: {
      satir: 39502,
      dosya: 260,
      test_satir: 7561,
      diller: [
        { dil: "Python", satir: 21254, dosya: 138, pay: 53.8, rol: "Sunucu: API ve iş kuralları", rol_en: "Server: API and business rules" },
        { dil: "TypeScript", satir: 17459, dosya: 115, pay: 44.2, rol: "Arayüz: sayfalar ve grafikler", rol_en: "Interface: pages and charts" },
      ],
    },
    sayilar: [
      { kod: "modul", ad: "Modül", ad_en: "Modules", deger: 14 },
      { kod: "uc", ad: "API ucu", ad_en: "API endpoints", deger: 144 },
    ],
    canli: [{ ad: "Çatı müşteri", ad_en: "Parent customers", deger: 464 }],
    yigin: ["FastAPI", "React"],
  },
  { anlik: true },
)
const BOS_PROJE = oge("proje", "Takip edilen projeler özeti", "Tracked projects summary", { kpi: [kpi("Süren proje", "Ongoing projects", 0), kpi("Beklemede", "On hold", 0)], tablo: { sutunlar: [sutun("TAM")], satirlar: [] } })

describe("Ceyrek Bazli Sunum: kisa ozet duzeni", () => {
  it("kisa kartta KPI ve ilk satirlar gorunur; tablonun tamami Ayrinti ve 'Tum ayrintilari ac' ile acilir", async () => {
    sahteSunucu({ "/api/v1/sunum/donem": donem([ONEDESK]) })
    sarmala(<SunumSayfasi dil="tr" />)
    expect(await screen.findByRole("heading", { name: "Onedesk özeti" })).toBeInTheDocument()
    expect(screen.getByText("12")).toBeInTheDocument()
    for (const ad of ["Alfa A.Ş.", "Beta Ltd", "Gama Holding"]) expect(screen.getByText(ad)).toBeInTheDocument() // ilk 3 satir
    expect(screen.queryByText("Delta Lojistik")).not.toBeInTheDocument()
    expect(screen.queryByRole("table")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Tüm ayrıntıları aç" }))
    expect(await screen.findByText("Delta Lojistik")).toBeInTheDocument()
    expect(screen.getByRole("table", { name: "Onedesk özeti" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Tüm ayrıntıları kapat" })).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Ayrıntı · 4 satır/ })) // tek kartı kapatır
    await waitFor(() => expect(screen.queryByText("Delta Lojistik")).not.toBeInTheDocument())
    expect(screen.getByRole("button", { name: "Tüm ayrıntıları aç" })).toBeInTheDocument()
  })

  it("kaydi olmayan alanlar kart acmaz, tek satirlik notta toplanir; elle sabitlenmis bos oge kart kalir", async () => {
    sahteSunucu({ "/api/v1/sunum/donem": donem([ONEDESK, BOS_PROJE]) })
    sarmala(<SunumSayfasi dil="tr" />)
    expect(await screen.findByRole("heading", { name: "Onedesk özeti" })).toBeInTheDocument()
    expect(screen.queryByRole("heading", { name: "Takip edilen projeler özeti" })).not.toBeInTheDocument()
    expect(screen.getByText("Bu çeyrekte kaydı olmayan alanlar: Takip edilen projeler özeti.")).toBeInTheDocument()
    cleanup()

    sahteSunucu({ "/api/v1/sunum/donem": donem([{ ...BOS_PROJE, durum: "kayitli", gonderen: "Admin Kisi" }], { yonetebilir: true }) })
    sarmala(<SunumSayfasi dil="tr" />)
    expect(await screen.findByRole("heading", { name: "Takip edilen projeler özeti" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Kaldır/ })).toBeInTheDocument()
  })

  it("Sayilarla TAM Ekibi: yuvarlak sayaclar; onceki ceyrek degeri; fark oku yalniz gecmis ceyrekte", async () => {
    sahteSunucu({ "/api/v1/sunum/donem": donem([SAYILAR], { ceyrek: 4 }) })
    sarmala(<SunumSayfasi dil="tr" />)
    expect(await screen.findByRole("heading", { name: "Sayılarla TAM Ekibi" })).toBeInTheDocument()
    expect(screen.getByText("23")).toBeInTheDocument()
    expect(screen.getByText("112")).toBeInTheDocument()
    expect(screen.getByText("900")).toBeInTheDocument()
    expect(screen.getByText("5 açıldı · 3 kapandı")).toBeInTheDocument()
    expect(screen.getAllByText(/Ç3:/).length).toBe(3) // onceki ceyrek etiketi
    expect(screen.queryByText(/▲|▼/)).not.toBeInTheDocument() // devam eden ceyrek tamamlanmis ceyrekle kiyaslanmaz
    cleanup()

    sahteSunucu({ "/api/v1/sunum/donem": donem([SAYILAR], { ceyrek: 1, zaman: "gecmis" }) })
    sarmala(<SunumSayfasi dil="tr" />)
    expect(await screen.findByText("▲ 3")).toBeInTheDocument() // 23 - 20
    expect(screen.getByText("▲ 24")).toBeInTheDocument() // 112 - 88
    expect(screen.getByText("▼ 24")).toBeInTheDocument() // 900 - 924
    expect(screen.getAllByText(/Ç4 2025:/).length).toBe(3) // Ç1'in oncesi: onceki yilin Ç4'u
  })

  it("TAM Life tanitimi: amac, kapsam, fayda, kac satir kod, hangi dil, kod ne yapiyor", async () => {
    sahteSunucu({ "/api/v1/sunum/donem": donem([TANITIM]) })
    sarmala(<SunumSayfasi dil="tr" />)
    expect(await screen.findByRole("heading", { name: "TAM ekibinin tek ekran paneli" })).toBeInTheDocument()
    expect(screen.getByAltText("TAM Life")).toBeInTheDocument()
    expect(screen.getByText("39.502")).toBeInTheDocument()
    expect(screen.getByText("260 dosya · 2 dil")).toBeInTheDocument()
    expect(screen.getByText("21.254 · %53,8")).toBeInTheDocument()
    expect(screen.getByText("Sunucu: API ve iş kuralları")).toBeInTheDocument()
    expect(screen.getByText("Arayüz: sayfalar ve grafikler")).toBeInTheDocument()
    expect(screen.getByText("Kodun %19'i (7.561 satır) otomatik test kodudur.")).toBeInTheDocument()
    for (const baslik of ["Amaç", "Kapsam", "Fayda", "Kod ne yapıyor?", "Rakamlarla", "Panelde şu an"]) expect(screen.getByRole("heading", { name: baslik })).toBeInTheDocument()
    expect(screen.getByLabelText("Altyapı")).toBeInTheDocument()
    expect(screen.getByText("Tek ekranda toplamak.")).toBeInTheDocument()
    expect(screen.getByText("Müşteri Yönetimi")).toBeInTheDocument()
    expect(screen.getByText("2 modül")).toBeInTheDocument()
    expect(screen.getByText(/Aynı veri, aynı ekran\./)).toBeInTheDocument()
    expect(screen.getByText("464")).toBeInTheDocument()
    expect(screen.getByText("FastAPI")).toBeInTheDocument()
    expect(screen.getByText(/Ölçüm: .*Yalnız dolu satırlar sayılır/)).toBeInTheDocument()
    expect(screen.getByText("Canlı")).toBeInTheDocument() // rozet baslik bandinin icinde
  })

  it("English iken kisa kart, tanitim ve sayilar EN metinlerle cizilir", async () => {
    sahteSunucu({ "/api/v1/sunum/donem": donem([SAYILAR, TANITIM, ONEDESK]) })
    sarmala(<SunumSayfasi dil="en" />)
    expect(await screen.findByRole("heading", { name: "TAM Team in Numbers" })).toBeInTheDocument()
    expect(screen.getByText("5 opened · 3 closed")).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "The single-screen panel of the TAM team" })).toBeInTheDocument()
    expect(screen.getByText("Bring it into one screen.")).toBeInTheDocument()
    expect(screen.getByText("Server: API and business rules")).toBeInTheDocument()
    expect(screen.getByText("2 modules")).toBeInTheDocument()
    expect(screen.getByText("Current quarter · computed live")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Open all details" })).toBeInTheDocument()
    expect(screen.getAllByText(/Q3:/).length).toBe(3)
  })
})

describe("Rol Yonetimi: ek yetkiler ve Ceyrek Bazli Sunum bolumu", () => {
  const ROLLER = {
    catalog: [{ id: "sunum", label: "Çeyrek Bazlı Sunum", label_en: "Quarterly Presentation", admin_only: false, children: [] }],
    permission_catalog: [
      {
        id: "sunum.gonder",
        label: "Çeyrek bazlı sunumu yönet",
        label_en: "Manage the quarterly presentation",
        description: "Sunuma öğe gönderebilir",
        description_en: "Can send items",
        where: "TAM Takvim › grafik",
        where_en: "TAM Calendar › chart",
        area: "sunum",
      },
    ],
    roles: [
      { role: "admin", label: "Admin", editable: false, modules: ["sunum"], landing: "ozet", permissions: ["sunum.gonder"], saved: false },
      { role: "TeamMngr", label: "Manager", editable: true, modules: ["sunum"], landing: "ozet", permissions: [], saved: true },
    ],
  }

  it("yetki duz dilde anlatilir; rol isareti aninda kaydedilir ve rol kartina yansir; kaynak isareti listeyi gonderir", async () => {
    const cagrilar = sahteSunucu({
      "/api/v1/roller/TeamMngr": { role: "TeamMngr", modules: ["sunum"], landing: "ozet", permissions: ["sunum.gonder"] },
      "/api/v1/roller": ROLLER,
      "/api/v1/sunum/kaynaklar": KAYNAKLAR,
    })
    sarmala(<RollerSayfasi dil="tr" />)
    expect(await screen.findByText("1 · Sunumu yönetebilecek roller")).toBeInTheDocument()
    expect(screen.getAllByText("Ne sağlar:").length).toBeGreaterThan(0)
    expect(screen.getByText("Sunuma öğe gönderebilir")).toBeInTheDocument()
    expect(screen.queryByText("Ek yetkiler")).toBeNull() // rol kartindaki "Ek yetkiler" kaldirildi

    const alan = screen.getByText("1 · Sunumu yönetebilecek roller").closest("section") as HTMLElement
    const admin = within(alan).getByRole("checkbox", { name: /Admin/ })
    expect(admin).toBeChecked()
    expect(admin).toBeDisabled()
    fireEvent.click(within(alan).getByRole("checkbox", { name: /Manager/ }))
    await waitFor(() => expect(within(alan).getByRole("checkbox", { name: /Manager/ })).toBeChecked())
    expect(cagrilar.find((c) => c.yontem === "PUT" && c.yol.includes("/roller/TeamMngr"))?.govde).toEqual({ modules: ["sunum"], landing: "ozet", permissions: ["sunum.gonder"] })

    fireEvent.click(await screen.findByRole("checkbox", { name: /Müşteri portföy özeti/ }))
    await waitFor(() => expect(cagrilar.some((c) => c.yontem === "PUT" && c.yol.includes("/sunum/kaynaklar"))).toBe(true))
    expect(cagrilar.find((c) => c.yontem === "PUT" && c.yol.includes("/sunum/kaynaklar"))?.govde).toEqual({ kaynaklar: ["takvim", "portfoy"] })
    expect(screen.getByRole("region", { name: "Benim Yerim" })).toBeInTheDocument() // kaynaklar menu bolumune gore gruplu
  })
})
