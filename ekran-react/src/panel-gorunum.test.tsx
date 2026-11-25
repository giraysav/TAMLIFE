import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { Bolum, Panel } from "@/components/sayfa-ui"
import { Sidebar, SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { yaziDegistir, yaziOku, yaziUygula } from "@/lib/yazi"
import type { Kullanici } from "@/lib/oturum"
import { MusteriKarti } from "@/musteri/musteri-karti"
import type { Kart } from "@/musteri/musteri-karti"
import { KullaniciKarti } from "@/shell/kullanici-karti"
import { MusteriListesi } from "@/yonetim/utilizasyon/musteri-listesi"

beforeEach(() => {
  window.localStorage.clear()
  delete document.documentElement.dataset.yazi
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function sarmala(cocuk: ReactNode) {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
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
      if (anahtar === undefined) return new Response(JSON.stringify({ detail: "yok" }), { status: 404, headers: { "Content-Type": "application/json" } })
      return new Response(JSON.stringify({ status: "success", data: cevaplar[anahtar] }), { status: 200, headers: { "Content-Type": "application/json" } })
    }),
  )
  return cagrilar
}

describe("Gorunum olcegi (yazi boyutu)", () => {
  it("varsayilan 'buyuk'; secim <html data-yazi> ve tarayici deposuna yazilir", () => {
    expect(yaziOku()).toBe("buyuk")
    yaziUygula()
    expect(document.documentElement.dataset.yazi).toBe("buyuk")
    yaziDegistir("cok")
    expect(document.documentElement.dataset.yazi).toBe("cok")
    expect(window.localStorage.getItem("tamlife.yazi")).toBe("cok")
    expect(yaziOku()).toBe("cok")
    window.localStorage.setItem("tamlife.yazi", "gecersiz")
    expect(yaziOku()).toBe("buyuk")
  })

  it("hesap menusunde Yazi boyutu secenekleri var; secim uygulanir", () => {
    const kullanici: Kullanici = { username: "x", display_name: "X Y", profile: { username: "x", display_name: "X Y", ad_user: false, first_name: "X", last_name: "Y", phone: "", company: "", website: "" }, role: "TeamMember", is_admin: false, idle_timeout_minutes: 30, landing: "ozet", navigation: [] }
    render(<KullaniciKarti kullanici={kullanici} dil="tr" onDil={() => {}} onGit={() => {}} onCikis={() => {}} talepVar={false} />)
    fireEvent.click(screen.getByRole("button", { name: /Hesap menüsü/ }))
    const grup = screen.getByRole("group", { name: "Yazı boyutu" })
    expect(within(grup).getByRole("menuitemradio", { name: "Büyük" })).toHaveAttribute("aria-checked", "true")
    fireEvent.click(within(grup).getByRole("menuitemradio", { name: "Çok büyük" }))
    expect(document.documentElement.dataset.yazi).toBe("cok")
    expect(within(screen.getByRole("group", { name: "Yazı boyutu" })).getByRole("menuitemradio", { name: "Çok büyük" })).toHaveAttribute("aria-checked", "true")
  })
})

describe("Alan basliklari (Turkcell paleti)", () => {
  it("Bolum ve Panel basliklari ayni lacivert-mavi gradyanli bandi kullanir", () => {
    render(
      <>
        <Bolum anahtar="t-bolum" baslik="Birinci alan">
          <p>icerik</p>
        </Bolum>
        <Panel baslik="Ikinci alan" aciklama="alt not">
          <p>govde</p>
        </Panel>
      </>,
    )
    const bolumBandi = screen.getByRole("heading", { name: "Birinci alan" }).closest("summary")
    const panelBandi = screen.getByRole("heading", { name: "Ikinci alan" }).closest("div[class*='from-tl-navy']")
    for (const bant of [bolumBandi, panelBandi]) {
      expect(bant).not.toBeNull()
      expect(bant).toHaveClass("bg-gradient-to-r", "from-tl-navy", "to-tl-blue", "border-tl-yellow")
    }
    expect(screen.getByRole("heading", { name: "Birinci alan" })).toHaveClass("text-white", "uppercase")
  })
})

