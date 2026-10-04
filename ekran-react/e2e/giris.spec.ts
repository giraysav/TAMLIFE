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
  await page.locator("button[aria-haspopup='menu']").click()
  await page.getByRole("menuitem", { name: "Yönetim" }).click()
  await page.getByRole("link", { name: /Sistem Yönetimi/ }).click()
  await expect(page.getByText("ORACLE_REPORTDB")).toBeVisible()
  await page.locator("button[aria-haspopup='menu']").click()
  await page.getByRole("menuitem", { name: "Çıkış" }).click()
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
  await expect(page.getByText("Onedesk / REPORTDB").first()).toBeVisible()
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


async function girisYap(page: import("@playwright/test").Page) {
  await page.goto("/")
  await page.getByLabel("Kullanıcı adı (AD/LDAP)").fill(KULLANICI)
  await page.getByLabel("Şifre").fill(PAROLA)
  await page.getByRole("button", { name: "Giriş" }).click()
  await expect(page.getByRole("heading", { name: `Hoş geldin, ${KULLANICI}` })).toBeVisible()
}

test("yan menu: grup sirasi, ok ile ac/kapat, Onedesk adi", async ({ page }) => {
  test.skip(!PAROLA, "E2E_PASS tanimli degil")
  await girisYap(page)
  const gruplar = await page.locator("nav[aria-label='TAM Life'] button[aria-expanded]").allTextContents()
  expect(gruplar.map((g) => g.trim())).toEqual(["Genel", "Benim Yerim", "Raporlar"])
  await expect(page.locator("nav[aria-label='TAM Life']").getByText("Yönetim", { exact: true })).toHaveCount(0)
  await expect(page.getByRole("link", { name: "Onedesk", exact: true }).first()).toBeVisible()
  await expect(page.getByText("OneDesk", { exact: true })).toHaveCount(0)
  await expect(page.locator("nav a", { hasText: "Geliştirme Talepleri" })).toHaveCount(0)
  const calisma = page.getByRole("button", { name: "Benim Yerim" })
  await expect(calisma).toHaveAttribute("aria-expanded", "true")
  await calisma.click()
  await expect(calisma).toHaveAttribute("aria-expanded", "false")
  await expect(page.locator("nav a", { hasText: "Müşteri Yönetimi" })).toHaveCount(0)
  await calisma.click()
  await expect(page.locator("nav a", { hasText: "Müşteri Yönetimi" })).toHaveCount(1)
})

