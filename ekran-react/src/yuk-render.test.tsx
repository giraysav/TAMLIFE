import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { Profiler, type ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MusteriKarti, type Kart } from "@/musteri/musteri-karti"
import { RollerSayfasi } from "@/shell/roller-sayfasi"

/* Render ve state izolasyonu: periyodik yenileme (polling) ve onbellek gecersizlestirme altinda form state'i ve mutasyon
 * sonucu ezilmez; ayni veriyle gelen yenileme gereksiz render uretmez. Sunucu, testin degistirebildigi sahte fetch'tir. */

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const json = (veri: unknown, durum = 200) =>
  new Response(JSON.stringify(durum < 400 ? { status: "success", data: veri } : { detail: veri }), { status: durum, headers: { "Content-Type": "application/json" } })

/** Yol parcasina gore cevap ureten sahte sunucu; cevap fonksiyon olabilir (her istekte yeniden cagrilir, Promise donebilir). */
function sunucu(yollar: Record<string, (istek: RequestInit | undefined) => unknown>) {
  const cagrilar: { yol: string; yontem: string }[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn(async (girdi: string, ayar?: RequestInit) => {
      cagrilar.push({ yol: String(girdi), yontem: ayar?.method ?? "GET" })
      const anahtar = Object.keys(yollar).find((k) => String(girdi).includes(k))
      return anahtar === undefined ? json("yok", 404) : json(await yollar[anahtar]!(ayar))
    }),
  )
  return cagrilar
}

function sayac() {
  const commitler: string[] = []
  const sar = (cocuk: ReactNode) => (
    <Profiler id="olcum" onRender={(_, faz) => commitler.push(faz)}>
      {cocuk}
    </Profiler>
  )
  return { commitler, sar }
}

const KART: Kart = {
  kimlik: { id: 9, unvan: "112 ACIL SERVIS", musteri_no: "M-1", ncst: "N-1", segment: "SA", sektor: "Kamu", envanter: 12, tam: "Ayşe TAM", tam_id: 7, ayri_rapor: null, cati: null, istirakler: [] },
  operasyon: { ft_hacim: "1.5 M", tam_ft: "0.5 M", final_skor: 81.25, skor_talebi_bekliyor: false, kendi: { envanter: 12, alarm: 0, sikayet: 0, talep: 0, alarm_kapanan: 11, sikayet_kapanan: 2, talep_kapanan: 33 }, istirak_dahil: null },
  iletisim: { sales_manager: "Selin Satış", presales_manager: "", tac_name: "Tolga TAC", tac_gsm: "", tac_email: "tac@example.com", sol_kmt_name: "", sol_kmt_gsm: "", sol_kmt_email: "", mobil_kmt_name: "", mobil_kmt_gsm: "", mobil_kmt_email: "", mobil_kmt_detail: "" },
  kritik_ci: { basliklar: [], satirlar: [] },
  raporlar: { toplam: 0, son: [] },
  erisim: { rapor: true, gelir: true, kimlik_duzenle: true, iletisim_duzenle: true, sil: true, tam_degistir: false, rapor_geri_al: true, ayri_rapor_sec: true, istirak_ekle: true },
}

function karti(istemci: QueryClient, sar: (c: ReactNode) => ReactNode) {
  return render(<QueryClientProvider client={istemci}>{sar(<MusteriKarti id={9} dil="tr" />)}</QueryClientProvider>)
}

