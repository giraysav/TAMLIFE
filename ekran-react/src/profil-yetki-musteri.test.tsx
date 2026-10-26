import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { Kullanici } from "@/lib/oturum"
import { ImzaEditoru } from "@/shell/imza-editoru"
import { ProfilSayfasi } from "@/shell/profil-sayfasi"
import { RollerSayfasi } from "@/shell/roller-sayfasi"
import { MusteriListesi, satirlariAyir } from "@/yonetim/utilizasyon/musteri-listesi"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function sarmala(cocuk: ReactNode) {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={istemci}>{cocuk}</QueryClientProvider>)
}

type Cagri = { yol: string; yontem: string; govde: unknown }
type Cevap = unknown

/** fetch'i yola gore cevaplar ({yol parcasi: data}, ilk eslesen); cagrilarin yontem ve govdesini kaydeder. */
function sahteSunucu(cevaplar: Record<string, Cevap>): Cagri[] {
  const cagrilar: Cagri[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn(async (girdi: string, ayar?: RequestInit) => {
      cagrilar.push({ yol: String(girdi), yontem: ayar?.method ?? "GET", govde: typeof ayar?.body === "string" ? JSON.parse(ayar.body) : null })
      const anahtar = Object.keys(cevaplar).find((k) => String(girdi).includes(k))
      if (anahtar === undefined) return new Response(JSON.stringify({ detail: "yok" }), { status: 404, headers: { "Content-Type": "application/json" } })
      const cevap = cevaplar[anahtar] as { __durum?: number; detail?: string }
      if (cevap && typeof cevap === "object" && "__durum" in cevap) {
        return new Response(JSON.stringify({ detail: cevap.detail }), { status: cevap.__durum, headers: { "Content-Type": "application/json" } })
      }
      return new Response(JSON.stringify({ status: "success", data: cevaplar[anahtar] }), { status: 200, headers: { "Content-Type": "application/json" } })
    }),
  )
  return cagrilar
}

const PROFIL = { username: "gsav", display_name: "Giray Sav", ad_user: true, first_name: "Giray", last_name: "Sav", phone: "", company: "", website: "" }
const KULLANICI: Kullanici = { username: "gsav", display_name: "Giray Sav", profile: PROFIL, role: "TeamMember", is_admin: false, idle_timeout_minutes: 30, landing: "ozet", navigation: [] }

