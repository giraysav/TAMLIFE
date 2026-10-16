import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { Kullanici } from "@/lib/oturum"
import { KullaniciKarti } from "@/shell/kullanici-karti"
import { ProfilSayfasi } from "@/shell/profil-sayfasi"

vi.mock("@/lib/foto", async (asil) => ({ ...(await asil<typeof import("@/lib/foto")>()), kareJpeg: vi.fn(async () => new Blob(["jpeg"], { type: "image/jpeg" })) }))

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const PROFIL = { username: "gsav", display_name: "Giray Sav", ad_user: true, first_name: "Giray", last_name: "Sav", phone: "", company: "", address: "", website: "" }
const kisi = (photo_version: number | null): Kullanici => ({
  username: "gsav",
  display_name: "Giray Sav",
  profile: { ...PROFIL, photo_version },
  role: "TeamMember",
  is_admin: false,
  idle_timeout_minutes: 30,
  landing: "ozet",
  navigation: [],
})

describe("Profil fotografi", () => {
  it("hesap karti fotograf varsa resmi, yoksa bas harfleri gosterir", () => {
    const { container, unmount } = render(<KullaniciKarti kullanici={kisi(null)} dil="tr" onDil={() => {}} onGit={() => {}} onCikis={() => {}} talepVar={false} />)
    expect(container.querySelector("img")).toBeNull()
    expect(screen.getByText("GS")).toBeInTheDocument()
    unmount()
    const ikinci = render(<KullaniciKarti kullanici={kisi(123)} dil="tr" onDil={() => {}} onGit={() => {}} onCikis={() => {}} talepVar={false} />)
    expect(ikinci.container.querySelector("img")?.getAttribute("src")).toBe("/api/v1/session/photo?v=123")
  })

  it("profil sayfasinda secilen fotograf JPEG olarak yuklenir, kaldirilabilir; kart yenilenir", async () => {
    const cagrilar: { yol: string; yontem: string; tur: string | null }[] = []
    vi.stubGlobal(
      "fetch",
      vi.fn(async (girdi: string, ayar?: RequestInit) => {
        const yontem = ayar?.method ?? "GET"
        cagrilar.push({ yol: String(girdi), yontem, tur: new Headers(ayar?.headers).get("Content-Type") })
        const data = { photo_version: yontem === "PUT" ? 456 : null }
        return new Response(JSON.stringify({ status: "success", data }), { status: 200, headers: { "Content-Type": "application/json" } })
      }),
    )
    const onKaydedildi = vi.fn()
    render(<ProfilSayfasi kullanici={kisi(null)} dil="tr" onKaydedildi={onKaydedildi} />)
    fireEvent.change(screen.getByLabelText("Fotoğraf seç"), { target: { files: [new File(["x"], "ben.png", { type: "image/png" })] } })
    expect(await screen.findByText("Fotoğraf kaydedildi.")).toBeInTheDocument()
    expect(cagrilar[0]).toMatchObject({ yol: "/api/v1/session/photo", yontem: "PUT", tur: "image/jpeg" })
    expect(screen.getByAltText("Profil fotoğrafı").getAttribute("src")).toBe("/api/v1/session/photo?v=456")
    fireEvent.click(screen.getByRole("button", { name: "Fotoğrafı kaldır" }))
    expect(await screen.findByText("Fotoğraf kaldırıldı.")).toBeInTheDocument()
    expect(cagrilar[1]).toMatchObject({ yontem: "DELETE" })
    expect(screen.queryByAltText("Profil fotoğrafı")).toBeNull()
    expect(onKaydedildi).toHaveBeenCalledTimes(2)
  })
})
