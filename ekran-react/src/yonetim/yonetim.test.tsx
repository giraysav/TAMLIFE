import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { sorguMetni } from "@/lib/sorgu"
import type { Katalog, KuralGovdesi, Ozet } from "@/yonetim/api"
import Arizalar from "@/yonetim/bolumler/arizalar"
import Durum from "@/yonetim/bolumler/durum"
import { ym } from "@/yonetim/metin"
import { kaynakAdiOner } from "@/yonetim/tampon/kaynaklar"
import { BOS_KURAL, KuralFormu } from "@/yonetim/tampon/kural-formu"
import { bayt, sureYaz, zaman } from "@/lib/bicim"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function sarmala(cocuk: ReactNode) {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={istemci}>{cocuk}</QueryClientProvider>)
}

/** fetch'i yola gore cevaplar: {yol parcasi: data}. Taniml olmayan yol 404. */
function sahteSunucu(cevaplar: Record<string, unknown>) {
  const cagrilar: string[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn(async (girdi: string) => {
      cagrilar.push(String(girdi))
      const anahtar = Object.keys(cevaplar).find((k) => String(girdi).includes(k))
      return anahtar === undefined
        ? new Response(JSON.stringify({ detail: "yok" }), { status: 404, headers: { "Content-Type": "application/json" } })
        : new Response(JSON.stringify({ status: "success", data: cevaplar[anahtar] }), { status: 200, headers: { "Content-Type": "application/json" } })
    }),
  )
  return cagrilar
}

describe("bicimleyiciler ve yardimcilar", () => {
  it("bayt okunur birime cevrilir", () => {
    expect(bayt(null)).toBe("—")
    expect(bayt(512)).toBe("512 B")
    expect(bayt(2048)).toMatch(/^2 KB$/)
    expect(bayt(5 * 1024 * 1024)).toMatch(/^5 MB$/)
  })
  it("sure kisa yazilir", () => {
    expect(sureYaz(30)).toBe("30 sn")
    expect(sureYaz(600)).toBe("10 dk")
    expect(sureYaz(7200)).toMatch(/^2 sa$/)
  })
  it("zaman: gecersiz/bos tire doner, ISO yerel bicime gider", () => {
    expect(zaman(null)).toBe("—")
    expect(zaman("bozuk")).toBe("—")
    expect(zaman("2026-10-07T12:30:00Z")).toMatch(/2026/)
  })
  it("sorguMetni bos degerleri atar ve kodlar", () => {
    expect(sorguMetni({ a: "x y", b: "", c: null, d: undefined, e: 0 })).toBe("?a=x+y&e=0")
    expect(sorguMetni({ a: "" })).toBe("")
  })
  it("dosya adindan kaynak adi: tarih eki ve uzanti atilir", () => {
    expect(kaynakAdiOner("alarm-ozeti_2026-10.csv")).toBe("alarm-ozeti")
    expect(kaynakAdiOner("rapor.csv")).toBe("rapor")
    expect(kaynakAdiOner("veri20261007.txt")).toBe("veri")
  })
  it("TR ve EN metin anahtarlari ayni (EN: typeof TR) ve fonksiyonlar calisir", () => {
    expect(Object.keys(ym("en"))).toEqual(Object.keys(ym("tr")))
    expect(ym("tr").sayfaBilgi(2, 5, 120)).toBe("Sayfa 2/5 · 120 kayıt")
    expect(ym("en").sayfaBilgi(2, 5, 120)).toBe("Page 2/5 · 120 records")
  })
})

const OZET: Ozet = {
  saglik: {
    genel: "uyari",
    zaman: "2026-10-07T12:00:00Z",
    kontroller: [
      { id: "veritabani", durum: "ok", ayrinti: "Yanıt 3 ms", veri: {} },
      { id: "sema", durum: "uyari", ayrinti: "Sürüm kaydı yok.", veri: {} },
      { id: "ariza", durum: "ok", ayrinti: "Son 24 saatte 0 hata kaydı.", veri: {} },
    ],
  },
  gostergeler: {
    veritabani: { motor: "sqlite", boyut_bayt: 196608, surum: "0005_yonetim_tampon", surum_uyumlu: true },
    ariza: { acik: 2, son_24s: 3, son_24s_hata: 1, son_zaman: null },
    gunluk: { son_24s: 42, red_24s: 1, toplam: 100 },
    oturum: { aktif: 1 },
    tampon: { hazir_parti: 1, kural: 2, kural_etkin: 1, son: null },
  },
  baglantilar: [
    { id: "ad", slot: "AD", configured: false },
    { id: "oracle_reportdb", slot: "ORACLE_REPORTDB", configured: true },
  ],
}

