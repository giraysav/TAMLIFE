import { expect, test, type Page } from "@playwright/test"
import { dbDegistir, PAROLA } from "./ortam"
import { buyukHarf as B } from "../src/lib/buyuk-harf"  // ekran sidebar disinda buyuk harf ve Turkce karaktersiz gosterir

/* Oturum acikken hesap veritabaninda pasiflesir, rolu degisir/silinir ya da satiri silinirse: sonraki gezinme ANINDA giris ekranina
 * duser (sunucu 401, istemci onbellegi temizlenir), yazma istegi 401/403 alir, ayni parola ile yeniden girilemez ya da yetki kalkar. */

const ANINDA_MS = 3000

async function gir(page: Page, ad: string) {
  await page.goto("/")
  await page.getByLabel(B("Kullanıcı adı (AD/LDAP)")).fill(ad)
  await page.getByLabel(B("Şifre")).fill(PAROLA)
  await page.getByRole("button", { name: B("Giriş") }).click()
  await expect(page.getByRole("heading", { name: B(`Hoş geldin, ${ad}`) })).toBeVisible()
}

async function gezintiGiriseDuser(page: Page, adres: string) {
  const bas = Date.now()
  await page.goto(adres)
  await expect(page.getByRole("button", { name: B("Giriş") })).toBeVisible({ timeout: ANINDA_MS })
  expect(Date.now() - bas).toBeLessThan(ANINDA_MS)
  await expect(page.getByRole("heading", { name: new RegExp(B("Hoş geldin")) })).toHaveCount(0)
}

async function yazmaDurumu(page: Page): Promise<number> {
  return page.evaluate(async () => {
    const csrf = document.cookie.match(/tamlife_csrf=([^;]+)/)?.[1] ?? ""
    const r = await fetch("/api/v1/takvim/gun", {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({ tarih: "2026-06-01", durum: "calisiyor", online: 1, yuzyuze: 0 }),
    })
    return r.status
  })
}

test.beforeEach(() => dbDegistir("sifirla"))

test("pasife cekilen hesap: iki sekmede de sonraki gezinme giris ekranina duser, yazma reddedilir, yeniden giris olmaz", async ({ page, context }) => {
  await gir(page, "e2e.uye")
  const ikinci = await context.newPage()
  await ikinci.goto("/#/takvim")
  await expect(ikinci.getByRole("button", { name: B("Giriş") })).toHaveCount(0)
  expect(await yazmaDurumu(page)).toBe(200)

  dbDegistir("pasif", "e2e.uye")
  expect([401, 403]).toContain(await yazmaDurumu(ikinci)) // ilk istek bir yazma olsa da gecmez
  await gezintiGiriseDuser(page, "/#/musteri")
  await gezintiGiriseDuser(ikinci, "/#/ozet")
  expect((await page.request.get("/api/v1/session/me")).status()).toBe(401)

  await page.getByLabel(B("Kullanıcı adı (AD/LDAP)")).fill("e2e.uye")
  await page.getByLabel(B("Şifre")).fill(PAROLA)
  await page.getByRole("button", { name: B("Giriş") }).click()
  await expect(page.getByRole("alert")).toBeVisible()
  await expect(page.getByRole("button", { name: B("Giriş") })).toBeVisible()
})

test("Yonetim sayfasindaki admin'in rolu dusurulur: sonraki bolum 401, yeniden giriste Yonetim 403", async ({ page }) => {
  await gir(page, "e2e.admin")
  await page.goto("/#/yonetim/durum")
  await expect(page.getByText("Genel Durum").first()).toBeVisible()

  dbDegistir("rol", "e2e.admin", "TeamMember")
  await gezintiGiriseDuser(page, "/#/yonetim/veritabani")

  await gir(page, "e2e.admin") // rol artik TeamMember
  expect((await page.request.get("/api/v1/yonetim/ozet")).status()).toBe(403)
  await page.goto("/#/yonetim/durum")
  await expect(page.getByText("Genel Durum")).toHaveCount(0)
})

test("hesap satiri veritabanindan silinir: sonraki gezinme 401 ve giris ekrani; ayni parola reddedilir", async ({ page }) => {
  await gir(page, "e2e.uye")
  dbDegistir("sil", "e2e.uye")
  await gezintiGiriseDuser(page, "/#/takvim")
  const r = await page.request.post("/api/v1/session/login", { data: { username: "e2e.uye", password: PAROLA } })
  expect(r.status()).toBe(401)
})

test("rol degeri silinir (bos): oturum duser; yeniden giris admin yetkisi vermez", async ({ page }) => {
  await gir(page, "e2e.admin")
  dbDegistir("rolsuz", "e2e.admin")
  await gezintiGiriseDuser(page, "/#/yonetim/durum")
  const r = await page.request.post("/api/v1/session/login", { data: { username: "e2e.admin", password: PAROLA } })
  if (r.status() === 200) expect((await page.request.get("/api/v1/yonetim/ozet")).status()).toBe(403)
  else expect(r.status()).toBe(401)
})

test("rol degismeden devam eden oturum etkilenmez (yanlis pozitif yok)", async ({ page }) => {
  await gir(page, "e2e.uye")
  dbDegistir("pasif", "e2e.admin") // baska hesap
  await page.goto("/#/takvim")
  await expect(page.getByRole("button", { name: B("Giriş") })).toHaveCount(0)
  expect(await yazmaDurumu(page)).toBe(200)
})
