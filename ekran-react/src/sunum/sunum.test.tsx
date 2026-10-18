import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { RollerSayfasi } from "@/shell/roller-sayfasi"
import { SunumSayfasi, sunumSayfalari } from "@/sunum/sunum-sayfasi"
import type { Oge } from "@/sunum/sunum-tipleri"

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
    expect(screen.getByRole("heading", { name: "Müşteri portföy özeti" })).toBeInTheDocument() // verisi olmayan modulun da alani var
    expect(screen.getByText("Bu çeyrekte bu alanda veri yok.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Sunuma sabitle/ })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Sunum içeriği" })).toBeInTheDocument() // yetkiliye icerik penceresi

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
    expect(screen.queryByRole("button", { name: "Presentation content" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Approve presentation" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Full-screen presentation" })).toBeInTheDocument() // herkes sunabilir
  })

  it("TAM Takvim ozet halkasi izin yerine online ve yuz yuze toplantilari gosterir", async () => {
    sahteSunucu({ "/api/v1/sunum/donem": donem([oge("takvim", "TAM Takvim özeti", "TAM Calendar summary", { genel: { ...OZET, online: 4, yuzyuze: 3 }, uyeler: [] })]) })
    sarmala(<SunumSayfasi dil="tr" />)
    const kart = await screen.findByRole("region", { name: "TAM Takvim özeti" })
    expect(within(kart).getByRole("img", { name: "Online toplantı: 4, Yüz yüze toplantı: 3" })).toBeInTheDocument()
    expect(within(kart).getByText("Toplam toplantı")).toBeInTheDocument()
    expect(within(kart).queryByText(/İzin ve tatil günü/)).not.toBeInTheDocument()
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
    kpi("Aylık gelir faydası (TRY)", "Monthly revenue benefit (TRY)", 250000, { kod: "gelir" }),
    kpi("Yıl içi gelir faydası (TRY)", "In-year revenue benefit (TRY)", 1800000, { kod: "yillik_gelir" }),
    kpi("Fayda sağlanan iş", "Work delivering benefit", 12, { kod: "fayda" }),
    kpi("Müşteri", "Customers", 48, { alt: "31 çatı · 17 iştirak", alt_en: "31 parent · 17 affiliates", kod: "musteri" }),
    kpi("Ortalama utilizasyon", "Average utilization", 74.5, { kod: "utilizasyon" }),
    kpi("TAM", "TAMs", 9, { kod: "tam" }),
  ],
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

  it("verisi olmayan modul de kendi alaninda durur; icerigi olmayan modul 'veri yok' der", async () => {
    sahteSunucu({ "/api/v1/sunum/donem": donem([ONEDESK, BOS_PROJE, oge("baglantili", "Bağlantılı araçlar", "Connected tools", { kpi: [], tablo: { sutunlar: [], satirlar: [] } })]) })
    sarmala(<SunumSayfasi dil="tr" />)
    expect(await screen.findByRole("heading", { name: "Onedesk özeti" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Takip edilen projeler özeti" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Bağlantılı araçlar" })).toBeInTheDocument()
    expect(screen.getByText("Bu çeyrekte bu alanda veri yok.")).toBeInTheDocument()
    cleanup()

    sahteSunucu({ "/api/v1/sunum/donem": donem([{ ...BOS_PROJE, durum: "kayitli", gonderen: "Admin Kisi" }], { yonetebilir: true }) })
    sarmala(<SunumSayfasi dil="tr" />)
    expect(await screen.findByRole("heading", { name: "Takip edilen projeler özeti" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Kaldır/ })).toBeInTheDocument()
  })

  it("Sayilarla TAM Ekibi: gelir, musteri, utilizasyon ve ekip buyuklugunu ozetler", async () => {
    sahteSunucu({ "/api/v1/sunum/donem": donem([SAYILAR], { ceyrek: 4 }) })
    sarmala(<SunumSayfasi dil="tr" />)
    expect(await screen.findByRole("heading", { name: "Sayılarla TAM Ekibi" })).toBeInTheDocument()
    for (const deger of ["250.000", "1.800.000", "12", "48", "74,5", "9"]) expect(screen.getByText(deger)).toBeInTheDocument()
    expect(screen.getByText("31 çatı · 17 iştirak")).toBeInTheDocument()
    expect(screen.queryByText("Proje")).not.toBeInTheDocument()
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
    expect(screen.getByText("31 parent · 17 affiliates")).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "The single-screen panel of the TAM team" })).toBeInTheDocument()
    expect(screen.getByText("Bring it into one screen.")).toBeInTheDocument()
    expect(screen.getByText("Server: API and business rules")).toBeInTheDocument()
    expect(screen.getByText("2 modules")).toBeInTheDocument()
    expect(screen.getByText("Current quarter · computed live")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Open all details" })).toBeInTheDocument()
    expect(screen.getByText("Monthly revenue benefit (TRY)")).toBeInTheDocument()
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

  it("yetki duz dilde anlatilir; rol isareti aninda kaydedilir; sunum icerigi secimi artik burada degil", async () => {
    const cagrilar = sahteSunucu({
      "/api/v1/roller/TeamMngr": { role: "TeamMngr", modules: ["sunum"], landing: "ozet", permissions: ["sunum.gonder"] },
      "/api/v1/roller": ROLLER,
      "/api/v1/sunum/kaynaklar": KAYNAKLAR,
    })
    sarmala(<RollerSayfasi dil="tr" />)
    expect(await screen.findByText("Sunumu yönetebilecek roller")).toBeInTheDocument()
    expect(screen.getAllByText("Ne sağlar:").length).toBeGreaterThan(0)
    expect(screen.getByText("Sunuma öğe gönderebilir")).toBeInTheDocument()
    expect(screen.queryByText("Ek yetkiler")).toBeNull() // rol kartindaki "Ek yetkiler" kaldirildi

    const alan = screen.getByText("Sunumu yönetebilecek roller").closest("section") as HTMLElement
    const admin = within(alan).getByRole("checkbox", { name: /Admin/ })
    expect(admin).toBeChecked()
    expect(admin).toBeDisabled()
    fireEvent.click(within(alan).getByRole("checkbox", { name: /Manager/ }))
    await waitFor(() => expect(within(alan).getByRole("checkbox", { name: /Manager/ })).toBeChecked())
    expect(cagrilar.find((c) => c.yontem === "PUT" && c.yol.includes("/roller/TeamMngr"))?.govde).toEqual({ permissions: ["sunum.gonder"] })
    expect(screen.queryByText("Giriş sayfası")).toBeNull() // giris sayfasi secimi kalkti (2026-10-14)

    expect(screen.queryByRole("checkbox", { name: /Müşteri portföy özeti/ })).toBeNull()
    expect(cagrilar.some((c) => c.yol.includes("/sunum/kaynaklar"))).toBe(false)
  })
})

