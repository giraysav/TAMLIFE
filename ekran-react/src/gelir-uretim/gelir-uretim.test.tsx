import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { bicimDili } from "@/lib/bicim"
import type { Dil } from "@/shell/metin"
import { gelirUretimMetin } from "@/gelir-uretim/gelir-uretim-metin"
import type { Kayit, Onizleme, OnizlemeSatiri, UygulaSonucu } from "@/gelir-uretim/gelir-uretim-metin"
import { GelirUretimSayfasi } from "@/gelir-uretim/gelir-uretim-sayfasi"
import { kisilerMetni, saatMetni, tarihAraligi, tutarMetni } from "@/gelir-uretim/ortak"

beforeEach(() => window.localStorage.clear())
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  bicimDili("tr")
})

// --- sahte veri: yalniz bu testin uydurdugu adlar ve tutarlar ---------------------------------------------------------
function kayit(ek: Partial<Kayit> & Pick<Kayit, "id" | "title">): Kayit {
  return {
    kind: "proje",
    benefit_type: "gelir",
    status: "devam",
    status_note: "",
    description: "",
    customers: "",
    revenue_amount: null,
    revenue_currency: "TRY",
    revenue_period: "ay",
    revenue_note: "",
    year_revenue: null,
    hours_per_month: null,
    hours_note: "",
    extra_note: "",
    start_date: null,
    end_date: null,
    other_people: "",
    people: [],
    created_by: "Mudur",
    created_at: "2026-10-01T12:00:00Z",
    updated_by: "",
    updated_at: null,
    ...ek,
  }
}

const ALFA = kayit({
  id: 1,
  title: "Alfa Test İşi",
  customers: "Alfa Müşteri A.Ş.",
  revenue_amount: 1250.75,
  year_revenue: 5000,
  start_date: "2026-01-15",
  status_note: "Pilot başarıyla tamamlandı",
  description: "Detay açıklama metni",
  extra_note: "Ek not metni",
  people: [{ id: 2, name: "Ayse Test" }],
})
const BETA = kayit({
  id: 2,
  kind: "inisiyatif",
  benefit_type: "verimlilik",
  title: "Beta İnisiyatifi",
  status: "tamamlandi",
  revenue_note: "15,8 KTL",
  hours_per_month: 12.5,
  start_date: "2026-02-01",
  end_date: "2026-03-31",
  other_people: "Dış Kişi",
})
const GAMA = kayit({
  id: 3,
  benefit_type: "tasarruf",
  title: "Gama Tasarrufu",
  status: "baslamadi",
  revenue_amount: 250000,
  revenue_currency: "USD",
  revenue_period: "tek_sefer",
  people: [{ id: 9, name: "Eski Personel" }],
})
const KAYITLAR = [ALFA, BETA, GAMA]
const OZET = {
  is_sayisi: 3,
  toplam_is: 3,
  durum_sayilari: { baslamadi: 1, devam: 1, tamamlandi: 1, iptal: 0 },
  aylik_gelir: { TRY: 12500.5 },
  yillik_gelir: { TRY: 120000 },
  tek_seferlik_gelir: { USD: 250000 },
  yil_ici_gelir: 450000,
  aylik_saat: 12.5,
}
const SECENEKLER = {
  personel: [
    { id: 2, ad: "Ayse Test" },
    { id: 3, ad: "Can Test" },
  ],
  yillar: [2026, 2025],
}

