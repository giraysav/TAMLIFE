import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { KartKayitlari, sureMetni } from "@/musteri/kayitlar"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function sarmala(c: ReactNode) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{c}</QueryClientProvider>)
}

function sunucu(cevap: (yol: string) => unknown) {
  const cagrilar: string[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn(async (girdi: string) => {
      cagrilar.push(String(girdi))
      return new Response(JSON.stringify({ status: "success", data: cevap(String(girdi)) }), { status: 200, headers: { "Content-Type": "application/json" } })
    }),
  )
  return cagrilar
}

const kayit = (id: number, ek: object = {}) => ({
  id, ticket: `1013400000${id}`, ci: `nw_li_cust_${id}`, baslik: "AVAILABILITY", durum: "Outstanding/Handled",
  acilis: "2026-10-18T10:00:00Z", kapanis: null, sure_dk: 95, ...ek,
})  // prettier-ignore

describe("Musteri karti kayit listesi", () => {
  it("acik alarmlar: baslik, acik sure, sayfalama ve kapat", async () => {
    const cagrilar = sunucu(() => ({ tur: "alarm", durum: "acik", yil: 2026, toplam: 25, sayfa: 1, adet: 10, kayitlar: [kayit(1)] }))
    const kapat = vi.fn()
    sarmala(<KartKayitlari dil="tr" id={90} tur="alarm" durum="acik" onKapat={kapat} />)
    const bolum = await screen.findByRole("region", { name: "Açık alarm kayıtları" })
    expect(await within(bolum).findByText("25 kayıt")).toBeTruthy()
    expect(within(bolum).getByText("1 sa 35 dk")).toBeTruthy()
    expect(within(bolum).queryByText("Kapanış")).toBeNull()
    expect(cagrilar[0]).toContain("/api/v1/musteri/90/kayitlar?tur=alarm&durum=acik&page=1&per_page=10")
    fireEvent.click(within(bolum).getByRole("button", { name: "Sonraki" }))
    await waitFor(() => expect(cagrilar.some((c) => c.includes("page=2"))).toBe(true))
    fireEvent.click(within(bolum).getByRole("button", { name: "Listeyi kapat" }))
    expect(kapat).toHaveBeenCalled()
  })

  it("kapanan sikayetler: yil basligi, kapanis ve sure; bos listede bilgi", async () => {
    sunucu(() => ({ tur: "sikayet", durum: "kapali", yil: 2026, toplam: 1, sayfa: 1, adet: 10, kayitlar: [kayit(2, { kapanis: "2026-10-18T12:00:00Z", sure_dk: 3000, durum: "Closed/atm" })] }))
    sarmala(<KartKayitlari dil="tr" id={90} tur="sikayet" durum="kapali" onKapat={() => {}} />)
    const bolum = await screen.findByRole("region", { name: "2026 yılında kapanan şikayet kayıtları" })
    expect(await within(bolum).findByText("Kapanış")).toBeTruthy()
    expect(await within(bolum).findByText("2 gün 2 sa")).toBeTruthy()
    cleanup()
    sunucu(() => ({ tur: "talep", durum: "acik", yil: 2026, toplam: 0, sayfa: 1, adet: 10, kayitlar: [] }))
    sarmala(<KartKayitlari dil="tr" id={90} tur="talep" durum="acik" onKapat={() => {}} />)
    expect(await screen.findByText("Bu süzgeçte kayıt yok.")).toBeTruthy()
  })

  it("sure metni", () => {
    const t = { dk: "dk", sa: "sa", gun: "gün" }
    expect([sureMetni(null, t), sureMetni(45, t), sureMetni(60, t), sureMetni(1500, t), sureMetni(2880, t)]).toEqual(["—", "45 dk", "1 sa", "1 gün 1 sa", "2 gün"])
  })
})
