import { useState } from "react"
import { FileDown, FileSpreadsheet } from "lucide-react"
import { DUGME } from "@/components/sayfa-ui"
import { apiYolu } from "@/lib/http"
import { dosyaIndir, raporPdfOlustur } from "@/musteri/rapor-pdf"
import type { Dil } from "@/shell/metin"

const METIN = {
  tr: { excel: "Excel", pdf: "PDF", hazirlaniyor: "Hazırlanıyor…", ipucuExcel: "Çeyreğin tüm alanları ve tabloları (Excel)", ipucuPdf: "Ekrandaki sunumun aynısı (A4 yatay PDF)", hata: "PDF oluşturulamadı." },
  en: { excel: "Excel", pdf: "PDF", hazirlaniyor: "Preparing…", ipucuExcel: "All areas and tables of the quarter (Excel)", ipucuPdf: "Same as the presentation on screen (A4 landscape PDF)", hata: "Could not create the PDF." },
} as const

/** Ceyrek Sunum ust satirindaki Excel / PDF dugmeleri. PDF (2026-10-20 kullanici: "paneldeki sunumun aynisi, gorselli"): ekrandaki
 *  sayfa html2canvas ile resme cevrilir (renkler sRGB'ye, dugmeler gizli, kartlar sayfa kesiminde bolunmez), jsPDF ile A4 yatay. */
export function SunumDisaAktar({ dil, yil, ceyrek, bos, hedef }: { dil: Dil; yil: number; ceyrek: number; bos: boolean; hedef: () => HTMLElement | null }) {
  const m = METIN[dil]
  const [bekliyor, setBekliyor] = useState(false)
  const [hata, setHata] = useState("")
  async function pdf() {
    const el = hedef()
    if (!el) return
    setBekliyor(true)
    setHata("")
    try {
      const blob = await raporPdfOlustur(el, 1.5, 0.92, { yon: "l", ekranGorunumu: true, gizle: "[data-pdf-gizle]" })
      dosyaIndir(blob, `TAMLIFE_Ceyrek_Sunum_${yil}_Q${ceyrek}.pdf`)
    } catch (e) {
      console.error("sunum pdf", e) // teshis: html2canvas / jsPDF hatasi
      setHata(m.hata)
    } finally {
      setBekliyor(false)
    }
  }
  return (
    <>
      <a className={`${DUGME} ${bos ? "pointer-events-none opacity-50" : ""}`} href={apiYolu(`/api/v1/sunum/excel?yil=${yil}&ceyrek=${ceyrek}`)} download title={m.ipucuExcel} aria-disabled={bos}>
        <FileSpreadsheet aria-hidden className="size-4" />
        {m.excel}
      </a>
      <button type="button" className={DUGME} title={m.ipucuPdf} disabled={bos || bekliyor} onClick={() => void pdf()}>
        <FileDown aria-hidden className="size-4" />
        {bekliyor ? m.hazirlaniyor : m.pdf}
      </button>
      {hata ? <span role="alert" className="text-xs font-bold text-red-600">{hata}</span> : null}
    </>
  )
}
