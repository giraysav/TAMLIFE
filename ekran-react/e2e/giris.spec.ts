import { expect, test } from "@playwright/test"

test("giris ekrani acilir", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByRole("button", { name: "Giris" })).toBeVisible()
})
