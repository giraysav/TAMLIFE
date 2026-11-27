import { useRef, useState } from "react"
import type { CSSProperties, ReactNode } from "react"
import { FileDown, FileSpreadsheet } from "lucide-react"
import { DUGME } from "@/components/sayfa-ui"
import { para, sayi, tarih } from "@/lib/bicim"
import { apiYolu } from "@/lib/http"
import { sorguMetni } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"
import { dosyaIndir, raporPdfOlustur } from "@/musteri/rapor-pdf"
import { PARALAR, gelirUretimMetin } from "@/gelir-uretim/gelir-uretim-metin"
import type { Kayit, Ozet, Para } from "@/gelir-uretim/gelir-uretim-metin"
import { TABAN, kisilerMetni, saatMetni, tarihAraligi, tutarMetni } from "@/gelir-uretim/ortak"
import type { Metin } from "@/gelir-uretim/ortak"

export type RaporSuzgeci = { q: string; tur: string; durum: string; fayda: string; tam: string; yil: string }

/* PDF sablonu yalniz satir ici (hex) stil kullanir: html2canvas kopyasinda stil dosyalari kaldirilir (rapor-pdf.ts). */
const LACIVERT = "#0b2a5b"
const SARI = "#ffc72c"
const GRI = "#64748b"
const CIZGI = "#e2e8f0"
const KOK: CSSProperties = { width: 794, boxSizing: "border-box", padding: "36px 40px", background: "#ffffff", color: "#1e293b", fontFamily: "Arial, Helvetica, sans-serif", fontSize: 11, lineHeight: 1.45 }
const KUTU: CSSProperties = { border: `1px solid ${CIZGI}`, borderRadius: 8, padding: "8px 10px" }
const ETIKET: CSSProperties = { color: GRI, fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.4 }

const paraToplami = (toplam: Partial<Record<Para, number>>) =>
  PARALAR.filter((p) => toplam[p] !== undefined)
    .map((p) => para(toplam[p] ?? 0, p))
    .join(" + ") || "—"

function Alan({ etiket, children, genis = false }: { etiket: string; children: ReactNode; genis?: boolean }) {
  return (
    <div style={{ gridColumn: genis ? "1 / -1" : undefined, minWidth: 0 }}>
      <div style={ETIKET}>{etiket}</div>
      <div style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", fontWeight: 600 }}>{children || "—"}</div>
    </div>
  )
}

