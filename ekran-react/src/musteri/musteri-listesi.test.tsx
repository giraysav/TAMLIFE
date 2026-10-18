import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { MusteriListesi } from "@/musteri/musteri-listesi"
import { MusteriYolu } from "@/musteri/musteri-yolu"

const PORTFOY = {
  items: [{ id: 11, name: "Alfa Telekom", segment: "MA", owner: "İpek Ak", owner_id: 2, score: 80, alarm: 0, sikayet: 0, talep: 0, istirakler: [] }],
  ozet: { cati: 1, istirak: 0, alarm: 0, sikayet: 0, talep: 0, ortalama_skor: 80, skorlu: 1 },
  total: 1,
  page: 1,
  pages: 1,
}

function sarmala(cocuk: ReactNode) {
  const istemci = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={istemci}>
      <MusteriYolu.Provider value="musteri">{cocuk}</MusteriYolu.Provider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  window.history.replaceState(null, "", "#/musteri")
  vi.stubGlobal(
    "fetch",
    vi.fn(async (girdi: string) => {
      const veri = String(girdi).includes("/secenekler")
        ? { segmentler: ["SMB", "MA"], yonetici: true, kendi_id: null, tam: [{ id: 3, ad: "Zeynep Öz" }, { id: 2, ad: "İpek Ak" }, { id: 1, ad: "Ayşe Çınar" }], catilar: [] }
        : PORTFOY
      return new Response(JSON.stringify({ status: "success", data: veri }), { status: 200, headers: { "Content-Type": "application/json" } })
    }),
  )
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("Musteri Yonetimi filtreleri", () => {
  it("personeli alfabetik gosterir ve karttan geri donuldugunde yonetici filtresini korur", async () => {
    const ilk = sarmala(<MusteriListesi dil="tr" yazabilir />)
    const secim = await screen.findByRole("combobox", { name: "TAM" })
    expect(within(secim).getAllByRole("option").map((o) => o.textContent)).toEqual(["Tüm personel", "Ayşe Çınar", "İpek Ak", "Zeynep Öz"])

    fireEvent.change(secim, { target: { value: "2" } })
    await waitFor(() => expect(window.location.hash).toBe("#/musteri?tam=2"))
    const filtreliAdres = window.location.hash

    act(() => {
      window.location.hash = "#/musteri?m=11"
    })
    act(() => window.history.back())
    await waitFor(() => expect(window.location.hash).toBe(filtreliAdres))

    ilk.unmount()
    sarmala(<MusteriListesi dil="tr" yazabilir />)
    expect(await screen.findByRole("combobox", { name: "TAM" })).toHaveValue("2")
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("tam=2"))).toBe(true))
  })
})
