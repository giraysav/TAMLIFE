import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { RadarSayfasi } from "@/radar/radar-sayfasi"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function sunucu(veri: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ status: "success", data: veri }), { status: 200, headers: { "Content-Type": "application/json" } })),
  )
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={istemci}>
      <RadarSayfasi dil="tr" />
    </QueryClientProvider>,
  )
}

describe("Musteri Radar sayfasi", () => {
  it("adaylar: sira, unvan, alarm acik/kapanan, toplam; bayat veri uyarisi ve veri zamani", async () => {
    sunucu({ var: true, taze: false, veri_zamani: "2026-10-06 12:30:00", satirlar: [{ sira: 1, musteri_no: "10000004", unvan: "BETA ENERJI", aktif: 30, kapanan: 1200, toplam: 1230 }] })
    expect(await screen.findByText("BETA ENERJI")).toBeInTheDocument()
    expect(screen.getByText("30 / 1.200")).toBeInTheDocument()
    expect(screen.getByText("1.230")).toBeInTheDocument()
    expect(screen.getByText(/güncel değil/)).toBeInTheDocument()
    expect(screen.getByText(/Veri zamanı: 2026-10-06 12:30:00/)).toBeInTheDocument()
    expect(screen.getAllByTitle("OneDesk bilet şeması erişimi bekleniyor")).toHaveLength(2)
  })

  it("TEMIP kayit kipi: ticketli/son kayit, kart adayi rozeti, ozet; Kayitlar dugmesi musterinin kayitlarini acar", async () => {
    const radar = {
      var: true, taze: true, veri_zamani: "2026-10-17T18:00:00Z", kaynak: "kayit", toplam_musteri: 1, toplam_kayit: 73, sayfa: 1, adet: 50,
      satirlar: [{ sira: 1, musteri_no: "23659267", unvan: "VODAFONE NET", aktif: 3, kapanan: 70, toplam: 73, ticketli: 60, son_kayit: "2026-10-17T16:46:00Z", kart_adayi: { id: 9, ad: "VODAFONE" } }],
    }
    const kayit = {
      musteri_no: "23659267", unvan: "VODAFONE NET", toplam: 1, sayfa: 1, adet: 50,
      kayitlar: [{ kimlik: "43601244", ticket: "10134785623", ci: "nw_li_cust_x", baslik: "AVAILABILITY", durum: "closed", ayrinti: "Closed/atm", acilis: "2026-10-17T16:46:00Z", kapanis: "2026-10-17T17:57:00Z" }],
    }
    const fetchSahte = vi.fn(async (url: string) =>
      new Response(JSON.stringify({ status: "success", data: url.includes("/kayitlar") ? kayit : radar }), { status: 200, headers: { "Content-Type": "application/json" } }),
    )
    vi.stubGlobal("fetch", fetchSahte)
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RadarSayfasi dil="tr" />
      </QueryClientProvider>,
    )
    expect(await screen.findByText("VODAFONE NET")).toBeInTheDocument()
    expect(screen.getByText(/1 müşteri · 73 kayıt/)).toBeInTheDocument()
    expect(screen.getByText(/Aynı ünvanlı kart var: VODAFONE/)).toBeInTheDocument()
    expect(screen.getByText("60")).toBeInTheDocument()
    expect(String(fetchSahte.mock.calls[0][0])).toContain("adet=50")
    fireEvent.click(screen.getByRole("button", { name: "Kayıtlar" }))
    expect(await screen.findByText("10134785623")).toBeInTheDocument()
    expect(screen.getByText("Closed/atm")).toBeInTheDocument()
    expect(String(fetchSahte.mock.calls.at(-1)?.[0])).toContain("/api/v1/radar/23659267/kayitlar")
  })

  it("ReportDB verisi yoksa aciklama", async () => {
    sunucu({ var: false, taze: false, veri_zamani: null, satirlar: [] })
    expect(await screen.findByText(/ReportDB verisi henüz alınmadı/)).toBeInTheDocument()
  })

  it("yonetici: Personele ata -> personel sec -> yeni kart ac; uye kullanicida dugme yok", async () => {
    vi.stubGlobal("confirm", () => true)
    const radar = {
      var: true, taze: true, veri_zamani: "2026-10-17T18:00:00Z", kaynak: "kayit", toplam_musteri: 1, toplam_kayit: 3, sayfa: 1, adet: 50,
      satirlar: [{ sira: 1, musteri_no: "22306933", unvan: "TURK EKONOMI BANKASI A.S.", aktif: 1, kapanan: 2, toplam: 3, ticketli: 1, son_kayit: null, kart_adayi: null }],
    }  // prettier-ignore
    const cagrilar: { yol: string; govde: unknown }[] = []
    vi.stubGlobal(
      "fetch",
      vi.fn(async (girdi: string, ayar?: RequestInit) => {
        const yol = String(girdi)
        cagrilar.push({ yol: `${ayar?.method ?? "GET"} ${yol}`, govde: typeof ayar?.body === "string" ? JSON.parse(ayar.body) : null })
        const veri = yol.includes("/temip/personel") ? [{ id: 5, ad: "Ornek Tam" }]
          : yol.includes("/temip/kartlar") ? []
          : yol.includes("/temip/atamalar") ? []
          : yol.includes("/temip/ata") ? { musteri_no: "22306933", kart: "TEB YENI", kayit: 3, yeniden_baglanan: 3, yeni_kart: true }
          : radar  // prettier-ignore
        return new Response(JSON.stringify({ status: "success", data: veri }), { status: 200, headers: { "Content-Type": "application/json" } })
      }),
    )
    const { unmount } = render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RadarSayfasi dil="tr" />
      </QueryClientProvider>,
    )
    expect(await screen.findByText("TURK EKONOMI BANKASI A.S.")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Personele ata" })).toBeNull() // yalniz admin
    unmount()
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RadarSayfasi dil="tr" yonetici />
      </QueryClientProvider>,
    )
    fireEvent.click(await screen.findByRole("button", { name: "Personele ata" }))
    const panel = await screen.findByRole("region", { name: "22306933 numarasını personele ata" })
    const secim = within(panel).getByLabelText("Personel") as HTMLSelectElement
    await waitFor(() => expect(secim.options.length).toBe(2))
    fireEvent.change(secim, { target: { value: "5" } })
    fireEvent.click(within(panel).getByRole("tab", { name: "Yeni kart aç" }))
    expect((within(panel).getByLabelText("Yeni kartın ünvanı") as HTMLInputElement).value).toBe("TURK EKONOMI BANKASI A.S.")
    fireEvent.click(within(panel).getByRole("button", { name: "Yeni kart aç ve ata" }))
    expect(await within(panel).findByText("22306933 → TEB YENI: 3 kayıt karta bağlandı.")).toBeInTheDocument()
    expect(cagrilar.find((c) => c.yol.startsWith("POST") && c.yol.endsWith("/temip/ata"))?.govde).toEqual({ musteri_no: "22306933", tam_id: 5, unvan: "TURK EKONOMI BANKASI A.S." })
    await waitFor(() => expect(cagrilar.filter((c) => c.yol.startsWith("GET /api/v1/radar")).length).toBeGreaterThan(2)) // atama Radar listesini tazeler
  })

  it("Yonetim sunumu: portfoy slayti (KPI, firsat siralamasi, tema), musteri slayti (kok neden, oneri, ozet, sikayet erisimi yok); YZ kapali notu", async () => {
    const musteri = {
      musteri_no: "30000003", unvan: "ORNEK LOJISTIK A.S.", toplam: 1257, acik: 23, kapanan: 1234, aylik_ortalama: 209.5, lokasyon_sayisi: 145, sdwan_oran: 45.5,
      yedek_oran: 33.6, kendiliginden_oran: 48.3, medyan_cozum_dk: 236, anlik_oran: 0.1, uzun_oran: 96.3, kalite_oran: 0, son30: 224, onceki30: 269, degisim: -16.7, aylar: [{ ay: "2026-09", toplam: 300 }, { ay: "2026-10", toplam: 224 }],
      sure_profili: [{ anahtar: "anlik", ad: "Anlık (< 5 dk)", adet: 1, oran: 0.1 }, { anahtar: "uzun", ad: "Uzun (1–8 sa)", adet: 900, oran: 96.3 }],
      etki: [{ anahtar: "AVAILABILITY", ad: "Erişilemezlik (devre kesintisi)", adet: 1257, oran: 100 }],
      hizmetler: [{ ad: "Mobil erişim (3G/4.5G)", adet: 734, lokasyon: 49, oran: 58.4 }],
      lokasyonlar: [{ ad: "nw_li_cust_a_sdwan", adet: 76 }],
      skor: 71, firsat: "yuksek", ozet: ["1.257 alarm (aylık ortalama 209,5)"], oneriler: [{ baslik: "Mevcut yedek hatların 4.5G/5G'ye yükseltilmesi", gerekce: "Kesintilerin %96,3'ü 1 saatten uzun" }], yz: null,
    }
    const sunum = {
      veri_zamani: "2026-10-25T15:02:50Z", musteri_sayisi: 1, toplam_alarm: 1257, acik_alarm: 23, lokasyon: 145, firsat: { yuksek: 1, orta: 0, dusuk: 0 },
      sure_profili: [{ anahtar: "uzun", ad: "Uzun (1–8 sa)", adet: 900, oran: 96.3 }], etki: [{ anahtar: "AVAILABILITY", ad: "Erişilemezlik (devre kesintisi)", adet: 1257, oran: 100 }], musteriler: [musteri],
      sikayet_talep: { erisim: false, kaynak: "OneDesk", neden: "Okuma yetkisi yok." }, yz: { hazir: false, eksik: ["ANTHROPIC_API_KEY"] },
    }
    vi.stubGlobal("fetch", vi.fn(async (url: string) =>
      new Response(JSON.stringify({ status: "success", data: url.includes("/radar/sunum") ? sunum : { var: true, taze: true, veri_zamani: null, kaynak: "kayit", satirlar: [] } }), { status: 200, headers: { "Content-Type": "application/json" } }),
    ))
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RadarSayfasi dil="tr" yonetici />
      </QueryClientProvider>,
    )
    fireEvent.click(await screen.findByRole("tab", { name: "Yönetim sunumu" }))
    expect(await screen.findByRole("region", { name: "Müşteri Radar · Satış Fırsatı Portföyü" })).toBeInTheDocument()
    expect(screen.getByText(/1 TAM'sız kurumsal müşteri 1.257 ağ alarmı üretti; 1 müşteri yüksek fırsat sınıfında/)).toBeInTheDocument()
    const slayt = screen.getByRole("region", { name: "ORNEK LOJISTIK A.S." })
    expect(within(slayt).getByText("Önerilen fırsat: Mevcut yedek hatların 4.5G/5G'ye yükseltilmesi")).toBeInTheDocument()
    expect(within(slayt).getByText("Mobil erişim (3G/4.5G)")).toBeInTheDocument()
    expect(within(slayt).getByText("3,9 sa")).toBeInTheDocument() // medyan kesinti 236 dk
    expect(within(slayt).getByText(/Veri bekleniyor: Okuma yetkisi yok./)).toBeInTheDocument()
    expect(within(slayt).getByText("Lokasyonların %45,5'i SD-WAN")).toBeInTheDocument()
    expect(screen.getByText(/YZ analizi kapalı/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText("Sunum kapsamı"), { target: { value: "portfoy" } })
    expect(screen.queryByRole("region", { name: "ORNEK LOJISTIK A.S." })).toBeNull()
  })
})
