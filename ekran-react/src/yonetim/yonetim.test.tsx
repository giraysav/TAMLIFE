import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"
import { sorguMetni } from "@/lib/sorgu"
import type { Katalog, KuralGovdesi, Ozet } from "@/yonetim/api"
import Arizalar from "@/yonetim/bolumler/arizalar"
import Durum from "@/yonetim/bolumler/durum"
import Kurum from "@/yonetim/bolumler/kurum"
import Veritabani from "@/yonetim/bolumler/veritabani"
import { ym } from "@/yonetim/metin"
import { VeriAkislariPaneli } from "@/yonetim/tampon/akislar"
import { ReportdbKatalogu } from "@/yonetim/tampon/katalog"
import { GenelCsvYukle } from "@/yonetim/tampon/csv-yukle"
import { Dagitim } from "@/yonetim/tampon/dagitim"
import { Kaynaklar } from "@/yonetim/tampon/kaynaklar"
import { tm } from "@/yonetim/tampon/metin"
import { HamMusteriBolumu } from "@/yonetim/tampon/musteri-ham"
import { TemipEslesmesi } from "@/yonetim/tampon/temip"
import { atamaMetin } from "@/components/temip-atama"
import { BOS_KURAL, KuralFormu } from "@/yonetim/tampon/kural-formu"
import { Rehber } from "@/yonetim/tampon/rehber"
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
    vi.fn(async (girdi: string, ayar?: RequestInit) => {
      cagrilar.push(`${ayar?.method ?? "GET"} ${String(girdi)}`)
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
    { id: "ad", slot: "AD", tur: "dizin", configured: false },
    { id: "oracle_reportdb", slot: "ORACLE_REPORTDB", tur: "veritabani", configured: true },
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
    expect(screen.queryByText(/AD ·|ORACLE_REPORTDB/)).not.toBeInTheDocument() // kurum baglantilari ayri sekmede, Oracle Veritabani'nda
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
    const t = ym("tr")
    const hedef = screen.getByLabelText(t.hedef)
    const islem = screen.getByLabelText(t.islem)
    fireEvent.change(hedef, { target: { value: "customer.alarm_count" } })
    expect(within(islem).getAllByRole("option").map((o) => o.textContent)).toEqual(["Seçin…", "Say (satır adedi)", "Topla"])
    fireEvent.change(islem, { target: { value: "topla" } })
    expect(screen.getByRole("combobox", { name: t.degerSutunu })).toBeInTheDocument()
    fireEvent.change(islem, { target: { value: "say" } })
    expect(screen.queryByRole("combobox", { name: t.degerSutunu })).not.toBeInTheDocument()
    // metin hedefine gecince sayisal islem gecersiz: sifirlanir ve "eslesmeyeni sifirla" kaybolur
    fireEvent.change(hedef, { target: { value: "customer.sector" } })
    expect((islem as HTMLSelectElement).value).toBe("")
    expect(screen.queryByText(t.eslesmeyeniSifirla)).not.toBeInTheDocument()
    expect(within(islem).getAllByRole("option").map((o) => o.textContent)).toEqual(["Seçin…", "En sık değer"])
    expect(secim(t.kuralKaynak)).toBeInTheDocument()
    // her alanin altinda sade dilde kisa ipucu var
    expect(screen.getByText(tm("tr").kuralIpuclari.anahtarSutunu)).toBeInTheDocument()
    expect(screen.getByText(tm("tr").kuralIpuclari.hedef)).toBeInTheDocument()
    expect(screen.getByText(tm("tr").kuralIpuclari.enBuyukYas)).toBeInTheDocument()
  })

  it("koşul ekleme (en fazla 5), degersiz isleçte deger alani yok, kaydet govdeyi dogru uretir", () => {
    const t = ym("tr")
    const onKaydet = ac()
    fireEvent.change(screen.getByLabelText(t.hedef), { target: { value: "customer.alarm_count" } })
    fireEvent.change(screen.getByLabelText(t.islem), { target: { value: "say" } })
    for (let i = 0; i < 5; i += 1) fireEvent.click(screen.getByRole("button", { name: "Koşul ekle" }))
    expect(screen.queryByRole("button", { name: "Koşul ekle" })).not.toBeInTheDocument()
    expect(screen.getAllByRole("button", { name: "Koşulu sil" })).toHaveLength(5)
    // ilk kosul: Durum dolu (degersiz) -> deger alani yok; digerlerini sil
    const sutunlar = screen.getAllByRole("combobox", { name: "Sütun" })
    fireEvent.change(sutunlar[0], { target: { value: "Durum" } })
    fireEvent.change(screen.getAllByRole("combobox", { name: t.islec })[0], { target: { value: "dolu" } })
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

describe("Veri Girisi kaynaklari", () => {
  it("yalniz hazir Oracle kaynaginda baglanti testi var; sonuc ve ReportDB durumu gorunur", async () => {
    const t = ym("tr")
    const kaynak = { neden: "", eksik: [], parti_sayisi: 0, son: null }
    const cagrilar = sahteSunucu({
      "/kaynaklar/oracle_reportdb/test": { ok: false, mesaj: "ORA-12541: ***", ipucu: "Dinleyiciye ulaşılamadı (adres / port)." },
      "/api/v1/tampon/kaynaklar": [
        { ...kaynak, anahtar: "oracle_reportdb", ad: "REPORTDB", tur: "oracle", hazir: true, yapilandirma: "tamam",
          reportdb: { kartlara_yaz: false, kural: 2, yas_dk: 3.5, taze: true, tazelik_dk: 20 } },
        { ...kaynak, anahtar: "oracle_onent", ad: "ONENTDB", tur: "oracle", hazir: false, yapilandirma: "kapalı" },
      ],
    })
    sarmala(<Kaynaklar dil="tr" />)
    const dugmeler = await screen.findAllByRole("button", { name: t.baglantiTesti })
    expect(dugmeler).toHaveLength(1)
    expect(screen.getByText(t.kartlaraYaz(false) + " · " + t.sonVeriYasi(3.5, true))).toBeTruthy()
    fireEvent.click(dugmeler[0])
    expect(await screen.findByText(/ORA-12541: \*\*\* — Dinleyiciye/)).toBeTruthy()
    expect(cagrilar.some((c) => c === "POST /api/v1/tampon/kaynaklar/oracle_reportdb/test")).toBe(true)
  })
})

describe("Ham Musteri Verisi", () => {
  it("son partiyi onizler, satirlari gosterir ve onayla kartlara yazar", async () => {
    vi.stubGlobal("confirm", () => true)
    const kaynak = { neden: "", eksik: [], parti_sayisi: 1, hazir: true, yapilandirma: "tamam", tur: "dosya" }
    const cagrilar = sahteSunucu({
      "/musteri-ham/onizle": {
        parti_id: 7,
        ozet: { toplam: 2, guncelle: 1, degisiklik_yok: 0, yeni: 0, hata: 1, uyari: 0, alan_degisikligi: 1, yeni_olustur: false, genis_bicim: false, uygulanacak: 1, tanimsiz_sutunlar: ["Not"] },
        uyum: { toplam: 30, eslesen: 3, alanlar: [{ sutun: "Müşteri Adı", alan: "Müşteri Ünvanı" }], eksik: [], fazla: ["Not"], zorunlu_eksik: [], uyumlu: true, bicim: "liste" },
        satirlar: [
          { sira: 1, unvan: "Alfa", durum: "guncelle", degisiklikler: [{ alan: "segment", baslik: "Segment", eski: "SA", yeni: "MA" }], hatalar: [], uyarilar: [] },
          { sira: 2, unvan: "Beta", durum: "hata", degisiklikler: [], hatalar: ["TAC E-posta: geçerli bir e-posta adresi olmalı"], uyarilar: [] },
        ],
        kesildi: 0,
        plan_ozeti: "h",
      },
      "/musteri-ham/uygula": { kayit_id: 3, ozet: { guncellenen: 1, olusturulan: 0 } },
      "/musteri-ham/aktarimlar": [],
      "/api/v1/tampon/kaynaklar": [{ ...kaynak, anahtar: "musteri_ham", ad: "Ham Müşteri Verisi", son: { id: 7, durum: "ready", satir: 2, zaman: null, hata: "" } }],
    })
    sarmala(<HamMusteriBolumu dil="tr" onYeniParti={() => {}} />)
    fireEvent.click(await screen.findByRole("button", { name: tm("tr").ham.onizle }))
    expect(await screen.findByText(tm("tr").ham.bicim.liste)).toBeTruthy()
    expect(screen.getByText("TAC E-posta: geçerli bir e-posta adresi olmalı")).toBeTruthy()
    expect(screen.getByRole("link", { name: tm("tr").ham.bosSablon })).toHaveAttribute("href", "/api/v1/tampon/musteri-ham/sablon.xlsx")
    fireEvent.click(screen.getByRole("button", { name: tm("tr").ham.uygula(1) }))
    expect(await screen.findByText(tm("tr").ham.uygulandi(1, 0))).toBeTruthy()
    expect(cagrilar).toContain("POST /api/v1/tampon/musteri-ham/uygula")
  })
})

describe("Veritabani", () => {
  it("dis veritabanlari artik Kurum Baglantilari'nda: burada yalniz yonlendirme", async () => {
    const t = ym("tr")
    const cagrilar = sahteSunucu({
      "/api/v1/yonetim/veritabani": {
        motor: "sqlite", dosya: "dev.db", boyut_bayt: 1024, disk_serbest_bayt: 2048, surum: "0002_ad_kimlik", hedef_surum: "0002_ad_kimlik",
        surum_uyumlu: true, eksik_tablolar: [], tablolar: [], toplam_satir: 0, butunluk: "ok",
        yedek: { dizin: "yedek", desteklenir: true, saklanan: 30, adet: 0, liste: [], ayni_disk: true, geri_donus: { klasor: "yedek\\ROLLBACK", betik: true, sifre: true } },
      },
    })
    sarmala(<Veritabani dil="tr" />)
    expect(await screen.findByRole("link", { name: t.kurumaGit })).toHaveAttribute("href", "#/yonetim/kurum")
    expect(cagrilar.some((c) => c.includes("/tampon/kaynaklar"))).toBe(false)
  })

  it("yedek: ayni diskte uyari, geri donus sifreli betikle (panelde geri yukleme yok)", async () => {
    const t = ym("tr")
    sahteSunucu({
      "/api/v1/yonetim/veritabani": {
        motor: "sqlite", dosya: "dev.db", boyut_bayt: 1024, disk_serbest_bayt: 2048, surum: "0002_ad_kimlik", hedef_surum: "0002_ad_kimlik",
        surum_uyumlu: true, eksik_tablolar: [], tablolar: [], toplam_satir: 0, butunluk: "ok",
        yedek: { dizin: "yedek", desteklenir: true, saklanan: 30, adet: 0, liste: [], ayni_disk: true, geri_donus: { klasor: "yedek\\ROLLBACK", betik: true, sifre: false } },
      },
    })
    sarmala(<Veritabani dil="tr" />)
    expect(await screen.findByText(t.yedekAyriDisk)).toBeTruthy()
    expect(screen.getByText(t.geriDonusEksik("yedek\\ROLLBACK"))).toBeTruthy()
    expect(screen.queryByRole("button", { name: /geri y[uü]kle/i })).toBeNull()
  })
})

describe("Kurum Baglantilari", () => {
  const AD = {
    id: "ad",
    tur: "dizin",
    label: "AD / LDAPS",
    state: "incomplete",
    missing: ["AD_DOMAIN"],
    bilgiler: { sunucu: "dc.ornek.local", port: 636, ldaps: true, ssl: true, alan: "", ca_dosyasi: false, grup_kisiti: true, otomatik_ac: true },
  }

  it("AD karti: durum, gizli olmayan ayarlar, eksik anahtar; erisim testi adimlari (bind yok)", async () => {
    const t = ym("tr")
    const cagrilar = sahteSunucu({
      "/api/v1/yonetim/kurum/ad-testi": {
        tamam: false,
        adimlar: [
          { adim: "dns", durum: "ok", baslik: "DNS: dc.ornek.local", ayrinti: "10.0.0.5" },
          { adim: "tcp", durum: "hata", baslik: "Ag: dc.ornek.local:636", ayrinti: "TimeoutError: timed out" },
        ],
      },
      "/api/v1/yonetim/kurum": { baglantilar: [AD] },
    })
    sarmala(<Kurum dil="tr" />)
    expect(await screen.findByText(t.kurum.adBaslik)).toBeInTheDocument()
    expect(screen.getAllByText(t.kurum.durum.incomplete)).toHaveLength(2) // ozet dugmesi + kart
    expect(screen.getByText("dc.ornek.local")).toBeInTheDocument()
    expect(screen.getByText(t.kurum.caYok)).toBeInTheDocument()
    expect(screen.getByText("AD_DOMAIN")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: t.kurum.test }))
    expect(await screen.findByText(t.kurum.hata)).toBeInTheDocument()
    expect(screen.getByText(t.kurum.adim.tcp)).toBeInTheDocument()
    expect(screen.getByText("TimeoutError: timed out")).toBeInTheDocument()
    expect(cagrilar).toContain("POST /api/v1/yonetim/kurum/ad-testi")
  })

  const ORACLE = {
    tur: "oracle",
    missing: [],
    son_parti: null,
    bilgiler: { sunucu: "reportdb-scan.ornek", port: 1521, servis: "REPORTDB", kullanici: "OKUYUCU", parola: true, zaman_asimi: 10, oracle_istemci: true, sorgu_tamam: true, sorgu_hata: null },
  }

  it("Oracle kartlari: AD ile ayni duzen; yalniz hazir kaynak test edilir, Tumunu test et hepsini dener", async () => {
    const t = ym("tr")
    const cagrilar = sahteSunucu({
      "/api/v1/yonetim/kurum/oracle_reportdb/test": {
        tamam: false,
        adimlar: [
          { adim: "ayar", durum: "ok", baslik: "Ayarlar tamam", ayrinti: "port 1521" },
          { adim: "dns", durum: "ok", baslik: "Sunucu adı çözüldü", ayrinti: "1 adres" },
          { adim: "tcp", durum: "ok", baslik: "Porta ulaşıldı (1521)", ayrinti: "" },
          { adim: "oturum", durum: "hata", baslik: "Oracle oturumu", ayrinti: "ORA-01017: ***\nKullanıcı adı ya da parola hatalı." },
        ],
      },
      "/api/v1/yonetim/kurum/ad-testi": { tamam: true, adimlar: [] },
      "/api/v1/yonetim/kurum": {
        baglantilar: [
          AD,
          { ...ORACLE, id: "oracle_reportdb", label: "REPORTDB", state: "ready", acma_anahtari: "ORACLE_REPORTDB_ENABLED",
            son_parti: { id: 7, durum: "ready", satir: 120, zaman: null, hata: "" }, reportdb: { kartlara_yaz: true, kural: 2, yas_dk: 4, taze: true, tazelik_dk: 20 } },
          { ...ORACLE, id: "oracle_galapagos", label: "GALAPAGOSDB", state: "disabled", acma_anahtari: "GALAPAGOSDB_DB_ENABLED",
            bilgiler: { ...ORACLE.bilgiler, sunucu: "", oracle_istemci: false, sorgu_tamam: false, sorgu_hata: "İçeri alma sorgusu tanımlı değil." } },
        ],
      },
    })
    sarmala(<Kurum dil="tr" />)
    expect(await screen.findByRole("heading", { name: "REPORTDB" })).toBeInTheDocument()
    expect(screen.getByText(t.kurum.oracleNe.oracle_galapagos)).toBeInTheDocument()
    expect(screen.getAllByText("reportdb-scan.ornek")).toHaveLength(1) // REPORTDB sunucusu acik; GALAPAGOSDB'de "tanimli degil"
    expect(screen.getByText(t.kurum.oracleKapali("GALAPAGOSDB_DB_ENABLED"))).toBeInTheDocument()
    expect(screen.getByText("İçeri alma sorgusu tanımlı değil.")).toBeInTheDocument()
    expect(screen.getByText(t.kartlaraYaz(true) + " · " + t.sonVeriYasi(4, true))).toBeInTheDocument()
    expect(screen.getByText(/^#7 · Hazır/)).toBeInTheDocument()
    expect(screen.getAllByRole("button", { name: t.kurum.test })).toHaveLength(2) // AD + REPORTDB; kapali GALAPAGOSDB yok
    fireEvent.click(screen.getByRole("button", { name: t.kurum.tumunuTest }))
    expect(await screen.findByText(t.kurum.adim.oturum)).toBeInTheDocument()
    expect(screen.getByText(/parola hatalı/)).toBeInTheDocument()
    expect(cagrilar).toContain("POST /api/v1/yonetim/kurum/oracle_reportdb/test")
    expect(cagrilar).toContain("POST /api/v1/yonetim/kurum/ad-testi")
    expect(cagrilar.some((c) => c.includes("oracle_galapagos/test"))).toBe(false)
  })

  it("Yonetim sekme sirasi: Kurum Baglantilari, Veri Girisi ile Veritabani arasinda (EN de var)", () => {
    expect(Object.keys(ym("tr").bolumler)).toEqual(["durum", "utilizasyon", "tampon", "kurum", "veritabani", "roller", "arizalar", "gunlukler"])
    expect(ym("en").bolumler.kurum).toBe("Corporate connections")
  })
})

describe("Veri Girisi rehberi", () => {
  it("Nasil calisir: akis, kaynaklar, kural alanlari (formdaki ipucuyla ayni metin), ornekler ve geri al", () => {
    window.localStorage.setItem("mkBolum:yonetim-tampon-rehber", "1") // varsayilan kapali (tembel): acik hatirlanmis gibi
    render(<Rehber dil="tr" />)
    expect(screen.getByText(tm("tr").rehber.baslik)).toBeInTheDocument()
    expect(screen.getByText(/Tampon \(parti\)/)).toBeInTheDocument()
    for (const b of [tm("tr").rehber.kaynaklarBaslik, tm("tr").rehber.alanlarBaslik, tm("tr").rehber.ornekBaslik, tm("tr").rehber.uygulaBaslik]) expect(screen.getByText(b)).toBeInTheDocument()
    expect(screen.getByText(tm("tr").kuralIpuclari.eslesmeAlani)).toBeInTheDocument()
    expect(screen.getByText(tm("tr").rehber.ornekler[0][0])).toBeInTheDocument()
    cleanup()
    render(<Rehber dil="en" />)
    expect(screen.getByText("How does it work?")).toBeInTheDocument()
  })
})

describe("Veri Girisi optimizasyonu", () => {
  const a = tm("tr")
  const akis = { yontem: "dosya", yer: "yonetim/tampon", son: null, aciklama: "" }

  it("veri akislari: bayat uyarisi, durum rozetleri, baska ekrana baglanti", async () => {
    sahteSunucu({
      "/api/v1/tampon/akislar": {
        akislar: [
          { ...akis, anahtar: "oracle_reportdb", ad: "ReportDB alarm özeti", yontem: "işçi (6 dk)", yer: "yonetim/tampon?sekme=canli", son: "2026-10-06T15:25:16Z", durum: "bayat" },
          { ...akis, anahtar: "onedesk", ad: "Onedesk kayıt aktarımı", yer: "onedesk", son: "2026-10-14T16:07:46Z", durum: "bilgi" },
          { ...akis, anahtar: "temip", ad: "TEMIP alarm kayıtları", yer: "yonetim/tampon?sekme=akis", durum: "taze", son: "2026-10-18T07:00:00Z", acik: 5, kapali: 2, radar: 3 },
        ],
        dagitim: { kural: 0, etkin: 0, son_uygulama: null },
        uyarilar: ["ReportDB alarm özeti: veri bayat"],
        zaman: "2026-10-18T07:00:00Z",
      },
    })
    sarmala(<VeriAkislariPaneli dil="tr" />)
    expect(await screen.findByText(/1 akışta veri bayat/)).toBeTruthy()
    expect(screen.getByText(a.akislar.durumAdi.bayat)).toBeTruthy()
    expect(screen.getByText(/5 açık · 2 kapalı · 3 Radar'da/)).toBeTruthy()
    const baglantilar = screen.getAllByRole("link", { name: a.akislar.git })
    // 2026-10-24: Veri Girisi sekmeli; akis kendi sekmesine (Canli DB / Veri Akisi / Import) ya da baska ekrana gider
    expect(baglantilar.map((x) => x.getAttribute("href"))).toEqual(["#/yonetim/tampon?sekme=canli", "#/onedesk", "#/yonetim/tampon?sekme=akis"])
  })

  it("dagitim ve TEMIP tembel: kapaliyken istek gitmez, kural onerisi dagitimi acar", async () => {
    const cagrilar = sahteSunucu({ "/api/v1/tampon/kurallar": [], "/api/v1/tampon/hedefler": { hedefler: [], islemler: [], eslesme_alanlari: {} }, "/api/v1/tampon/uygulamalar": [] })
    const ozellik = { dil: "tr" as const, parti: null, kaynakAnahtarlari: [], kural: 0, etkin: 0 }
    const { rerender } = sarmala(
      <>
        <Dagitim {...ozellik} oneri={null} />
        <TemipEslesmesi dil="tr" />
      </>,
    )
    expect(screen.getByText(a.kuralRozeti(0, 0))).toBeTruthy()
    await new Promise((r) => setTimeout(r, 20))
    expect(cagrilar).toEqual([])
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <Dagitim {...ozellik} oneri={{ kolon: "Müşteri No", alan: "customer_no", sayac: 1 }} />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(cagrilar.some((c) => c.includes("/api/v1/tampon/kurallar"))).toBe(true))
    expect(cagrilar.some((c) => c.includes("/temip/eslesme"))).toBe(false)
  })

  it("TEMIP eslesmesi: sema hazir degilse komut setini, hazirsa ozet ve personeli gosterir", async () => {
    window.localStorage.setItem("mkBolum:yonetim-tampon-temip", "1")
    sahteSunucu({ "/api/v1/tampon/temip/eslesme": { hazir: false, neden: "0013_onedesk_temip uygulanmadı." } })
    sarmala(<TemipEslesmesi dil="tr" />)
    expect(await screen.findByText(/temip_kayit_ice_al\.ps1/)).toBeTruthy()
    cleanup()
    const ozet = { musteri: 0, acik: 0, kapali: 0 }
    sahteSunucu({
      "/api/v1/tampon/temip/eslesme": {
        hazir: true,
        ozet: { kart: { musteri: 1, acik: 2, kapali: 1 }, kart_personelsiz: ozet, radar: { musteri: 1, acik: 1, kapali: 0 }, belirsiz: ozet },
        personel: [{ personel: "Ornek Tam", personel_kullanici: "ornek_tam", tam: true, kart: 1, musteri_no: 1, acik: 2, acik_ticketli: 1, kapali: 1 }],
        uyari: { belirsiz_numara: [], personelsiz_kart: [], bicimsiz_kart_no: ["UZUN-NO"], kayitsiz_numarali_kart: 4 },
        bagli_olmayan: 0,
        toplam: 1,
        sayfa: 1,
        adet: 50,
        musteriler: [{ musteri_no: "10000001", temip_unvan: "ORNEK A.S.", durum: "kart", kart_id: 3, panel_unvan: "ORNEK-A", cati: "", personel: "Ornek Tam",
          personel_kullanici: "ornek_tam", acik: 2, acik_ticketli: 1, kapali: 1, toplam: 3, aday_kartlar: "" }],
      },
    })
    sarmala(<TemipEslesmesi dil="tr" />)
    expect(await screen.findByRole("link", { name: "ORNEK-A" })).toHaveAttribute("href", "#/musteri?m=3")
    expect(screen.getAllByText("Ornek Tam").length).toBeGreaterThan(0)
    expect(screen.getByText(/8 haneden uzun Müşteri No yazılı \(hiç eşleşmez\): UZUN-NO/)).toBeTruthy()
  })

  it("genel CSV: kaynak adi ve dosyayla tampona yukler", async () => {
    const cagrilar = sahteSunucu({ "/api/v1/tampon/yukle": { id: 9, kaynak: "csv_alarm", satir: 3, durum: "ready" } })
    const secilen: number[] = []
    sarmala(<GenelCsvYukle dil="tr" onYeniParti={(id) => secilen.push(id)} />)
    fireEvent.click(screen.getByRole("button", { name: a.csv.yukle }))
    expect(await screen.findByText(a.csv.eksik)).toBeTruthy()
    fireEvent.change(screen.getByLabelText(a.csv.kaynakAdi, { exact: false }), { target: { value: "alarm" } })
    fireEvent.change(screen.getByLabelText(a.csv.dosya), { target: { files: [new File(["No;Adet\n1;2\n"], "a.csv", { type: "text/csv" })] } })
    fireEvent.click(screen.getByRole("button", { name: a.csv.yukle }))
    expect(await screen.findByText(a.csv.yuklendi(9, 3))).toBeTruthy()
    expect(cagrilar).toContain("PUT /api/v1/tampon/yukle?kaynak=alarm&dosya=a.csv")
    expect(secilen).toEqual([9])
  })
})

describe("Veri Girisi yeni duzen (2026-10-24)", () => {
  const a = tm("tr")
  const y = a.yapi
  let Tampon: typeof import("@/yonetim/bolumler/tampon").default
  // Sekme modulu agir (tum Veri Girisi bilesenleri): ilk testin 5 sn sinirina sayilmasin diye bir kez, uzun sureyle yuklenir.
  beforeAll(async () => {
    Tampon = (await import("@/yonetim/bolumler/tampon")).default
  }, 60_000)
  afterEach(() => {
    window.location.hash = ""
  })
  async function ac(hash: string) {
    window.location.hash = hash
    sarmala(<Tampon dil="tr" />)
    return screen.getAllByRole("tablist")
  }

  it("bes sekme; varsayilan Canli DB ve dort veritabani alt sekmesi", async () => {
    sahteSunucu({})
    const [ana, dbler] = await ac("#/yonetim/tampon")
    expect(within(ana).getAllByRole("tab").map((s) => s.textContent)).toEqual([y.sekme.canli, y.sekme.akis, y.sekme.import, y.sekme.eslesme, y.sekme.fark])
    expect(within(ana).getByRole("tab", { name: y.sekme.canli })).toHaveAttribute("aria-selected", "true")
    expect(within(dbler).getAllByRole("tab").map((s) => s.textContent)).toEqual(["ReportDB", "ONEDESKDB", "ONENTDB", "GALAPAGOSDB"])
    expect(screen.queryByText(y.importAciklama)).toBeNull()
  })

  it("adreste parti varsa Veri Akisi acilir; hat adimlari sirayla", async () => {
    sahteSunucu({})
    const [ana] = await ac("#/yonetim/tampon?parti=5")
    expect(within(ana).getByRole("tab", { name: y.sekme.akis })).toHaveAttribute("aria-selected", "true")
    const hat = screen.getByRole("list", { name: y.sekme.akis })
    expect(within(hat).getAllByRole("listitem").map((x) => x.textContent?.replace("→", "").trim())).toEqual(y.adimlar.map((s, i) => `${i + 1} · ${s}`))
  })

  it("Import: tek giris noktasi - ham musteri, genel CSV, Gelir Faydasi ve Urun-Tutar", async () => {
    sahteSunucu({})
    await ac("#/yonetim/tampon?sekme=import")
    expect(screen.getByText(y.importAciklama)).toBeInTheDocument()
    for (const b of [a.ham.baslik, a.csv.baslik, y.gelirFaydasi, y.urunTutar]) expect(screen.getAllByText(b).length).toBeGreaterThan(0)
    expect(screen.getByRole("button", { name: "Excel'den içe aktar" })).toBeInTheDocument()
  })

  it("Musteri Eslesmesi: kaynak bazinda oran rozeti, kartsiz numaralar ve yonlendirme", async () => {
    sahteSunucu({
      "/api/v1/tampon/eslesme": {
        kaynaklar: [
          { anahtar: "onedesk:temip", ad: "TEMIP alarm kayıtları", toplam: 362478, karta_eslesen: 150005, tam_atanmis: 150005, kartsiz: 212473, oran: 41.4, yer: "yonetim/tampon?sekme=akis", not: "" },
          { anahtar: "urun_tutar", ad: "Ürün-Tutar Excel", toplam: 44, karta_eslesen: 44, tam_atanmis: 44, kartsiz: 0, oran: 100, yer: "yonetim/tampon?sekme=import", not: "" },
        ],
        kartlar: { toplam: 339, tam_atanmis: 339, tam_siz: 0 },
        kartsiz_ilk: [{ musteri_no: "23659267", ad: "ORNEK TOPTAN A.S.", adet: 54021 }],
        zaman: "2026-10-24T08:00:00Z",
      },
    })
    await ac("#/yonetim/tampon?sekme=eslesme")
    expect(await screen.findByText("%41.4")).toBeInTheDocument()
    expect(screen.getByText("%100")).toBeInTheDocument()
    expect(screen.getByText(a.eslesme.kartlar(339, 339, 0))).toBeInTheDocument()
    expect(screen.getByText("23659267")).toBeInTheDocument()
    expect(screen.getAllByRole("link", { name: a.eslesme.git }).map((x) => x.getAttribute("href"))).toEqual(["#/yonetim/tampon?sekme=akis", "#/yonetim/tampon?sekme=import"])
    expect(screen.getByRole("link", { name: a.eslesme.radar })).toHaveAttribute("href", "#/radar")
    expect(screen.getByRole("link", { name: a.eslesme.temipAta })).toHaveAttribute("href", "#/yonetim/tampon?sekme=fark")
  })

  it("Fark: eslesmeyenler listelenir; secilen kartsizlar toplu personele, TAM'siz kart personele atanir", async () => {
    const f = a.fark
    const satir = (musteri_no: string, durum: string, ek: Record<string, unknown> = {}) => ({
      musteri_no, temip_unvan: `ORNEK ${musteri_no}`, durum, kart_id: "", panel_unvan: "", cati: "", personel: "", personel_kullanici: "",
      acik: 1, acik_ticketli: 0, kapali: 2, toplam: 3, aday_kartlar: "", kaynak: "TEMIP", ...ek,
    })
    const liste = {
      hazir: true,
      ozet: { radar: { musteri: 2, kayit: 6, acik: 2 }, belirsiz: { musteri: 1, kayit: 3, acik: 1 }, kart_personelsiz: { musteri: 1, kayit: 3, acik: 1 } },
      toplam_kayit: 20,
      toplam: 4,
      sayfa: 1,
      adet: 50,
      satirlar: [
        satir("11111111", "radar"),
        satir("22222222", "radar"),
        satir("33333333", "belirsiz", { aday_kartlar: "ORNEK-B, ORNEK-C" }),
        satir("44444444", "kart_personelsiz", { kart_id: 7, panel_unvan: "ORNEK-D" }),
      ],
    }
    const govdeler: { yol: string; govde: unknown }[] = []
    vi.stubGlobal("confirm", () => true)
    vi.stubGlobal(
      "fetch",
      vi.fn(async (girdi: string, ayar?: RequestInit) => {
        const yol = String(girdi)
        if (ayar?.method === "POST") govdeler.push({ yol, govde: JSON.parse(String(ayar.body)) })
        const veri = yol.includes("/fark/toplu-ata") ? { atanan: 1, atlanan: [{ musteri_no: "22222222", neden: "Bu ünvanla kayıtlı başka bir müşteri var." }], kartlar: ["ORNEK 11111111"], yeniden_baglanan: 3, etkilenen_kart: 1 }
          : yol.includes("/fark/kart-sahibi") ? { kart_id: 7, kart: "ORNEK-D", personel: "Ornek Tam" }
          : yol.includes("/fark/radara-ata") ? { atanan: 2, atlanan: [] }
          : yol.includes("/tampon/fark") ? liste
          : yol.includes("/temip/personel") ? [{ id: 5, ad: "Ornek Tam" }]
          : yol.includes("/temip/atamalar") ? []
          : null
        return new Response(JSON.stringify(veri === null ? { detail: "yok" } : { status: "success", data: veri }), { status: veri === null ? 404 : 200, headers: { "Content-Type": "application/json" } })
      }),
    )
    await ac("#/yonetim/tampon?sekme=fark")
    expect(await screen.findByText(f.toplamKayit("12", "20"))).toBeInTheDocument()
    expect(screen.getByText("ORNEK-B, ORNEK-C")).toBeInTheDocument()
    expect(screen.queryByRole("checkbox", { name: f.sec("33333333") })).toBeNull()  // yalniz kartsiz secilir
    const ata = screen.getByRole("button", { name: f.topluAta })
    expect(ata).toBeDisabled()
    fireEvent.click(screen.getByRole("button", { name: f.sayfayiSec }))
    expect(screen.getByText(f.secili(2))).toBeInTheDocument()
    await screen.findAllByRole("option", { name: "Ornek Tam" })
    fireEvent.change(screen.getByRole("combobox", { name: f.topluPersonel }), { target: { value: "5" } })
    fireEvent.click(ata)
    expect(await screen.findByText(f.topluSonuc(1, "3", 1))).toBeInTheDocument()
    expect(govdeler[0]).toEqual({ yol: "/api/v1/tampon/fark/toplu-ata", govde: { musteri_nolar: ["11111111", "22222222"], tam_id: 5 } })
    expect(screen.getByText(f.secili(0))).toBeInTheDocument()

    fireEvent.change(screen.getByRole("combobox", { name: `${f.tamSec} · ORNEK-D` }), { target: { value: "5" } })
    fireEvent.click(screen.getByRole("button", { name: f.tamSec }))
    expect(await screen.findByText(f.tamAtandi("ORNEK-D", "Ornek Tam"))).toBeInTheDocument()
    expect(govdeler[1]).toEqual({ yol: "/api/v1/tampon/fark/kart-sahibi", govde: { kart_id: 7, tam_id: 5 } })

    // Musteri Radar personel gibi secilir: kart acilmaz, numaralar Radar'a gider
    fireEvent.click(screen.getByRole("button", { name: f.sayfayiSec }))
    fireEvent.change(screen.getByRole("combobox", { name: f.topluPersonel }), { target: { value: "radar" } })
    expect(screen.getByRole("option", { name: f.radarSecenek })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: f.topluAta }))
    expect(await screen.findByText(f.radarSonuc(2, 0))).toBeInTheDocument()
    expect(govdeler[2]).toEqual({ yol: "/api/v1/tampon/fark/radara-ata", govde: { musteri_nolar: ["11111111", "22222222"] } })
  })
})

describe("ReportDB ham veri okuyucu", () => {
  const k = tm("tr").katalog
  const tablo = (id: number, ad: string, ust: string, isabet: number) => ({ id, sahip: "TEMIP", ad, ust, pencere: "tüm tablo", satir: 100, isabet, oran: 1, sutunlar: [] })
  const katalog = {
    kaynak: "oracle_reportdb",
    katalog: { id: 1, durum: "ready", baslangic: "2026-10-18T08:00:00Z", bitis: "2026-10-18T08:00:30Z", olusturan: "admin", ozet: { nesne: 15, sutun: 788, sure_sn: 30 }, hata: "" },
    calisiyor: false,
    son_hata: "",
    semalar: [],
    parametreler: { ara: "nw_li_", alan: "NETWORK", degerler: ["ACCESS", "NOC DESTECH"], saat: 6, satir_siniri: 1000000, eslesmeyen: [] },
    parametre_agaci: [
      { domain: "ACCESS", isabet: 5, satir: 100, tablolar: [tablo(2, "ACTIVEALARMS_5DK_S1", "ACTIVEALARMS_5DK", 5), tablo(9, "ALARMS", "", 0)] },
      { domain: "NOC DESTECH", isabet: 30, satir: 100, tablolar: [tablo(2, "ACTIVEALARMS_5DK_S1", "ACTIVEALARMS_5DK", 10), tablo(3, "VIEW_REPORT_EXPORT", "", 20)] },
    ],
  }
  const veri = {
    id: 3, ad: "TEMIP.VIEW_REPORT_EXPORT", pencere: "ilk 1.000.000 satır", ara: "nw_li_", domainler: ["ACCESS", "NOC DESTECH"],
    sutunlar: ["NODE1", "IDENTIFIER", "NETWORK"], isabetli: ["NODE1"], gizlenen_bos: 40, toplam_ham: 2, toplam: 2, sayfa: 1, adet: 100,
    satirlar: [["nw_li_cust_a", 1, "NOC DESTECH"], ["nw_li_cust_b", 2, "NOC DESTECH"]], filtreli: [],
  }

  it("filtreler: domain dugmeleri, tarama filtresi, isabetli tablolar; bos sutun gizli, isabet vurgulu", async () => {
    const cagrilar = sahteSunucu({ "/api/v1/tampon/katalog/veri": veri, "/api/v1/tampon/katalog": katalog })
    sarmala(<ReportdbKatalogu dil="tr" />)
    expect(await screen.findByText("nw_li_cust_a")).toBeTruthy()
    expect(screen.getByText(k.taramaFiltresi("nw_li_"))).toBeTruthy()
    expect(screen.getByText(k.gizlenenBos(40))).toBeTruthy()
    const secenekler = within(screen.getByLabelText(k.tablo)).getAllByRole("option").map((o) => o.textContent)
    expect(secenekler).toEqual([k.tabloSecenegi("VIEW_REPORT_EXPORT", "20"), k.tabloSecenegi("ACTIVEALARMS_5DK › ACTIVEALARMS_5DK_S1", "15")]) // isabetsiz ALARMS yok
    expect(screen.getByText("nw_li_cust_a").className).toContain("bg-tl-yellow")
    expect(cagrilar.some((c) => c.includes("/katalog/veri?nesne=3") && c.includes("domain=ACCESS&domain=NOC%20DESTECH"))).toBe(true)
    fireEvent.click(screen.getByRole("button", { name: "NETWORK = ACCESS" }))
    await waitFor(() => expect(cagrilar.some((c) => c.includes("/katalog/veri?nesne=3") && c.endsWith("domain=NOC%20DESTECH"))).toBe(true))
    fireEvent.click(screen.getByRole("button", { name: "NETWORK = NOC DESTECH" }))
    expect(await screen.findByText(k.domainEnAzBir)).toBeTruthy()
  })

  it("sutun basligi: Excel filtresi (deger listesi, tumunu sec, tamam) ve siralama", async () => {
    const cagrilar = sahteSunucu({
      "/api/v1/tampon/katalog/veri/degerler": { sutun: "NODE1", farkli: 2, kesildi: false, degerler: [{ deger: "nw_li_cust_a", adet: 1 }, { deger: "nw_li_cust_b", adet: 1 }] },
      "/api/v1/tampon/katalog/veri": veri,
      "/api/v1/tampon/katalog": katalog,
    })
    sarmala(<ReportdbKatalogu dil="tr" />)
    fireEvent.click(await screen.findByRole("button", { name: k.filtreMenusu("NODE1") }))
    const menu = await screen.findByRole("dialog", { name: k.filtreMenusu("NODE1") })
    expect(await within(menu).findByText("nw_li_cust_b")).toBeTruthy()
    fireEvent.click(within(menu).getByRole("checkbox", { name: /nw_li_cust_b/ }))
    expect((within(menu).getByRole("checkbox", { name: k.tumunuSec }) as HTMLInputElement).checked).toBe(false)
    fireEvent.click(within(menu).getByRole("button", { name: k.tamam }))
    await waitFor(() => expect(cagrilar.some((c) => c.includes(`filtre=${encodeURIComponent(JSON.stringify({ NODE1: ["nw_li_cust_a"] }))}`))).toBe(true))
    expect(screen.queryByRole("dialog")).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: k.filtreMenusu("IDENTIFIER") }))
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: k.siralaZa }))
    await waitFor(() => expect(cagrilar.some((c) => c.includes("sirala=IDENTIFIER") && c.includes("yon=desc"))).toBe(true))
  })

  it("katalog yoksa bos kutu; yenile isciyi baslatir", async () => {
    const cagrilar = sahteSunucu({ "/api/v1/tampon/katalog/yenile": { basladi: true, calisiyor: true }, "/api/v1/tampon/katalog": { ...katalog, katalog: null } })
    sarmala(<ReportdbKatalogu dil="tr" />)
    expect(await screen.findByText(k.yok)).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: k.yenile }))
    expect(await screen.findByText(k.basladi)).toBeTruthy()
    expect(cagrilar).toContain("POST /api/v1/tampon/katalog/yenile")
  })
})