function satir(ek: Partial<OnizlemeSatiri> & Pick<OnizlemeSatiri, "satir" | "durum" | "title">): OnizlemeSatiri {
  return {
    kind: "proje",
    status: "devam",
    benefit_type: "gelir",
    people: [],
    other_people: "",
    revenue_amount: null,
    revenue_currency: "TRY",
    revenue_period: "ay",
    revenue_note: "",
    year_revenue: null,
    hours_per_month: null,
    start_date: null,
    end_date: null,
    uyarilar: [],
    ...ek,
  }
}
const ONIZLEME: Onizleme = {
  dosya: "gelir.xlsx",
  sayfa: "Sayfa1",
  baslik_satiri: 2,
  plan: { toplam: 4, yeni: 2, var: 1, tekrar: 0, hatali: 1 },
  uyarilar: ["‘Fayda türü’ sütunu bulunamadı; tür metinden çıkarıldı."],
  satirlar: [
    satir({ satir: 5, durum: "yeni", title: "Yeni İş Bir", people: ["Ayse Test"], revenue_amount: 1000, start_date: "2026-01-01" }),
    satir({
      satir: 6,
      durum: "yeni",
      kind: "inisiyatif",
      title: "Yeni İş İki",
      status: "tamamlandi",
      benefit_type: "verimlilik",
      other_people: "Dış Kişi",
      revenue_note: "15,8 KTL",
      hours_per_month: 8,
      uyarilar: ["Tutar sayıya çevrilemedi, nota yazıldı."],
    }),
    satir({ satir: 7, durum: "var", title: "Alfa Test İşi" }),
    satir({ satir: 8, durum: "hatali", title: "", status: "", benefit_type: "", uyarilar: ["İşin özeti boş."] }),
  ],
}
const UYGULA: UygulaSonucu = { ...ONIZLEME.plan, eklendi: 2, uyarilar: [] }

// --- sahte sunucu ----------------------------------------------------------------------------------------------
type Cagri = { yol: string; yontem: string; govde: unknown; basliklar: Record<string, string> }
type Ayar = {
  items?: Kayit[]
  liste?: { durum: number; ayrinti?: string }
  onizleme?: { durum: number; veri?: Onizleme; ayrinti?: string }
}

function kur({ yazabilir = true, dil = "tr", ...ayar }: Ayar & { yazabilir?: boolean; dil?: Dil } = {}) {
  const cagrilar: Cagri[] = []
  const yanit = (durum: number, veri: unknown, ayrinti?: string) =>
    new Response(JSON.stringify(durum < 400 ? { status: "success", data: veri } : { detail: ayrinti ?? "hata" }), { status: durum, headers: { "Content-Type": "application/json" } })
  vi.stubGlobal(
    "fetch",
    vi.fn(async (girdi: string, init?: RequestInit) => {
      const yontem = init?.method ?? "GET"
      const yol = String(girdi)
      cagrilar.push({ yol, yontem, govde: typeof init?.body === "string" ? JSON.parse(init.body) : (init?.body ?? null), basliklar: (init?.headers ?? {}) as Record<string, string> })
      if (yol.includes("/ice-al/onizleme")) return ayar.onizleme && ayar.onizleme.durum >= 400 ? yanit(ayar.onizleme.durum, null, ayar.onizleme.ayrinti) : yanit(200, ayar.onizleme?.veri ?? ONIZLEME)
      if (yol.includes("/ice-al/uygula")) return yanit(200, UYGULA)
      if (yontem !== "GET") return yanit(200, { id: 1 })
      if (ayar.liste && ayar.liste.durum >= 400) return yanit(ayar.liste.durum, null, ayar.liste.ayrinti)
      const items = ayar.items ?? KAYITLAR
      return yanit(200, { items, ozet: { ...OZET, is_sayisi: items.length }, secenekler: SECENEKLER, yazabilir })
    }),
  )
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={istemci}>
      <GelirUretimSayfasi dil={dil} yazabilir={yazabilir} />
    </QueryClientProvider>,
  )
  const getler = () => cagrilar.filter((c) => c.yontem === "GET")
  return { cagrilar, getler, sonGet: () => getler()[getler().length - 1] }
}

const kart = (baslik: string) => screen.getByRole("button", { name: new RegExp(baslik) })

