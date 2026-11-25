import { defineConfig } from "@playwright/test"
import { DIZIN, PORT, PYTHON } from "./e2e-oturum/ortam"

/* Oturum dusme uctan uca testleri: kendi gecici panelini (bos DB + derlenmis dist, port 8198) acar; canliya dokunmaz.
 *   npm run build; npx playwright test -c playwright.oturum.config.ts
 * Sunucuda: E2E_PYTHON=..\.venv\Scripts\python.exe (varsayilan bu); tarayici yoksa E2E_CHROMIUM=<chrome.exe yolu>. */
export default defineConfig({
  testDir: "./e2e-oturum",
  workers: 1, // testler ayni gecici DB'deki hesaplari degistirir
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    launchOptions: process.env.E2E_CHROMIUM ? { executablePath: process.env.E2E_CHROMIUM } : {},
  },
  webServer: {
    command: `"${PYTHON}" -m araclar.yuk.e2e_sunucu sunucu --dizin "${DIZIN}" --port ${PORT}`,
    cwd: "../backend",
    url: `http://127.0.0.1:${PORT}/api/v1/health`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
})