describe("Profil: kisi kendi bilgilerini duzenler", () => {
  it("AD kullanici adi kilitli; diger alanlar duzenlenir, kaydet yalniz degisince acilir ve PUT gonderir", async () => {
    const cagrilar = sahteSunucu({ "/api/v1/session/profile": { ...PROFIL, phone: "+90 532 000 00 00", company: "Teknocan", display_name: "Giray Sav" } })
    const onKaydedildi = vi.fn()
    sarmala(<ProfilSayfasi kullanici={KULLANICI} dil="tr" onKaydedildi={onKaydedildi} />)

    const kullaniciAdi = screen.getByLabelText("Kullanıcı adı (AD/LDAP)")
    expect(kullaniciAdi).toHaveValue("gsav")
    expect(kullaniciAdi).toBeDisabled()
    expect(screen.getByLabelText("Ad")).toHaveValue("Giray")
    expect(screen.getByLabelText("Soyad")).toHaveValue("Sav")

    const kaydet = screen.getByRole("button", { name: "Kaydet" })
    expect(kaydet).toBeDisabled()
    fireEvent.change(screen.getByLabelText("Telefon"), { target: { value: "+90 532 000 00 00" } })
    fireEvent.change(screen.getByLabelText("Şirket"), { target: { value: "Teknocan" } })
    fireEvent.change(screen.getByLabelText("Web adresi"), { target: { value: "teknocan.com" } })
    expect(screen.queryByLabelText("Adres")).toBeNull() // 2026-10-26: adres alani kalkti (yerine e-posta imzasi)
    expect(kaydet).toBeEnabled()
    fireEvent.click(kaydet)

    expect(await screen.findByText("Profil kaydedildi.")).toBeInTheDocument()
    const put = cagrilar.find((c) => c.yontem === "PUT")
    expect(put?.yol).toContain("/api/v1/session/profile")
    // Kullanici adi ve rol govdeye girmez: yalniz kisinin duzenleyebildigi alanlar gider.
    expect(put?.govde).toEqual({ first_name: "Giray", last_name: "Sav", phone: "+90 532 000 00 00", company: "Teknocan", website: "teknocan.com" })
    expect(onKaydedildi).toHaveBeenCalledTimes(1)
    expect(screen.getByRole("button", { name: "Kaydet" })).toBeDisabled() // sunucunun dondurdugu deger artik "kayitli"
  })

  it("sunucu reddederse hata metni gosterilir ve oturum yenilenmez", async () => {
    sahteSunucu({ "/api/v1/session/profile": { __durum: 400, detail: "Telefon numarası geçersiz." } })
    const onKaydedildi = vi.fn()
    sarmala(<ProfilSayfasi kullanici={KULLANICI} dil="tr" onKaydedildi={onKaydedildi} />)
    fireEvent.change(screen.getByLabelText("Telefon"), { target: { value: "abc" } })
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }))
    expect(await screen.findByText("Telefon numarası geçersiz.")).toBeInTheDocument()
    expect(onKaydedildi).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "Kaydet" })).toBeEnabled() // duzeltip yeniden denenebilir
  })

  it("hesap bilgileri karti salt okunur kalir", () => {
    sarmala(<ProfilSayfasi kullanici={KULLANICI} dil="tr" />)
    expect(screen.getByText("Hesap bilgileri")).toBeInTheDocument()
    expect(screen.getByText("Member")).toBeInTheDocument()
    expect(screen.getByText("Standart")).toBeInTheDocument()
  })
})

