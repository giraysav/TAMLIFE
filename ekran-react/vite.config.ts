import path from "node:path"
import { fileURLToPath } from "node:url"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

const rootDir = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(rootDir, "src"),
    },
  },
  server: {
    host: "127.0.0.1",
    strictPort: false,
    // Yerel gelistirme: API (backend/dev.ps1) 8117'de. Tarayici tek kaynaktan (Vite) konusur, CORS/Origin sorunu olmaz.
    proxy: { "/api": "http://127.0.0.1:8117" },
  },
})