describe("TAM Utilizasyon > Musteri Listesi: personel filtresi", () => {
  const LISTE = {
    total: 5,
    items: [
      { id: 1, name: "Alfa A.Ş.", parent_id: null, parent_name: null, segment: "MA", owner_id: 7, owner: "Ayşe TAM", score: 72.5, affiliates: 1 },
      { id: 2, name: "Alfa Enerji", parent_id: 1, parent_name: "Alfa A.Ş.", segment: "MA", owner_id: 7, owner: "Ayşe TAM", score: null, affiliates: 0 },
      { id: 3, name: "Beta Telekom", parent_id: null, parent_name: null, segment: "SA", owner_id: 8, owner: "Can TAM", score: 10, affiliates: 0 },
      { id: 4, name: "Gama Gıda", parent_id: null, parent_name: null, segment: "", owner_id: null, owner: null, score: null, affiliates: 0 },
      { id: 5, name: "Delta Yapı", parent_id: null, parent_name: null, segment: "SMB", owner_id: 8, owner: "Can TAM", score: null, affiliates: 0 },
    ],
  }

  it("kisi secince yalniz o kisinin musterileri kalir; birden fazla kisi, Sorumlusuz ve temizleme calisir", async () => {
    sahteSunucu({ "/api/v1/yonetim/musteriler": LISTE })
    sarmala(<MusteriListesi dil="tr" />)
    await screen.findByText("Beta Telekom")
    expect(screen.getByText("5 müşteri")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Sorumlu TAM: Tüm personel" }))
    const grup = screen.getByRole("group", { name: "Sorumlu TAM" })
    // sayilarla birlikte: Ayse 2, Can 2, Sorumlusuz 1 (Sorumlusuz en sonda)
    const etiketler = within(grup).getAllByRole("checkbox").map((k) => k.closest("label")?.textContent)
    expect(etiketler).toEqual(["Ayşe TAM2", "Can TAM2", "Sorumlusuz1"])

    fireEvent.click(within(grup).getByRole("checkbox", { name: /Ayşe TAM/ }))
    expect(screen.getByText("2 / 5 müşteri")).toBeInTheDocument()
    expect(screen.queryByText("Beta Telekom")).toBeNull()
    expect(screen.getByRole("button", { name: "Sorumlu TAM: Ayşe TAM" })).toBeInTheDocument()

    fireEvent.click(within(grup).getByRole("checkbox", { name: /Sorumlusuz/ }))
    expect(screen.getByText("3 / 5 müşteri")).toBeInTheDocument()
    expect(screen.getByText("Gama Gıda")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Sorumlu TAM: 2 kişi" })).toBeInTheDocument()

    // "listelenen tumunu sec" yalniz suzulmus satirlari isaretler
    fireEvent.click(screen.getByRole("checkbox", { name: "Listelenen tüm müşterileri seç" }))
    expect(screen.getByText(/3 \/ 5 müşteri · 3 seçili/)).toBeInTheDocument()

    fireEvent.click(within(grup).getByRole("button", { name: "Filtreyi temizle" }))
    expect(screen.getByText(/5 müşteri · 3 seçili/)).toBeInTheDocument()
    expect(screen.getByText("Beta Telekom")).toBeInTheDocument()
  })

  it("filtre arama ile birlikte calisir (kesisim)", async () => {
    sahteSunucu({ "/api/v1/yonetim/musteriler": LISTE })
    sarmala(<MusteriListesi dil="tr" />)
    await screen.findByText("Beta Telekom")
    fireEvent.click(screen.getByRole("button", { name: "Sorumlu TAM: Tüm personel" }))
    fireEvent.click(within(screen.getByRole("group", { name: "Sorumlu TAM" })).getByRole("checkbox", { name: /Can TAM/ }))
    fireEvent.change(screen.getByPlaceholderText("Müşteri ara…"), { target: { value: "delta" } })
    expect(screen.getByText("1 / 5 müşteri")).toBeInTheDocument()
    expect(screen.getByText("Delta Yapı")).toBeInTheDocument()
    expect(screen.queryByText("Beta Telekom")).toBeNull()
  })
})

describe("Musteri karti: tek cerceve, dugmeler, Operasyon penceresi", () => {
  const KART: Kart = {
    kimlik: { id: 9, unvan: "112 ACIL SERVIS", musteri_no: "M-1", ncst: "N-1", segment: "SA", sektor: "Kamu", envanter: 12, tam: "Ayşe TAM", tam_id: 7, ayri_rapor: null, rapor_muaf: false, cati: null, istirakler: [] },
    operasyon: { ft_hacim: "1.5 M", tam_ft: "0.5 M", final_skor: 81.25, skor_talebi_bekliyor: false, kendi: { envanter: 12, alarm: 0, sikayet: 0, talep: 0, alarm_kapanan: 11, sikayet_kapanan: 2, talep_kapanan: 33 }, istirak_dahil: null },
    iletisim: { sales_manager: "Selin Satış", presales_manager: "Pelin Pre", tac_name: "Tolga TAC", tac_gsm: "0532 111 22 33", tac_email: "tac@example.com", sol_kmt_name: "", sol_kmt_gsm: "", sol_kmt_email: "", mobil_kmt_name: "Mehmet Mobil", mobil_kmt_gsm: "", mobil_kmt_email: "", mobil_kmt_detail: "Hafta sonu ulaşılamaz" },
    kritik_ci: { basliklar: ["Müşteri", "CI Adı"], satirlar: [["112 ACIL SERVIS", "Core Router 1"]] },
    raporlar: { toplam: 0, son: [] },
    erisim: { rapor: true, gelir: true, kimlik_duzenle: true, iletisim_duzenle: true, sil: true, tam_degistir: false, rapor_geri_al: true, ayri_rapor_sec: true, rapor_muaf_sec: true, istirak_ekle: true },
  }

  it("Ekip (Destech), Gelirler ve Izleme (Cacti, 2026-10-26 tamamen kalkti) yok; ekip ve iletisim musteri bilgileriyle ayni cercevede", async () => {
    sahteSunucu({ "/api/v1/musteri/9": { ...KART, ekip: { basliklar: ["Ad"], satirlar: [["x"]] }, gelirler: { ict: { toplam: {}, son: [] } } } })
    sarmala(<MusteriKarti id={9} dil="tr" />)
    const baslik = await screen.findByRole("heading", { name: "112 ACIL SERVIS", level: 2 })
    expect(baslik).toBeInTheDocument()
    for (const yok of ["Ekip (Destech)", "Gelirler", "İzleme (Cacti)"]) expect(screen.queryByText(yok)).toBeNull()

    const kimlik = screen.getByText("Müşteri No").closest("div.rounded-xl") as HTMLElement
    expect(kimlik).not.toBeNull()
    expect(within(kimlik).getByText("Ayşe TAM")).toBeInTheDocument() // sorumlu TAM
    expect(within(kimlik).getByRole("heading", { name: "Ekip & İletişim" })).toBeInTheDocument()
    expect(within(kimlik).getByText("Tolga TAC")).toBeInTheDocument()
    expect(within(kimlik).getByRole("link", { name: "tac@example.com" })).toHaveAttribute("href", "mailto:tac@example.com")
    expect(within(kimlik).getByRole("link", { name: "0532 111 22 33" })).toHaveAttribute("href", "tel:0532 111 22 33")
    expect(within(kimlik).getByText("Selin Satış")).toBeInTheDocument()
    expect(within(kimlik).getByText(/Hafta sonu ulaşılamaz/)).toBeInTheDocument()
  })

  it("Aylik Rapor dugmesi buyuk sari baglanti; CI NAME ve Topo Maker Duzenle / Iştirak ekle / Sil ile ayni satirda", async () => {
    sahteSunucu({ "/api/v1/musteri/9": KART })
    sarmala(<MusteriKarti id={9} dil="tr" />)
    await screen.findByRole("heading", { name: "112 ACIL SERVIS", level: 2 })
    const rapor = screen.getByRole("link", { name: /Aylık Rapor Gönder/ })
    expect(rapor).toHaveAttribute("href", "#/musteri?m=9&sekme=rapor")
    expect(rapor).toHaveClass("from-tl-yellow")

    const duzenle = screen.getByRole("button", { name: "Düzenle" })
    const satir = duzenle.parentElement as HTMLElement
    expect(within(satir).getByRole("button", { name: /İştirak ekle/ })).toBeInTheDocument()
    expect(within(satir).getByRole("button", { name: /CI NAME/ })).toBeInTheDocument()
    expect(within(satir).getByRole("link", { name: /Topo Maker/ })).toHaveAttribute("href", "#/musteri?m=9&sekme=topoloji")
    expect(within(satir).getByRole("button", { name: /Müşteriyi sil/ })).toBeInTheDocument()
  })

  it("2026-10-31: sil dugmesi personelde 'Musteri silme onayina gonder'; admin'e talep gider", async () => {
    const cagrilar = sahteSunucu({
      "/api/v1/musteri/9/silme-talebi": { zaten: false, bildirilen: 1 },
      "/api/v1/musteri/9": { ...KART, erisim: { ...KART.erisim, sil: false, sil_talebi: true } },
    })
    vi.stubGlobal("confirm", vi.fn(() => true))
    sarmala(<MusteriKarti id={9} dil="tr" />)
    await screen.findByRole("heading", { name: "112 ACIL SERVIS", level: 2 })
    expect(screen.queryByRole("button", { name: /Müşteriyi sil/ })).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: /Müşteri silme onayına gönder/ }))
    expect(await screen.findByText("Silme talebi admin'e iletildi.")).toBeInTheDocument()
    expect(cagrilar.some((c) => c.yontem === "POST" && c.yol.endsWith("/api/v1/musteri/9/silme-talebi"))).toBe(true)
    expect(cagrilar.some((c) => c.yontem === "DELETE")).toBe(false)
  })

  it("2026-10-31: istirakler kapaliyken ilk 6 + '+N'; acilinca aranabilir izgara (NCST / TAM ile)", async () => {
    const istirakler = Array.from({ length: 10 }, (_, i) => ({ id: 100 + i, unvan: `AKSA ${["ADANA", "BURSA", "CORUM", "DUZCE", "ELAZIG", "GEBZE", "HATAY", "IZMIR", "KARS", "MUS"][i]} DOGALGAZ`, ncst: `N-${i}`, tam: "Ayşe TAM" }))
    sahteSunucu({ "/api/v1/musteri/9": { ...KART, kimlik: { ...KART.kimlik, istirakler } } })
    sarmala(<MusteriKarti id={9} dil="tr" />)
    await screen.findByRole("heading", { name: "112 ACIL SERVIS", level: 2 })
    expect(screen.getByRole("link", { name: "AKSA ADANA DOGALGAZ" })).toHaveAttribute("href", "#/musteri?m=100")
    expect(screen.queryByRole("link", { name: /AKSA HATAY/ })).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "+4 iştirak" }))
    expect(screen.getByRole("link", { name: /AKSA HATAY DOGALGAZ/ })).toHaveTextContent("N-6 · Ayşe TAM")
    fireEvent.change(screen.getByLabelText("İştirak ara…"), { target: { value: "izmir" } })
    expect(screen.getAllByRole("link", { name: /^AKSA / })).toHaveLength(1)
    fireEvent.click(screen.getByRole("button", { name: "Daralt" }))
    expect(screen.queryByLabelText("İştirak ara…")).toBeNull()
  })

  it("Duzenle formu arka plan yenilemesinde yazilani korur; Vazgec sonrasi sunucu degerine doner", async () => {
    sahteSunucu({ "/api/v1/musteri/9": KART })
    const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={istemci}>
        <MusteriKarti id={9} dil="tr" />
      </QueryClientProvider>,
    )
    await screen.findByRole("heading", { name: "112 ACIL SERVIS", level: 2 })
    fireEvent.click(screen.getByRole("button", { name: "Düzenle" }))
    const unvan = () => document.querySelector<HTMLInputElement>("#k-name") as HTMLInputElement
    expect(unvan().value).toBe("112 ACIL SERVIS")
    fireEvent.change(unvan(), { target: { value: "YAZILAN AD" } })
    await act(() => istemci.refetchQueries({ queryKey: ["musteri", "kart", 9] }))
    expect(unvan().value).toBe("YAZILAN AD")
    fireEvent.click(screen.getByRole("button", { name: "Vazgeç" }))
    fireEvent.click(screen.getByRole("button", { name: "Düzenle" }))
    expect(unvan().value).toBe("112 ACIL SERVIS")
  })

  it("Duzenle: istirak secilince cati alani acilir ve secilen iliski kaydedilir", async () => {
    const cagrilar = sahteSunucu({
      "/api/v1/musteri/9/iletisim": { ok: true },
      "/api/v1/musteri/9/kimlik": { ok: true },
      "/api/v1/musteri/9": { ...KART, cati_secenekleri: [{ id: 8, ad: "TEST CATI" }] },
    })
    sarmala(<MusteriKarti id={9} dil="tr" />)
    await screen.findByRole("heading", { name: "112 ACIL SERVIS", level: 2 })
    fireEvent.click(screen.getByRole("button", { name: "Düzenle" }))
    const form = screen.getByRole("form", { name: "Düzenle" })
    expect(within(form).getByRole("combobox", { name: "Müşteri türü" })).toHaveValue("cati")
    expect(within(form).queryByRole("combobox", { name: "Çatı müşteri" })).toBeNull()
    fireEvent.change(within(form).getByRole("combobox", { name: "Müşteri türü" }), { target: { value: "istirak" } })
    const cati = within(form).getByRole("combobox", { name: "Çatı müşteri" })
    expect(cati).toBeRequired()
    expect(cati).toHaveValue("")
    fireEvent.change(cati, { target: { value: "8" } })
    fireEvent.click(within(form).getByRole("button", { name: "Kaydet" }))
    await waitFor(() => expect(cagrilar.find((c) => c.yontem === "PUT" && c.yol.endsWith("/kimlik"))?.govde).toMatchObject({ parent_id: 8 }))
  })

  it("Mevcut istirakin catisi secili gelir; catiya donuste parent_id null gonderilir", async () => {
    const cagrilar = sahteSunucu({
      "/api/v1/musteri/9/iletisim": { ok: true },
      "/api/v1/musteri/9/kimlik": { ok: true },
      "/api/v1/musteri/9": { ...KART, kimlik: { ...KART.kimlik, cati: { id: 8, unvan: "TEST CATI" } }, cati_secenekleri: [{ id: 8, ad: "TEST CATI" }] },
    })
    sarmala(<MusteriKarti id={9} dil="tr" />)
    await screen.findByRole("heading", { name: "112 ACIL SERVIS", level: 2 })
    fireEvent.click(screen.getByRole("button", { name: "Düzenle" }))
    const form = screen.getByRole("form", { name: "Düzenle" })
    expect(within(form).getByRole("combobox", { name: "Müşteri türü" })).toHaveValue("istirak")
    expect(within(form).getByRole("combobox", { name: "Çatı müşteri" })).toHaveValue("8")
    fireEvent.change(within(form).getByRole("combobox", { name: "Müşteri türü" }), { target: { value: "cati" } })
    expect(within(form).queryByRole("combobox", { name: "Çatı müşteri" })).toBeNull()
    fireEvent.click(within(form).getByRole("button", { name: "Kaydet" }))
    await waitFor(() => expect(cagrilar.find((c) => c.yontem === "PUT" && c.yol.endsWith("/kimlik"))?.govde).toMatchObject({ parent_id: null }))
  })

  it("CI NAME dugmesi CI listesini cekmecede acar", async () => {
    sahteSunucu({ "/api/v1/musteri/9": KART })
    sarmala(<MusteriKarti id={9} dil="tr" />)
    await screen.findByRole("heading", { name: "112 ACIL SERVIS", level: 2 })
    expect(screen.queryByText("Core Router 1")).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: /CI NAME/ }))
    const pencere = await screen.findByRole("dialog")
    expect(within(pencere).getByText("Core Router 1")).toBeInTheDocument()
    fireEvent.click(within(pencere).getByRole("button", { name: "Kapat" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
  })

  it("Operasyon: Alarm, Talep, Sikayet acik / yil ici kapanan dugmeleri; tiklayinca o kayitlar listelenir, ikinci tiklama kapatir", async () => {
    const cagrilar = sahteSunucu({
      "/api/v1/musteri/9/kayitlar": { tur: "talep", durum: "kapali", yil: 2026, toplam: 0, sayfa: 1, adet: 10, kayitlar: [] },
      "/api/v1/musteri/9": KART,
    })
    sarmala(<MusteriKarti id={9} dil="tr" />)
    await screen.findByRole("heading", { name: "112 ACIL SERVIS", level: 2 })
    const pencere = screen.getByRole("region", { name: "Operasyon" })
    expect(pencere).toHaveClass("rounded-2xl", "from-tl-navy", "to-tl-blue")
    const kutular = ["Alarm", "Talep", "Şikayet"].map((e) => within(pencere).getByText(e).parentElement?.textContent)
    expect(kutular).toEqual(["Alarm0/11", "Talep0/33", "Şikayet0/2"])
    expect(screen.queryByRole("region", { name: /kapanan talep kayıtları/ })).toBeNull() // kapanan tablosu varsayilan yok
    const dugme = within(pencere).getByRole("button", { name: "Talep: Yıl içi kapanan 33" })
    fireEvent.click(dugme)
    expect(dugme).toHaveAttribute("aria-pressed", "true")
    expect(await screen.findByRole("region", { name: "2026 yılında kapanan talep kayıtları" })).toBeTruthy()
    expect(cagrilar.some((c) => c.yol.includes("/api/v1/musteri/9/kayitlar?tur=talep&durum=kapali"))).toBe(true)
    fireEvent.click(dugme)
    expect(screen.queryByRole("region", { name: /kapanan talep kayıtları/ })).toBeNull()
  })

  it("Duzenle tek formu acar (kimlik + ekip ve iletisim); tek Kaydet once iletisimi sonra kimligi gonderir", async () => {
    const cagrilar = sahteSunucu({ "/api/v1/musteri/9/iletisim": { ok: true }, "/api/v1/musteri/9/kimlik": { ok: true }, "/api/v1/musteri/9": KART })
    sarmala(<MusteriKarti id={9} dil="tr" />)
    await screen.findByRole("heading", { name: "112 ACIL SERVIS", level: 2 })
    fireEvent.click(screen.getByRole("button", { name: "Düzenle" }))
    const form = screen.getByRole("form", { name: "Düzenle" })
    fireEvent.change(within(form).getByLabelText("NCST"), { target: { value: "N-77" } })
    fireEvent.change(within(form).getByLabelText("TAC · E-posta"), { target: { value: "yeni@example.com" } })
    fireEvent.click(within(form).getByRole("button", { name: "Kaydet" }))

    await waitFor(() => expect(screen.queryByRole("form", { name: "Düzenle" })).toBeNull())
    const yazmalar = cagrilar.filter((c) => c.yontem === "PUT")
    expect(yazmalar.map((c) => c.yol.replace(/^.*\/musteri\/9/, ""))).toEqual(["/iletisim", "/kimlik"])
    expect((yazmalar[0]!.govde as Record<string, string>).tac_email).toBe("yeni@example.com")
    expect((yazmalar[1]!.govde as Record<string, string>).ncst).toBe("N-77")
  })

  it("iletisim reddedilirse kimlik gonderilmez ve form acik kalir", async () => {
    const cagrilar: Cagri[] = []
    vi.stubGlobal(
      "fetch",
      vi.fn(async (girdi: string, ayar?: RequestInit) => {
        cagrilar.push({ yol: String(girdi), yontem: ayar?.method ?? "GET", govde: null })
        if (String(girdi).endsWith("/iletisim")) return new Response(JSON.stringify({ detail: "E-posta geçersiz" }), { status: 422, headers: { "Content-Type": "application/json" } })
        return new Response(JSON.stringify({ status: "success", data: KART }), { status: 200, headers: { "Content-Type": "application/json" } })
      }),
    )
    sarmala(<MusteriKarti id={9} dil="tr" />)
    await screen.findByRole("heading", { name: "112 ACIL SERVIS", level: 2 })
    fireEvent.click(screen.getByRole("button", { name: "Düzenle" }))
    const form = screen.getByRole("form", { name: "Düzenle" })
    fireEvent.change(within(form).getByLabelText("TAC · E-posta"), { target: { value: "a@b" } })
    fireEvent.click(within(form).getByRole("button", { name: "Kaydet" }))
    expect(await within(form).findByRole("status")).toHaveTextContent(/Kaydedilemedi|geçersiz/i)
    expect(cagrilar.some((c) => c.yontem === "PUT" && c.yol.endsWith("/kimlik"))).toBe(false)
    expect(screen.getByRole("form", { name: "Düzenle" })).toBeInTheDocument()
  })
})

describe("kabuk kaydirmasi", () => {
  it("kabuk sayfaya sabit: belgeyi uzatan mutlak konumlu oge (sr-only) ikinci kaydirma cubugu acmaz, yan menu hareket etmez", () => {
    vi.stubGlobal("matchMedia", (sorgu: string) => ({ matches: false, media: sorgu, addEventListener: () => undefined, removeEventListener: () => undefined }))
    render(
      <SidebarProvider>
        <Sidebar>menu</Sidebar>
        <SidebarInset>
          <table>
            <caption className="sr-only">Ekip Özeti</caption>
          </table>
        </SidebarInset>
      </SidebarProvider>,
    )
    const icerik = screen.getByRole("main")
    expect(icerik).toHaveClass("relative", "overflow-auto") // mutlak konumlu ogeler icerigin icinde kalir, kaydiran tek yer
    const kabuk = icerik.parentElement as HTMLElement
    expect(kabuk).toHaveClass("relative", "overflow-hidden", "h-full") // belge hic kaymaz: yan menu ve kullanici karti sabit
  })
})
