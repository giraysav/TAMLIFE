import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, FolderKanban, ShieldAlert, Users } from "lucide-react"
import { BosKutu, DUGME, HataKutu, Kpi, Panel, Rozet, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { hataMesaji, oku } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"
import { ekipMetin } from "@/ekip/ekip-metin"

type OnemliIs = { id: number; baslik: string; oncelik: string; hedef: string | null }
export type EkipSatiri = {
  id: number
  ad: string
  bugun: string | null
  bugun_ad: string
  musteri: number
  rapor_atilan: number
  rapor_beklenen: number
  uyum: number
  risk: number
  puanlama_disi: boolean
  final_skor: number | null
  agirlik_puani: number | null
  online: number
  yuzyuze: number
  proje_acik: number
  onemli_isler: OnemliIs[]
  cumle: string
}
export type EkipOzetVeri = {
  tarih: string
  kapsam: "ekip" | "kendi"
  risk_var: boolean
  cumle: string | null
  sayilar: { kisi: number; kritik_uyum: number; yuksek_risk: number; acik_proje: number; bugun_izinli: number }
  satirlar: EkipSatiri[]
  esikler: { kritik_uyum: number; yuksek_risk: number }
}

const IZIN = new Set(["yillik_izin", "sirket_izni", "raporlu"])
const sayiYaz = (n: number | null) => (n === null ? "—" : String(n).replace(".", ","))

/**
 * Genel Bakis > Ekip Ozeti (uretim 'TAM Ozet' kutucugu; ayri modul degil). Yonetici tum ekibi, TAM yalniz kendini gorur.
 * `sikisik`: Genel Bakis tek ekrana sigsin diye kutu ust kutunun kalan yuksekligini alir; yalniz tablo satirlari kutunun icinde kayar.
 */
export function EkipOzeti({ dil, onGit, sikisik = false }: { dil: Dil; onGit: (id: string) => void; sikisik?: boolean }) {
  const t = ekipMetin(dil)
  const q = useQuery({ queryKey: ["ekip-ozet"], queryFn: () => oku<EkipOzetVeri>("/api/v1/ekip/ozet") })
  const [secili, setSecili] = useState<number | null>(null)

  if (q.isPending) return <Panel baslik={t.baslik}><Yukleniyor metin={t.yukleniyor} /></Panel>
  if (q.isError) return <Panel baslik={t.baslik}><HataKutu metin={hataMesaji(q.error, t.yuklenemedi)} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} /></Panel>

  const v = q.data
  const kendi = v.kapsam === "kendi"
  const { sayilar, esikler } = v
  const kisi = kendi ? v.satirlar[0] : v.satirlar.find((s) => s.id === secili)
  return (
    <Panel baslik={kendi ? t.baslikKendi : t.baslik} aciklama={kendi ? t.aciklamaKendi : t.aciklama} sinif={sikisik ? "flex min-h-[28rem] w-full flex-col" : "w-full"} govdeSinif={sikisik ? "flex min-h-0 flex-1 flex-col p-3" : "p-4"}>
      <div className={sikisik ? "flex min-h-0 flex-1 flex-col gap-2.5" : "grid gap-4"}>
        {!kendi ? (
          <div className="grid shrink-0 grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi kucuk={sikisik} etiket={t.kisi} deger={sayilar.kisi} ikon={Users} alt={sayilar.bugun_izinli ? t.bugunIzinli(sayilar.bugun_izinli) : undefined} />
            <Kpi kucuk={sikisik} etiket={t.kritikUyum} deger={sayilar.kritik_uyum} ikon={AlertTriangle} ton={sayilar.kritik_uyum ? "amber" : "gri"} alt={t.kritikUyumAlt(esikler.kritik_uyum)} />
            <Kpi kucuk={sikisik} etiket={t.yuksekRisk} deger={v.risk_var ? sayilar.yuksek_risk : "—"} ikon={ShieldAlert} ton={v.risk_var && sayilar.yuksek_risk ? "kirmizi" : "gri"} alt={v.risk_var ? t.yuksekRiskAlt(esikler.yuksek_risk) : t.riskVeriYok} />
            <Kpi kucuk={sikisik} etiket={t.acikProje} deger={sayilar.acik_proje} ikon={FolderKanban} ton="sari" />
          </div>
        ) : null}
        {!kendi && v.cumle ? <p className="shrink-0 rounded-xl bg-tl-blue/5 px-3 py-2 text-xs font-bold text-tl-navy">{v.cumle}</p> : null}
        <VeriTablosu
          kaydirmali={sikisik}
          baslik={kendi ? t.baslikKendi : t.baslik}
          satirlar={v.satirlar}
          anahtar={(s) => s.id}
          vurgulu={(s) => s.id === secili}
          bos={<BosKutu ikon={Users} baslik={t.bos} />}
          kolonlar={[
            { baslik: t.kisi, hucre: (s) => <span className="font-black text-tl-navy">{s.ad}</span> },
            {
              baslik: t.kolBugun,
              hucre: (s) => (s.bugun ? <Rozet ton={IZIN.has(s.bugun) ? "amber" : "yesil"}>{s.bugun_ad}</Rozet> : <span className="text-slate-400">{t.kayitYok}</span>),
            },
            { baslik: t.kolMusteri, hucre: (s) => s.musteri, sinif: "text-center" },
            {
              baslik: t.kolRapor,
              hucre: (s) =>
                s.rapor_beklenen ? (
                  <span className="inline-flex items-center gap-1.5">
                    {s.rapor_atilan}/{s.rapor_beklenen}
                    <Rozet ton={s.uyum < esikler.kritik_uyum ? "kirmizi" : s.uyum < 80 ? "amber" : "yesil"}>%{s.uyum}</Rozet>
                  </span>
                ) : (
                  "—"
                ),
            },
            {
              baslik: t.kolRisk,
              hucre: (s) =>
                v.risk_var ? <span className={s.risk >= esikler.yuksek_risk ? "font-black text-rose-600" : ""}>{s.risk}</span> : <span title={t.riskVeriYok}>—</span>,
              sinif: "text-center",
            },
            {
              baslik: t.kolSkor,
              hucre: (s) =>
                s.puanlama_disi ? (
                  <span className="text-slate-400">{t.puanlamaDisi}</span>
                ) : (
                  <span title={t.skorIpucu(sayiYaz(s.final_skor), sayiYaz(s.agirlik_puani))}>{sayiYaz(s.agirlik_puani)}</span>
                ),
              sinif: "text-center",
            },
            { baslik: t.kolProje, hucre: (s) => s.proje_acik, sinif: "text-center" },
            { baslik: t.kolToplanti, hucre: (s) => <span title={t.toplantiIpucu(s.online, s.yuzyuze)}>{s.online + s.yuzyuze}</span>, sinif: "text-center" },
            ...(kendi
              ? []
              : [
                  {
                    baslik: "",
                    hucre: (s: EkipSatiri) => (
                      <button type="button" className={DUGME} aria-expanded={s.id === secili} onClick={() => setSecili(s.id === secili ? null : s.id)}>
                        {s.id === secili ? t.kapat : t.ayrinti}
                      </button>
                    ),
                    sinif: "text-right",
                  },
                ]),
          ]}
        />
        {kisi ? (
          <div className={`grid gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3 ${sikisik ? "max-h-40 shrink-0 overflow-auto" : ""}`} aria-live="polite">
            <p className="text-xs font-bold text-slate-700">{kisi.cumle}</p>
            {kisi.onemli_isler.length ? (
              <div className="grid gap-1">
                <span className="text-[0.625rem] font-black uppercase tracking-widest text-slate-500">{t.onemliIsler}</span>
                <ul className="grid gap-1 text-xs">
                  {kisi.onemli_isler.map((i) => (
                    <li key={i.id} className="flex flex-wrap items-center gap-2">
                      <Rozet ton={i.oncelik === "kritik" ? "kirmizi" : "amber"}>{i.oncelik}</Rozet>
                      <span className="font-bold text-tl-navy">{i.baslik}</span>
                      {i.hedef ? <span className="text-slate-400">{t.hedef} {i.hedef}</span> : null}
                    </li>
                  ))}
                </ul>
                <button type="button" className={`${DUGME} justify-self-start`} onClick={() => onGit("proje")}>
                  {t.projelereGit}
                </button>
              </div>
            ) : null}
          </div>
        ) : null}
        <p className={`font-bold text-slate-400 ${sikisik ? "shrink-0 text-[0.625rem]" : "text-[0.6875rem]"}`}>{t.dipnot}</p>
      </div>
    </Panel>
  )
}