describe("Gelir Faydasi Saglanan Isler sayfasi", () => {
  it("KPI seridi, kartlar, rozetler, tarih ve tutar metinleri; admin dugmeleri ile Excel baglantisi gorunur", async () => {
    kur()
    expect(await screen.findByText("Alfa Test İşi")).toBeInTheDocument()

    const kpi = (etiket: string) => screen.getByText(etiket).parentElement as HTMLElement
    expect(kpi("İş sayısı")).toHaveTextContent("3")
    expect(kpi("İş sayısı")).toHaveTextContent("1 devam · 1 tamamlandı")
    expect(kpi("Aylık gelir faydası")).toHaveTextContent("12.501 ₺")
    expect(kpi("Aylık gelir faydası")).toHaveTextContent("Yıllık: 120.000 ₺ · Tek seferlik: 250.000 $")
    expect(kpi("Yıl içi gelir")).toHaveTextContent("450.000 ₺")
    expect(kpi("Aylık efor kazancı")).toHaveTextContent("12,5")

    const alfa = kart("Alfa Test İşi")
    for (const metin of ["Proje", "Devam ediyor", "Gelir", "Alfa Müşteri A.Ş.", "1.250,75 ₺ / ay", "Yıl içi: 5.000,00 ₺", "15.01.2026 – devam ediyor", "Ayse Test"]) expect(alfa).toHaveTextContent(metin)
    const beta = kart("Beta İnisiyatifi")
    for (const metin of ["TAM inisiyatifi", "Tamamlandı", "Verimlilik", "15,8 KTL", "12,5 saat/ay", "01.02.2026 – 31.03.2026", "Dış Kişi"]) expect(beta).toHaveTextContent(metin)
    const gama = kart("Gama Tasarrufu")
    for (const metin of ["Başlamadı", "Tasarruf", "250.000,00 $ tek sefer", "Tarih yok", "Eski Personel"]) expect(gama).toHaveTextContent(metin)

    expect(screen.getByRole("button", { name: "Yeni kayıt" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Excel'den içe aktar" })).toBeInTheDocument()
    const excel = screen.getByRole("link", { name: "Excel'e aktar" })
    expect(excel).toHaveAttribute("href", "/api/v1/gelir-uretim/excel")
    expect(excel).toHaveAttribute("download")
  })

  it("admin olmayan kullanici yalniz okur: yeni, ice aktar, duzenle ve sil yok; Excel baglantisi ve ayrinti acik", async () => {
    kur({ yazabilir: false })
    expect(await screen.findByText("Alfa Test İşi")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Yeni kayıt" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Excel'den içe aktar" })).not.toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Excel'e aktar" })).toBeInTheDocument()

    fireEvent.click(kart("Alfa Test İşi"))
    const pencere = await screen.findByRole("dialog")
    expect(within(pencere).getByText("Alfa Müşteri A.Ş.")).toBeInTheDocument()
    expect(within(pencere).queryByRole("button", { name: "Düzenle" })).not.toBeInTheDocument()
    expect(within(pencere).queryByRole("button", { name: "Sil" })).not.toBeInTheDocument()
  })

  it("suzgecler sorguya yansir; yil secilince ipucu cikar; Temizle hepsini sifirlar", async () => {
    const { sonGet } = kur()
    await screen.findByText("Alfa Test İşi")
    expect(sonGet()?.yol).toBe("/api/v1/gelir-uretim")

    fireEvent.change(screen.getByLabelText("Tür"), { target: { value: "inisiyatif" } })
    await waitFor(() => expect(sonGet()?.yol).toContain("tur=inisiyatif"))
    fireEvent.change(screen.getByLabelText("Durum"), { target: { value: "tamamlandi" } })
    await waitFor(() => expect(sonGet()?.yol).toContain("durum=tamamlandi"))
    fireEvent.change(screen.getByLabelText("Fayda türü"), { target: { value: "verimlilik" } })
    await waitFor(() => expect(sonGet()?.yol).toContain("fayda=verimlilik"))
    fireEvent.change(screen.getByLabelText("TAM"), { target: { value: "3" } })
    await waitFor(() => expect(sonGet()?.yol).toContain("tam=3"))
    expect(screen.queryByText(/Yıl seçilince/)).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText("Yıl"), { target: { value: "2026" } })
    await waitFor(() => expect(sonGet()?.yol).toContain("yil=2026"))
    expect(screen.getByText(/Yıl seçilince başlangıç tarihi olmayan işler listelenmez/)).toBeInTheDocument()

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "alfa" } })
    await waitFor(() => expect(sonGet()?.yol).toContain("q=alfa"))

    fireEvent.click(screen.getByRole("button", { name: "Temizle" }))
    await waitFor(() => expect(sonGet()?.yol).toBe("/api/v1/gelir-uretim"))
    for (const etiket of ["Tür", "Durum", "Fayda türü", "TAM", "Yıl"]) expect(screen.getByLabelText(etiket)).toHaveValue("")
    expect(screen.getByRole("searchbox")).toHaveValue("")
    expect(screen.queryByRole("button", { name: "Temizle" })).not.toBeInTheDocument()
  })

  it("ayrinti cekmecesi tum alanlari gosterir; admin icin Duzenle ve Sil var, Kapat cekmeceyi kapatir", async () => {
    kur()
    await screen.findByText("Alfa Test İşi")
    fireEvent.click(kart("Alfa Test İşi"))
    const pencere = await screen.findByRole("dialog")
    expect(within(pencere).getByRole("heading", { name: "İş ayrıntısı" })).toBeInTheDocument()
    expect(within(pencere).getByRole("heading", { name: "Alfa Test İşi" })).toBeInTheDocument()
    for (const metin of ["Alfa Müşteri A.Ş.", "Ayse Test", "15.01.2026", "devam ediyor", "Pilot başarıyla tamamlandı", "Detay açıklama metni", "Ek not metni", "1.250,75 ₺ / ay", "5.000,00 ₺"]) {
      expect(within(pencere).getByText(metin)).toBeInTheDocument()
    }
    expect(within(pencere).getByText(/Mudur · 01\.10\.2026/)).toBeInTheDocument()
    expect(within(pencere).getByRole("button", { name: "Düzenle" })).toBeInTheDocument()
    expect(within(pencere).getByRole("button", { name: "Sil" })).toBeInTheDocument()
    fireEvent.click(within(pencere).getByRole("button", { name: "Kapat" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
  })

  it("not alanindaki tutar ve efor ayrintida gorunur; olmayan gruplar gizlenir", async () => {
    kur()
    await screen.findByText("Beta İnisiyatifi")
    fireEvent.click(kart("Beta İnisiyatifi"))
    const pencere = await screen.findByRole("dialog")
    expect(within(pencere).getByText("15,8 KTL")).toBeInTheDocument()
    expect(within(pencere).getByText("12,5 saat/ay")).toBeInTheDocument()
    expect(within(pencere).getByText("Dış Kişi")).toBeInTheDocument()
    expect(within(pencere).queryByText("Detaylı açıklama")).not.toBeInTheDocument()
    expect(within(pencere).queryByText("Ek açıklamalar")).not.toBeInTheDocument()
  })

  it("yeni kayit: dogrulama mesajlari, ardindan POST govdesi; kayit sonrasi liste yenilenir ve cekmece kapanir", async () => {
    const { cagrilar, getler } = kur()
    await screen.findByText("Alfa Test İşi")
    fireEvent.click(screen.getByRole("button", { name: "Yeni kayıt" }))
    const pencere = await screen.findByRole("dialog")
    const ic = within(pencere)
    const kaydet = () => fireEvent.click(ic.getByRole("button", { name: "Kaydet" }))

    kaydet()
    expect(await ic.findByText("Başlık zorunlu.")).toBeInTheDocument()
    expect(cagrilar.some((c) => c.yontem === "POST")).toBe(false)

    fireEvent.change(ic.getByLabelText("Başlık"), { target: { value: "  Yeni Test İşi  " } })
    fireEvent.change(ic.getByLabelText("Gelir tutarı"), { target: { value: "1.250,75" } })
    kaydet()
    expect(await ic.findByText(/Gelir tutarı: sıfır ya da pozitif bir sayı girin/)).toBeInTheDocument()

    fireEvent.change(ic.getByLabelText("Gelir tutarı"), { target: { value: "1250,75" } })
    fireEvent.change(ic.getByLabelText("Para birimi"), { target: { value: "USD" } })
    fireEvent.change(ic.getByLabelText("Dönem"), { target: { value: "yil" } })
    fireEvent.change(ic.getByLabelText("Yıl içi gelir (TL)"), { target: { value: "5000" } })
    fireEvent.change(ic.getByLabelText("Aylık efor kazancı (saat)"), { target: { value: "12,5" } })
    fireEvent.change(ic.getByLabelText("Tür"), { target: { value: "inisiyatif" } })
    fireEvent.change(ic.getByLabelText("Fayda türü"), { target: { value: "tasarruf" } })
    fireEvent.change(ic.getByLabelText("Başlangıç tarihi"), { target: { value: "2026-03-01" } })
    fireEvent.change(ic.getByLabelText("Bitiş tarihi"), { target: { value: "2026-02-01" } })
    kaydet()
    expect(await ic.findByText("Bitiş tarihi başlangıçtan önce olamaz.")).toBeInTheDocument()

    fireEvent.change(ic.getByLabelText("Bitiş tarihi"), { target: { value: "2026-12-31" } })
    fireEvent.click(ic.getByRole("checkbox", { name: "Can Test" }))
    const onceki = getler().length
    kaydet()
    await waitFor(() => expect(cagrilar.find((c) => c.yontem === "POST")).toBeDefined())
    const cagri = cagrilar.find((c) => c.yontem === "POST")
    expect(cagri?.yol).toBe("/api/v1/gelir-uretim")
    expect(cagri?.govde).toEqual({
      kind: "inisiyatif",
      benefit_type: "tasarruf",
      title: "Yeni Test İşi",
      status: "devam",
      status_note: "",
      description: "",
      customers: "",
      revenue_amount: 1250.75,
      revenue_currency: "USD",
      revenue_period: "yil",
      revenue_note: "",
      year_revenue: 5000,
      hours_per_month: 12.5,
      hours_note: "",
      extra_note: "",
      start_date: "2026-03-01",
      end_date: "2026-12-31",
      other_people: "",
      person_ids: [3],
    })
    expect(cagri?.basliklar["Content-Type"]).toBe("application/json")
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
    await waitFor(() => expect(getler().length).toBeGreaterThan(onceki))
  })

  it("bos tutar ve tarih null gider; sinir disi sayi reddedilir", async () => {
    const { cagrilar } = kur()
    await screen.findByText("Alfa Test İşi")
    fireEvent.click(screen.getByRole("button", { name: "Yeni kayıt" }))
    const ic = within(await screen.findByRole("dialog"))
    fireEvent.change(ic.getByLabelText("Başlık"), { target: { value: "Sade İş" } })
    fireEvent.change(ic.getByLabelText("Aylık efor kazancı (saat)"), { target: { value: "2000000" } })
    fireEvent.click(ic.getByRole("button", { name: "Kaydet" }))
    expect(await ic.findByText(/Aylık efor kazancı \(saat\): sıfır ya da pozitif/)).toBeInTheDocument()
    fireEvent.change(ic.getByLabelText("Aylık efor kazancı (saat)"), { target: { value: "" } })
    fireEvent.click(ic.getByRole("button", { name: "Kaydet" }))
    await waitFor(() => expect(cagrilar.find((c) => c.yontem === "POST")).toBeDefined())
    expect(cagrilar.find((c) => c.yontem === "POST")?.govde).toMatchObject({
      title: "Sade İş",
      kind: "proje",
      benefit_type: "gelir",
      status: "devam",
      revenue_amount: null,
      year_revenue: null,
      hours_per_month: null,
      start_date: null,
      end_date: null,
      person_ids: [],
    })
  })

  it("duzenle: mevcut degerler dolar, etkin olmayan bagli kisi (pasif) isaretli kalir ve PUT ile gonderilir", async () => {
    const { cagrilar } = kur()
    await screen.findByText("Gama Tasarrufu")
    fireEvent.click(kart("Gama Tasarrufu"))
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Düzenle" }))
    const pencere = await screen.findByRole("dialog")
    const ic = within(pencere)
    expect(ic.getByText("Kaydı düzenle")).toBeInTheDocument()
    expect(ic.getByLabelText("Başlık")).toHaveValue("Gama Tasarrufu")
    expect(ic.getByLabelText("Gelir tutarı")).toHaveValue("250000")
    expect(ic.getByLabelText("Para birimi")).toHaveValue("USD")
    expect(ic.getByLabelText("Dönem")).toHaveValue("tek_sefer")
    expect(ic.getByLabelText("Durum")).toHaveValue("baslamadi")
    expect(ic.getByRole("checkbox", { name: "Eski Personel (pasif)" })).toBeChecked()
    expect(ic.getByRole("checkbox", { name: "Ayse Test" })).not.toBeChecked()

    fireEvent.change(ic.getByLabelText("Başlık"), { target: { value: "Gama Tasarrufu 2" } })
    fireEvent.click(ic.getByRole("button", { name: "Kaydet" }))
    await waitFor(() => expect(cagrilar.find((c) => c.yontem === "PUT")).toBeDefined())
    const cagri = cagrilar.find((c) => c.yontem === "PUT")
    expect(cagri?.yol).toBe("/api/v1/gelir-uretim/3")
    expect(cagri?.govde).toMatchObject({ title: "Gama Tasarrufu 2", revenue_amount: 250000, revenue_currency: "USD", revenue_period: "tek_sefer", start_date: null, end_date: null, person_ids: [9] })
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
  })

  it("sil: onay verilirse DELETE gider ve cekmece kapanir; verilmezse hicbir sey gonderilmez", async () => {
    const onay = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true)
    const { cagrilar } = kur()
    await screen.findByText("Alfa Test İşi")
    fireEvent.click(kart("Alfa Test İşi"))
    const sil = () => fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Sil" }))
    sil()
    expect(onay).toHaveBeenLastCalledWith("“Alfa Test İşi” kaydı silinsin mi?")
    expect(cagrilar.some((c) => c.yontem === "DELETE")).toBe(false)
    sil()
    await waitFor(() => expect(cagrilar.find((c) => c.yontem === "DELETE")?.yol).toBe("/api/v1/gelir-uretim/1"))
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
  })

  it("Excel'den ice aktar: dosya secince onizleme (hicbir sey yazilmaz), sonuca gore suzme, ardindan yalniz yeni satirlar uygulanir", async () => {
    const { cagrilar, getler } = kur()
    await screen.findByText("Alfa Test İşi")
    fireEvent.click(screen.getByRole("button", { name: "Excel'den içe aktar" }))
    const ic = within(await screen.findByRole("dialog"))
    expect(ic.getByText(/En fazla 5 MB ve 500 satır/)).toBeInTheDocument()
    expect(ic.queryByRole("button", { name: /yeni kaydı ekle/ })).not.toBeInTheDocument()

    const dosya = new File([new Uint8Array([80, 75, 3, 4])], "gelir.xlsx", { type: "application/octet-stream" })
    fireEvent.change(ic.getByLabelText("Excel dosyası seç (.xlsx)"), { target: { files: [dosya] } })

    expect(await ic.findByText("#5")).toBeInTheDocument()
    const onizleme = cagrilar.find((c) => c.yol.includes("/ice-al/onizleme"))
    expect(onizleme?.yontem).toBe("POST")
    expect(onizleme?.yol).toBe("/api/v1/gelir-uretim/ice-al/onizleme?dosya=gelir.xlsx")
    expect(onizleme?.govde).toBeInstanceOf(Blob)
    expect(onizleme?.basliklar["Content-Type"]).toBe("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    expect(cagrilar.some((c) => c.yol.includes("/ice-al/uygula"))).toBe(false)

    expect(ic.getByText("gelir.xlsx · sayfa: Sayfa1")).toBeInTheDocument()
    expect(ic.getByText(/Fayda türü’ sütunu bulunamadı/)).toBeInTheDocument()
    expect(ic.getByText(/Tutar sayıya çevrilemedi/)).toBeInTheDocument()
    expect(ic.getByText(/İşin özeti boş/)).toBeInTheDocument()
    for (const ad of [/^Satır\s*4$/, /^Yeni\s*2$/, /^Zaten var\s*1$/, /^Hatalı\s*1$/]) expect(ic.getByRole("button", { name: ad })).toBeInTheDocument()
    expect(ic.getByRole("button", { name: /^Dosyada tekrar\s*0$/ })).toBeDisabled()
    // Satir ayrintilari: kisiler, tutar, tarih, saat
    expect(ic.getByText("Ayse Test · 1.000,00 ₺ / ay · 01.01.2026 – devam ediyor")).toBeInTheDocument()
    expect(ic.getByText("Dış Kişi · 8 saat/ay")).toBeInTheDocument()

    fireEvent.click(ic.getByRole("button", { name: /^Hatalı\s*1$/ }))
    expect(ic.queryByText("#5")).not.toBeInTheDocument()
    expect(ic.getByText("#8")).toBeInTheDocument()
    expect(ic.getByRole("button", { name: /^Hatalı\s*1$/ })).toHaveAttribute("aria-pressed", "true")
    fireEvent.click(ic.getByRole("button", { name: /^Satır\s*4$/ }))
    expect(ic.getByText("#5")).toBeInTheDocument()

    const onceki = getler().length
    fireEvent.click(ic.getByRole("button", { name: "2 yeni kaydı ekle" }))
    expect(await ic.findByText("2 kayıt eklendi. 2 satır eklenmedi (zaten var, tekrar ya da hatalı).")).toBeInTheDocument()
    const uygula = cagrilar.find((c) => c.yol.includes("/ice-al/uygula"))
    expect(uygula?.yol).toBe("/api/v1/gelir-uretim/ice-al/uygula?dosya=gelir.xlsx")
    expect(uygula?.govde).toBeInstanceOf(Blob)
    await waitFor(() => expect(getler().length).toBeGreaterThan(onceki))
    expect(ic.queryByRole("button", { name: /yeni kaydı ekle/ })).not.toBeInTheDocument()
  })

  it("ice aktar: eklenecek yeni satir yoksa Ekle dugmesi kapali ve aciklama gorunur", async () => {
    const hicYeni: Onizleme = { ...ONIZLEME, plan: { toplam: 1, yeni: 0, var: 1, tekrar: 0, hatali: 0 }, uyarilar: [], satirlar: [ONIZLEME.satirlar[2] as OnizlemeSatiri] }
    kur({ onizleme: { durum: 200, veri: hicYeni } })
    await screen.findByText("Alfa Test İşi")
    fireEvent.click(screen.getByRole("button", { name: "Excel'den içe aktar" }))
    const ic = within(await screen.findByRole("dialog"))
    fireEvent.change(ic.getByLabelText("Excel dosyası seç (.xlsx)"), { target: { files: [new File(["x"], "bos.xlsx")] } })
    expect(await ic.findByText("Eklenecek yeni satır yok.")).toBeInTheDocument()
    expect(ic.getByRole("button", { name: "0 yeni kaydı ekle" })).toBeDisabled()
  })

  it("ice aktar: sunucu hatasi mesajiyla gosterilir; 5 MB'tan buyuk dosya hic gonderilmez", async () => {
    const { cagrilar } = kur({ onizleme: { durum: 400, ayrinti: "Başlık sütunu bulunamadı." } })
    await screen.findByText("Alfa Test İşi")
    fireEvent.click(screen.getByRole("button", { name: "Excel'den içe aktar" }))
    const ic = within(await screen.findByRole("dialog"))
    fireEvent.change(ic.getByLabelText("Excel dosyası seç (.xlsx)"), { target: { files: [new File(["x"], "yanlis.xlsx")] } })
    expect(await ic.findByText("Başlık sütunu bulunamadı.")).toBeInTheDocument()
    expect(ic.queryByRole("button", { name: /yeni kaydı ekle/ })).not.toBeInTheDocument()

    const buyuk = new File(["x"], "buyuk.xlsx")
    Object.defineProperty(buyuk, "size", { value: 6 * 1024 * 1024 })
    const onceki = cagrilar.filter((c) => c.yol.includes("/ice-al/")).length
    fireEvent.change(ic.getByLabelText("Başka dosya seç"), { target: { files: [buyuk] } })
    expect(await ic.findByText("Dosya çok büyük (en fazla 5 MB).")).toBeInTheDocument()
    expect(cagrilar.filter((c) => c.yol.includes("/ice-al/")).length).toBe(onceki)
    expect(ic.queryByText("Başlık sütunu bulunamadı.")).not.toBeInTheDocument()
  })

  it("bos durumlar: kayit yok (admin ve okuyucu metni), suzgecte sonuc yok; yukleme hatasinda Tekrar dene", async () => {
    kur({ items: [] })
    expect(await screen.findByText("Henüz kayıt yok")).toBeInTheDocument()
    expect(screen.getByText("Yeni kayıt ekleyin ya da Excel dosyasından içe aktarın.")).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText("Durum"), { target: { value: "iptal" } })
    expect(await screen.findByText("Sonuç bulunamadı")).toBeInTheDocument()
    cleanup()

    kur({ items: [], yazabilir: false })
    expect(await screen.findByText("Henüz bir kayıt eklenmedi.")).toBeInTheDocument()
    cleanup()

    kur({ liste: { durum: 500 } })
    expect(await screen.findByRole("alert")).toHaveTextContent("Yüklenemedi.")
    expect(screen.getByRole("button", { name: "Tekrar dene" })).toBeInTheDocument()
  })

  it("Ingilizce arayuz: basliklar, rozetler ve dugmeler", async () => {
    bicimDili("en")
    kur({ dil: "en" })
    expect(await screen.findByText("Alfa Test İşi")).toBeInTheDocument()
    expect(screen.getByText("Work items")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "New record" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Import from Excel" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Export to Excel" })).toBeInTheDocument()
    expect(kart("Alfa Test İşi")).toHaveTextContent("In progress")
    expect(kart("Alfa Test İşi")).toHaveTextContent("15/01/2026 – ongoing")
    expect(kart("Beta İnisiyatifi")).toHaveTextContent("TAM initiative")
    expect(screen.getByLabelText("Benefit type")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "New record" }))
    const ic = within(await screen.findByRole("dialog"))
    fireEvent.click(ic.getByRole("button", { name: "Save" }))
    expect(await ic.findByText("Title is required.")).toBeInTheDocument()
  })
})