describe("Roller: acilip kapanan rol kutulari, roldeki personel ve kisi bazli sunum yetkisi", () => {
  const ROLLER = {
    catalog: [
      { id: "sunum", label: "Çeyrek Sunum", label_en: "Quarterly Presentation", admin_only: false, children: [] },
      { id: "takvim", label: "TAM Takvim", label_en: "TAM Calendar", admin_only: false, children: [] },
    ],
    permission_catalog: [
      {
        id: "sunum.gonder",
        label: "Çeyrek sunumu yönet",
        label_en: "Manage the quarterly presentation",
        description: "Sunuma öğe gönderebilir",
        description_en: "Can send items",
        where: "TAM Takvim › grafik",
        where_en: "TAM Calendar › chart",
        area: "sunum",
      },
    ],
    roles: [
      { role: "admin", label: "Admin", editable: false, modules: ["sunum", "takvim"], landing: "ozet", permissions: ["sunum.gonder"], saved: false },
      { role: "TeamMngr", label: "Manager", editable: true, modules: ["sunum"], landing: "ozet", permissions: ["sunum.gonder"], saved: true },
      { role: "TeamMember", label: "Member", editable: true, modules: ["takvim"], landing: "ozet", permissions: [], saved: true },
    ],
    users: [
      { id: 1, username: "ladinadmin", display_name: "Ladin Admin", role: "admin", auth: "AD", ad_domain: "TURKCELL", last_login_at: "2026-10-12T08:30:00+00:00", permissions: [] },
      { id: 2, username: "mudur1", display_name: "Mehmet Müdür", role: "TeamMngr", auth: "AD", ad_domain: "TURKCELL", last_login_at: null, permissions: [] },
      { id: 3, username: "gsav", display_name: "Giray Sav", role: "TeamMember", auth: "AD", ad_domain: "TURKCELL", last_login_at: "2026-10-11T07:00:00+00:00", permissions: [] },
      { id: 4, username: "yerel1", display_name: "Yerel Kişi", role: "TeamMember", auth: "Yerel", ad_domain: "", last_login_at: null, permissions: ["sunum.gonder"] },
    ],
  }
  const SUNUCU = { "/api/v1/sunum/kaynaklar": { duzenleyebilir: true, kaynaklar: [] } }

  it("rol kutulari kapali gelir, basliga tiklayinca acilir; icinde o roldeki AD personeli listelenir", async () => {
    sahteSunucu({ "/api/v1/roller": ROLLER, ...SUNUCU })
    sarmala(<RollerSayfasi dil="tr" />)
    const member = await screen.findByRole("button", { name: /Member/ })
    expect(member).toHaveAttribute("aria-expanded", "false")
    expect(screen.queryByText(/^Göreceği sayfalar/)).toBeNull()
    expect(screen.queryByText("Giray Sav", { selector: "span.truncate.font-medium" })).toBeNull()
    // Baslik sayfa ve kisi sayisini kapali iken de gosterir.
    expect(within(member).getByText("2 kişi")).toBeInTheDocument()
    expect(within(member).getByText("1 sayfa")).toBeInTheDocument()

    fireEvent.click(member)
    expect(member).toHaveAttribute("aria-expanded", "true")
    const bolge = screen.getByRole("region", { name: /Member/ })
    expect(within(bolge).getByText(/^Göreceği sayfalar/)).toBeInTheDocument()
    expect(within(bolge).getByText("Bu roldeki personel (2)")).toBeInTheDocument()
    expect(within(bolge).getByText("Giray Sav")).toBeInTheDocument()
    expect(within(bolge).getByText("gsav")).toBeInTheDocument() // AD kullanici adi
    expect(within(bolge).getByText("AD hesabı")).toBeInTheDocument()
    expect(within(bolge).getByText("Yerel hesap")).toBeInTheDocument()
    expect(within(bolge).getAllByText("Henüz girmedi").length).toBeGreaterThan(0)

    fireEvent.click(member)
    expect(member).toHaveAttribute("aria-expanded", "false")
    expect(screen.queryByRole("region", { name: /Member/ })).toBeNull()
  })

  it("admin kutusu sabit gorunumu anlatir ve roldeki kisiyi gosterir; eski sunucu (users yok) bozulmaz", async () => {
    sahteSunucu({ "/api/v1/roller": { ...ROLLER, users: undefined }, ...SUNUCU })
    sarmala(<RollerSayfasi dil="tr" />)
    const admin = await screen.findByRole("button", { name: /Admin/ })
    fireEvent.click(admin)
    expect(screen.getByText("Admin tüm sayfaları görür, tüm ek yetkilere sahiptir ve bu görünüm değiştirilemez.")).toBeInTheDocument()
    expect(screen.getByText("Bu rolde henüz personel yok. AD ile ilk girişte kişi Member olarak eklenir.")).toBeInTheDocument()
  })

  it("Ceyrek Sunum yanindaki acilir listede personel onay kutulariyla secilir ve kisiye ozel yetki kaydedilir", async () => {
    const cagrilar = sahteSunucu({
      "/api/v1/roller/kisiler/3": { id: 3, permissions: ["sunum.gonder"] },
      "/api/v1/roller": ROLLER,
      ...SUNUCU,
    })
    sarmala(<RollerSayfasi dil="tr" />)
    const dugme = await screen.findByRole("button", { name: /Yetkili personel/ })
    expect(dugme).toHaveAttribute("aria-expanded", "false")
    // Admin + Manager (rolden) + yerel1 (kisiye ozel) = 3 yetkili.
    expect(within(dugme).getByText("3")).toBeInTheDocument()

    fireEvent.click(dugme)
    const liste = screen.getByRole("group", { name: "Yetkili personel" })
    const admin = within(liste).getByRole("checkbox", { name: "Ladin Admin" })
    expect(admin).toBeChecked()
    expect(admin).toBeDisabled() // admin her zaman yetkili
    const mudur = within(liste).getByRole("checkbox", { name: "Mehmet Müdür" })
    expect(mudur).toBeChecked()
    expect(mudur).toBeDisabled() // Manager rolune verilmis yetki role dahil herkese gecer
    expect(within(liste).getByText("Rolden: Manager")).toBeInTheDocument()
    expect(within(liste).getByRole("checkbox", { name: "Yerel Kişi" })).toBeChecked()

    fireEvent.change(within(liste).getByPlaceholderText("Personel ara…"), { target: { value: "giray" } })
    expect(within(liste).queryByRole("checkbox", { name: "Ladin Admin" })).toBeNull()
    const giray = within(liste).getByRole("checkbox", { name: "Giray Sav" })
    expect(giray).not.toBeChecked()
    fireEvent.click(giray)

    await waitFor(() => expect(within(liste).getByRole("checkbox", { name: "Giray Sav" })).toBeChecked())
    const put = cagrilar.find((c) => c.yontem === "PUT")
    expect(put?.yol).toContain("/api/v1/roller/kisiler/3")
    expect(put?.govde).toEqual({ permissions: ["sunum.gonder"] })
    expect(within(dugme).getByText("4")).toBeInTheDocument()

    fireEvent.keyDown(document, { key: "Escape" })
    expect(screen.queryByRole("group", { name: "Yetkili personel" })).toBeNull()
  })

  const SILEBILEN = { ...ROLLER, can_delete_users: true, delete_account: "admin", users: ROLLER.users.map((u) => ({ ...u, deletable: u.username !== "ladinadmin" })) }

  it("kullanici silme: dugme yalniz silme yetkilisinde; onay sorar, vazgec silmez, onaylayinca DELETE gider ve satir listeden duser", async () => {
    const cagrilar = sahteSunucu({
      "/api/v1/roller/kisiler/3": { id: 3, username: "gsav", display_name: "Giray Sav", devredilen: 2, bosaltilan: 1, silinen: 0 },
      "/api/v1/roller": SILEBILEN,
      ...SUNUCU,
    })
    sarmala(<RollerSayfasi dil="tr" />)
    fireEvent.click(await screen.findByRole("button", { name: /Admin/ }))
    expect(screen.queryByRole("button", { name: /Kullanıcıyı sil/ })).toBeNull() // kendi hesabi (ladinadmin) silinemez: dugme yok
    fireEvent.click(screen.getByRole("button", { name: /Admin/ }))

    const member = screen.getByRole("button", { name: /Member/ })
    fireEvent.click(member)
    const bolge = screen.getByRole("region", { name: /Member/ })
    fireEvent.click(within(bolge).getByRole("button", { name: "Kullanıcıyı sil: Giray Sav" }))
    expect(within(bolge).getByRole("alert")).toHaveTextContent("Giray Sav (gsav) silinsin mi?")
    expect(within(bolge).getByRole("alert")).toHaveTextContent("AD'de hesabı varsa")
    fireEvent.click(within(bolge).getByRole("button", { name: "Vazgeç" }))
    expect(within(bolge).queryByRole("alert")).toBeNull()
    expect(cagrilar.some((c) => c.yontem === "DELETE")).toBe(false)

    fireEvent.click(within(bolge).getByRole("button", { name: "Kullanıcıyı sil: Giray Sav" }))
    fireEvent.click(within(bolge).getByRole("button", { name: "Evet, sil" }))
    expect(await screen.findByText("Giray Sav silindi. 2 kayıt size devredildi.")).toBeInTheDocument()
    expect(cagrilar.find((c) => c.yontem === "DELETE")?.yol).toContain("/api/v1/roller/kisiler/3")
    expect(within(screen.getByRole("region", { name: /Member/ })).queryByText("gsav")).toBeNull()
    expect(within(member).getByText("1 kişi")).toBeInTheDocument()
    expect(within(screen.getByRole("region", { name: /Member/ })).getByText("Yerel Kişi")).toBeInTheDocument() // digerleri yerinde
  })

  it("kullanici silme: sunucu reddederse hata onay kutusunda gorunur ve kisi listede kalir", async () => {
    sahteSunucu({
      "/api/v1/roller/kisiler/3": { __durum: 403, detail: "Kullanıcı silme yetkisi yalnızca 'admin' hesabındadır." },
      "/api/v1/roller": SILEBILEN,
      ...SUNUCU,
    })
    sarmala(<RollerSayfasi dil="tr" />)
    fireEvent.click(await screen.findByRole("button", { name: /Member/ }))
    const bolge = screen.getByRole("region", { name: /Member/ })
    fireEvent.click(within(bolge).getByRole("button", { name: "Kullanıcıyı sil: Giray Sav" }))
    fireEvent.click(within(bolge).getByRole("button", { name: "Evet, sil" }))
    expect(await within(bolge).findByText("Kullanıcı silme yetkisi yalnızca 'admin' hesabındadır.")).toBeInTheDocument()
    expect(within(bolge).getByText("gsav")).toBeInTheDocument()
    expect(within(bolge).getByRole("button", { name: "Evet, sil" })).toBeEnabled() // yeniden denenebilir
  })

  it("silme yetkisi olmayan admin: dugme yok, sayfa silme yetkisinin hangi hesapta oldugunu soyler", async () => {
    sahteSunucu({
      "/api/v1/roller": { ...ROLLER, can_delete_users: false, delete_account: "admin", users: ROLLER.users.map((u) => ({ ...u, deletable: false })) },
      ...SUNUCU,
    })
    sarmala(<RollerSayfasi dil="tr" />)
    expect(await screen.findByText("Kullanıcı silme yalnız 'admin' hesabına açıktır.")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /Member/ }))
    expect(screen.queryByRole("button", { name: /Kullanıcıyı sil/ })).toBeNull()
    expect(screen.getByText("Giray Sav")).toBeInTheDocument()
  })
})

