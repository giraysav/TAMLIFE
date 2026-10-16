import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { DuzenlenebilirTablo } from "@/components/duzenlenebilir-tablo"
import type { Kolon } from "@/components/duzenlenebilir-tablo"
import { Sekmeler } from "@/components/sayfa-ui"
import { ModulYayi } from "@/components/ui/modul-yayi"
import { baslangicHarfleri, bicimDili, para, tarih } from "@/lib/bicim"
import { hareketDegistir, hareketUygula, hareketVarMi } from "@/lib/hareket"
import type { Kullanici } from "@/lib/oturum"
import { kisaUnvan } from "@/musteri/portfoy-metin"
import { KullaniciKarti } from "@/shell/kullanici-karti"
import { metin, yerelMenu } from "@/shell/metin"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("bicimleyiciler", () => {
  it("para tutari birimiyle yazar", () => {
    expect(para(12500.5)).toBe("12.500,50 ₺")
    expect(para(10, "USD")).toBe("10,00 $")
    expect(para(5, "GBP")).toBe("5,00 GBP")
    expect(para(null)).toBe("—")
  })
  it("tarih GG.AA.YYYY olur; bos ve bozuk deger tire", () => {
    expect(tarih("2026-03-10")).toBe("10.03.2026")
    expect(tarih("2026-03-10T23:59:00Z")).toBe("10.03.2026")
    expect(tarih(null)).toBe("—")
    expect(tarih("bozuk")).toBe("—")
  })
  it("bas harfler", () => {
    expect(baslangicHarfleri("Elif Kaya")).toBe("EK")
    expect(baslangicHarfleri("admin")).toBe("AD")
    expect(baslangicHarfleri("")).toBe("?")
  })
  it("English iken sayi ve tarih ingilizce bicimde", () => {
    bicimDili("en")
    expect([para(12500.5), tarih("2026-03-10")]).toEqual(["12,500.50 ₺", "10/03/2026"])
    bicimDili("tr")
  })
})

describe("yerelMenu", () => {
  const menu = [{ id: "musteri", label: "Müşteri Yönetimi", label_en: "Customer Management", description: "Portföy", description_en: "Portfolio", group: "work" as const, icon: "customers", ready: true, children: [{ id: "musteri/liste", label: "Liste", description: "", ready: true }] }]
  it("English iken EN ad/aciklama, EN yoksa TR; Turkcede liste aynen", () => {
    const [m] = yerelMenu(menu, "en")
    expect([m?.label, m?.description, m?.children[0]?.label]).toEqual(["Customer Management", "Portfolio", "Liste"])
    expect(yerelMenu(menu, "tr")).toBe(menu)
  })
})

describe("kisaUnvan", () => {
  it("sondaki yasal ekleri atar", () => {
    expect(kisaUnvan("Marmara Gıda Sanayi ve Ticaret A.Ş.")).toBe("Marmara Gıda")
    expect(kisaUnvan("Karadeniz Enerji Üretim A.Ş.")).toBe("Karadeniz Enerji Üretim")
  })
  it("tek kelimeyi bos birakmaz, uzunu kelime sinirinda keser", () => {
    expect(kisaUnvan("A.Ş.")).toBe("A.Ş.")
    const kisa = kisaUnvan("Cok Uzun Bir Musteri Unvani Burada Devam Ediyor Holding", 26)
    expect(kisa.endsWith("…")).toBe(true)
    expect(kisa.length).toBeLessThanOrEqual(27)
  })
})

const KOLONLAR: Kolon[] = [
  { anahtar: "musteri", baslik: "Müşteri adı", tip: "musteri", zorunlu: true },
  { anahtar: "proje", baslik: "Proje bilgisi", tip: "metin", zorunlu: true },
  { anahtar: "tutar", baslik: "Gelir bilgisi", tip: "tutarPara", sag: true },
]
const TABLO_METIN = { ekle: "Satır ekle", kaydet: "Kaydet", vazgec: "Vazgeç", duzenle: "Düzenle", sil: "Sil", silOnay: "Silinsin mi?", islemSutunu: "İşlemler", hata: "Olmadı.", paraBirimi: "Para birimi" }

