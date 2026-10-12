import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { sorguMetni } from "@/lib/sorgu"
import type { Katalog, KuralGovdesi, Ozet } from "@/yonetim/api"
import Arizalar from "@/yonetim/bolumler/arizalar"
import Durum from "@/yonetim/bolumler/durum"
import Kurum from "@/yonetim/bolumler/kurum"
import Veritabani from "@/yonetim/bolumler/veritabani"
import { ym } from "@/yonetim/metin"
import { Kaynaklar } from "@/yonetim/tampon/kaynaklar"
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
    expect(screen.getByText(t.kuralIpuclari.anahtarSutunu)).toBeInTheDocument()
    expect(screen.getByText(t.kuralIpuclari.hedef)).toBeInTheDocument()
    expect(screen.getByText(t.kuralIpuclari.enBuyukYas)).toBeInTheDocument()
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
    sarmala(<Kaynaklar dil="tr" onYeniParti={() => {}} />)
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
    const t = ym("tr")
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
    sarmala(<Kaynaklar dil="tr" onYeniParti={() => {}} />)
    fireEvent.click(await screen.findByRole("button", { name: t.ham.onizle }))
    expect(await screen.findByText(t.ham.bicim.liste)).toBeTruthy()
    expect(screen.getByText("TAC E-posta: geçerli bir e-posta adresi olmalı")).toBeTruthy()
    expect(screen.getByRole("link", { name: t.ham.bosSablon })).toHaveAttribute("href", "/api/v1/tampon/musteri-ham/sablon.xlsx")
    fireEvent.click(screen.getByRole("button", { name: t.ham.uygula(1) }))
    expect(await screen.findByText(t.ham.uygulandi(1, 0))).toBeTruthy()
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
        yedek: { dizin: "yedek", desteklenir: true, saklanan: 30, adet: 0, liste: [] },
      },
    })
    sarmala(<Veritabani dil="tr" />)
    expect(await screen.findByRole("link", { name: t.kurumaGit })).toHaveAttribute("href", "#/yonetim/kurum")
    expect(cagrilar.some((c) => c.includes("/tampon/kaynaklar"))).toBe(false)
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
    const t = ym("tr")
    render(<Rehber dil="tr" />)
    expect(screen.getByText(t.rehber.baslik)).toBeInTheDocument()
    expect(screen.getByText(/Tampon \(parti\)/)).toBeInTheDocument()
    for (const b of [t.rehber.kaynaklarBaslik, t.rehber.alanlarBaslik, t.rehber.ornekBaslik, t.rehber.uygulaBaslik]) expect(screen.getByText(b)).toBeInTheDocument()
    expect(screen.getByText(t.kuralIpuclari.eslesmeAlani)).toBeInTheDocument()
    expect(screen.getByText(t.rehber.ornekler[0][0])).toBeInTheDocument()
    cleanup()
    render(<Rehber dil="en" />)
    expect(screen.getByText("How does it work?")).toBeInTheDocument()
  })
})
