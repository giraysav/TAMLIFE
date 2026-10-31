import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"
import { KisiselBildirim } from "@/shell/bildirim"
import { oku, yaz } from "@/lib/sorgu"

vi.mock("@/lib/sorgu", () => ({ oku: vi.fn(), yaz: vi.fn() }))
beforeAll(() => {
  // jsdom dialog'u modal acmaz: yalniz open ozniteligi yeter
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) { this.setAttribute("open", "") }
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) { this.removeAttribute("open") }
})
afterEach(() => { cleanup(); vi.clearAllMocks() })

describe("kisisel bildirim zili (2026-10-31)", () => {
  it("okunmamis sayisini gosterir, tumunu okundu isaretler", async () => {
    vi.mocked(oku).mockResolvedValue({
      okunmamis: 2,
      son: [
        { id: 5, tur: "talep", mesaj: "Talebiniz #7 “Rapor”: durum İncelemede → Tamamlandı", adres: "#/talep", zaman: "2026-10-31T09:00:00Z", okundu: false },
        { id: 4, tur: "talep", mesaj: "Talebiniz #7 “Rapor”: durum Yeni → İncelemede", adres: "#/talep", zaman: "2026-10-30T09:00:00Z", okundu: false },
      ],
    })
    vi.mocked(yaz).mockResolvedValue({ okundu: 2 })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <KisiselBildirim dil="tr" dugmeSinifi="" />
      </QueryClientProvider>,
    )
    fireEvent.click(await screen.findByRole("button", { name: "2 okunmamış bildirim" }))
    expect(screen.getByText(/durum İncelemede → Tamamlandı/).closest("a")).toHaveAttribute("href", "#/talep")
    fireEvent.click(screen.getByRole("button", { name: "Tümünü okundu işaretle" }))
    await waitFor(() => expect(yaz).toHaveBeenCalledWith("POST", "/api/v1/bildirim/okundu", {}))
  })
})
