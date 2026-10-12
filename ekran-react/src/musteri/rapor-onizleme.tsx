import { forwardRef } from "react"
import type { CSSProperties } from "react"
import { apiYolu } from "@/lib/http"

/**
 * Aylik rapor PDF sablonu (uretim customer_detail.html #pdf_report_template): ust bant (unvan, donem, Teknocan),
 * renkli bolum kutulari, grafikler (Bilgilendirme altinda, iki sutun), elle eklenen gorseller ve imzali alt bant.
 * YALNIZ satir ici hex stil: PDF'e cevirirken stil dosyalari kaldirilir (html2canvas Tailwind v4 oklch renklerini okuyamaz).
 * Basliklar RAPOR dilindedir (panel dili degil); grafiklerin ustundeki baslik da rapor diline uyar.
 */

export type RaporGrafigi = { anahtar: string; baslik: string; gorsel: string }

const LACIVERT = "#002855"
const SARI = "#ffc72c"
const METIN = {
  tr: {
    rapor: "TAM Aylık Rapor",
    olumlu: "Olumlu Gelişmeler",
    devam: "Devam Eden Çalışmalar",
    kritik: "Kritik Konular",
    bilgi: "Bilgilendirmeler",
    oneri: "Öneriler",
    unvan: "Teknik Müşteri Yöneticisi (TAM)",
  },
  en: {
    rapor: "TAM Monthly Report",
    olumlu: "Positive Developments",
    devam: "Ongoing Work",
    kritik: "Critical Issues",
    bilgi: "Information",
    oneri: "Suggestions",
    unvan: "Technical Account Manager (TAM)",
  },
}
const BOLUMLER = [
  { alan: "olumlu", kenar: "#ccfbf1", zemin: "#f0fdfa", baslik: "#0f766e" },
  { alan: "devam", kenar: "#dbeafe", zemin: "#f5f9ff", baslik: LACIVERT },
  { alan: "kritik", kenar: "#ffe4e6", zemin: "#fff7f8", baslik: "#be123c" },
  { alan: "bilgi", kenar: "#e0f2fe", zemin: "#f4fbff", baslik: "#0369a1" },
  { alan: "oneri", kenar: "#d1fae5", zemin: "#f2fdf8", baslik: "#047857" },
] as const

const YAZI = "'Segoe UI', Calibri, Arial, sans-serif"
const kutu: CSSProperties = { borderRadius: 12, borderStyle: "solid", borderWidth: 1, padding: 14, marginBottom: 14 }
const paragraf: CSSProperties = { margin: 0, paddingLeft: 14, fontSize: 11.5, lineHeight: 1.6, color: "#334155", fontWeight: 500, whiteSpace: "pre-line" }

function Sekil({ baslik, gorsel }: { baslik: string; gorsel: string }) {
  return (
    <figure style={{ margin: 0, padding: 10, borderRadius: 12, border: "1px solid #e2e8f0", background: "#ffffff", breakInside: "avoid" }}>
      <figcaption style={{ fontSize: 11.5, fontWeight: 800, color: LACIVERT, marginBottom: 6 }}>{baslik}</figcaption>
      <img src={gorsel} alt={baslik} style={{ display: "block", width: "100%", height: "auto", maxHeight: "110mm", objectFit: "contain" }} />
    </figure>
  )
}

type Props = {
  musteriAdi: string
  donem: string
  dil: "tr" | "en"
  alanlar: Record<string, string>
  grafikler: RaporGrafigi[]
  ekler: RaporGrafigi[]
}

export const RaporOnizleme = forwardRef<HTMLDivElement, Props>(function RaporOnizleme({ musteriAdi, donem, dil, alanlar, grafikler, ekler }, ref) {
  const m = METIN[dil]
  const imza = (alanlar.imza ?? "").split("\n").map((s) => s.trim()).filter(Boolean)
  const bant: CSSProperties = { background: LACIVERT, color: "#ffffff", padding: 18, borderRadius: 16, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }
  return (
    <div
      ref={ref}
      lang={dil}
      data-testid="rapor-pdf"
      style={{ width: "210mm", minHeight: "297mm", padding: "15mm", boxSizing: "border-box", background: "#ffffff", color: LACIVERT, fontFamily: YAZI, display: "flex", flexDirection: "column", justifyContent: "space-between", flexShrink: 0 }}
    >
      <div>
        <div data-pdf-blok style={{ ...bant, marginBottom: 22 }}>
          <div style={{ minWidth: 0 }}>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 900, lineHeight: 1.25, color: "#ffffff" }}>{musteriAdi}</h1>
            <p style={{ margin: "4px 0 0", fontSize: 11.5, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", color: SARI }}>
              {m.rapor} - {donem}
            </p>
          </div>
          <img src={apiYolu("/rapor-teknocan.png")} alt="Teknocan" width={96} height={96} style={{ width: 96, height: 96, borderRadius: 48, flexShrink: 0 }} />
        </div>
        {BOLUMLER.map((b) => (
          <div key={b.alan} style={{ ...kutu, borderColor: b.kenar, background: b.zemin }}>
            <h3 style={{ margin: "0 0 6px", fontSize: 11.5, fontWeight: 900, letterSpacing: 1, textTransform: "uppercase", color: b.baslik }}>{m[b.alan]}</h3>
            <p style={paragraf}>{alanlar[b.alan] ?? ""}</p>
            {b.alan === "bilgi" && grafikler.length > 0 ? (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 14 }}>
                {grafikler.map((g) => (
                  <Sekil key={g.anahtar} baslik={g.baslik} gorsel={g.gorsel} />
                ))}
              </div>
            ) : null}
            {b.alan === "bilgi" && ekler.length > 0 ? (
              <div style={{ display: "grid", gap: 14, marginTop: 14 }}>
                {ekler.map((g) => (
                  <Sekil key={g.anahtar} baslik={g.baslik} gorsel={g.gorsel} />
                ))}
              </div>
            ) : null}
          </div>
        ))}
      </div>
      <div data-pdf-blok style={{ ...bant, marginTop: 28 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <img src={apiYolu("/rapor-turkcell-imza.png")} alt="Turkcell" width={56} height={56} style={{ width: 56, height: 56, borderRadius: 12, flexShrink: 0 }} />
          <div>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 900, color: "#ffffff" }}>{imza[0] ?? ""}</p>
            <p style={{ margin: "2px 0 0", fontSize: 10.5, fontWeight: 700, color: SARI }}>{m.unvan}</p>
          </div>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <span style={{ display: "block", fontSize: 10, fontWeight: 700, letterSpacing: 2, textTransform: "uppercase", color: "#94a3b8" }}>Turkcell Superonline</span>
          <span style={{ fontSize: 11.5, fontWeight: 900, color: SARI }}>www.superonline.net</span>
        </div>
      </div>
    </div>
  )
})