describe("Ceyrek Bazli Sunum: icerik penceresi, surukle-birak, onay ve tam ekran", () => {
  const TUMU = { ...KAYNAKLAR, kaynaklar: KAYNAKLAR.kaynaklar.map((k) => ({ ...k, acik: true })) }
  const IKI = donem([oge("takvim", "TAM Takvim özeti", "TAM Calendar summary", { genel: OZET, uyeler: [] }), ONEDESK], { yonetebilir: true })

  it("pencerede modul isareti ve sirasi kaydedilir", async () => {
    const cagrilar = sahteSunucu({ "/api/v1/sunum/donem": DONEM, "/api/v1/sunum/kaynaklar": KAYNAKLAR })
    sarmala(<SunumSayfasi dil="tr" />)
    fireEvent.click(await screen.findByRole("button", { name: "Sunum içeriği" }))
    const pencere = await screen.findByRole("dialog")
    expect(within(pencere).getByText("2 alandan 1 tanesi sunumda")).toBeInTheDocument()
    fireEvent.click(await within(pencere).findByRole("checkbox", { name: /Müşteri portföy özeti/ }))
    await waitFor(() => expect(cagrilar.some((c) => c.yontem === "PUT" && c.yol.includes("/sunum/kaynaklar"))).toBe(true))
    expect(cagrilar.find((c) => c.yontem === "PUT")?.govde).toEqual({ kaynaklar: ["takvim", "portfoy"], sira: ["takvim", "portfoy"] })
    fireEvent.click(within(pencere).getByRole("button", { name: "Müşteri portföy özeti: yukarı taşı" }))
    await waitFor(() => expect(cagrilar.filter((c) => c.yontem === "PUT").length).toBe(2))
    expect(cagrilar.filter((c) => c.yontem === "PUT")[1].govde).toMatchObject({ sira: ["portfoy", "takvim"] })
  })

  it("kart surukleyip birakilinca yeni sira kaydedilir", async () => {
    const cagrilar = sahteSunucu({ "/api/v1/sunum/donem": IKI, "/api/v1/sunum/kaynaklar": { ...TUMU, kaynaklar: [...TUMU.kaynaklar, { ...TUMU.kaynaklar[0], id: "onedesk", ad: "Onedesk özeti" }] } })
    sarmala(<SunumSayfasi dil="tr" />)
    const takvim = await screen.findByRole("region", { name: "TAM Takvim özeti" })
    await waitFor(() => expect(within(takvim).getByLabelText("Taşımak için sürükleyin")).toBeInTheDocument())
    const onedesk = screen.getByRole("region", { name: "Onedesk özeti" })
    const aktarim = { setData: () => undefined, effectAllowed: "", dropEffect: "" }
    fireEvent.dragStart(onedesk, { dataTransfer: aktarim })
    fireEvent.dragOver(takvim, { dataTransfer: aktarim })
    fireEvent.drop(takvim, { dataTransfer: aktarim })
    await waitFor(() => expect(cagrilar.some((c) => c.yontem === "PUT")).toBe(true))
    expect(cagrilar.find((c) => c.yontem === "PUT")?.govde).toEqual({ kaynaklar: ["onedesk", "portfoy", "takvim"], sira: ["onedesk", "portfoy", "takvim"] })
  })

  it("onay sunumu sabitler: tasima ve sabitleme kapanir, onay kaldirilabilir", async () => {
    let cagrilar = sahteSunucu({ "/api/v1/sunum/donem": IKI, "/api/v1/sunum/kaynaklar": TUMU, "/api/v1/sunum/onay": { onay: null } })
    sarmala(<SunumSayfasi dil="tr" />)
    fireEvent.click(await screen.findByRole("button", { name: "Sunumu onayla" }))
    await waitFor(() => expect(cagrilar.some((c) => c.yol.includes("/sunum/onay"))).toBe(true))
    expect(cagrilar.find((c) => c.yol.includes("/sunum/onay"))?.govde).toEqual({ yil: new Date().getFullYear(), ceyrek: Math.floor(new Date().getMonth() / 3) + 1, onay: true })
    cleanup()

    cagrilar = sahteSunucu({ "/api/v1/sunum/donem": { ...IKI, onay: { onaylayan: "Admin Kisi", zaman: "2026-10-14T09:00:00Z" } }, "/api/v1/sunum/kaynaklar": TUMU, "/api/v1/sunum/onay": { onay: null } })
    sarmala(<SunumSayfasi dil="tr" />)
    expect(await screen.findByText(/Onaylandı · Admin Kisi/)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Sunuma sabitle/ })).toBeNull()
    expect(screen.queryByLabelText("Taşımak için sürükleyin")).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "Onayı kaldır" }))
    await waitFor(() => expect(cagrilar.find((c) => c.yol.includes("/sunum/onay"))?.govde).toMatchObject({ onay: false }))
  })

  it("tam ekran sunum kartlari ayni sayfaya sigdirir; ayrinti ve kaydirma acmaz", async () => {
    sahteSunucu({ "/api/v1/sunum/donem": IKI, "/api/v1/sunum/kaynaklar": TUMU })
    sarmala(<SunumSayfasi dil="tr" />)
    fireEvent.click(await screen.findByRole("button", { name: "Tam ekran sunum" }))
    const slayt = await screen.findByRole("dialog", { name: "Tam ekran sunum" })
    expect(within(slayt).getByText("1 / 1")).toBeInTheDocument()
    expect(within(slayt).getByRole("heading", { level: 3, name: "TAM Takvim özeti" })).toBeInTheDocument()
    expect(within(slayt).getByRole("heading", { name: "Onedesk özeti" })).toBeInTheDocument()
    expect(within(slayt).queryByText("Delta Lojistik")).not.toBeInTheDocument()
    expect(within(slayt).queryByRole("table")).not.toBeInTheDocument()
    expect(slayt.querySelector("main")).toHaveClass("overflow-hidden")
    fireEvent.keyDown(slayt, { key: "Escape" })
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Tam ekran sunum" })).toBeNull())
  })

  it("tam ekran sayfalari icerik agirligina gore dort kisa karti birlestirir", () => {
    const kisa = [0, 1, 2, 3, 4].map((n) => oge(`k${n}`, `Kart ${n}`, `Card ${n}`, { kpi: [kpi("Değer", "Value", n)] }))
    expect(sunumSayfalari(kisa as Oge[]).map((s) => s.length)).toEqual([4, 1])
    expect(sunumSayfalari([SAYILAR as Oge, ...(kisa.slice(0, 2) as Oge[])]).map((s) => s.length)).toEqual([3])
    expect(sunumSayfalari([TANITIM as Oge, ...(kisa.slice(0, 2) as Oge[])]).map((s) => s.length)).toEqual([1, 2])
  })

  it("veri senkronu: once karsilastirir (farkli alan ve degisen KPI), Senkronla ile yeniler", async () => {
    const satir = (kaynak: string, ad: string, durum: string, farklar: unknown[] = []) => ({ kaynak, ad, ad_en: ad, durum, gonderen: "", zaman: "2026-07-01T08:00:00Z", farklar, kayit_no: "" })
    const KARSILASTIR = {
      donem: "2026-Q3",
      zaman: "gecmis",
      onayli: false,
      kontrol: "2026-10-15T09:00:00Z",
      kaynaklar: [satir("portfoy", "Müşteri portföy özeti", "farkli", [{ ad: "Çatı müşteri", eski: 2, yeni: 3 }]), satir("takvim", "TAM Takvim özeti", "guncel")],
      sayilar: { guncel: 1, farkli: 1, eksik: 0, canli: 0, kapsam_disi: 0, hata: 0 },
      senkron_gerekli: true,
      yonetebilir: true,
    }
    const SONRA = { ...KARSILASTIR, kaynaklar: [satir("portfoy", "Müşteri portföy özeti", "guncel"), KARSILASTIR.kaynaklar[1]], sayilar: { ...KARSILASTIR.sayilar, guncel: 2, farkli: 0 }, senkron_gerekli: false }
    const cagrilar = sahteSunucu({ "/api/v1/sunum/donem": DONEM, "/api/v1/sunum/kaynaklar": KAYNAKLAR, "/api/v1/sunum/karsilastir": KARSILASTIR, "/api/v1/sunum/senkron": { yenilenen: ["portfoy"], sonra: SONRA } })
    sarmala(<SunumSayfasi dil="tr" />)
    fireEvent.click(await screen.findByRole("button", { name: "Veri senkronu" }))
    const pencere = within(await screen.findByRole("dialog"))
    expect(await pencere.findByText(/1 alan güncel değil/)).toBeInTheDocument()
    expect(pencere.getByText("Farklı")).toBeInTheDocument()
    expect(pencere.getByText("Çatı müşteri")).toBeInTheDocument()
    expect(cagrilar.some((c) => c.yontem === "POST")).toBe(false) // karsilastirma hicbir sey yazmaz
    fireEvent.click(pencere.getByRole("button", { name: "Senkronla (1)" }))
    expect(await pencere.findByText("1 alan canlı veriyle yenilendi.")).toBeInTheDocument()
    expect(cagrilar.find((c) => c.yontem === "POST")?.govde).toEqual({ yil: new Date().getFullYear(), ceyrek: Math.floor(new Date().getMonth() / 3) + 1 })
    expect(pencere.getByText("Sunumdaki tüm veriler güncel.")).toBeInTheDocument()
    expect(pencere.getByRole("button", { name: "Senkronla" })).toBeDisabled()
  })

  it("veri senkronu: onayli ceyrekte senkron dugmesi kapali ve neden yazar; yetkisiz kullanici senkron dugmesi gormez", async () => {
    const KARSILASTIR = {
      donem: "2026-Q4", zaman: "guncel", onayli: true, kontrol: "2026-10-15T09:00:00Z", senkron_gerekli: true, yonetebilir: true,
      kaynaklar: [{ kaynak: "portfoy", ad: "Müşteri portföy özeti", ad_en: "x", durum: "farkli", gonderen: "Admin", zaman: "2026-10-01T08:00:00Z", farklar: [], kayit_no: "" }],
      sayilar: { guncel: 0, farkli: 1, eksik: 0, canli: 0, kapsam_disi: 0, hata: 0 },
    }  // prettier-ignore
    sahteSunucu({ "/api/v1/sunum/donem": DONEM, "/api/v1/sunum/kaynaklar": KAYNAKLAR, "/api/v1/sunum/karsilastir": KARSILASTIR })
    sarmala(<SunumSayfasi dil="tr" />)
    fireEvent.click(await screen.findByRole("button", { name: "Veri senkronu" }))
    const pencere = within(await screen.findByRole("dialog"))
    expect(await pencere.findByText(/önce onayı kaldırın/)).toBeInTheDocument()
    expect(pencere.getByRole("button", { name: "Senkronla (1)" })).toBeDisabled()
    cleanup()

    sahteSunucu({ "/api/v1/sunum/donem": DONEM, "/api/v1/sunum/kaynaklar": KAYNAKLAR, "/api/v1/sunum/karsilastir": { ...KARSILASTIR, onayli: false, yonetebilir: false } })
    sarmala(<SunumSayfasi dil="en" />)
    fireEvent.click(await screen.findByRole("button", { name: "Data sync" }))
    const p2 = within(await screen.findByRole("dialog"))
    expect(await p2.findByText(/1 areas are out of date/)).toBeInTheDocument()
    expect(p2.queryByRole("button", { name: /^Sync/ })).not.toBeInTheDocument()
  })
})