describe("TEMIP elle atama", () => {
  const a = atamaMetin("tr")
  const ozet = { musteri: 0, acik: 0, kapali: 0 }
  const eslesme = {
    hazir: true,
    ozet: { kart: ozet, kart_personelsiz: ozet, radar: { musteri: 1, acik: 1, kapali: 2 }, belirsiz: ozet },
    personel: [],
    uyari: { belirsiz_numara: [], personelsiz_kart: [], bicimsiz_kart_no: [], kayitsiz_numarali_kart: 0 },
    bagli_olmayan: 0, toplam: 1, sayfa: 1, adet: 50,
    musteriler: [{ musteri_no: "22306933", temip_unvan: "TURK EKONOMI BANKASI A.S.", durum: "radar", kart_id: "", panel_unvan: "", cati: "", personel: "",
      personel_kullanici: "", acik: 1, acik_ticketli: 1, kapali: 2, toplam: 3, aday_kartlar: "" }],
  }  // prettier-ignore

  it("Radar satirinda Karta ata: unvanla kart arar, onayla atar; elle atamalar listesi geri alinir", async () => {
    window.localStorage.setItem("mkBolum:yonetim-tampon-temip", "1")
    vi.stubGlobal("confirm", () => true)
    const atamalar = [{ musteri_no: "22306933", temip_unvan: "TURK EKONOMI BANKASI A.S.", kart_id: 7, kart: "TÜRK EKONOMI BANKASI A.S", kayit: 3, kim: "admin", zaman: "2026-10-18T19:00:00Z" }]
    const cagrilar: { yol: string; govde: unknown }[] = []
    vi.stubGlobal(
      "fetch",
      vi.fn(async (girdi: string, ayar?: RequestInit) => {
        const yol = String(girdi)
        cagrilar.push({ yol: `${ayar?.method ?? "GET"} ${yol}`, govde: typeof ayar?.body === "string" ? JSON.parse(ayar.body) : null })
        const veri = yol.includes("/temip/personel") ? [{ id: 5, ad: "Ornek Tam" }]
          : yol.includes("/temip/kartlar") ? [{ id: 7, ad: "TÜRK EKONOMI BANKASI A.S", musteri_no: "11245635", istirak: false }]
          : yol.includes("/temip/ata/kaldir") ? { musteri_no: "22306933", kart_id: 7 }
          : yol.includes("/temip/atamalar") ? atamalar
          : yol.includes("/temip/ata") ? { musteri_no: "22306933", kart: "TÜRK EKONOMI BANKASI A.S", kayit: 3, yeniden_baglanan: 3, yeni_kart: false }
          : eslesme  // prettier-ignore
        return new Response(JSON.stringify({ status: "success", data: veri }), { status: 200, headers: { "Content-Type": "application/json" } })
      }),
    )
    sarmala(<TemipEslesmesi dil="tr" />)
    fireEvent.click(await screen.findByRole("button", { name: a.karttaAta }))
    const panel = await screen.findByRole("region", { name: a.baslik("22306933") })
    expect((within(panel).getByLabelText(a.kartAra) as HTMLInputElement).value).toBe("TURK EKONOMI") // unvandan tohum
    fireEvent.click(await within(panel).findByRole("button", { name: a.ata }))
    expect(await within(panel).findByText(a.atandi("22306933", "TÜRK EKONOMI BANKASI A.S", "3"))).toBeTruthy()
    expect(cagrilar.find((c) => c.yol.startsWith("POST") && c.yol.endsWith("/temip/ata"))?.govde).toEqual({ musteri_no: "22306933", kart_id: 7 })
    expect(cagrilar.some((c) => c.yol.includes("/temip/kartlar?q=TURK"))).toBe(true)
    expect((await screen.findAllByText(a.liste(1))).length).toBeGreaterThan(0) // baslik + tablo aciklamasi
    fireEvent.click(screen.getByRole("button", { name: a.geriAl }))
    expect(await screen.findByText(a.geriAlindi("22306933"))).toBeTruthy()
    expect(cagrilar.find((c) => c.yol.endsWith("/temip/ata/kaldir"))?.govde).toEqual({ musteri_no: "22306933" })
  })
})
