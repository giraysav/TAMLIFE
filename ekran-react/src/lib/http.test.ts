import { afterEach, describe, expect, it, vi } from "vitest"

afterEach(() => {
  vi.unstubAllEnvs()
  vi.resetModules()
})

describe("apiYolu", () => {
  it("kok yolda yolu degistirmez ve gomulu degildir", async () => {
    vi.stubEnv("BASE_URL", "/")
    const { GOMULU, apiYolu } = await import("@/lib/http")
    expect(GOMULU).toBe(false)
    expect(apiYolu("/api/v1/session/me")).toBe("/api/v1/session/me")
  })

  it("uretim panelinin arkasinda taban yolu on ek yapar", async () => {
    vi.stubEnv("BASE_URL", "/admin/dev/")
    const { GOMULU, apiYolu } = await import("@/lib/http")
    expect(GOMULU).toBe(true)
    expect(apiYolu("/api/v1/musteri?page=1")).toBe("/admin/dev/api/v1/musteri?page=1")
  })
})