describe("Genel Durum", () => {
  it("saglik bandi, gostergeler, kontroller ve baglantilar cizilir", async () => {
    sahteSunucu({ "/api/v1/yonetim/ozet": OZET })
    sarmala(<Durum dil="tr" />)
    expect(await screen.findByText("Dikkat gerekli")).toBeInTheDocument()
    expect(screen.getByText("SQLITE")).toBeInTheDocument()
    expect(screen.getByText("Sürüm kaydı yok.")).toBeInTheDocument()
    // her kontrol renk + ikon + METIN: durum etiketi
    expect(screen.getAllByText("Tamam").length).toBe(2)
    expect(screen.getByText("Uyarı")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Açık arıza/ })).toHaveAttribute("href", "#/yonetim/arizalar")
    expect(screen.getByText("ORACLE_REPORTDB · ayarlı")).toBeInTheDocument()
    expect(screen.getByText("AD · ayarlı değil")).toBeInTheDocument()
  })

  it("EN dilinde metinler cevrilir", async () => {
    sahteSunucu({ "/api/v1/yonetim/ozet": OZET })
    sarmala(<Durum dil="en" />)
    expect(await screen.findByText("Needs attention")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Check now/ })).toBeInTheDocument()
  })

  it("sunucu hatasinda uyari kutusu ve tekrar dene", async () => {
    sahteSunucu({})
    sarmala(<Durum dil="tr" />)
    const kutu = await screen.findByRole("alert")
    expect(within(kutu).getByRole("button", { name: "Tekrar dene" })).toBeInTheDocument()
  })
})

