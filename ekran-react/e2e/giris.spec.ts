import { expect, test } from "@playwright/test"

const KULLANICI = process.env.E2E_USER ?? "admin"
const PAROLA = process.env.E2E_PASS ?? ""

test("oturum yokken giris ekrani, menu ve veri yok", async ({ page }) => {
  await page.goto("/#/admin")
  await expect(page.getByRole("button", { name: "Giriş" })).toBeVisible()
  await expect(page.getByText("Sistem Yönetimi")).toHaveCount(0)
})

test("yanlis parola reddedilir", async ({ page }) => {
  await page.goto("/")
  await page.getByLabel("Kullanıcı adı (AD/LDAP)").fill(KULLANICI)
  await page.getByLabel("Şifre").fill("kesinlikle-yanlis")
  await page.getByRole("button", { name: "Giriş" }).click()
  await expect(page.getByRole("alert")).toContainText("hatalı")
  await expect(page.getByLabel("Şifre")).toHaveValue("")
})

test("giris, menu, yonetim ve cikis", async ({ page }) => {
  test.skip(!PAROLA, "E2E_PASS tanimli degil")
  await page.goto("/")
  await page.getByLabel("Kullanıcı adı (AD/LDAP)").fill(KULLANICI)
  await page.getByLabel("Şifre").fill(PAROLA)
  await page.getByRole("button", { name: "Giriş" }).click()
  await expect(page.getByRole("heading", { name: `Hoş geldin, ${KULLANICI}` })).toBeVisible()
  await page.getByRole("link", { name: "Sistem Yönetimi" }).click()
  await expect(page.getByText("ORACLE_REPORTDB")).toBeVisible()
  await page.getByRole("button", { name: "Çıkış" }).first().click()
  await expect(page.getByRole("button", { name: "Giriş" })).toBeVisible()
  await page.goto("/#/admin")
  await expect(page.getByRole("button", { name: "Giriş" })).toBeVisible()
})

test("baglantilar sayfasi ve Ctrl+K arama", async ({ page }) => {
  test.skip(!PAROLA, "E2E_PASS tanimli degil")
  await page.goto("/")
  await page.getByLabel("Kullanıcı adı (AD/LDAP)").fill(KULLANICI)
  await page.getByLabel("Şifre").fill(PAROLA)
  await page.getByRole("button", { name: "Giriş" }).click()
  await expect(page.getByRole("heading", { name: `Hoş geldin, ${KULLANICI}` })).toBeVisible()
  await page.keyboard.press("Control+k")
  await page.getByPlaceholder("Modül ara…").fill("bağlantı")
  await page.getByRole("button", { name: /Kurum Bağlantıları/ }).click()
  await expect(page.getByText("AD / LDAP")).toBeVisible()
  await expect(page.getByText("OneDesk / REPORTDB").first()).toBeVisible()
})

test("veri yonetimi kabugu: Postgres yoksa soyler, 7 tablo adi listelenir", async ({ page }) => {
  test.skip(!PAROLA, "E2E_PASS tanimli degil")
  await page.goto("/")
  await page.getByLabel("Kullanıcı adı (AD/LDAP)").fill(KULLANICI)
  await page.getByLabel("Şifre").fill(PAROLA)
  await page.getByRole("button", { name: "Giriş" }).click()
  await expect(page.getByRole("heading", { name: `Hoş geldin, ${KULLANICI}` })).toBeVisible()
  await page.goto("/#/veri")
  await expect(page.getByText("PostgreSQL bağlı değil")).toBeVisible()
  for (const ad of ["veri_setleri", "ham_bloklar", "kurallar", "metrikler", "uygulama_gunlugu", "ingest_batch", "ingest_record"]) {
    await expect(page.getByText(ad, { exact: true })).toBeVisible()
  }
})