describe("DuzenlenebilirTablo", () => {
  it("satir ekler: alanlar dolunca Kaydet govdeyi gonderir", async () => {
    const onKaydet = vi.fn(async () => {})
    render(<DuzenlenebilirTablo kolonlar={KOLONLAR} satirlar={[]} metin={TABLO_METIN} bosKutu={<p>Kayıt yok</p>} onKaydet={onKaydet} onSil={vi.fn()} />)
    expect(screen.getByText("Kayıt yok")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Satır ekle" }))
    fireEvent.change(screen.getByLabelText("Müşteri adı"), { target: { value: "Alfa A.Ş." } })
    fireEvent.change(screen.getByLabelText("Proje bilgisi"), { target: { value: "OTP" } })
    fireEvent.change(screen.getByLabelText("Gelir bilgisi"), { target: { value: "1.250,50" } })
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }))
    await waitFor(() => expect(onKaydet).toHaveBeenCalledTimes(1))
    expect(onKaydet).toHaveBeenCalledWith({ musteri: "Alfa A.Ş.", proje: "OTP", tutar: "1.250,50", para_birimi: "TRY" }, null)
    await waitFor(() => expect(screen.queryByLabelText("Müşteri adı")).not.toBeInTheDocument()) // giris satiri kapanir
  })

  it("sunucu hatasini satirin altinda gosterir ve giris acik kalir", async () => {
    const onKaydet = vi.fn(async () => {
      throw new Error("Proje bilgisi zorunlu.")
    })
    render(<DuzenlenebilirTablo kolonlar={KOLONLAR} satirlar={[]} metin={TABLO_METIN} bosKutu={null} onKaydet={onKaydet} onSil={vi.fn()} />)
    fireEvent.click(screen.getByRole("button", { name: "Satır ekle" }))
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Proje bilgisi zorunlu.")
    expect(screen.getByLabelText("Müşteri adı")).toBeInTheDocument()
  })

  it("duzenle mevcut degerleri doldurur; sil onay ister", async () => {
    const onSil = vi.fn(async () => {})
    const onKaydet = vi.fn(async () => {})
    vi.stubGlobal("confirm", vi.fn(() => true))
    const satir = { id: 7, musteri: "Beta Ltd", proje: "Kampanya", tutar: 500, para_birimi: "USD" }
    render(<DuzenlenebilirTablo kolonlar={KOLONLAR} satirlar={[satir]} metin={TABLO_METIN} bosKutu={null} onKaydet={onKaydet} onSil={onSil} />)
    expect(screen.getByText("500,00 $")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Düzenle" }))
    expect(screen.getByLabelText("Müşteri adı")).toHaveValue("Beta Ltd")
    expect(screen.getByLabelText("Para birimi")).toHaveValue("USD")
    fireEvent.keyDown(screen.getByLabelText("Proje bilgisi"), { key: "Escape" })
    await waitFor(() => expect(screen.queryByLabelText("Proje bilgisi")).not.toBeInTheDocument())
    fireEvent.click(screen.getByRole("button", { name: "Sil" }))
    await waitFor(() => expect(onSil).toHaveBeenCalledWith(7))
  })

  it("saltOkunur: ekle, duzenle ve sil dugmeleri ile islem sutunu gorunmez", () => {
    const satir = { id: 7, musteri: "Beta Ltd", proje: "Kampanya", tutar: 500, para_birimi: "USD" }
    render(<DuzenlenebilirTablo kolonlar={KOLONLAR} satirlar={[satir]} metin={TABLO_METIN} bosKutu={null} onKaydet={vi.fn()} onSil={vi.fn()} saltOkunur />)
    expect(screen.getByText("Beta Ltd")).toBeInTheDocument()
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
    expect(screen.queryByText("İşlemler")).not.toBeInTheDocument()
  })
})

