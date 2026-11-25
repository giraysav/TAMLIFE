import type { RaporGrafigi } from "@/musteri/rapor-onizleme"
import type { oku, yaz } from "@/lib/sorgu"

/**
 * public/rapor-trafik.js (React paketinden ayri betik; index.html'de <script defer>): aylik rapor devre performansi grafikleri
 * (ReportDB LOE verisi, Apache ECharts 6.1.0). Betik yuklenmemisse window.TamlifeTrafik yoktur; rapor onsuz calisir.
 */
type TamlifeTrafik = {
  /** GET adres -> devre basina bir PNG grafik; hata ya da veri yoksa bos liste. */
  gorseller: (getir: typeof oku, adres: string, dil: "tr" | "en") => Promise<RaporGrafigi[]>
  /** Sunucu veriyi hazirliyor mu (son yanit `bekliyor`). */
  bekliyor: (adres: string) => boolean
  /** "Devre grafikleri" bolumunu kap icine cizer (ayni imzayla tekrar cagrilinca yalniz parametreleri gunceller). */
  devreKutusu?: (
    kap: HTMLElement,
    p: { taban: string; adres: string; dil: "tr" | "en"; getir: typeof oku; istek: typeof yaz; yenile: () => unknown },
  ) => void
}

declare global {
  interface Window {
    TamlifeTrafik?: TamlifeTrafik
  }
}
