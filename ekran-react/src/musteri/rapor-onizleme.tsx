import { forwardRef } from "react"
import type { CSSProperties, ReactNode } from "react"
import { apiYolu } from "@/lib/http"

/**
 * Aylik rapor PDF sablonu (uretim customer_detail.html #pdf_report_template): ust bant (unvan, donem, Teknocan),
 * renkli bolum kutulari ve imzali alt bant. Bolumler sayfa sayfa (data-pdf-sayfa = PDF'te zorunlu sayfa sonu):
 * olumlu / devam / kritik | bilgilendirmeler | alarm-talep-sikayet grafikleri | aylik trafik kullanimi | devre performansi | oneriler.
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
    sla: "Alarm, Talep ve Şikayet",
    trafik: "Aylık Trafik Kullanımı",
    devre: "Devre Performansı",
    unvan: "Technical Account Manager",
  },
  en: {
    rapor: "TAM Monthly Report",
    olumlu: "Positive Developments",
    devam: "Ongoing Work",
    kritik: "Critical Issues",
    bilgi: "Information",
    oneri: "Suggestions",
    sla: "Alarms, Requests and Complaints",
    trafik: "Monthly Traffic Usage",
    devre: "Circuit Performance",
    unvan: "Technical Account Manager",
  },
}
const BOLUMLER = [
  { alan: "olumlu", kenar: "#ccfbf1", zemin: "#f0fdfa", baslik: "#0f766e" },
  { alan: "devam", kenar: "#dbeafe", zemin: "#f5f9ff", baslik: LACIVERT },
  { alan: "kritik", kenar: "#ffe4e6", zemin: "#fff7f8", baslik: "#be123c" },
  { alan: "bilgi", kenar: "#e0f2fe", zemin: "#f4fbff", baslik: "#0369a1" },
  { alan: "oneri", kenar: "#d1fae5", zemin: "#f2fdf8", baslik: "#047857" },
] as const
/** Grafik sayfalarinin kutulari (beyaz zemin). */
const GORSEL_BOLUMLERI = {
  sla: { alan: "sla", kenar: "#ffe4e6", zemin: "#ffffff", baslik: "#be123c" },
  trafik: { alan: "trafik", kenar: "#dbeafe", zemin: "#ffffff", baslik: LACIVERT },
  devre: { alan: "devre", kenar: "#e0f2fe", zemin: "#ffffff", baslik: "#0369a1" },
} as const
type Bolum = { alan: Exclude<keyof (typeof METIN)["tr"], "rapor" | "unvan">; kenar: string; zemin: string; baslik: string }

const YAZI = "'Segoe UI', Calibri, Arial, sans-serif"
const kutu: CSSProperties = { borderRadius: 12, borderStyle: "solid", borderWidth: 1, padding: 14, marginBottom: 14 }
const paragraf: CSSProperties = { margin: 0, paddingLeft: 14, fontSize: 11.5, lineHeight: 1.6, color: "#334155", fontWeight: 500, whiteSpace: "pre-line" }

