import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { Giris } from "@/shell/giris"

function doldurVeGonder() {
  fireEvent.change(screen.getByLabelText("Kullanıcı adı"), { target: { value: "ayse" } })
  fireEvent.change(screen.getByLabelText("Şifre"), { target: { value: "gizli" } })
  fireEvent.click(screen.getByRole("button", { name: "Giriş" }))
}

describe("Giris ekrani (2026-11-18 tasarim)", () => {
  afterEach(cleanup)

  it("AD dogru ama panelde rol yoksa (403) yetki mesaji gosterilir", async () => {
    const giris = vi.fn().mockResolvedValue("yetki")
    render(<Giris dil="tr" giris={giris} />)
    doldurVeGonder()
    expect(await screen.findByRole("alert")).toHaveTextContent("Giriş Yetkiniz Bulunmamaktadır. Yetki Talep Ediniz.")
    expect(giris).toHaveBeenCalledWith("ayse", "gizli")
  })

  it("yanlis parola (red) genel hata mesajina duser, yetki mesajina degil", async () => {
    render(<Giris dil="tr" giris={vi.fn().mockResolvedValue("red")} />)
    doldurVeGonder()
    expect(await screen.findByRole("alert")).not.toHaveTextContent("Yetki Talep Ediniz")
  })

  it("Keyflow yetki talebi yeni sekmede, tanitim PDF'i indirilir", () => {
    render(<Giris dil="tr" giris={vi.fn()} />)
    const keyflow = screen.getByRole("link", { name: "Keyflow Yetki Talebi" })
    expect(keyflow).toHaveAttribute("target", "_blank")
    expect(keyflow).toHaveAttribute("rel", "noopener noreferrer")
    expect(keyflow.getAttribute("href")).toMatch(/^https:\/\/keyflow\.turkcell\.com\.tr\//)
    const tanitim = screen.getByRole("link", { name: "Tamlife Tanıtım" })
    expect(tanitim).toHaveAttribute("href", "/assets/tamlife-tanitim.pdf")
    expect(tanitim).toHaveAttribute("download", "TAMLife-Tanitim.pdf")
    expect(screen.getByRole("img", { name: "TAM.Life" })).toBeInTheDocument()
  })
})
