import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { MusteriKarti } from "@/musteri/portfoy-kart"
import type { PortfoyKart } from "@/musteri/portfoy-kart"
import { MusteriYolu } from "@/musteri/musteri-yolu"

afterEach(cleanup)

const m: PortfoyKart = { id: 7, name: "Alfa A.Ş.", segment: "kurumsal", owner: null, owner_id: null, score: null, alarm: 0, sikayet: 0, talep: 0, istirakler: [] }

describe("Musteri ekrani yolu", () => {
  it("varsayilan Musteri Yonetimi'ne baglanir", () => {
    render(<MusteriKarti m={m} dil="tr" />)
    expect(screen.getByRole("link")).toHaveAttribute("href", "#/musteri?m=7")
  })

  it.each(["baglantili", "toptan"])("%s modulunde kart ayni modulde acilir", (yol) => {
    render(
      <MusteriYolu.Provider value={yol}>
        <MusteriKarti m={m} dil="tr" />
      </MusteriYolu.Provider>,
    )
    expect(screen.getByRole("link")).toHaveAttribute("href", `#/${yol}?m=7`)
  })
})