describe("gelir uretim metin yardimcilari", () => {
  const t = gelirUretimMetin("tr")
  const tarihler = (start_date: string | null, end_date: string | null, status: Kayit["status"]) => tarihAraligi({ start_date, end_date, status }, t)

  it("tarih araligi: devam eden isin bitisi yok -> devam ediyor; tamamlanmis/iptal -> yalniz baslangic; tarih yok; yalniz bitis", () => {
    expect(tarihler("2026-01-15", null, "devam")).toBe("15.01.2026 – devam ediyor")
    expect(tarihler("2026-01-15", null, "tamamlandi")).toBe("15.01.2026")
    expect(tarihler("2026-01-15", null, "baslamadi")).toBe("15.01.2026")
    expect(tarihler("2026-01-15", "2026-03-31", "devam")).toBe("15.01.2026 – 31.03.2026")
    expect(tarihler(null, null, "devam")).toBe("Tarih yok")
    expect(tarihler(null, "2026-03-31", "tamamlandi")).toBe("Bitiş tarihi: 31.03.2026")
  })

  it("tutar, saat ve kisi metinleri: bos degerler bos metin verir", () => {
    expect(tutarMetni({ revenue_amount: 1250.75, revenue_currency: "TRY", revenue_period: "ay" }, t)).toBe("1.250,75 ₺ / ay")
    expect(tutarMetni({ revenue_amount: 5, revenue_currency: "EUR", revenue_period: "yil" }, t)).toBe("5,00 € / yıl")
    expect(tutarMetni({ revenue_amount: null, revenue_currency: "TRY", revenue_period: "ay" }, t)).toBe("")
    expect(saatMetni(12.5, t)).toBe("12,5 saat/ay")
    expect(saatMetni(null, t)).toBe("")
    expect(kisilerMetni(["Ayse Test", "Can Test"], " Dış Kişi ")).toBe("Ayse Test, Can Test, Dış Kişi")
    expect(kisilerMetni([], "")).toBe("")
  })

  it("TR ve EN sozlukleri ayni anahtarlara sahiptir", () => {
    const tr = Object.keys(gelirUretimMetin("tr")).sort()
    const en = Object.keys(gelirUretimMetin("en")).sort()
    expect(en).toEqual(tr)
  })
})