describe("Sekmeler", () => {
  it("secili sekme aria-selected olur ve tiklama bildirilir", () => {
    const onDegis = vi.fn()
    render(
      <Sekmeler
        etiket="Görünüm"
        deger="acik"
        onDegis={onDegis}
        secenekler={[
          { id: "acik", etiket: "Aktif", sayi: 5 },
          { id: "kapali", etiket: "Kapatılan" },
        ]}
      />,
    )
    expect(screen.getByRole("tab", { name: /Aktif/ })).toHaveAttribute("aria-selected", "true")
    fireEvent.click(screen.getByRole("tab", { name: "Kapatılan" }))
    expect(onDegis).toHaveBeenCalledWith("kapali")
  })
})

const PROFIL = { username: "admin", display_name: "Ayşe Yılmaz", ad_user: false, first_name: "Ayşe", last_name: "Yılmaz", phone: "", company: "", address: "", website: "" }
const KULLANICI: Kullanici = { username: "admin", display_name: "Ayşe Yılmaz", profile: PROFIL, role: "admin", is_admin: true, idle_timeout_minutes: 30, landing: "ozet", navigation: [] }

describe("KullaniciKarti (sol alt)", () => {
  it("admin: rol rozeti, Yonetim kisayolu, cikis", () => {
    const onGit = vi.fn()
    const onCikis = vi.fn()
    render(<KullaniciKarti kullanici={KULLANICI} dil="tr" onDil={vi.fn()} onGit={onGit} onCikis={onCikis} talepVar />)
    const dugme = screen.getByRole("button", { name: /Hesap menüsü: Ayşe Yılmaz/ })
    expect(dugme).toHaveAttribute("aria-expanded", "false")
    // Karttaki ad kisa kullanici adi (admin) degil personelin ad soyadi; bas harfleri de ondan turetilir.
    expect(screen.getByText("Ayşe Yılmaz")).toBeInTheDocument()
    expect(screen.getByText("AY")).toBeInTheDocument()
    expect(screen.getByText("Admin")).toBeInTheDocument()
    fireEvent.click(dugme)
    expect(dugme).toHaveAttribute("aria-expanded", "true")
    for (const ad of ["Profil", "Geliştirme Talepleri", "Çıkış"]) expect(screen.getByRole("menuitem", { name: ad })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("menuitem", { name: /Yönetim/ }))
    expect(onGit).toHaveBeenCalledWith("yonetim/durum")
    fireEvent.click(dugme)
    fireEvent.click(screen.getByRole("menuitem", { name: "Çıkış" }))
    expect(onCikis).toHaveBeenCalled()
  })

  it("Yonetim konsolu yalniz admin rolune: yonetici (TeamMngr) eski is_admin isaretiyle de goremez", () => {
    render(<KullaniciKarti kullanici={{ ...KULLANICI, username: "mudur", role: "TeamMngr", is_admin: true }} dil="tr" onDil={vi.fn()} onGit={vi.fn()} onCikis={vi.fn()} talepVar={false} />)
    fireEvent.click(screen.getByRole("button", { name: /Hesap menüsü/ }))
    expect(screen.queryByRole("menuitem", { name: /Yönetim/ })).not.toBeInTheDocument()
  })

  it("member: Yonetim kisayolu yok; Esc menuyu kapatir; dil secilir", () => {
    const onDil = vi.fn()
    render(<KullaniciKarti kullanici={{ ...KULLANICI, username: "ayse", role: "TeamMember", is_admin: false }} dil="tr" onDil={onDil} onGit={vi.fn()} onCikis={vi.fn()} talepVar={false} />)
    expect(screen.getByText("Member")).toBeInTheDocument()
    const dugme = screen.getByRole("button", { name: /Hesap menüsü/ })
    fireEvent.click(dugme)
    expect(screen.queryByRole("menuitem", { name: /Yönetim/ })).not.toBeInTheDocument()
    expect(screen.queryByRole("menuitem", { name: "Geliştirme Talepleri" })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("menuitemradio", { name: /English/ }))
    expect(onDil).toHaveBeenCalledWith("en")
    fireEvent.click(dugme)
    fireEvent.keyDown(document, { key: "Escape" })
    expect(dugme).toHaveAttribute("aria-expanded", "false")
    expect(metin("tr").rolEtiket.TeamMngr).toBe("Manager")
  })
})

