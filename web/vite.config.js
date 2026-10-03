import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const rootDir = path.dirname(fileURLToPath(import.meta.url));
const ekranSrc = path.resolve(rootDir, "../ekran-react/src");
const ekranRoot = path.resolve(rootDir, "../ekran-react");

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": ekranSrc,
      react: path.resolve(ekranRoot, "node_modules/react"),
      "react-dom": path.resolve(ekranRoot, "node_modules/react-dom"),
    },
    dedupe: ["react", "react-dom"],
  },
  css: {
    postcss: path.resolve(ekranRoot, "postcss.config.cjs"),
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8117",
    },
    fs: {
      allow: [rootDir, ekranRoot],
    },
  },
});