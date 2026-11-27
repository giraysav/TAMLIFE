import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import { AylikRapor } from "@/musteri/aylik-rapor"
import { ApiHata, oku, yaz } from "@/lib/sorgu"
import { yedekAnahtari, yedekOku, yedektenGeriYukle } from "@/musteri/taslak-otomatik"

vi.mock("@/lib/sorgu", async (gercek) => {
  const asil = await gercek<typeof import("@/lib/sorgu")>()
  return { sorguMetni: asil.sorguMetni, ApiHata: asil.ApiHata, oku: vi.fn(), yaz: vi.fn(), hataMesaji: (_h: unknown, text: string) => text }
})
vi.mock("@/musteri/rapor-pdf", () => ({ blobBase64: vi.fn(), dosyaIndir: vi.fn(), raporPdfOlustur: vi.fn(), seriGrafigi: vi.fn(() => null) }))

const ANAHTAR = yedekAnahtari(1, 2026, 10)
beforeEach(() => localStorage.clear())
afterEach(() => { cleanup(); vi.clearAllMocks() })

function sar({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
}

function sunucu(zaman: string | null = "2026-11-03T10:00:00") {
  const taslak = { yil: 2026, ay: 10, birim: true, alanlar: { konu: "Ekim raporu" }, varsayilanlar: { tr: {}, en: {} }, kayitli: !!zaman, guncelleyen: null, zaman,
    alicilar: { kime: "", bilgi: "" }, gonderim: null }
  vi.mocked(oku).mockImplementation(async (url: string) => {
    if (url.includes("/taslak")) return taslak
    if (url.includes("/gecmis")) return []
    return { dosyalar: [], ekler: [] }
  })
}

const ac = () => render(<AylikRapor musteriId={1} musteriAdi="Test" dil="tr" geriAlabilir={false} />, { wrapper: sar })
const konu = async () => (await screen.findByLabelText("Konu")) as HTMLInputElement
const taslakKayitlari = () => vi.mocked(yaz).mock.calls.filter(([y, u]) => y === "PUT" && String(u).includes("/rapor/taslak"))

describe("aylik rapor taslagi otomatik kaydi (2026-11-03)", () => {
  it("yazim durunca sunucuya yazar; once tarayiciya yedekler, kayittan sonra yedegi siler", async () => {
    sunucu()
    vi.mocked(yaz).mockResolvedValue({ zaman: "2026-11-03T10:05:00" })
    ac()
    fireEvent.change(await konu(), { target: { value: "Ekim raporu v2" } })
    expect(yedekOku(ANAHTAR)?.alanlar.konu).toBe("Ekim raporu v2")
    expect(taslakKayitlari()).toHaveLength(0)
    await waitFor(() => expect(taslakKayitlari()).toHaveLength(1), { timeout: 3000 })
    expect(taslakKayitlari()[0][2]).toEqual({ alanlar: { konu: "Ekim raporu v2" } })
    await waitFor(() => expect(screen.getByText(/Taslak kaydedildi/)).toBeInTheDocument())
    expect(yedekOku(ANAHTAR)).toBeNull()
  })

  it("degisiklik yoksa kaydetmez; sekme gizlenince beklemeden yazar", async () => {
    sunucu()
    vi.mocked(yaz).mockResolvedValue({ zaman: "2026-11-03T10:05:00" })
    ac()
    const girdi = await konu()
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    expect(taslakKayitlari()).toHaveLength(0)
    fireEvent.change(girdi, { target: { value: "Yarim kalan" } })
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden")
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    await waitFor(() => expect(taslakKayitlari()).toHaveLength(1))
    expect(taslakKayitlari()[0][3]).toBe(true) // keepalive: sayfa kapansa da tamamlanir
  })

  it("ekran kapaninca bekleyen degisikligi yazar", async () => {
    sunucu()
    vi.mocked(yaz).mockResolvedValue({ zaman: "2026-11-03T10:05:00" })
    const { unmount } = ac()
    fireEvent.change(await konu(), { target: { value: "Sekme degisti" } })
    unmount()
    await waitFor(() => expect(taslakKayitlari()).toHaveLength(1))
    expect(taslakKayitlari()[0][2]).toEqual({ alanlar: { konu: "Sekme degisti" } })
  })

  it("sunucuya ulasilamazsa yedek kalir, ekran yeniden acilinca geri yuklenir ve kaydedilir", async () => {
    sunucu()
    vi.mocked(yaz).mockRejectedValue(new ApiHata(0, ""))
    const { unmount } = ac()
    fireEvent.change(await konu(), { target: { value: "Ag koptu" } })
    await waitFor(() => expect(screen.getByText(/Sunucuya ulaşılamadı/)).toBeInTheDocument(), { timeout: 3000 })
    unmount()
    expect(yedekOku(ANAHTAR)?.alanlar.konu).toBe("Ag koptu")

    vi.mocked(yaz).mockResolvedValue({ zaman: "2026-11-03T10:09:00" })
    const onceki = taslakKayitlari().length
    ac()
    await waitFor(async () => expect((await konu()).value).toBe("Ag koptu"))
    expect(screen.getByText(/geri yüklendi/)).toBeInTheDocument()
    await waitFor(() => expect(taslakKayitlari().length).toBeGreaterThan(onceki), { timeout: 3000 })
    expect(taslakKayitlari().at(-1)?.[2]).toEqual({ alanlar: { konu: "Ag koptu" } })
    await waitFor(() => expect(yedekOku(ANAHTAR)).toBeNull())
  })
})

describe("yedektenGeriYukle", () => {
  const yedek = (taban: string) => localStorage.setItem(ANAHTAR, JSON.stringify({ alanlar: { konu: "yerel" }, taban, zaman: "" }))
  const sunucuHali = (zaman: string | null, gonderildi = false) => ({ alanlar: { konu: "sunucu" }, zaman, gonderildi })

  it("ayni sunucu surumunun ustune yazilmissa geri verir", () => {
    yedek("2026-11-03T10:00:00")
    expect(yedektenGeriYukle(ANAHTAR, sunucuHali("2026-11-03T10:00:00"))).toEqual({ konu: "yerel" })
  })
  it("ilk taslak (sunucuda kayit yok) da geri gelir", () => {
    yedek("")
    expect(yedektenGeriYukle(ANAHTAR, sunucuHali(null))).toEqual({ konu: "yerel" })
  })
  it("sunucu daha yeniyse ya da donem gonderildiyse yedegi siler", () => {
    yedek("2026-11-03T10:00:00")
    expect(yedektenGeriYukle(ANAHTAR, sunucuHali("2026-11-03T11:00:00"))).toBeNull()
    expect(yedekOku(ANAHTAR)).toBeNull()
    yedek("2026-11-03T10:00:00")
    expect(yedektenGeriYukle(ANAHTAR, sunucuHali("2026-11-03T10:00:00", true))).toBeNull()
    expect(yedekOku(ANAHTAR)).toBeNull()
  })
  it("onbellekteki eski yanitta yedege dokunmaz", () => {
    yedek("2026-11-03T10:00:00")
    expect(yedektenGeriYukle(ANAHTAR, sunucuHali("2026-11-03T09:00:00"))).toBeNull()
    expect(yedekOku(ANAHTAR)).not.toBeNull()
  })
})