describe("Musteri Listesi: toplu ekleme ve silme", () => {
  const LISTE = {
    total: 4,
    items: [
      { id: 1, name: "Alfa A.Ş.", parent_id: null, parent_name: null, segment: "MA", owner: "Ayşe TAM", score: 72.5, affiliates: 2 },
      { id: 2, name: "Alfa Enerji", parent_id: 1, parent_name: "Alfa A.Ş.", segment: "MA", owner: "Ayşe TAM", score: null, affiliates: 0 },
      { id: 3, name: "Alfa Yazılım", parent_id: 1, parent_name: "Alfa A.Ş.", segment: "MA", owner: "Ayşe TAM", score: 10, affiliates: 0 },
      { id: 4, name: "Beta Telekom", parent_id: null, parent_name: null, segment: "", owner: null, score: null, affiliates: 0 },
    ],
  }

  it("satirlariAyir: Unvan, 'Unvan; Segment' ve Excel'den gelen sekmeli iki sutun; bos satirlar atilir", () => {
    const sonuc = satirlariAyir("Alfa Teknoloji A.Ş.; MA\r\n\r\n  Beta Telekom  \nGama\tKA\nDelta; Ltd.; SMB")
    expect(sonuc.map((s) => [s.name, s.segment])).toEqual([
      ["Alfa Teknoloji A.Ş.", "MA"],
      ["Beta Telekom", undefined],
      ["Gama", "KA"],
      ["Delta; Ltd.", "SMB"], // son noktali virgul segmenti ayirir
    ])
    expect(satirlariAyir("   \n ; \n")).toEqual([])
  })

  it("tum musteriler agac sirasiyla listelenir; arama suzer; ustteki kutu listelenenleri secer", async () => {
    sahteSunucu({ "/api/v1/yonetim/musteriler": LISTE })
    sarmala(<MusteriListesi dil="tr" />)
    expect(await screen.findByRole("checkbox", { name: "Alfa A.Ş. müşterisini seç" })).toBeInTheDocument()
    expect(screen.getByText("4 müşteri")).toBeInTheDocument()
    expect(screen.getByText("Çatı · 2 iştirak")).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText("Müşteri ara…"), { target: { value: "enerji" } })
    expect(screen.getByText("1 / 4 müşteri")).toBeInTheDocument()
    expect(screen.queryByText("Beta Telekom")).toBeNull()
    fireEvent.click(screen.getByRole("checkbox", { name: "Listelenen tüm müşterileri seç" }))
    expect(screen.getByRole("checkbox", { name: "Alfa Enerji müşterisini seç" })).toBeChecked()
    expect(screen.getByText(/1 \/ 4 müşteri · 1 seçili/)).toBeInTheDocument()
  })

  it("secilenleri sil: onay kutusu cikar, yalniz secilen kimlikler gider, liste yenilenir", async () => {
    const cagrilar = sahteSunucu({ "/api/v1/yonetim/musteriler/sil": { silinen: 3 }, "/api/v1/yonetim/musteriler": LISTE })
    sarmala(<MusteriListesi dil="tr" />)
    await screen.findByText("Beta Telekom")
    const sil = screen.getByRole("button", { name: "Seçilenleri sil (0)" })
    expect(sil).toBeDisabled()

    fireEvent.click(screen.getByRole("checkbox", { name: "Alfa A.Ş. müşterisini seç" }))
    fireEvent.click(screen.getByRole("checkbox", { name: "Beta Telekom müşterisini seç" }))
    fireEvent.click(screen.getByRole("button", { name: "Seçilenleri sil (2)" }))
    // Cati silinince iştirakleri de gider: onay metni gercek sayiyi soyler (2 secili, 4 silinecek).
    expect(screen.getByRole("alert")).toHaveTextContent("2 müşteri seçili; iştirakleriyle birlikte 4 müşteri")
    fireEvent.click(screen.getByRole("button", { name: "Evet, sil" }))

    expect(await screen.findByText("3 müşteri silindi.")).toBeInTheDocument()
    const istek = cagrilar.find((c) => c.yontem === "POST" && c.yol.includes("/musteriler/sil"))
    expect(istek?.govde).toEqual({ ids: [1, 4] })
    expect(cagrilar.filter((c) => c.yontem === "GET" && c.yol.endsWith("/yonetim/musteriler")).length).toBeGreaterThan(1) // yenilendi
  })

  it("vazgec hicbir sey silmez; 'Tumunu sil' icin SIL yazilmadan onay dugmesi kapali kalir", async () => {
    const cagrilar = sahteSunucu({ "/api/v1/yonetim/musteriler/sil": { silinen: 4 }, "/api/v1/yonetim/musteriler": LISTE })
    sarmala(<MusteriListesi dil="tr" />)
    await screen.findByText("Beta Telekom")

    fireEvent.click(screen.getByRole("button", { name: "Tümünü sil" }))
    expect(screen.getByRole("alert")).toHaveTextContent("TÜM müşteriler (4)")
    const onayla = screen.getByRole("button", { name: "Evet, sil" })
    expect(onayla).toBeDisabled()
    fireEvent.change(screen.getByLabelText("Onaylamak için SİL yazın"), { target: { value: "evet" } })
    expect(onayla).toBeDisabled()
    fireEvent.click(screen.getByRole("button", { name: "Vazgeç" }))
    expect(screen.queryByRole("alert")).toBeNull()
    expect(cagrilar.some((c) => c.yontem === "POST")).toBe(false)

    fireEvent.click(screen.getByRole("button", { name: "Tümünü sil" }))
    fireEvent.change(screen.getByLabelText("Onaylamak için SİL yazın"), { target: { value: "sil" } })
    expect(screen.getByRole("button", { name: "Evet, sil" })).toBeEnabled()
    fireEvent.click(screen.getByRole("button", { name: "Evet, sil" }))
    expect(await screen.findByText("4 müşteri silindi.")).toBeInTheDocument()
    expect(cagrilar.find((c) => c.yontem === "POST")?.govde).toEqual({ hepsi: true, onay: "sil" })
  })

  it("toplu ekle: satirlar ve ust musteri gider; eklenemeyenler sebebiyle gosterilir ve metinde kalir", async () => {
    const cagrilar = sahteSunucu({
      "/api/v1/yonetim/musteriler/toplu-ekle": { eklenen: 1, atlanan: [{ ad: "Beta Telekom", sebep: "Aynı ünvanlı müşteri var." }] },
      "/api/v1/musteri/secenekler": { tam: [{ id: 9, ad: "Ayşe TAM" }] },
      "/api/v1/yonetim/musteriler": LISTE,
    })
    sarmala(<MusteriListesi dil="tr" />)
    await screen.findByText("Beta Telekom")
    fireEvent.click(screen.getByRole("button", { name: "Müşteri ekle" }))
    const form = await screen.findByRole("form", { name: "Müşteri ekle" })
    const ekle = within(form).getByRole("button", { name: "Ekle (0)" })
    expect(ekle).toBeDisabled()

    fireEvent.change(within(form).getByRole("textbox"), { target: { value: "Yeni Firma; MA\nBeta Telekom" } })
    fireEvent.change(within(form).getByLabelText(/^Çatı müşteri/), { target: { value: "1" } })
    await within(form).findByRole("option", { name: "Ayşe TAM" })
    fireEvent.change(within(form).getByLabelText(/^Sorumlu TAM/), { target: { value: "9" } })
    fireEvent.click(within(form).getByRole("button", { name: "Ekle (2)" }))

    expect(await screen.findByText("1 müşteri eklendi.")).toBeInTheDocument()
    expect(within(form).getByText("1 satır eklenmedi:")).toBeInTheDocument()
    expect(within(form).getByText("Aynı ünvanlı müşteri var.", { exact: false })).toBeInTheDocument()
    expect(within(form).getByRole("textbox")).toHaveValue("Beta Telekom") // yalniz eklenemeyen satir kaldi
    const istek = cagrilar.find((c) => c.yontem === "POST")
    expect(istek?.govde).toEqual({
      satirlar: [
        { name: "Yeni Firma", segment: "MA" },
        { name: "Beta Telekom", segment: null },
      ],
      parent_id: 1,
      owner_id: 9,
    })
  })
})

