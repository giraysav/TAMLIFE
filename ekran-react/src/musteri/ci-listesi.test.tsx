import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MusteriKarti } from "@/musteri/musteri-karti"
import type { Kart } from "@/musteri/musteri-karti"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function sarmala(cocuk: ReactNode) {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={istemci}>{cocuk}</QueryClientProvider>)
}

type Cagri = { yol: string; yontem: string; govde: unknown }

/** fetch: kart istegi KART, CI listesi istegi `liste(yol)` doner; cagrilar kaydedilir. */
function sahteSunucu(kart: Kart, liste: (yol: string) => unknown): Cagri[] {
  const cagrilar: Cagri[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn(async (girdi: string, ayar?: RequestInit) => {
      const yol = String(girdi)
      cagrilar.push({ yol, yontem: ayar?.method ?? "GET", govde: typeof ayar?.body === "string" ? JSON.parse(ayar.body) : null })
      const data = yol.includes("/kritik-ci") ? (ayar?.method === "PUT" ? { tamam: true } : liste(yol)) : yol.endsWith("/api/v1/musteri/9") ? kart : null
      if (data === null) return new Response(JSON.stringify({ detail: "yok" }), { status: 404, headers: { "Content-Type": "application/json" } })
      return new Response(JSON.stringify({ status: "success", data }), { status: 200, headers: { "Content-Type": "application/json" } })
    }),
  )
  return cagrilar
}

const KART: Kart = {
  kimlik: { id: 9, unvan: "112 ACIL SERVIS", musteri_no: "M-1", ncst: "N-1", segment: "SA", sektor: "Kamu", envanter: 12, tam: "Ayşe TAM", tam_id: 7, ayri_rapor: null, rapor_muaf: false, cati: null, istirakler: [] },
  operasyon: { ft_hacim: "", tam_ft: "", final_skor: null, skor_talebi_bekliyor: false, kendi: { envanter: 12, alarm: 0, sikayet: 0, talep: 0, alarm_kapanan: 0, sikayet_kapanan: 0, talep_kapanan: 0 }, istirak_dahil: null },
  iletisim: {},
  kritik_ci: { basliklar: ["CI Adı", "Lokasyon adı"], satirlar: [], toplam: 25, ozet: "25 CI · 2 kritik", ara: "CI adı ara…", adres: "/api/v1/musteri/9/kritik-ci" },
  erisim: { rapor: false, gelir: false, kimlik_duzenle: false, iletisim_duzenle: false, sil: false, tam_degistir: false, rapor_geri_al: false, ayri_rapor_sec: false, rapor_muaf_sec: false, istirak_ekle: false },
}

const LISTE = {
  basliklar: ["CI Adı", "Lokasyon adı"],
  kayitlar: [
    { ci: "C1", kritik: true, hucreler: ["nw_li_ankara_1", "MERKEZ"], lokasyon_duzeltildi: true, lokasyon_ilk: "ANKARA MRK" },
    { ci: "C2", kritik: false, hucreler: ["nw_mbl_izmir_2", ""], lokasyon_duzeltildi: false, lokasyon_ilk: "" },
  ],
  toplam: 25,
  eslesen: 7,
  ozet: "25 CI · 1 kritik",
  kritik_baslik: "Kritik CI",
  evet: "Evet",
  hayir: "Hayır",
  duzenleyebilir: true,
  lokasyon_sutun: 1,
  lokasyon_ipucu: "Lokasyon adını düzeltin",
  kurallar: [
    { onek: "nw_li", ad: "Leased line", ci: 20 },
    { onek: "diger", ad: "Diğer", ci: 5 },
  ],
  kural_baslik: "CI adı filtresi",
  kural_tumu: "Tümü",
  lokasyonlar: ["MERKEZ", "DEPO"],
  lok_baslik: "Lokasyon adı",
  lok_ipucu: "Lokasyon adında ara…",
}

async function cekmeceyiAc() {
  await screen.findByRole("heading", { name: "112 ACIL SERVIS", level: 2 })
  fireEvent.click(screen.getByRole("button", { name: /CI NAME/ }))
  return screen.findByRole("dialog")
}