function Sekil({ baslik, gorsel, yukseklik = "110mm" }: { baslik: string; gorsel: string; yukseklik?: string }) {
  return (
    <figure style={{ margin: 0, padding: 10, borderRadius: 12, border: "1px solid #e2e8f0", background: "#ffffff", breakInside: "avoid" }}>
      <figcaption style={{ fontSize: 11.5, fontWeight: 800, color: LACIVERT, marginBottom: 6 }}>{baslik}</figcaption>
      <img src={gorsel} alt={baslik} style={{ display: "block", width: "100%", height: "auto", maxHeight: yukseklik, objectFit: "contain" }} />
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
  /** Devre performansi grafikleri (public/rapor-trafik.js). */
  loe?: RaporGrafigi[]
}

export const RaporOnizleme = forwardRef<HTMLDivElement, Props>(function RaporOnizleme({ musteriAdi, donem, dil, alanlar, grafikler, ekler, loe = [] }, ref) {
  const m = METIN[dil]
  // Basliklar dil kurallariyla buyutulur: CSS text-transform'u html2canvas dil bilmeden uygular ("Gelişmeler" -> "GELIŞMELER")
  const buyuk = (s: string) => s.toLocaleUpperCase(dil === "en" ? "en-US" : "tr-TR")
  const imza = (alanlar.imza ?? "").split("\n").map((s) => s.trim()).filter(Boolean)
  const bant: CSSProperties = { background: LACIVERT, color: "#ffffff", padding: 18, borderRadius: 16, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }
  const bolum = (b: Bolum, icerik: ReactNode) => (
    <div style={{ ...kutu, borderColor: b.kenar, background: b.zemin }}>
      <h3 style={{ margin: "0 0 6px", fontSize: 11.5, fontWeight: 900, letterSpacing: 1, color: b.baslik }}>{buyuk(m[b.alan])}</h3>
      {icerik}
    </div>
  )
  const metinBolumu = (alan: (typeof BOLUMLER)[number]["alan"]) => bolum(BOLUMLER.find((b) => b.alan === alan)!, <p style={paragraf}>{alanlar[alan] ?? ""}</p>)
  /** Grafik bolumu kendi sayfasindan baslar; `yukseklik`: tek grafigin en fazla yuksekligi (sayfaya sigsin). */
  const gorselSayfasi = (b: Bolum, gorseller: RaporGrafigi[], sutunlar: string, yukseklik: string) => (
    <div data-pdf-sayfa>
      {bolum(
        b,
        <div style={{ display: "grid", gridTemplateColumns: sutunlar, gap: 14, marginTop: 8 }}>
          {gorseller.map((g) => (
            <Sekil key={g.anahtar} baslik={g.baslik} gorsel={g.gorsel} yukseklik={yukseklik} />
          ))}
        </div>,
      )}
    </div>
  )
  return (
    <div
      ref={ref}
      lang={dil}
      // data-harf-koru: rapor bir belge; ekrandaki BUYUK HARF / Turkce karaktersiz gosterim kurali (lib/buyuk-harf) uygulanmaz,
      // metin taslaktaki gibi imla kurallarina uygun ve Turkce harflerle cikar (2026-10-31 kullanici)
      data-harf-koru
      data-testid="rapor-pdf"
      style={{ width: "210mm", minHeight: "297mm", padding: "15mm", boxSizing: "border-box", background: "#ffffff", color: LACIVERT, fontFamily: YAZI, display: "flex", flexDirection: "column", justifyContent: "space-between", flexShrink: 0 }}
    >
      <div>
        <div data-pdf-blok style={{ ...bant, marginBottom: 22 }}>
          <div style={{ minWidth: 0 }}>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 900, lineHeight: 1.25, color: "#ffffff" }}>{musteriAdi}</h1>
            <p style={{ margin: "4px 0 0", fontSize: 11.5, fontWeight: 700, letterSpacing: 1, color: SARI }}>
              {buyuk(`${m.rapor} - ${donem}`)}
            </p>
          </div>
          <img src={apiYolu("/rapor-teknocan.png")} alt="Teknocan" width={96} height={96} style={{ width: 96, height: 96, borderRadius: 48, flexShrink: 0 }} />
        </div>
        {metinBolumu("olumlu")}
        {metinBolumu("devam")}
        {metinBolumu("kritik")}
        <div data-pdf-sayfa>{metinBolumu("bilgi")}</div>
        {grafikler.length ? gorselSayfasi(GORSEL_BOLUMLERI.sla, grafikler, "1fr 1fr", "72mm") : null}
        {ekler.length ? gorselSayfasi(GORSEL_BOLUMLERI.trafik, ekler, "1fr", "115mm") : null}
        {loe.length ? gorselSayfasi(GORSEL_BOLUMLERI.devre, loe, "1fr", "230mm") : null}
        <div data-pdf-sayfa>{metinBolumu("oneri")}</div>
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
          <span style={{ display: "block", fontSize: 10, fontWeight: 700, letterSpacing: 2, color: "#94a3b8" }}>TURKCELL SUPERONLINE</span>
          <span style={{ fontSize: 11.5, fontWeight: 900, color: SARI }}>www.superonline.net</span>
        </div>
      </div>
    </div>
  )
})