describe("MusteriKarti: polling altinda form state izolasyonu ve render butcesi", () => {
  it("25 yenileme turunda sunucu verisi degisirken formdaki uc alan korunur; Vazgec en son sunucu degerini gosterir", async () => {
    let tur = 0
    sunucu({ "/api/v1/musteri/9": () => ({ ...KART, kimlik: { ...KART.kimlik, unvan: `SUNUCU-${tur}`, ncst: `N-${tur}` }, iletisim: { ...KART.iletisim, tac_email: `t${tur}@x.com` } }) })
    const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    karti(istemci, (c) => c)
    await screen.findByRole("heading", { name: "SUNUCU-0", level: 2 })
    fireEvent.click(screen.getByRole("button", { name: "Düzenle" }))
    const form = screen.getByRole("form", { name: "Düzenle" })
    const alan = (etiket: string) => within(form).getByLabelText(etiket) as HTMLInputElement
    fireEvent.change(alan("NCST"), { target: { value: "YAZILAN-NCST" } })
    fireEvent.change(alan("TAC · E-posta"), { target: { value: "yazilan@ornek.com" } })
    const unvan = document.querySelector<HTMLInputElement>("#k-name")!
    fireEvent.change(unvan, { target: { value: "YAZILAN UNVAN" } })

    for (tur = 1; tur <= 25; tur++) {
      await act(() => istemci.refetchQueries({ queryKey: ["musteri", "kart", 9] })) // polling / websocket benzeri dis guncelleme
      expect(alan("NCST").value).toBe("YAZILAN-NCST")
    }
    expect(istemci.getQueryData<Kart>(["musteri", "kart", 9])?.kimlik.unvan).toBe("SUNUCU-25") // onbellek guncel
    expect(unvan.value).toBe("YAZILAN UNVAN")
    expect(alan("TAC · E-posta").value).toBe("yazilan@ornek.com")

    fireEvent.click(within(form).getByRole("button", { name: "Vazgeç" }))
    expect(screen.getByRole("heading", { name: "SUNUCU-25", level: 2 })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Düzenle" }))
    expect((document.querySelector<HTMLInputElement>("#k-name") as HTMLInputElement).value).toBe("SUNUCU-25")
  })

  it("ayni veriyle 30 yenileme gereksiz render uretmez; degisen veri tur basina en cok bir render", async () => {
    let kart: Kart = KART
    sunucu({ "/api/v1/musteri/9": () => kart })
    const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { commitler, sar } = sayac()
    karti(istemci, sar)
    await screen.findByRole("heading", { name: "112 ACIL SERVIS", level: 2 })
    const yenile = () => act(() => istemci.refetchQueries({ queryKey: ["musteri", "kart", 9] }))

    const once = commitler.length
    for (let i = 0; i < 30; i++) await yenile()
    expect(commitler.length - once).toBe(0) // yapisal paylasim: ayni JSON ayni referans, izlenen alan degismez

    const ara = commitler.length
    for (let i = 1; i <= 5; i++) {
      kart = { ...KART, operasyon: { ...KART.operasyon, final_skor: 80 + i } }
      await yenile()
    }
    expect(commitler.length - ara).toBeLessThanOrEqual(5)
  })

  it("duzenleme sirasinda her tus vurusu tek render; yenileme formu yeniden kurmaz (odak ve imlec korunur)", async () => {
    sunucu({ "/api/v1/musteri/9": () => KART })
    const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { commitler, sar } = sayac()
    karti(istemci, sar)
    await screen.findByRole("heading", { name: "112 ACIL SERVIS", level: 2 })
    fireEvent.click(screen.getByRole("button", { name: "Düzenle" }))
    const ncst = within(screen.getByRole("form", { name: "Düzenle" })).getByLabelText("NCST") as HTMLInputElement
    ncst.focus()
    const once = commitler.length
    for (const harf of "ABCDEFGHIJ") fireEvent.change(ncst, { target: { value: ncst.value + harf } })
    expect(commitler.length - once).toBe(10)
    await act(() => istemci.refetchQueries({ queryKey: ["musteri", "kart", 9] }))
    expect(within(screen.getByRole("form", { name: "Düzenle" })).getByLabelText("NCST")).toBe(ncst) // ayni DOM dugumu
    expect(document.activeElement).toBe(ncst)
  })
})

const ROLLER = {
  catalog: [{ id: "sunum", label: "Çeyrek Sunum", label_en: "Quarterly Presentation", admin_only: false, children: [] }],
  permission_catalog: [
    { id: "sunum.gonder", label: "Çeyrek sunumu yönet", label_en: "Manage", description: "", description_en: "", where: "", where_en: "", area: "sunum" },
  ],
  roles: [
    { role: "admin", label: "Admin", editable: false, modules: ["sunum"], landing: "ozet", permissions: ["sunum.gonder"], saved: false },
    { role: "TeamMember", label: "Member", editable: true, modules: ["sunum"], landing: "ozet", permissions: [], saved: true },
  ],
  users: [{ id: 3, username: "gsav", display_name: "Giray Sav", role: "TeamMember", auth: "AD", ad_domain: "TURKCELL", last_login_at: null, permissions: [] as string[] }],
}

describe("Roller: TanStack Query onbellek gecersizlestirme yarisi", () => {
  it("yazmadan once baslayan arka plan yenilemesi sonra donerse kaydedilen yetkiyi geri almaz", async () => {
    let geciken: ((v: unknown) => void) | null = null
    let getSayisi = 0
    sunucu({
      "/api/v1/roller/kisiler/3": () => ({ id: 3, permissions: ["sunum.gonder"] }),
      "/api/v1/roller": () => {
        getSayisi += 1
        if (getSayisi === 1) return ROLLER
        return new Promise((coz) => (geciken = coz)) // yavas yenileme: YAZMADAN ONCEKI veriyi tasir
      },
      "/api/v1/sunum/kaynaklar": () => ({ duzenleyebilir: true, kaynaklar: [] }),
    })
    const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={istemci}>
        <RollerSayfasi dil="tr" />
      </QueryClientProvider>,
    )
    fireEvent.click(await screen.findByRole("button", { name: /Yetkili personel/ }))
    void istemci.invalidateQueries({ queryKey: ["roller"] }) // baska sekmeden / periyodik yenileme
    await waitFor(() => expect(geciken).not.toBeNull())

    const liste = screen.getByRole("group", { name: "Yetkili personel" })
    fireEvent.click(within(liste).getByRole("checkbox", { name: "Giray Sav" }))
    await waitFor(() => expect(within(liste).getByRole("checkbox", { name: "Giray Sav" })).toBeChecked())

    await act(async () => geciken!(ROLLER)) // eski yanit simdi geliyor
    expect(within(screen.getByRole("group", { name: "Yetkili personel" })).getByRole("checkbox", { name: "Giray Sav" })).toBeChecked()
    expect(istemci.getQueryData<typeof ROLLER>(["roller"])?.users[0]!.permissions).toEqual(["sunum.gonder"])
  })

  it("arka arkaya 20 gecersizlestirme istek firtinasi yaratmaz (tekillestirme)", async () => {
    const cagrilar = sunucu({ "/api/v1/roller": () => ROLLER, "/api/v1/sunum/kaynaklar": () => ({ duzenleyebilir: true, kaynaklar: [] }) })
    const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={istemci}>
        <RollerSayfasi dil="tr" />
      </QueryClientProvider>,
    )
    await screen.findByRole("button", { name: /Yetkili personel/ })
    const once = cagrilar.filter((c) => c.yol.endsWith("/api/v1/roller")).length
    await act(async () => {
      for (let i = 0; i < 20; i++) void istemci.invalidateQueries({ queryKey: ["roller"] }, { cancelRefetch: false })
    })
    await waitFor(() => expect(istemci.isFetching({ queryKey: ["roller"] })).toBe(0))
    expect(cagrilar.filter((c) => c.yol.endsWith("/api/v1/roller")).length - once).toBe(1)
  })
})