test("kullanici menusu sag ustte: profil, yonetim, talepler, dil, cikis", async ({ page }) => {
  test.skip(!PAROLA, "E2E_PASS tanimli degil")
  await girisYap(page)
  await expect(page.locator("nav").getByText("Çıkış")).toHaveCount(0) // yan menude eski cikis cubugu yok
  await page.locator("button[aria-haspopup='menu']").click()
  for (const ad of ["Profil", "Yönetim", "Geliştirme Talepleri", "Çıkış"]) {
    await expect(page.getByRole("menuitem", { name: ad })).toBeVisible()
  }
  await expect(page.getByRole("menuitemradio", { name: /Türkçe/ })).toHaveAttribute("aria-checked", "true")
  await page.getByRole("menuitemradio", { name: /English/ }).click()
  await expect(page.getByRole("heading", { name: `Welcome, ${KULLANICI}` })).toBeVisible()
  await page.locator("button[aria-haspopup='menu']").click()
  await page.getByRole("menuitemradio", { name: /Türkçe/ }).click()
  await page.locator("button[aria-haspopup='menu']").click()
  await page.getByRole("menuitem", { name: "Profil" }).click()
  await expect(page.getByRole("heading", { name: "Profil", level: 1 })).toBeVisible()
  await expect(page.getByText("Oturum açan personelin bilgileri.")).toBeVisible()
  await page.locator("button[aria-haspopup='menu']").click()
  await page.getByRole("menuitem", { name: "Yönetim" }).click()
  await expect(page).toHaveURL(/#\/yonetim$/)
  await expect(page.getByRole("heading", { name: "Yönetim", level: 1 })).toBeVisible()
  await expect(page.getByRole("link", { name: /Kurum Bağlantıları/ })).toBeVisible()
  await page.locator("button[aria-haspopup='menu']").click()
  await page.getByRole("menuitem", { name: "Geliştirme Talepleri" }).click()
  await expect(page).toHaveURL(/#\/talep$/)
})

test("genel bakis tek parca, yeni adlar, Toptan yok", async ({ page }) => {
  test.skip(!PAROLA, "E2E_PASS tanimli degil")
  await girisYap(page)
  const main = page.locator("main")
  for (const kaldirilan of ["Modüller", "Ana sayfa kartı", "Panel tablosu", "Dış kaynak", "Rol yönetimi"]) {
    await expect(main.getByText(kaldirilan, { exact: true })).toHaveCount(0)
  }
  await expect(main.getByRole("button", { name: "Yönetim" })).toHaveCount(0)
  await expect(main.getByText("TAM Life tek panelde, tüm modüller bir arada.")).toBeVisible()
  const nav = page.locator("nav[aria-label='TAM Life']")
  for (const ad of ["ICT Sms & Gelir", "APN Gelir ve Kurulum", "Gelir Faydası Sağlanan İşler", "Çeyrek Bazlı Sunum", "Onedesk"]) {
    await expect(nav.getByRole("link", { name: ad })).toBeVisible()
  }
  for (const eski of ["TAM Toptan", "TAM SMS", "TAM APN", "TAM GELIR&URETIM", "TAM Sunum", "OneDesk"]) {
    await expect(nav.getByText(eski, { exact: true })).toHaveCount(0)
  }
})

test("sayfa icinde geri oku: modulden genel bakisa doner", async ({ page }) => {
  test.skip(!PAROLA, "E2E_PASS tanimli degil")
  await girisYap(page)
  await expect(page.getByRole("button", { name: "Geri" })).toHaveCount(0) // genel bakista yok
  await page.locator("nav a", { hasText: "Müşteri Yönetimi" }).click()
  await expect(page.getByRole("heading", { name: "Müşteri Yönetimi", level: 1 })).toBeVisible()
  await page.locator("nav a", { hasText: "Onedesk" }).click()
  await expect(page.getByRole("heading", { name: "Onedesk", level: 1 })).toBeVisible()
  await page.getByRole("button", { name: "Geri" }).click()
  await expect(page.getByRole("heading", { name: "Müşteri Yönetimi", level: 1 })).toBeVisible()
  await page.getByRole("button", { name: "Geri" }).click()
  await expect(page.getByRole("heading", { name: `Hoş geldin, ${KULLANICI}` })).toBeVisible()
})

test("rol yonetimi: uc rol, admin sabit, hicbir modul kilitli degil", async ({ page }) => {
  test.skip(!PAROLA, "E2E_PASS tanimli degil")
  await girisYap(page)
  await page.goto("/#/roller")
  await expect(page.getByRole("heading", { name: "Rol Yönetimi", level: 1 })).toBeVisible()
  for (const rol of ["Admin", "Manager", "Member"]) {
    await expect(page.locator("main").getByText(rol, { exact: true }).first()).toBeVisible()
  }
  await expect(page.getByText("Admin tüm sayfaları görür ve bu görünüm değiştirilemez.")).toBeVisible()
  const utilizasyon = page.getByRole("checkbox", { name: /TAM Utilizasyon/ })
  await expect(utilizasyon.first()).toBeEnabled() // hicbir modul kilitli degil
  await expect(page.getByRole("checkbox", { name: /Rol Yönetimi/ }).first()).toBeEnabled()
  await expect(page.getByText("varsayılan kapalı").first()).toBeVisible()
  await expect(page.getByLabel("Giriş sayfası").first()).toBeVisible()
  await expect(page.getByRole("button", { name: "Kaydet" })).toHaveCount(2)
})
