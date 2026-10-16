import { execFileSync } from "node:child_process"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"

export const PORT = Number(process.env.E2E_PORT ?? 8198)
export const DIZIN = process.env.E2E_DIZIN ?? path.join(os.tmpdir(), "tamlife-e2e-oturum")
export const PYTHON = process.env.E2E_PYTHON ?? (process.platform === "win32" ? "..\\.venv\\Scripts\\python.exe" : "python3")
export const PAROLA = process.env.E2E_PAROLA ?? "E2e-test-parolasi-2026"

/** Panel acikken DB'yi BASKA bir surecten degistirir (hesap.py / DBA / isci benzeri): pasif, rol, rolsuz, sil, sifirla. */
export function dbDegistir(...arg: string[]): void {
  execFileSync(PYTHON, ["-m", "araclar.yuk.e2e_sunucu", "degistir", "--dizin", DIZIN, ...arg], { cwd: path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../backend"), stdio: "inherit" })
}