/** A4 rapor sablonu: baslik, kapsam, ozet kutulari, her is icin bolunmeyen bir kart (data-pdf-blok). */
function Sablon({ kayitlar, ozet, filtre, t }: { kayitlar: Kayit[]; ozet: Ozet; filtre: string; t: Metin }) {
  const kutular: [string, string][] = [
    [t.kpiIs, sayi(kayitlar.length)],
    [t.kpiAylik, paraToplami(ozet.aylik_gelir)],
    [t.kpiYilIci, ozet.yil_ici_gelir > 0 ? para(ozet.yil_ici_gelir) : "—"],
    [t.kpiSaat, `${sayi(ozet.aylik_saat)} ${t.saatAy}`],
    [t.yillikSaat, `${sayi(ozet.yillik_saat)} ${t.saat}`],
  ]
  return (
    <div style={KOK}>
      <div style={{ borderBottom: `3px solid ${SARI}`, paddingBottom: 10, marginBottom: 14 }}>
        <div style={{ color: LACIVERT, fontSize: 18, fontWeight: 900 }}>{t.raporBaslik}</div>
        <div style={{ color: GRI, fontWeight: 700 }}>
          {t.raporKapsam(kayitlar.length)} · {t.raporTarihi(tarih(new Date().toISOString()))}
          {filtre ? ` · ${t.raporFiltre(filtre)}` : ""}
        </div>
      </div>
      <div data-pdf-blok style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8, marginBottom: 14 }}>
        {kutular.map(([ad, deger]) => (
          <div key={ad} style={{ ...KUTU, background: "#f8fafc" }}>
            <div style={ETIKET}>{ad}</div>
            <div style={{ color: LACIVERT, fontSize: 13, fontWeight: 900 }}>{deger}</div>
          </div>
        ))}
      </div>
      {kayitlar.map((k, i) => (
        <div key={k.id} data-pdf-blok style={{ ...KUTU, marginBottom: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 6 }}>
            <div style={{ color: LACIVERT, fontSize: 12, fontWeight: 900 }}>{`${i + 1}. ${k.title}`}</div>
            <div style={{ color: GRI, fontWeight: 700, whiteSpace: "nowrap" }}>{`${t.tur_[k.kind]} · ${t.durum_[k.status]} · ${t.fayda_[k.benefit_type]}`}</div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "6px 12px" }}>
            <Alan etiket={t.tamKisiler}>{kisilerMetni(k.people.map((p) => p.name), k.other_people)}</Alan>
            <Alan etiket={t.musteriler}>{k.customers}</Alan>
            <Alan etiket={`${t.baslangic} – ${t.bitis}`}>{tarihAraligi(k, t)}</Alan>
            <Alan etiket={t.kpiAylik}>{[tutarMetni(k, t), k.revenue_note].filter(Boolean).join(" · ")}</Alan>
            <Alan etiket={t.yilIci}>{k.year_revenue !== null ? para(k.year_revenue) : ""}</Alan>
            <Alan etiket={t.aylikSaat}>{[saatMetni(k.hours_per_month, t), k.hours_note].filter(Boolean).join(" · ")}</Alan>
            <Alan etiket={t.yillikSaat}>{k.hours_per_year !== null ? `${sayi(k.hours_per_year)} ${t.saat}` : ""}</Alan>
            <Alan etiket={t.onaylayan}>{k.approved_by}</Alan>
            <Alan etiket={t.guncelDurum} genis>
              {k.status_note}
            </Alan>
            <Alan etiket={t.yolHaritasi} genis>
              {k.roadmap}
            </Alan>
            <Alan etiket={t.aciklamaAlani} genis>
              {k.description}
            </Alan>
            {k.extra_note ? (
              <Alan etiket={t.ekAciklama} genis>
                {k.extra_note}
              </Alan>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  )
}

/**
 * Modul raporu: Excel (sunucu, 13 Excel sutunu + Ozet sayfasi) ve PDF (panelde, A4). Ikisi de ekrandaki filtrelere uyan ONAYLI isleri kapsar.
 * PDF kutuphaneleri yalniz istendiginde yuklenir (rapor-pdf.ts).
 */
export function RaporDugmeleri({ dil, suzgec, filtreMetni, kayitlar, ozet }: { dil: Dil; suzgec: RaporSuzgeci; filtreMetni: string; kayitlar: Kayit[]; ozet: Ozet | undefined }) {
  const t = gelirUretimMetin(dil)
  const sablon = useRef<HTMLDivElement>(null)
  const [hazirlaniyor, setHazirlaniyor] = useState(false)
  const [hata, setHata] = useState("")
  const onayli = kayitlar.filter((k) => k.approval === "onayli")

  async function pdfIndir() {
    setHata("")
    setHazirlaniyor(true)
    try {
      for (let i = 0; i < 2; i++) await new Promise((coz) => requestAnimationFrame(() => coz(null))) // sablon cizilsin
      if (!sablon.current) throw new Error("pdf")
      const gun = new Date().toISOString().slice(0, 10).replace(/-/g, "")
      dosyaIndir(await raporPdfOlustur(sablon.current), `Gelir_Faydasi_${gun}.pdf`)
    } catch {
      setHata(t.pdfHata)
    } finally {
      setHazirlaniyor(false)
    }
  }

  return (
    <>
      <a className={DUGME} href={apiYolu(`${TABAN}/excel${sorguMetni(suzgec)}`)} download title={t.raporIpucu}>
        <FileSpreadsheet aria-hidden className="size-4" />
        {t.excelRapor}
      </a>
      <button type="button" className={DUGME} title={hata || t.raporIpucu} disabled={hazirlaniyor || !ozet} onClick={() => void pdfIndir()}>
        <FileDown aria-hidden className="size-4" />
        {hazirlaniyor ? t.pdfHazirlaniyor : t.pdfRapor}
      </button>
      {hata ? (
        <span role="alert" className="text-xs font-bold text-rose-200">
          {hata}
        </span>
      ) : null}
      {hazirlaniyor && ozet ? (
        <div aria-hidden className="pointer-events-none fixed top-0 -left-[10000px]">
          {/* data-harf-koru: PDF bir belge; ekrandaki BUYUK HARF gosterim kurali uygulanmaz, metin girildigi gibi (Turkce harflerle) cikar */}
          <div ref={sablon} data-harf-koru style={{ width: 794 }}>
            <Sablon kayitlar={onayli} ozet={ozet} filtre={filtreMetni} t={t} />
          </div>
        </div>
      ) : null}
    </>
  )
}