describe("Profil: e-posta imzasi (2026-10-26)", () => {
  it("kayit yoksa hazir sablon acilir; kaydet duzenleyicinin HTML'ini gonderir ve sunucunun temizledigini gosterir", async () => {
    const SABLON = '<table><tbody><tr><td><img src="data:image/png;base64,AAAA" width="96" alt="Teknocan"></td><td><b>Giray Sav</b></td></tr></tbody></table>'
    const cagrilar: Cagri[] = []
    vi.stubGlobal(
      "fetch",
      vi.fn(async (girdi: string, ayar?: RequestInit) => {
        const yontem = ayar?.method ?? "GET"
        const govde = typeof ayar?.body === "string" ? JSON.parse(ayar.body) : null
        cagrilar.push({ yol: String(girdi), yontem, govde })
        const data = yontem === "PUT" ? { html: govde.html, sablon: SABLON, kayitli: true } : { html: "", sablon: SABLON, kayitli: false }
        return new Response(JSON.stringify({ status: "success", data }), { status: 200, headers: { "Content-Type": "application/json" } })
      }),
    )
    sarmala(<ImzaEditoru dil="tr" />)
    const alan = await screen.findByRole("textbox", { name: "E-posta imzası" })
    await waitFor(() => expect(alan.innerHTML).toContain("Giray Sav"))
    expect(screen.getByText("Henüz kaydedilmedi: hazır şablon gösteriliyor.")).toBeInTheDocument()
    expect(alan.querySelector("img")?.getAttribute("alt")).toBe("Teknocan")
    fireEvent.click(alan.querySelector("img") as HTMLImageElement)
    fireEvent.change(screen.getByLabelText("Seçili görselin genişliği"), { target: { value: "140" } })
    expect(alan.querySelector("img")?.getAttribute("width")).toBe("140")
    fireEvent.click(screen.getByRole("button", { name: "İmzayı kaydet" }))
    expect(await screen.findByText("İmza kaydedildi; aylık rapor iletisinde bu imza kullanılır.")).toBeInTheDocument()
    const put = cagrilar.find((c) => c.yontem === "PUT")
    expect(put?.yol).toContain("/api/v1/session/imza")
    expect(put && (put.govde as { html: string }).html).toContain('width="140"')
  })
})
