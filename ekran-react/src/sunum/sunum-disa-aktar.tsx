import { useState } from "react"
import { FileDown, FileSpreadsheet } from "lucide-react"
import { DUGME } from "@/components/sayfa-ui"
import { apiYolu } from "@/lib/http"
import { hataMesaji, oku } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"

type Tablo = { baslik: string; sutunlar: string[]; satirlar: unknown[][] }
type DisaAktarim = { donem: string; onay: { onaylayan: string } | null; bolumler: { kaynak: string; baslik: string; durum: string; tablolar: Tablo[] }[] }

const METIN = {
  tr: { excel: "Excel", pdf: "PDF", hazirlaniyor: "Hazırlanıyor…", ipucu: "Çeyreğin tüm alanları (ekrandaki veriyle aynı)", hata: "Dışa aktarılamadı.", yok: "Bu çeyrekte veri yok.", baslik: "TAMLIFE Çeyrek Sunum" },
  en: { excel: "Excel", pdf: "PDF", hazirlaniyor: "Preparing…", ipucu: "All areas of the quarter (same data as on screen)", hata: "Export failed.", yok: "No data for this quarter.", baslik: "TAMLIFE Quarterly Presentation" },
} as const

const kacis = (v: unknown) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] ?? c)
const hucre = (v: unknown, dil: Dil) => (typeof v === "number" ? v.toLocaleString(dil === "tr" ? "tr-TR" : "en-GB") : kacis(v))

/** PDF: disa aktarma verisinden yazdirma penceresi (A4 yatay; tarayici "PDF olarak kaydet"). Yeni bagimlilik yok. */
function yazdir(v: DisaAktarim, dil: Dil, pencere: Window) {
  const m = METIN[dil]
  const bolumler = v.bolumler
    .map(
      (b) =>
        `<section><h2>${kacis(b.baslik)} <small>${kacis(b.durum)}</small></h2>${
          b.tablolar.length
            ? b.tablolar
                .map((t) => `<h3>${kacis(t.baslik)}</h3><table><thead><tr>${t.sutunlar.map((s) => `<th>${kacis(s)}</th>`).join("")}</tr></thead><tbody>${t.satirlar.map((s) => `<tr>${s.map((h) => `<td>${hucre(h, dil)}</td>`).join("")}</tr>`).join("")}</tbody></table>`)
                .join("")
            : `<p class="bos">${m.yok}</p>`
        }</section>`,
    )
    .join("")
  pencere.document.write(
    `<!doctype html><html lang="${dil}"><head><meta charset="utf-8"><title>${kacis(m.baslik)} ${kacis(v.donem)}</title><style>
body{font:11px 'Segoe UI',Arial,sans-serif;color:#243447;margin:14px}h1{font-size:18px;color:#002855;margin:0 0 4px}h2{font-size:14px;color:#002855;margin:14px 0 4px;border-bottom:2px solid #ffc72c;padding-bottom:2px}
h2 small{font-size:10px;color:#64748b;font-weight:600}h3{font-size:11px;color:#0055a5;margin:8px 0 3px}table{border-collapse:collapse;width:100%;margin-bottom:6px}th{background:#002855;color:#fff;text-align:left}
th,td{border:1px solid #cbd5e1;padding:3px 5px;vertical-align:top}td{font-variant-numeric:tabular-nums}.bos{color:#94a3b8}section{break-inside:avoid-page}@page{size:A4 landscape;margin:10mm}
</style></head><body><h1>${kacis(m.baslik)} · ${kacis(v.donem)}${v.onay ? ` · ${kacis(v.onay.onaylayan)}` : ""}</h1>${bolumler}</body></html>`,
  )
  pencere.document.close()
  pencere.focus()
  pencere.print()
}

/** Ceyrek Sunum ust satirindaki Excel / PDF dugmeleri (2026-10-20 kullanici istegi). */
export function SunumDisaAktar({ dil, yil, ceyrek, bos }: { dil: Dil; yil: number; ceyrek: number; bos: boolean }) {
  const m = METIN[dil]
  const [bekliyor, setBekliyor] = useState(false)
  const [hata, setHata] = useState("")
  async function pdf() {
    const pencere = window.open("", "_blank") // acilir pencere engeline takilmasin: tiklama aninda acilir
    if (!pencere) return
    setBekliyor(true)
    setHata("")
    try {
      yazdir(await oku<DisaAktarim>(`/api/v1/sunum/disa-aktar?yil=${yil}&ceyrek=${ceyrek}`), dil, pencere)
    } catch (e) {
      pencere.close()
      setHata(hataMesaji(e, m.hata))
    } finally {
      setBekliyor(false)
    }
  }
  return (
    <>
      <a className={`${DUGME} ${bos ? "pointer-events-none opacity-50" : ""}`} href={apiYolu(`/api/v1/sunum/excel?yil=${yil}&ceyrek=${ceyrek}`)} download title={m.ipucu} aria-disabled={bos}>
        <FileSpreadsheet aria-hidden className="size-4" />
        {m.excel}
      </a>
      <button type="button" className={DUGME} title={m.ipucu} disabled={bos || bekliyor} onClick={() => void pdf()}>
        <FileDown aria-hidden className="size-4" />
        {bekliyor ? m.hazirlaniyor : m.pdf}
      </button>
      {hata ? <span role="alert" className="text-xs font-bold text-red-600">{hata}</span> : null}
    </>
  )
}
