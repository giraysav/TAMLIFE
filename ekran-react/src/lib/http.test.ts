import { afterEach, describe, expect, it, vi } from "vitest"
import { musteriAlaniBasligi } from "@/lib/http"

afterEach(() => {
  vi.unstubAllEnvs()
  vi.resetModules()
})

describe("apiYolu", () => {
  it("kok yolda yolu degistirmez", async () => {
    vi.stubEnv("BASE_URL", "/")
    const { apiYolu } = await import("@/lib/http")
    expect(apiYolu("/api/v1/session/me")).toBe("/api/v1/session/me")
  })

  it("arayuz alt yolda sunuluyorsa taban yolu on ek yapar", async () => {
    vi.stubEnv("BASE_URL", "/panel/")
    const { apiYolu } = await import("@/lib/http")
    expect(apiYolu("/api/v1/musteri?page=1")).toBe("/panel/api/v1/musteri?page=1")
  })
})

describe("oturumYok", () => {
  it("yalniz 401 oturum yok sayilir", async () => {
    const { oturumYok } = await import("@/lib/http")
    expect(oturumYok(new Response(null, { status: 401 }))).toBe(true)
    expect(oturumYok(new Response(null, { status: 403 }))).toBe(false)
    expect(oturumYok(new Response("{}", { status: 200 }))).toBe(false)
  })
})

describe("musteriAlaniBasligi", () => {
  it("Toptan / Baglantili Araclar ekraninda yalniz musteri karti uclarina alan basligi gider", () => {
    window.location.hash = "#/toptan?m=5"
    expect(musteriAlaniBasligi("/api/v1/musteri/5")).toEqual({ "X-Musteri-Alani": "toptan" })
    expect(musteriAlaniBasligi("/api/v1/topoloji/analiz")).toEqual({ "X-Musteri-Alani": "toptan" })
    expect(musteriAlaniBasligi("/api/v1/ekip/ozet")).toEqual({})
    window.location.hash = "#/baglantili"
    expect(musteriAlaniBasligi("/api/v1/musteri/portfoy")).toEqual({ "X-Musteri-Alani": "baglantili" })
    window.location.hash = "#/musteri?m=5"
    expect(musteriAlaniBasligi("/api/v1/musteri/5")).toEqual({})
    window.location.hash = ""
  })
})