describe("ModulYayi", () => {
  it("dar ekranda kartlar liste olur ve tiklanir", () => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
        unobserve() {}
      },
    )
    const onClick = vi.fn()
    render(<ModulYayi ogeler={[{ anahtar: "onedesk", etiket: "Onedesk", ikon: <span />, renk: ["#fb7185", "#e11d48"], onClick }]} alt={<img alt="Teknocan" />} />)
    fireEvent.click(screen.getByRole("button", { name: "Onedesk" }))
    expect(onClick).toHaveBeenCalledTimes(1)
    expect(screen.getByRole("img", { name: "Teknocan" })).toBeInTheDocument()
  })

  it("yalin modda yalnizca gorsel cizilir, modul dugmesi cikmaz", () => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
        unobserve() {}
      },
    )
    render(
      <ModulYayi
        yalin
        arkaPlan={{ src: "sahne.jpg", alt: "Teknocan" }}
        ogeler={[{ anahtar: "onedesk", etiket: "Onedesk", ikon: <span />, renk: ["#fb7185", "#e11d48"] }]}
      />,
    )
    expect(screen.getByRole("img", { name: "Teknocan" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Onedesk" })).not.toBeInTheDocument()
  })

  it("alt verilmezse yayin altinda ek alan cizilmez", () => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
        unobserve() {}
      },
    )
    render(<ModulYayi ogeler={[{ anahtar: "onedesk", etiket: "Onedesk", ikon: <span />, renk: ["#fb7185", "#e11d48"] }]} />)
    expect(screen.queryByRole("img")).not.toBeInTheDocument()
    expect(screen.queryByRole("heading")).not.toBeInTheDocument()
  })
})

describe("animasyon tercihi", () => {
  it("sistem hareketi kapatmissa varsayilan kapali; hesap menusu ile acilip kapanir ve hatirlanir", () => {
    window.localStorage.clear()
    vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener: () => {}, removeEventListener: () => {} }))
    expect(hareketVarMi()).toBe(false)
    hareketUygula()
    expect(document.documentElement.dataset.hareket).toBe("kapat")
    hareketDegistir() // kullanici acar: isletim sistemi ayarina bakilmaz
    expect(hareketVarMi()).toBe(true)
    expect(document.documentElement.dataset.hareket).toBe("ac")
    expect(window.localStorage.getItem("tamlife.hareket")).toBe("ac")
    hareketDegistir()
    expect(hareketVarMi()).toBe(false)
    expect(window.localStorage.getItem("tamlife.hareket")).toBe("kapat")
    window.localStorage.clear()
  })

  it("sistem hareketi serbest birakmissa varsayilan acik", () => {
    window.localStorage.clear()
    vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }))
    expect(hareketVarMi()).toBe(true)
  })

  it("hesap menusunde Animasyonlar anahtari durumu yansitir", () => {
    window.localStorage.clear()
    vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener: () => {}, removeEventListener: () => {} }))
    render(<KullaniciKarti kullanici={KULLANICI} dil="tr" onDil={vi.fn()} onGit={vi.fn()} onCikis={vi.fn()} talepVar={false} />)
    fireEvent.click(screen.getByRole("button", { name: /Hesap menüsü/ }))
    const anahtar = screen.getByRole("menuitemcheckbox", { name: "Animasyonlar" })
    expect(anahtar).toHaveAttribute("aria-checked", "false")
    fireEvent.click(anahtar)
    expect(screen.getByRole("menuitemcheckbox", { name: "Animasyonlar" })).toHaveAttribute("aria-checked", "true")
    window.localStorage.clear()
  })
})