describe("Musteri karti CI listesi (CI NAME cekmecesi, 2026-11-20..25)", () => {
  it("dugmede toplam CI sayisi; satirlar sunucudan, kritik satir vurgulu, eslesen > gosterilen ise 'n / eslesen'", async () => {
    const cagrilar = sahteSunucu(KART, () => LISTE)
    sarmala(<MusteriKarti id={9} dil="tr" />)
    await screen.findByRole("heading", { name: "112 ACIL SERVIS", level: 2 })
    expect(screen.getByRole("button", { name: /CI NAME/ })).toHaveTextContent("25")
    const pencere = await cekmeceyiAc()
    expect(await within(pencere).findByText("nw_li_ankara_1")).toBeInTheDocument()
    expect(cagrilar.some((c) => c.yontem === "GET" && c.yol.endsWith("/api/v1/musteri/9/kritik-ci"))).toBe(true)
    expect(within(pencere).getByText("25 CI · 1 kritik")).toBeInTheDocument()
    expect(within(pencere).getByText("2 / 7")).toBeInTheDocument()
    const kritik = within(pencere).getByRole("combobox", { name: "Kritik CI: nw_li_ankara_1" })
    expect(kritik).toHaveValue("1")
    expect(kritik.closest("tr")).toHaveStyle({ backgroundColor: "#fef3c7" })
    expect(within(pencere).getByRole("combobox", { name: "Kritik CI: nw_mbl_izmir_2" })).toHaveValue("0")
  })

  it("CI adi oneki ve Lokasyon adi filtreleri arama ile birlikte sunucuya gider; 'Tumu' filtreyi kaldirir", async () => {
    const cagrilar = sahteSunucu(KART, () => LISTE)
    sarmala(<MusteriKarti id={9} dil="tr" />)
    const pencere = await cekmeceyiAc()
    await within(pencere).findByText("nw_li_ankara_1")
    const filtre = within(pencere).getByRole("group", { name: "CI adı filtresi" })
    expect(within(filtre).getByRole("checkbox", { name: "Tümü" })).toBeChecked()
    fireEvent.click(within(filtre).getByRole("checkbox", { name: "Leased line (20)" }))
    fireEvent.change(within(pencere).getByRole("searchbox", { name: "CI adı ara…" }), { target: { value: " ankara " } })
    fireEvent.change(within(pencere).getByRole("combobox", { name: "Lokasyon adı" }), { target: { value: "MERKEZ" } })
    await waitFor(() => expect(cagrilar.some((c) => c.yol.endsWith("/kritik-ci?q=ankara&kural=nw_li&lok=MERKEZ"))).toBe(true))
    expect(within(filtre).getByRole("checkbox", { name: "Tümü" })).not.toBeChecked()
    fireEvent.click(within(filtre).getByRole("checkbox", { name: "Tümü" }))
    await waitFor(() => expect(cagrilar.some((c) => c.yol.endsWith("/kritik-ci?q=ankara&lok=MERKEZ"))).toBe(true))
  })

  it("Kritik CI secimi ve Lokasyon adi duzeltmesi PUT ile kaydedilir; degismeyen lokasyon istek gondermez", async () => {
    const cagrilar = sahteSunucu(KART, () => LISTE)
    sarmala(<MusteriKarti id={9} dil="tr" />)
    const pencere = await cekmeceyiAc()
    await within(pencere).findByText("nw_mbl_izmir_2")
    fireEvent.change(within(pencere).getByRole("combobox", { name: "Kritik CI: nw_mbl_izmir_2" }), { target: { value: "1" } })
    await waitFor(() => expect(cagrilar.find((c) => c.yontem === "PUT" && c.yol.endsWith("/kritik-ci"))?.govde).toEqual({ ci: "C2", kritik: true }))

    const lokasyon = within(pencere).getByRole("textbox", { name: "Lokasyon adı: nw_li_ankara_1" })
    expect(lokasyon).toHaveValue("MERKEZ")
    expect(lokasyon).toHaveAttribute("placeholder", "ANKARA MRK")
    fireEvent.blur(lokasyon, { target: { value: " MERKEZ " } })
    lokasyon.focus()
    fireEvent.change(lokasyon, { target: { value: "  GENEL MUDURLUK " } })
    fireEvent.keyDown(lokasyon, { key: "Enter" }) // Enter odagi birakir, kayit blur'da
    await waitFor(() => expect(cagrilar.filter((c) => c.yontem === "PUT" && c.yol.endsWith("/kritik-ci/lokasyon")).map((c) => c.govde)).toEqual([{ ci: "C1", lokasyon: "GENEL MUDURLUK" }]))
  })

  it("adres yoksa (kartta Musteri No yok) karttaki sabit matris gosterilir, istek gitmez", async () => {
    const cagrilar = sahteSunucu({ ...KART, kritik_ci: { basliklar: ["Müşteri", "CI Adı"], satirlar: [["112 ACIL SERVIS", "Core Router 1"]], adres: null } }, () => LISTE)
    sarmala(<MusteriKarti id={9} dil="tr" />)
    const pencere = await cekmeceyiAc()
    expect(within(pencere).getByText("Core Router 1")).toBeInTheDocument()
    expect(cagrilar.some((c) => c.yol.includes("/kritik-ci"))).toBe(false)
  })
})