describe("Arizalar", () => {
  const ARIZA = {
    id: 7,
    kayit_no: "abcd1234ef567890abcd1234ef567890",
    kod: "TL-DB-01",
    seviye: "error",
    kaynak: "GET /api/v1/x",
    mesaj: "disk dolu",
    istisna: "OperationalError",
    kullanici: "admin",
    zaman: "2026-10-07T10:00:00Z",
    durum: "open",
    not: "",
    kapatan: "",
    kapanis: null,
    cozum_adimi: "Disk alanını kontrol edin.",
  }

  it("listelenir; kayit secilince ayrinti, cozum adimi ve gunluk baglantisi gorunur", async () => {
    sahteSunucu({
      "/api/v1/yonetim/arizalar": { toplam: 1, sayfa: 1, adet: 15, satirlar: [ARIZA] },
      "/api/v1/yonetim/ariza-kodlari": [{ kod: "TL-DB-01", aciklama: "Veritabanı işlemi tamamlanamadı", cozum: "Diski kontrol edin" }],
    })
    sarmala(<Arizalar dil="tr" />)
    expect(await screen.findByText("Ayrıntı için listeden bir kayıt seçin.")).toBeInTheDocument()
    fireEvent.click(await screen.findByRole("button", { name: "abcd1234" }))
    expect(await screen.findByText("Disk alanını kontrol edin.")).toBeInTheDocument()
    expect(screen.getByText("disk dolu")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Uygulama günlüğünde ara" })).toHaveAttribute("href", "#/yonetim/gunlukler?kayit=abcd1234")
    expect(screen.getByRole("button", { name: "Durumu güncelle" })).toBeInTheDocument()
  })

  it("filtre degisince sunucuya durum parametresi gider", async () => {
    const cagrilar = sahteSunucu({
      "/api/v1/yonetim/arizalar": { toplam: 0, sayfa: 1, adet: 15, satirlar: [] },
      "/api/v1/yonetim/ariza-kodlari": [],
    })
    sarmala(<Arizalar dil="tr" />)
    expect(await screen.findByText("Kayıtlı arıza yok.")).toBeInTheDocument()
    fireEvent.change(screen.getAllByRole("combobox")[0], { target: { value: "closed" } })
    await waitFor(() => expect(cagrilar.some((u) => u.includes("durum=closed"))).toBe(true))
  })
})

describe("Kural formu", () => {
  const KATALOG: Katalog = {
    hedefler: [
      { anahtar: "customer.alarm_count", ad: "Aktif alarm", sutun: "alarm_count", tip: "sayi" },
      { anahtar: "customer.sector", ad: "Sektör", sutun: "sector", tip: "metin" },
    ],
    islemler: [
      { anahtar: "say", ad: "Say (satır adedi)", tip: "sayi" },
      { anahtar: "topla", ad: "Topla", tip: "sayi" },
      { anahtar: "en_cok", ad: "En sık değer", tip: "metin" },
    ],
    islecler: ["esit", "dolu"],
    degersiz_islecler: ["dolu"],
    eslesme_alanlari: [{ anahtar: "customer_no", ad: "Müşteri No" }],
  }
  const BASLANGIC: KuralGovdesi = { ...BOS_KURAL, name: "K1", source_key: "csv_a", key_column: "Müşteri No" }

  function ac(onKaydet = vi.fn()) {
    render(
      <KuralFormu
        dil="tr"
        katalog={KATALOG}
        baslangic={BASLANGIC}
        duzenleme={false}
        kaynakAnahtarlari={["csv_a"]}
        sutunlar={["Müşteri No", "Durum", "Adet"]}
        hata=""
        kaydediliyor={false}
        onKaydet={onKaydet}
        onVazgec={() => undefined}
      />,
    )
    return onKaydet
  }
  const secim = (ad: RegExp | string) => screen.getByRole("combobox", { name: ad })

  it("islem listesi hedef tipine gore suzulur; say secilince deger sutunu gizlenir", () => {
    ac()
    const hedef = screen.getByLabelText("Hedef (sabit)")
    const islem = screen.getByLabelText("İşlem")
    fireEvent.change(hedef, { target: { value: "customer.alarm_count" } })
    expect(within(islem).getAllByRole("option").map((o) => o.textContent)).toEqual(["Seçin…", "Say (satır adedi)", "Topla"])
    fireEvent.change(islem, { target: { value: "topla" } })
    expect(screen.getByRole("combobox", { name: "Değer sütunu" })).toBeInTheDocument()
    fireEvent.change(islem, { target: { value: "say" } })
    expect(screen.queryByRole("combobox", { name: "Değer sütunu" })).not.toBeInTheDocument()
    // metin hedefine gecince sayisal islem gecersiz: sifirlanir ve "eslesmeyeni sifirla" kaybolur
    fireEvent.change(hedef, { target: { value: "customer.sector" } })
    expect((islem as HTMLSelectElement).value).toBe("")
    expect(screen.queryByText("Eşleşmeyen kartları sıfırla")).not.toBeInTheDocument()
    expect(within(islem).getAllByRole("option").map((o) => o.textContent)).toEqual(["Seçin…", "En sık değer"])
    expect(secim(/Kaynaklar/)).toBeInTheDocument()
  })

  it("koşul ekleme (en fazla 5), degersiz isleçte deger alani yok, kaydet govdeyi dogru uretir", () => {
    const onKaydet = ac()
    fireEvent.change(screen.getByLabelText("Hedef (sabit)"), { target: { value: "customer.alarm_count" } })
    fireEvent.change(screen.getByLabelText("İşlem"), { target: { value: "say" } })
    for (let i = 0; i < 5; i += 1) fireEvent.click(screen.getByRole("button", { name: "Koşul ekle" }))
    expect(screen.queryByRole("button", { name: "Koşul ekle" })).not.toBeInTheDocument()
    expect(screen.getAllByRole("button", { name: "Koşulu sil" })).toHaveLength(5)
    // ilk kosul: Durum dolu (degersiz) -> deger alani yok; digerlerini sil
    const sutunlar = screen.getAllByRole("combobox", { name: "Sütun" })
    fireEvent.change(sutunlar[0], { target: { value: "Durum" } })
    fireEvent.change(screen.getAllByRole("combobox", { name: "İşleç" })[0], { target: { value: "dolu" } })
    for (let i = 0; i < 4; i += 1) fireEvent.click(screen.getAllByRole("button", { name: "Koşulu sil" })[1])
    expect(screen.queryByLabelText("Değer")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }))
    expect(onKaydet).toHaveBeenCalledTimes(1)
    expect(onKaydet.mock.calls[0][0]).toMatchObject({
      name: "K1",
      source_key: "csv_a",
      target: "customer.alarm_count",
      operation: "say",
      value_column: "",
      conditions: [{ kolon: "Durum", islec: "dolu", deger: "" }],
      zero_unmatched: false,
      max_age_minutes: null,
    })
  })
})

beforeEach(() => {
  window.localStorage.clear()
})
