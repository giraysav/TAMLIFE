import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

const KULLANICI = process.env.E2E_USER ?? "admin"
const PAROLA = process.env.E2E_PASS ?? ""

async function girisYap(page: Page) {
  await page.goto("/")
  await page.getByLabel("Kullanıcı adı (AD/LDAP)").fill(KULLANICI)
  await page.getByLabel("Şifre").fill(PAROLA)
  await page.getByRole("button", { name: "Giriş" }).click()
  await expect(page.getByRole("heading", { name: `Hoş geldin, ${KULLANICI}` })).toBeVisible()
}

test("musteri karti ve aylik rapor akisi (ekle, duzenle, iletisim, taslak, alici, gonder, kilit, geri al, sil)", async ({ page }) => {
  test.skip(!PAROLA, "E2E_PASS tanimli degil")
  page.on("dialog", (d) => void d.accept())
  const ad = `E2E Test Musterisi ${Date.now()}`
  await girisYap(page)

  await page.locator("nav a", { hasText: "Müşteri Yönetimi" }).click()
  await expect(page.getByRole("heading", { name: "Müşteri Yönetimi", level: 1 })).toBeVisible()
  await page.getByRole("button", { name: "Müşteri ekle" }).click()
  await page.getByLabel("Ünvan").fill(ad)
  await page.getByLabel("Segment").selectOption("MA")
  await page.getByRole("button", { name: "Kaydet" }).click()

  // yeni musterinin karti acilir (eski panel duzeni: lacivert kimlik karti, katlanir bolumler)
  await expect(page.getByRole("heading", { name: ad, level: 2 })).toBeVisible()
  await expect(page.getByText("Müşteri Kartı", { exact: true })).toBeVisible()
  for (const bolum of ["Ekip & İletişim", "Operasyon", "Ekip (Destech)", "Kritik CI", "İzleme (Cacti)"]) {
    await expect(page.locator("summary", { hasText: bolum })).toBeVisible()
  }
  await expect(page.getByText("Yıl içi kapanan")).toHaveCount(3)
  await page.getByRole("button", { name: "Geri" }).click()
  await expect(page.getByRole("link", { name: ad })).toBeVisible()
  await page.getByRole("link", { name: ad }).click()

  // kimlik duzenle (Duzenle dugmesi formu acar)
  await page.getByRole("button", { name: "Düzenle" }).click()
  const kimlik = page.getByRole("form", { name: "Düzenle" })
  await kimlik.getByLabel("Sektör").fill("Enerji")
  await kimlik.getByLabel("NCST").fill("N-77")
  await kimlik.getByRole("button", { name: "Kaydet" }).click()
  await expect(page.getByText("Enerji", { exact: true }).first()).toBeVisible()
  await page.reload()
  await expect(page.getByText("N-77", { exact: true })).toBeVisible()

  // ekip ve iletisim: gecersiz e-posta reddedilir, gecerli kaydedilir
  const iletisim = page.getByRole("form", { name: "Ekip & İletişim" })
  await iletisim.getByLabel("TAC · E-posta").fill("a@b")
  await iletisim.getByRole("button", { name: "Kaydet" }).click()
  await expect(iletisim.getByRole("status")).toContainText("Kaydedilemedi")
  await iletisim.getByLabel("TAC · E-posta").fill("tac@example.com")
  await iletisim.getByRole("button", { name: "Kaydet" }).click()
  await expect(iletisim.getByRole("status")).toHaveText("Kaydedildi.")

  // aylik rapor sayfasi: hero'daki Aylik Rapor kutusu acar; sol form, sag gecmis ve alicilar
  await page.locator("main").getByRole("link", { name: /Aylık Rapor/ }).first().click()
  await expect(page.getByRole("heading", { name: ad, level: 2 })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Operasyonel Rapor İçeriği Girişi" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Rapor Geçmişi" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Rapor Alıcıları" })).toBeVisible()
  await expect(page.getByLabel("Konu", { exact: true })).toHaveValue(new RegExp(`TAM Aylık Rapor - .* \\| ${ad}`))
  await expect(page.getByLabel("Olumlu gelişmeler")).toHaveValue(/Bu dönem için ayrıca/)
  await page.getByLabel("Olumlu gelişmeler").fill("E2E olumlu not")
  await page.getByRole("button", { name: "Taslağı kaydet" }).click()
  await expect(page.getByText("Kaydedildi.").first()).toBeVisible()
  await page.getByLabel("Kime").fill("kisi@example.com")
  await page.getByRole("button", { name: "Alıcıları kaydet" }).click()
  await expect(page.getByText("Kaydedildi.").first()).toBeVisible()
  await page.getByRole("button", { name: "Raporu gönder" }).click()
  await expect(page.getByText("✓ Bu ayın raporu gönderildi.")).toBeVisible()
  await expect(page.getByRole("button", { name: "Raporu gönder" })).toBeDisabled()
  await expect(page.getByLabel("Olumlu gelişmeler")).toBeDisabled()
  await expect(page.getByRole("button", { name: "Geri al" })).toBeVisible()

  // admin geri alir: ay yeniden acilir
  await page.getByRole("button", { name: "Geri al" }).click()
  await expect(page.getByRole("button", { name: "Raporu gönder" })).toBeEnabled()
  await expect(page.getByLabel("Olumlu gelişmeler")).toBeEnabled()
  await expect(page.getByText("Geri alındı").first()).toBeVisible()

  // karta don, Gonderilen Aylik Rapor modulu gecmisi gosterir
  await page.getByRole("link", { name: "Müşteri kartı" }).click()
  await expect(page.getByRole("heading", { name: ad, level: 2 })).toBeVisible()
  await page.locator("nav a", { hasText: "Gönderilen Aylık Rapor" }).click()
  await expect(page.getByRole("link", { name: ad })).toBeVisible()

  // temizlik: musteriyi sil
  await page.goto("/#/musteri")
  await page.getByRole("link", { name: ad }).click()
  await page.getByRole("button", { name: "Müşteriyi sil" }).click()
  await expect(page.getByRole("link", { name: ad })).toHaveCount(0)
})
