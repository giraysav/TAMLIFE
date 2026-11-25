import type { Analiz } from "@/topoloji/topo-maker"

/**
 * public/topo-harita.js (React paketinden ayri betik; index.html'de <script defer>): TopoMaker il haritasi (ECharts 6.1.0 +
 * tr-iller.json). Betik yoksa window.TamlifeHarita yoktur; TopoMaker basit SVG haritaya duser.
 */
type TamlifeHarita = {
  /** Haritayi kap icine cizer; il zemini yuklenemezse false doner. */
  ciz: (
    kap: HTMLElement,
    p: {
      sehirler: Analiz["sehirler"]
      agac: Analiz["adres_agaci"] | null
      secili: string
      dil: string
      birim: "servis" | "cihaz"
      onIl?: (il: string) => void
    },
  ) => Promise<boolean>
  birak: (kap: HTMLElement) => void
}

declare global {
  interface Window {
    TamlifeHarita?: TamlifeHarita
  }
}
