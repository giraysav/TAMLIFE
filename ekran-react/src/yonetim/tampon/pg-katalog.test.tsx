import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { PgKataloglari } from "@/yonetim/tampon/pg-katalog"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const kat = { id: 4, durum: "ready", baslangic: "2026-10-19T10:00:00Z", bitis: "2026-10-19T10:01:00Z", kim: "admin", ozet: { semalar: ["public"], nesne: 1, sutun: 2 }, hata: "" }
const veri: Record<string, unknown> = {
  "/api/v1/tampon/pg": [
    { id: "pg_onent", label: "ONENTDB", acma_anahtari: "ONENTDB_PG_ENABLED", acik: true, eksik: [], hazir: true, state: "ready", katalog: kat, son: kat, calisiyor: false },
    { id: "pg_onedesk", label: "ONEDESKDB", acma_anahtari: "ONEDESKDB_PG_ENABLED", acik: false, eksik: [], hazir: false, state: "disabled", katalog: null, son: null, calisiyor: false },
  ],
  "/api/v1/tampon/pg/pg_onent/katalog": { kaynak: "pg_onent", son: kat, katalog: kat, calisiyor: false, semalar: [{ ad: "public", nesneler: [{ id: 9, ad: "musteri", tur: "tablo", satir: 120, sutun: 2, aciklama: "" }] }] },
  "/api/v1/tampon/pg/nesne/9": {
    id: 9, sema: "public", ad: "musteri", tur: "tablo", satir: 120, aciklama: "",
    sutunlar: [{ ad: "id", tip: "integer", bos: false, aciklama: "" }, { ad: "telefon", tip: "text", bos: true, aciklama: "" }],
    ornek: { sutunlar: ["id", "telefon"], satirlar: [[1, "***"]], not: "Kişisel veri gibi duran sütunların değeri gizlendi." },
  }, // prettier-ignore
}

describe("PgKataloglari", () => {
  it("kaynak durumu, kapali kaynak talimati, sema -> tablo -> sutun + ornek", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (girdi: string) => {
        const yol = String(girdi).split("?")[0]
        return new Response(JSON.stringify({ status: "success", data: veri[yol] }), { status: 200, headers: { "Content-Type": "application/json" } })
      }),
    )
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <PgKataloglari dil="tr" />
      </QueryClientProvider>,
    )
    const bolum = screen.getByRole("heading", { name: /PostgreSQL kaynakları/ }).closest("details") as HTMLDetailsElement
    bolum.open = true // varsayilan kapali + tembel: acilinca kurulur
    fireEvent(bolum, new Event("toggle"))
    const onent = await screen.findByRole("region", { name: "ONENTDB" })
    expect(within(onent).getByText(/1 şema · 1 nesne · 2 sütun/)).toBeInTheDocument()
    const onedesk = screen.getByRole("region", { name: "ONEDESKDB" })
    expect(within(onedesk).getByText(/ONEDESKDB_PG_ENABLED=true/)).toBeInTheDocument()
    expect(within(onedesk).getByRole("button", { name: "Kataloğu yenile" })).toBeDisabled()
    fireEvent.click(await within(onent).findByRole("button", { name: /public/ }))
    fireEvent.click(within(onent).getByRole("button", { name: /musteri/ }))
    expect(await within(onent).findByText("public.musteri")).toBeInTheDocument()
    expect(within(onent).getByText("***")).toBeInTheDocument()
    expect(within(onent).getByText(/değeri gizlendi/)).toBeInTheDocument()
  })
})
