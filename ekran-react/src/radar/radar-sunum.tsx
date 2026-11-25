import { useRef, useState } from "react"
import type { ReactNode } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { FileDown, Inbox, Lightbulb, Radar, Sparkles } from "lucide-react"
import { Bildirim, BosKutu, DUGME, DUGME_ANA, GIRDI, HataKutu, Rozet, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { Sutunlar, YatayCubuklar } from "@/components/grafik"
import type { Seri } from "@/components/grafik"
import { sayi, zaman } from "@/lib/bicim"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { dosyaIndir, raporPdfOlustur } from "@/musteri/rapor-pdf"
import type { Dil } from "@/shell/metin"
import { sunumMetin } from "@/radar/radar-sunum-metin"

type Firsat = "yuksek" | "orta" | "dusuk"
type Dagilim = { anahtar: string; ad: string; adet: number; oran: number }
type YzYorumu = { metin: string; zaman: string; kim: string; model: string | null }
export type RadarMusterisi = {
  musteri_no: string
  unvan: string
  toplam: number
  acik: number
  kapanan: number
  aylik_ortalama: number
  lokasyon_sayisi: number
  sdwan_oran: number
  yedek_oran: number
  kendiliginden_oran: number
  medyan_cozum_dk: number | null
  anlik_oran: number
  uzun_oran: number
  kalite_oran: number
  son30: number
  onceki30: number
  degisim: number | null
  aylar: { ay: string; toplam: number }[]
  sure_profili: Dagilim[]
  etki: Dagilim[]
  hizmetler: { ad: string; adet: number; lokasyon: number; oran: number }[]
  lokasyonlar: { ad: string; adet: number }[]
  skor: number
  firsat: Firsat
  ozet: string[]
  oneriler: { baslik: string; gerekce: string }[]
  yz: YzYorumu | null
}
export type RadarPortfoyu = {
  veri_zamani: string | null
  musteri_sayisi: number
  toplam_alarm: number
  acik_alarm: number
  lokasyon: number
  firsat: Record<Firsat, number>
  sure_profili: Dagilim[]
  etki: Dagilim[]
  musteriler: RadarMusterisi[]
  sikayet_talep: { erisim: boolean; kaynak: string; neden: string }
  yz: { hazir: boolean; eksik: string[] }
}

// Tek seri (buyukluk): marka laciverti. Kategorik renk gerekmez: her grafik tek olcu gosterir, kimlik etiketle tasinir.
const SERI: Seri[] = [{ anahtar: "adet", ad: "Alarm", renk: "#002855" }]
const FIRSAT_TON: Record<Firsat, "yesil" | "amber" | "gri"> = { yuksek: "yesil", orta: "amber", dusuk: "gri" }
const PDF_GENISLIK = 1600

/** Musteri Radar yonetim sunumu (2026-10-25): satis direktorleri / GMY icin portfoy slayti + musteri basina slayt (kok neden, trend,
 *  lokasyon, satis firsati, kural tabanli ozet ve istege bagli YZ yorumu). PDF: Ceyrek Sunum'la ayni yontem (A4 yatay, slayt bolunmez). */
export function RadarSunumu({ dil, yonetici = false }: { dil: Dil; yonetici?: boolean }) {
  const t = sunumMetin(dil)
  const [kapsam, setKapsam] = useState("tumu")
  const [pdfBekliyor, setPdfBekliyor] = useState(false)
  const [pdfHata, setPdfHata] = useState("")
  const kok = useRef<HTMLDivElement>(null)
  const q = useQuery({ queryKey: ["radar", "sunum"], queryFn: () => oku<RadarPortfoyu>("/api/v1/radar/sunum") })

  if (q.isPending) return <Yukleniyor metin={t.yukleniyor} />
  if (q.isError) return <HataKutu metin={hataMesaji(q.error, t.yuklenemedi)} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
  const p = q.data
  if (!p.musteri_sayisi) return <BosKutu ikon={Radar} baslik={t.bos} />
  const gosterilen = kapsam === "tumu" ? p.musteriler : p.musteriler.filter((m) => m.musteri_no === kapsam)

  async function pdf() {
    const el = kok.current
    if (!el) return
    setPdfBekliyor(true)
    setPdfHata("")
    // Yakalama genisligi sabit: sayfa yuksekligi genislik / 1,414 (A4 yatay); 1600 px'te her slayt tek sayfaya sigar, ekran boyutundan bagimsiz.
    el.style.width = `${PDF_GENISLIK}px`
    try {
      await new Promise((r) => requestAnimationFrame(() => r(null)))
      const blob = await raporPdfOlustur(el, 1.5, 0.92, { yon: "l", ekranGorunumu: true, gizle: "[data-pdf-gizle]" })
      dosyaIndir(blob, `TAMLIFE_Musteri_Radar_Sunum_${new Date().toISOString().slice(0, 10)}.pdf`)
    } catch (e) {
      console.error("radar sunum pdf", e) // teshis: html2canvas / jsPDF hatasi
      setPdfHata(t.pdfHata)
    } finally {
      el.style.width = ""
      setPdfBekliyor(false)
    }
  }

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="grid gap-1 text-xs font-bold text-slate-600">
          {t.kapsam}
          <select className={`${GIRDI} min-w-72`} value={kapsam} onChange={(e) => setKapsam(e.target.value)}>
            <option value="tumu">{t.tumu}</option>
            <option value="portfoy">{t.portfoySec}</option>
            {p.musteriler.map((m) => (
              <option key={m.musteri_no} value={m.musteri_no}>
                {m.unvan}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className={DUGME_ANA} disabled={pdfBekliyor} onClick={() => void pdf()}>
          <FileDown aria-hidden className="size-4" />
          {pdfBekliyor ? t.pdfHazirlaniyor : t.pdf}
        </button>
        {pdfHata ? <span className="text-xs font-bold text-rose-600">{pdfHata}</span> : null}
      </div>
      {yonetici && !p.yz.hazir ? <Bildirim ton="amber">{t.yzKapali(p.yz.eksik.join(", "))}</Bildirim> : null}
      <div ref={kok} className="grid min-w-0 gap-6 [&>*]:min-w-0">
        {kapsam === "tumu" || kapsam === "portfoy" ? <PortfoySlayti dil={dil} p={p} /> : null}
        {kapsam === "tumu" || kapsam === "portfoy" ? <TabloSlayti dil={dil} p={p} /> : null}
        {kapsam === "portfoy"
          ? null
          : gosterilen.map((m) => <MusteriSlayti key={m.musteri_no} dil={dil} m={m} p={p} yonetici={yonetici} />)}
      </div>
    </div>
  )
}

function Slayt({ dil, ust, baslik, alt, sag, veriZamani, children }: { dil: Dil; ust: string; baslik: string; alt?: string; sag?: ReactNode; veriZamani: string | null; children: ReactNode }) {
  const t = sunumMetin(dil)
  return (
    <section data-pdf-blok aria-label={baslik} className="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <header className="flex flex-wrap items-center gap-4 bg-tl-navy px-6 py-4 text-white">
        <span aria-hidden className="h-10 w-1.5 shrink-0 rounded-full bg-tl-yellow" />
        <div className="min-w-[12rem] flex-1">
          <p className="text-[0.625rem] font-black uppercase tracking-[0.16em] text-tl-yellow">{ust}</p>
          <h3 className="text-xl font-black leading-tight">{baslik}</h3>
          {alt ? <p className="mt-0.5 text-xs font-bold text-white/70">{alt}</p> : null}
        </div>
        {sag}
      </header>
      <div className="grid gap-3.5 p-4 sm:px-6 sm:py-5 [&>*]:min-w-0">{children}</div>
      <footer className="flex flex-wrap justify-between gap-2 border-t border-slate-100 px-6 py-2 text-[0.625rem] font-bold text-slate-400">
        <span>{t.kaynak(veriZamani ? zaman(veriZamani) : "—")}</span>
        <span>{t.gizli} · TAMLIFE</span>
      </footer>
    </section>
  )
}

function Kpi({ etiket, deger, alt }: { etiket: string; deger: ReactNode; alt?: ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/70 px-4 py-2.5">
      <p className="text-[0.625rem] font-black uppercase tracking-wide text-slate-500">{etiket}</p>
      <p className="mt-1 font-mono text-xl font-black leading-none text-tl-navy">{deger}</p>
      {alt ? <p className="mt-1 text-[0.625rem] font-bold text-slate-400">{alt}</p> : null}
    </div>
  )
}

function Bolum({ baslik, alt, children, sinif = "" }: { baslik: string; alt?: string; children: ReactNode; sinif?: string }) {
  return (
    <div className={`grid min-w-0 content-start gap-2.5 rounded-xl border border-slate-200 px-4 py-3.5 [&>*]:min-w-0 ${sinif}`}>
      <div>
        <h4 className="text-sm font-black text-tl-navy">{baslik}</h4>
        {alt ? <p className="text-[0.6875rem] font-bold text-slate-400">{alt}</p> : null}
      </div>
      {children}
    </div>
  )
}

function FirsatRozeti({ dil, firsat }: { dil: Dil; firsat: Firsat }) {
  return <Rozet ton={FIRSAT_TON[firsat]}>{sunumMetin(dil).firsat[firsat]}</Rozet>
}

function PortfoySlayti({ dil, p }: { dil: Dil; p: RadarPortfoyu }) {
  const t = sunumMetin(dil)
  return (
    <Slayt dil={dil} ust={t.portfoyAlt} baslik={t.portfoyBaslik} veriZamani={p.veri_zamani}>
      <p className="text-base font-black leading-snug text-tl-navy sm:text-lg">{t.portfoyMesaj(sayi(p.musteri_sayisi), sayi(p.toplam_alarm), p.firsat.yuksek)}</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Kpi etiket={t.kpiMusteri} deger={sayi(p.musteri_sayisi)} />
        <Kpi etiket={t.kpiAlarm} deger={sayi(p.toplam_alarm)} />
        <Kpi etiket={t.kpiAcik} deger={sayi(p.acik_alarm)} />
        <Kpi etiket={t.kpiLokasyon} deger={sayi(p.lokasyon)} />
        <Kpi etiket={t.kpiYuksek} deger={sayi(p.firsat.yuksek)} alt={`${t.firsat.orta} ${p.firsat.orta} · ${t.firsat.dusuk} ${p.firsat.dusuk}`} />
      </div>
      <div className="grid gap-4 lg:grid-cols-5">
        <Bolum baslik={t.siralama} alt={t.siralamaAlt} sinif="lg:col-span-3">
          <ol className="grid gap-2">
            {p.musteriler.map((m, i) => (
              <li key={m.musteri_no} className="grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 text-xs">
                <span className="font-mono font-black text-slate-400">{i + 1}</span>
                <span className="flex min-w-0 items-center gap-2">
                  <span className="truncate font-bold text-slate-700" title={m.unvan}>
                    {m.unvan}
                  </span>
                  <FirsatRozeti dil={dil} firsat={m.firsat} />
                </span>
                <span className="font-mono font-black text-tl-navy">{m.skor}</span>
                <span />
                <span className="col-span-2 flex h-2 overflow-hidden rounded-full bg-slate-100" role="img" aria-label={`${m.unvan}: ${m.skor} / 100`} title={`${m.skor} / 100 · ${t.alarmAdet(sayi(m.toplam))}`}>
                  <span className="block h-full rounded-full bg-tl-navy" style={{ width: `${m.skor}%` }} />
                </span>
              </li>
            ))}
          </ol>
        </Bolum>
        <Bolum baslik={t.profil} alt={t.profilAlt} sinif="lg:col-span-2">
          <DagilimCubuklari dagilim={p.sure_profili} sayiyla />
          <EtkiListesi dil={dil} etki={p.etki} />
        </Bolum>
      </div>
      <p className="text-[0.625rem] font-bold leading-relaxed text-slate-400">{t.skorAciklama}</p>
    </Slayt>
  )
}

/** Portfoyun musteri bazinda tablosu (ayri slayt: her slayt tek A4 yatay sayfaya sigsin). */
function TabloSlayti({ dil, p }: { dil: Dil; p: RadarPortfoyu }) {
  const t = sunumMetin(dil)
  return (
    <Slayt dil={dil} ust={t.portfoyBaslik} baslik={t.tablo} veriZamani={p.veri_zamani}>
      <VeriTablosu<RadarMusterisi>
        baslik={t.tablo}
        satirlar={p.musteriler}
        anahtar={(m) => m.musteri_no}
        kolonlar={[
          { baslik: t.kolMusteri, hucre: (m) => <span className="line-clamp-1 max-w-64">{m.unvan}</span> },
          { baslik: t.kolFirsat, hucre: (m) => <FirsatRozeti dil={dil} firsat={m.firsat} /> },
          { baslik: t.kolAlarm, hucre: (m) => sayi(m.toplam), sinif: "text-right font-mono" },
          { baslik: t.kolAcik, hucre: (m) => sayi(m.acik), sinif: "text-right font-mono" },
          { baslik: t.kolLokasyon, hucre: (m) => sayi(m.lokasyon_sayisi), sinif: "text-right font-mono" },
          { baslik: t.kolKok, hucre: (m) => `%${sayi(m.uzun_oran)}`, sinif: "text-right font-mono" },
          { baslik: t.kolOneri, hucre: (m) => <span className="line-clamp-2 max-w-72 font-normal">{m.oneriler[0]?.baslik ?? "—"}</span> },
          { baslik: t.kolSkor, hucre: (m) => <span className="font-mono font-black text-tl-navy">{m.skor}</span>, sinif: "text-right" },
        ]}
      />
    </Slayt>
  )
}

function DagilimCubuklari({ dagilim, sayiyla = false }: { dagilim: Dagilim[]; sayiyla?: boolean }) {
  return (
    <YatayCubuklar
      seriler={SERI}
      satirlar={dagilim.map((x) => ({ anahtar: x.anahtar, etiket: x.ad, degerler: { adet: x.adet }, sag: sayiyla ? `%${sayi(x.oran)} · ${sayi(x.adet)}` : `%${sayi(x.oran)}` }))}
    />
  )
}

function EtkiListesi({ dil, etki }: { dil: Dil; etki: Dagilim[] }) {
  return (
    <div className="grid gap-1 border-t border-slate-100 pt-2">
      <p className="text-[0.625rem] font-black uppercase tracking-wide text-slate-500">{sunumMetin(dil).etki}</p>
      {etki.map((e) => (
        <p key={e.anahtar} className="flex justify-between gap-3 text-xs">
          <span className="font-bold text-slate-600">{e.ad}</span>
          <span className="shrink-0 font-mono font-black text-tl-navy">
            %{sayi(e.oran)} · {sayi(e.adet)}
          </span>
        </p>
      ))}
    </div>
  )
}

function sureMetni(dk: number | null, dil: Dil): string {
  const t = sunumMetin(dil)
  if (dk === null) return "—"
  return dk < 120 ? t.dakika(sayi(dk)) : t.saat(sayi(Math.round(dk / 6) / 10))
}

function ayEtiketi(ay: string, dil: Dil): string {
  const [y, a] = ay.split("-").map(Number)
  return `${new Date(y, a - 1, 1).toLocaleDateString(dil === "en" ? "en-GB" : "tr-TR", { month: "short" })} ${String(y).slice(2)}`
}

function MusteriSlayti({ dil, m, p, yonetici }: { dil: Dil; m: RadarMusterisi; p: RadarPortfoyu; yonetici: boolean }) {
  const t = sunumMetin(dil)
  return (
    <Slayt
      dil={dil}
      ust={t.musteriNo(m.musteri_no)}
      baslik={m.unvan}
      veriZamani={p.veri_zamani}
      sag={
        <div className="flex items-center gap-3 rounded-xl bg-white/10 px-4 py-2">
          <span className="text-[0.625rem] font-black uppercase tracking-wide text-white/80">{t.firsat[m.firsat]}</span>
          <span className="font-mono text-3xl font-black leading-none text-tl-yellow">{m.skor}</span>
        </div>
      }
    >
      {m.oneriler[0] ? <p className="text-base font-black leading-snug text-tl-navy sm:text-lg">{t.onerilenFirsat(m.oneriler[0].baslik)}</p> : null}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Kpi etiket={t.kpiAlarm} deger={sayi(m.toplam)} />
        <Kpi etiket={t.kpiAylik} deger={sayi(m.aylik_ortalama)} />
        <Kpi etiket={t.kpiAcik} deger={sayi(m.acik)} />
        <Kpi etiket={t.kpiLokasyon} deger={sayi(m.lokasyon_sayisi)} alt={m.yedek_oran ? t.yedek(sayi(m.yedek_oran)) : undefined} />
        <Kpi etiket={t.kpiMedyan} deger={sureMetni(m.medyan_cozum_dk, dil)} />
        <Kpi etiket={t.kpiUzun} deger={`%${sayi(m.uzun_oran)}`} />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Bolum baslik={t.trend} alt={t.trendAlt(sayi(m.son30), sayi(m.onceki30))}>
          <Sutunlar seriler={SERI} sutunlar={m.aylar.map((a) => ({ etiket: ayEtiketi(a.ay, dil), degerler: { adet: a.toplam } }))} yukseklik={100} />
          <p className="border-t border-slate-100 pt-2 text-[0.625rem] font-black uppercase tracking-wide text-slate-500">{t.lokasyonlar}</p>
          <ol className="grid gap-1">
            {m.lokasyonlar.slice(0, 4).map((l) => (
              <li key={l.ad} className="flex min-w-0 items-baseline justify-between gap-3 text-xs">
                <span className="min-w-0 truncate font-mono text-[0.6875rem] text-slate-600" title={l.ad}>
                  {l.ad}
                </span>
                <span className="shrink-0 font-mono font-black text-tl-navy">{sayi(l.adet)}</span>
              </li>
            ))}
          </ol>
        </Bolum>
        <Bolum baslik={t.arizaProfili} alt={t.arizaAlt}>
          <DagilimCubuklari dagilim={m.sure_profili} />
          <EtkiListesi dil={dil} etki={m.etki} />
        </Bolum>
        <Bolum baslik={t.hizmetler} alt={t.hizmetAlt(sayi(m.lokasyon_sayisi))}>
          <YatayCubuklar
            seriler={SERI}
            satirlar={m.hizmetler.slice(0, 5).map((h) => ({ anahtar: h.ad, etiket: h.ad, degerler: { adet: h.adet }, sag: t.hizmetSag(sayi(h.oran), sayi(h.lokasyon)) }))}
          />
          {m.sdwan_oran ? <p className="text-[0.625rem] font-bold text-slate-400">{t.sdwan(sayi(m.sdwan_oran))}</p> : null}
        </Bolum>
      </div>
      <div className="grid gap-4 lg:grid-cols-5">
        <Bolum baslik={t.firsatlar} sinif="lg:col-span-2">
          <ol className="grid gap-2">
            {m.oneriler.map((o, i) => (
              <li key={o.baslik} className="flex gap-2.5 text-xs">
                <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-tl-yellow font-mono text-[0.625rem] font-black text-tl-navy">{i + 1}</span>
                <span className="grid gap-0.5">
                  <span className="font-black text-tl-navy">{o.baslik}</span>
                  <span className="font-bold text-slate-500">{o.gerekce}</span>
                </span>
              </li>
            ))}
          </ol>
        </Bolum>
        <Bolum baslik={t.ozet} alt={t.ozetAlt} sinif="lg:col-span-3">
          <ul className="grid gap-1 text-xs font-bold text-slate-600">
            {m.ozet.map((c) => (
              <li key={c} className="flex gap-2">
                <Lightbulb aria-hidden className="mt-0.5 size-3.5 shrink-0 text-tl-blue" />
                <span>{c}</span>
              </li>
            ))}
          </ul>
          <YzBolumu dil={dil} m={m} hazir={p.yz.hazir} yonetici={yonetici} />
        </Bolum>
      </div>
      <div className="flex items-start gap-3 rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-2.5 text-xs">
        <Inbox aria-hidden className="mt-0.5 size-4 shrink-0" style={{ color: "#94a3b8" }} /* PDF: html2canvas SVG icinde oklch renk cizemez, hex */ />
        <p className="min-w-0">
          <span className="font-black text-tl-navy">{t.sikayetTalep}</span>
          <span className="font-bold text-slate-500">
            {" · "}
            {t.sikayetYok}: {p.sikayet_talep.neden}
          </span>
        </p>
      </div>
    </Slayt>
  )
}

function YzBolumu({ dil, m, hazir, yonetici }: { dil: Dil; m: RadarMusterisi; hazir: boolean; yonetici: boolean }) {
  const t = sunumMetin(dil)
  const [hata, setHata] = useState("")
  const [yeni, setYeni] = useState<YzYorumu | null>(null)
  const uret = useMutation({
    mutationFn: () => yaz<YzYorumu>("POST", `/api/v1/radar/${encodeURIComponent(m.musteri_no)}/yz`, {}),
    onSuccess: (y) => {
      setYeni(y)
      setHata("")
    },
    onError: (e) => setHata(hataMesaji(e, t.yzHata)),
  })
  const yz = yeni ?? m.yz
  if (!yz && !(yonetici && hazir) && !hata) return null
  return (
    <div className="grid gap-2 border-t border-slate-100 pt-3">
      {yz ? (
        <div className="grid gap-1 rounded-lg bg-tl-blue/5 p-3">
          <p className="flex items-center gap-1.5 text-[0.6875rem] font-black text-tl-blue">
            <Sparkles aria-hidden className="size-3.5" />
            {t.yzBaslik}
          </p>
          <p className="whitespace-pre-line text-xs font-bold leading-relaxed text-slate-700">{yz.metin}</p>
          <p className="text-[0.625rem] font-bold text-slate-400">{t.yzBilgi(yz.model ?? "", zaman(yz.zaman), yz.kim)}</p>
        </div>
      ) : null}
      {yonetici && hazir ? (
        <div data-pdf-gizle className="grid gap-1">
          <button type="button" className={`${DUGME} justify-self-start`} disabled={uret.isPending} onClick={() => uret.mutate()}>
            <Sparkles aria-hidden className="size-3.5" />
            {uret.isPending ? t.yzUretiliyor : yz ? t.yzYenile : t.yzUret}
          </button>
          <p className="text-[0.625rem] font-bold text-slate-400">{t.yzNot}</p>
        </div>
      ) : null}
      {hata ? <p className="text-[0.6875rem] font-bold text-rose-600">{hata}</p> : null}
    </div>
  )
}
