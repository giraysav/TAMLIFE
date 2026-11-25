import { useEffect, useMemo, useRef, useState } from "react"
import type { FormEvent } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { Map as HaritaIkon, Network, TriangleAlert, Upload, ZoomIn, ZoomOut } from "lucide-react"
import { Alan, Bildirim, BosKutu, DUGME, DUGME_SARI, GIRDI, HataKutu, Kpi, Panel, SayfaKabi, Sekmeler, Yukleniyor } from "@/components/sayfa-ui"
import { sayi } from "@/lib/bicim"
import { hataMesaji, oku, sorguMetni, yaz, yukle } from "@/lib/sorgu"
import type { Kart } from "@/musteri/musteri-karti"
import type { Dil } from "@/shell/metin"
import { topolojiMetin } from "@/topoloji/topoloji-metin"

export type Dugum = {
  id: string
  tur: "bulut" | "switch" | "router"
  etiket: string
  lokasyon: string
  il: string
  /** Simgedeki kisa ad (envanter ciziminde servis kisaltmasi / DEVRE); yoksa SW / RT. */
  kisa?: string
  /** CI ayrintisi (ad, urun, model, hiz) ve hiz: ipucunda. */
  ci?: string
  bw?: string
  /** Kartta Kritik CI isaretli: kirmizi cerceve. */
  kritik?: boolean
}
export type Kenar = { id: string; kaynak: string; hedef: string; altyapi: string; etiket: string; yedek: boolean; devre: string; renk: string }
type Sehir = { il: string; adet: number; enlem: number; boylam: number }
export type Analiz = {
  spof: boolean
  spof_noktalari: { lokasyon: string; bb: string; altyapilar: string[]; neden: "tek_devre" | "ortak_bb" | "ortak_erisim" | "ortak_router"; devreler: string[] }[]
  dugumler: Dugum[]
  kenarlar: Kenar[]
  sehirler: Sehir[]
  konumsuz_iller: string[]
  kolonlar: Record<string, string>
  satir: number
  lokasyon: number
  degerlendirme: "riskli" | "sinirli"
  uyarilar: string[]
  musteri?: { id: number; unvan: string }
  renkler: Record<string, string>
  /** Envanterden cizimde "envanter" (dosya analizinde yok). */
  kaynak?: "envanter"
  /** Envanter cizimi: secili il / ilce / saha (acik adres anahtari) ve kural onekleri ('-' = hicbiri). */
  secim?: { il: string; ilce: string; saha: string; kural: string }
  /** Envanter cizimi: il > ilce > saha secicileri (CI sayilariyla). */
  adres_agaci?: { il: string; ci: number; ilceler: { ilce: string; ci: number; sahalar: { anahtar: string; baslik: string; adres: string; ci: number }[] }[] }[]
  /** TopoMaker cizim kural seti (CI adi oneki; `sabit` = "Diger"). */
  kurallar?: CizimKurali[]
  /** Kural ekleme / silme / varsayilan kaydetme yetkisi (yonetici). */
  kural_duzenler?: boolean
  urun_tutar?: { yuklu?: boolean; devre?: number; eslesen_devre?: number; eslesen_ci?: number; il_farkli?: number }
  cizime_giren?: number
  duzeltilen_ci?: number
}
type CizimKurali = { onek: string; ad: string; ciz: boolean; ci: number; secili: boolean; sabit?: boolean }

const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
const SUTUN = 112
const SEVIYE = [44, 170, 296] as const
const LOK_ARALIK = 28

type Konum = { x: number; y: number }
export type Yerlesim = { konum: Record<string, Konum>; lokasyonlar: { ad: string; x1: number; x2: number }[]; genislik: number }

/** Hiyerarsik yerlesim: bulut ustte; her lokasyon kendi sutun blogunda, switch'ler (ve dogrudan baglanan 4.5G/xDSL router'lar)
 *  ikinci, switch arkasindaki router'lar ucuncu seviyede. Birden cok switch'e bagli router ilk switch'in altina konur. */
export function yerlesim(dugumler: Dugum[], kenarlar: Kenar[]): Yerlesim {
  const komsu = new Map<string, string[]>()
  for (const k of kenarlar) {
    const liste = komsu.get(k.kaynak) ?? []
    if (!liste.includes(k.hedef)) liste.push(k.hedef)
    komsu.set(k.kaynak, liste)
  }
  const gruplar = new Map<string, Dugum[]>()
  for (const d of dugumler) {
    if (d.tur === "bulut") continue
    const liste = gruplar.get(d.lokasyon) ?? []
    liste.push(d)
    gruplar.set(d.lokasyon, liste)
  }
  const ust = new Set(komsu.get("ISP_CLOUD") ?? [])
  const konum: Record<string, Konum> = {}
  const lokasyonlar: Yerlesim["lokasyonlar"] = []
  let x = 0
  for (const [ad, liste] of gruplar) {
    const bas = x
    const yerlesen = new Set<string>()
    for (const d of liste) {
      if (!ust.has(d.id) || yerlesen.has(d.id)) continue
      const altlar = d.tur === "switch" ? (komsu.get(d.id) ?? []).filter((r) => !yerlesen.has(r)) : []
      const genislik = Math.max(1, altlar.length)
      konum[d.id] = { x: x + (genislik * SUTUN) / 2, y: SEVIYE[1] }
      yerlesen.add(d.id)
      altlar.forEach((r, i) => {
        konum[r] = { x: x + i * SUTUN + SUTUN / 2, y: SEVIYE[2] }
        yerlesen.add(r)
      })
      x += genislik * SUTUN
    }
    for (const d of liste) {
      if (yerlesen.has(d.id)) continue // baglantisiz kalan (beklenmez) dugum de gorunsun
      konum[d.id] = { x: x + SUTUN / 2, y: SEVIYE[2] }
      x += SUTUN
    }
    lokasyonlar.push({ ad, x1: bas, x2: x })
    x += LOK_ARALIK
  }
  const genislik = Math.max(x - LOK_ARALIK, 320)
  konum.ISP_CLOUD = { x: genislik / 2, y: SEVIYE[0] }
  return { konum, lokasyonlar, genislik }
}

function kisalt(metin: string, uzunluk = 16) {
  return metin.length > uzunluk ? `${metin.slice(0, uzunluk - 1)}…` : metin
}

function TopolojiCizimi({ veri, t }: { veri: Analiz; t: ReturnType<typeof topolojiMetin> }) {
  const [olcek, setOlcek] = useState(1)
  const [secili, setSecili] = useState<string | null>(null)
  const { konum, lokasyonlar, genislik } = useMemo(() => yerlesim(veri.dugumler, veri.kenarlar), [veri])
  const yukseklik = SEVIYE[2] + 80
  const kullanilan = [...new Set(veri.kenarlar.map((k) => k.altyapi))]
  const ilgili = (k: Kenar) => secili !== null && (k.kaynak === secili || k.hedef === secili)
  const paralel = useMemo(() => {
    const toplam = new Map<string, number>()
    const sira = new Map<string, number>()
    for (const k of veri.kenarlar) {
      const anahtar = `${k.kaynak}>${k.hedef}`
      toplam.set(anahtar, (toplam.get(anahtar) ?? 0) + 1)
    }
    return new Map(veri.kenarlar.map((k) => {
      const anahtar = `${k.kaynak}>${k.hedef}`
      const no = sira.get(anahtar) ?? 0
      sira.set(anahtar, no + 1)
      return [k.id, (no - ((toplam.get(anahtar) ?? 1) - 1) / 2) * 16]
    }))
  }, [veri.kenarlar])
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={DUGME} aria-label="+" onClick={() => setOlcek((o) => Math.min(2, o + 0.2))}>
          <ZoomIn aria-hidden className="size-4" />
        </button>
        <button type="button" className={DUGME} aria-label="-" onClick={() => setOlcek((o) => Math.max(0.4, o - 0.2))}>
          <ZoomOut aria-hidden className="size-4" />
        </button>
        <span className="text-[0.625rem] font-black uppercase tracking-wide text-slate-400">{t.lejant}:</span>
        {kullanilan.map((a) => (
          <span key={a} className="inline-flex items-center gap-1 text-[0.6875rem] font-bold text-slate-600">
            <span aria-hidden className="inline-block h-1 w-5 rounded" style={{ background: veri.renkler[a] ?? "#7F8C8D" }} />
            {a}
          </span>
        ))}
        <span className="text-[0.6875rem] font-bold text-slate-400">· {t.yedek}</span>
      </div>
      <div className="max-h-[70vh] overflow-auto rounded-xl border border-slate-200 bg-slate-50">
        <svg role="img" aria-label={t.topolojiAlt} width={genislik * olcek} height={yukseklik * olcek} viewBox={`0 0 ${genislik} ${yukseklik}`} className="block">
          {lokasyonlar.map((l) => (
            <g key={l.ad}>
              <rect x={l.x1 + 4} y={SEVIYE[1] - 34} width={l.x2 - l.x1 - 8} height={SEVIYE[2] - SEVIYE[1] + 74} rx={12} fill="#ffffff" stroke="#e2e8f0" />
              <text x={(l.x1 + l.x2) / 2} y={yukseklik - 14} textAnchor="middle" className="fill-tl-navy text-[11px] font-black">
                {kisalt(l.ad, Math.max(8, Math.floor((l.x2 - l.x1) / 7)))}
                <title>{`${t.lokasyonEtiket}: ${l.ad}`}</title>
              </text>
            </g>
          ))}
          {veri.kenarlar.map((k) => {
            const a = konum[k.kaynak]
            const b = konum[k.hedef]
            if (!a || !b) return null
            const y1 = a.y + (k.kaynak === "ISP_CLOUD" ? 18 : 16)
            const y2 = b.y - 16
            const orta = (y1 + y2) / 2
            const sapma = paralel.get(k.id) ?? 0
            const vurgu = ilgili(k)
            return (
              <g key={k.id} opacity={secili === null || vurgu ? 1 : 0.25}>
                <path d={`M${a.x},${y1} C${a.x + sapma},${orta} ${b.x + sapma},${orta} ${b.x},${y2}`} fill="none" stroke={k.renk} strokeWidth={vurgu ? 3.5 : 2} strokeDasharray={k.yedek ? "6 4" : undefined} />
                {k.etiket && k.etiket !== "LAN" ? (
                  <text x={(a.x + b.x) / 2 + (b.x - a.x) * 0.25 + sapma} y={orta + (y2 - orta) * 0.5} textAnchor="middle" paintOrder="stroke" stroke="#fff" strokeWidth={3} className="fill-slate-700 text-[9px] font-bold">
                    {kisalt(k.etiket, 18)}
                  </text>
                ) : null}
                <title>{`${k.devre} · ${k.altyapi}${k.yedek ? " (yedek)" : ""}${k.etiket ? ` · ${k.etiket}` : ""}`}</title>
              </g>
            )
          })}
          {veri.dugumler.map((d) => {
            const p = konum[d.id]
            if (!p) return null
            const tikla = () => setSecili((s) => (s === d.id ? null : d.id))
            if (d.tur === "bulut")
              return (
                <g key={d.id} onClick={tikla} className="cursor-pointer">
                  <rect x={p.x - 64} y={p.y - 18} width={128} height={36} rx={8} fill="#1A5276" stroke="#0B2545" strokeWidth={2} />
                  <text x={p.x} y={p.y + 5} textAnchor="middle" className="text-[13px] font-black" fill="#FFD700">
                    {d.etiket}
                  </text>
                </g>
              )
            const ipucu = `${t.lokasyonEtiket}: ${d.lokasyon}${d.il ? ` · ${d.il}` : ""}${d.etiket ? ` · ${d.etiket}` : ""}${d.ci ? ` · ${d.ci}` : ""}${d.bw ? ` · ${d.bw}` : ""}${d.kritik ? ` · ${t.kritikCi}` : ""}`
            return d.tur === "switch" ? (
              <g key={d.id} onClick={tikla} className="cursor-pointer" data-tur="switch">
                <rect x={p.x - 48} y={p.y - 16} width={96} height={32} rx={6} fill="#FFD100" stroke={secili === d.id ? "#0A1628" : "#F39C12"} strokeWidth={2} />
                <text x={p.x} y={p.y - 2} textAnchor="middle" className="text-[10px] font-black" fill="#0A1628">
                  {d.kisa ?? "SW"}
                </text>
                <text x={p.x} y={p.y + 10} textAnchor="middle" className="text-[9px] font-bold" fill="#0A1628">
                  {kisalt(d.etiket || "—")}
                </text>
                <title>{ipucu}</title>
              </g>
            ) : (
              <g key={d.id} onClick={tikla} className="cursor-pointer" data-tur="router">
                <circle cx={p.x} cy={p.y} r={18} fill="#3498DB" stroke={secili === d.id ? "#0A1628" : d.kritik ? "#DC2626" : "#2980B9"} strokeWidth={d.kritik ? 3.5 : 2} />
                <text x={p.x} y={p.y + 4} textAnchor="middle" className="text-[10px] font-black" fill="#0A1628">
                  {d.kisa ?? "RT"}
                </text>
                <text x={p.x} y={p.y + 32} textAnchor="middle" className="fill-slate-600 text-[9px] font-bold">
                  {kisalt(d.etiket || "—")}
                </text>
                <title>{ipucu}</title>
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}

const HARITA = { g: 640, y: 300, bati: 25.6, dogu: 44.9, kuzey: 42.3, guney: 35.7 }

function CografiHarita({ veri, t }: { veri: Analiz; t: ReturnType<typeof topolojiMetin> }) {
  const x = (boylam: number) => ((boylam - HARITA.bati) / (HARITA.dogu - HARITA.bati)) * HARITA.g
  const y = (enlem: number) => ((HARITA.kuzey - enlem) / (HARITA.kuzey - HARITA.guney)) * HARITA.y
  return (
    <div className="grid gap-3">
      <Bildirim>{t.haritaNot}</Bildirim>
      {veri.sehirler.length === 0 ? (
        <BosKutu ikon={HaritaIkon} baslik={t.haritaBos} />
      ) : (
        <div className="overflow-auto rounded-xl border border-slate-200 bg-slate-50">
          <svg role="img" aria-label={t.haritaAlt} viewBox={`-20 -20 ${HARITA.g + 40} ${HARITA.y + 40}`} className="block min-w-[640px]">
            {[27, 30, 33, 36, 39, 42].map((b) => (
              <line key={`b${b}`} x1={x(b)} x2={x(b)} y1={0} y2={HARITA.y} stroke="#e2e8f0" />
            ))}
            {[36, 38, 40, 42].map((e) => (
              <line key={`e${e}`} x1={0} x2={HARITA.g} y1={y(e)} y2={y(e)} stroke="#e2e8f0" />
            ))}
            {veri.sehirler.map((s) => (
              <g key={s.il} data-il={s.il}>
                <circle cx={x(s.boylam)} cy={y(s.enlem)} r={15} fill="#FFD100" stroke="#003DA5" strokeWidth={2} />
                <text x={x(s.boylam)} y={y(s.enlem) + 4} textAnchor="middle" className="text-[11px] font-black" fill="#003DA5">
                  {s.adet}
                </text>
                <text x={x(s.boylam)} y={y(s.enlem) + 30} textAnchor="middle" className="fill-tl-navy text-[10px] font-black">
                  {s.il}
                </text>
                <title>{`${s.il}: ${s.adet} ${t.cihaz}`}</title>
              </g>
            ))}
          </svg>
        </div>
      )}
      {veri.konumsuz_iller.length ? (
        <p className="text-[0.6875rem] font-bold text-slate-500">
          {t.konumsuz}: {veri.konumsuz_iller.join(", ")}
        </p>
      ) : null}
    </div>
  )
}

type EnvanterIstegi = { ara: string; il: string; ilce: string; saha: string; kural?: string }

/** Il haritasi: public/topo-harita.js (ECharts 6.1.0 + tr-iller.json il zemini; il renklendirme, sayili pinler, yakinlastirma,
 *  ilce ipucu). Betik yoksa ya da il zemini yuklenemezse eski basit SVG haritaya (CografiHarita) duser. Envanter ciziminde ile
 *  tiklamak o ili secer (onIl). Yukseklik satir ici: derlenmis CSS'te olmayan sinif harita kutusunu 0 px birakiyordu. */
function IlHaritasi({ veri, t, dil, onIl }: { veri: Analiz; t: ReturnType<typeof topolojiMetin>; dil: Dil; onIl?: (il: string) => void }) {
  const kap = useRef<HTMLDivElement>(null)
  const [cizilebilir, setCizilebilir] = useState(true)
  // onIl her cizimde yeni islev; haritayi yalniz veri ya da dil degisince yeniden cizmek icin bagimliliga alinmaz.
  useEffect(() => {
    const el = kap.current
    if (!el || !window.TamlifeHarita) {
      setCizilebilir(false)
      return
    }
    let gecerli = true
    window.TamlifeHarita.ciz(el, {
      sehirler: veri.sehirler,
      agac: veri.adres_agaci || null,
      secili: veri.secim?.il || "",
      dil,
      birim: veri.kaynak === "envanter" ? "servis" : "cihaz",
      onIl,
    }).then((cizildi) => {
      if (gecerli && !cizildi) setCizilebilir(false)
    })
    return () => {
      gecerli = false
      window.TamlifeHarita?.birak(el)
    }
  }, [veri, dil])
  return cizilebilir ? (
    <div ref={kap} role="img" aria-label={t.haritaAlt} className="w-full rounded-xl border border-slate-200 bg-white" style={{ height: "clamp(380px, 62vh, 640px)" }} />
  ) : (
    <CografiHarita veri={veri} t={t} />
  )
}

/** TopoMaker (uretim topoMakerModal): musteri kartindaki arac bolumunden acilir. Iki kaynak: yuklenen devre envanteri dosyasi
 *  (sunucuda saklanmaz) ya da musterinin CI envanteri (il > ilce > acik adres secimi, CI adi oneki kurallari). Cizim SVG (CDN yok). */
export function TopoMaker({ dil, musteriId }: { dil: Dil; musteriId: number }) {
  const t = topolojiMetin(dil)
  const [dosya, setDosya] = useState<File | null>(null)
  const [uyari, setUyari] = useState("")
  const [sekme, setSekme] = useState<"topoloji" | "harita">("topoloji")
  const kart = useQuery({ queryKey: ["musteri", "kart", musteriId], queryFn: () => oku<Kart>(`/api/v1/musteri/${musteriId}`) })
  const m = useMutation({
    mutationFn: (d: File) => yukle<Analiz>(`/api/v1/topoloji/analiz${sorguMetni({ musteri: musteriId, dosya: d.name })}`, d, d.name.toLowerCase().endsWith(".xlsx") ? XLSX : "text/csv"),
  })
  const [envanterAra, setEnvanterAra] = useState("")
  const [yeniOnek, setYeniOnek] = useState("")
  const [yeniKuralAdi, setYeniKuralAdi] = useState("")
  const envanter = useMutation({
    mutationFn: (s: EnvanterIstegi) =>
      oku<Analiz>(`/api/v1/topoloji/envanter${sorguMetni({ musteri: musteriId, ara: s.ara, il: s.il, ilce: s.ilce, saha: s.saha, kural: s.kural, en_fazla: 25 })}`),
  })
  // Gosterilen sonuc: en son calisan kaynak (dosya yuklemesi envanter sonucunu, envanter cizimi dosya sonucunu sifirlar).
  const sonuc = envanter.isIdle ? m : envanter
  const v = sonuc.data

  function gonder(e: FormEvent) {
    e.preventDefault()
    if (!dosya) {
      setUyari(t.dosyaSec)
      return
    }
    if (dosya.size > 10 * 1024 * 1024) {
      setUyari(t.dosyaBuyuk)
      return
    }
    setUyari("")
    envanter.reset()
    m.mutate(dosya)
  }

  function envanterCiz(e: FormEvent) {
    e.preventDefault()
    setUyari("")
    m.reset()
    envanter.mutate({ ara: envanterAra.trim(), il: v?.secim?.il ?? "", ilce: v?.secim?.ilce ?? "", saha: "", kural: v?.secim?.kural ?? "" })
  }

  /** Secimi degistirip yeniden cizer (verilmeyen alanlar son secimden). */
  function sec(degisen: Partial<EnvanterIstegi>) {
    setUyari("")
    envanter.mutate({ ara: envanterAra.trim(), il: "", ilce: "", saha: "", ...v?.secim, ...degisen })
  }

  function kuralSec(onek: string) {
    const secili = new Set((v?.kurallar ?? []).filter((k) => k.secili).map((k) => k.onek))
    if (secili.has(onek)) secili.delete(onek)
    else secili.add(onek)
    sec({ kural: [...secili].join(",") || "-", ilce: "", saha: "" })
  }

  /** Kural setini kaydeder (yalniz yonetici; "Diger" sabit, gonderilmez) ve verilen secimle yeniden cizer. */
  async function kurallariKaydet(kurallar: Pick<CizimKurali, "onek" | "ad" | "ciz" | "sabit">[], degisen?: Partial<EnvanterIstegi>) {
    try {
      await yaz("PUT", "/api/v1/topoloji/kurallar", { kurallar: kurallar.filter((k) => !k.sabit).map((k) => ({ onek: k.onek, ad: k.ad, ciz: k.ciz })) })
      sec(degisen ?? {})
    } catch (h) {
      window.alert(hataMesaji(h, "!"))
    }
  }

  /** Cizime giren CI sayisi, Urun-Tutar devre / adres eslesmesi ve elle duzeltilen lokasyonlar. */
  function envanterOzeti(a: Analiz) {
    const ut = a.urun_tutar || {}
    const parcalar = [`${t.envCizimde}: ${(a.cizime_giren ?? 0).toLocaleString(dil)} / ${a.satir.toLocaleString(dil)} CI`]
    if (ut.devre)
      parcalar.push(`${t.envUt}: ${ut.eslesen_devre} / ${ut.devre} ${t.envUtDevre} (${ut.eslesen_ci} CI)` + (ut.il_farkli ? ` · ${ut.il_farkli} ${t.envUtFarkli}` : ""))
    else if (!ut.yuklu) parcalar.push(t.envUtYok)
    if (a.duzeltilen_ci) parcalar.push(`${t.envDuzeltilen}: ${a.duzeltilen_ci}`)
    return parcalar.join(" · ")
  }

  const secilenIl = v?.adres_agaci?.find((x) => x.il === v.secim?.il)
  const secilenIlce = secilenIl?.ilceler.find((x) => x.ilce === v?.secim?.ilce)

  return (
    <div className="grid grid-cols-1 gap-4">
      <SayfaKabi ikon={Network} baslik={t.baslik} aciklama={t.aciklama} />
      {kart.isError ? <HataKutu metin={hataMesaji(kart.error, t.musteriHata)} /> : (
        <Bildirim>{t.musteri}: <strong>{kart.data?.kimlik.unvan ?? t.musteriYukleniyor}</strong></Bildirim>
      )}
      <Panel>
        <form onSubmit={gonder} className="flex flex-wrap items-end gap-3">
          <Alan etiket={t.dosya} ipucu={t.dosyaIpucu} sinif="min-w-[16rem] flex-1">
            <input type="file" accept=".csv,.xlsx" className={GIRDI} onChange={(e) => setDosya(e.target.files?.[0] ?? null)} />
          </Alan>
          <button type="submit" className={DUGME_SARI} disabled={m.isPending || kart.isPending || kart.isError}>
            <Upload aria-hidden className="size-4" />
            {t.baslat}
          </button>
        </form>
        <form onSubmit={envanterCiz} className="mt-3 flex flex-wrap items-end gap-3 border-t border-slate-100 pt-3">
          <Alan etiket={t.envanterEtiket} ipucu={t.envanterIpucu} sinif="min-w-[16rem] flex-1">
            <input type="search" className={GIRDI} placeholder={t.envanterAra} value={envanterAra} maxLength={200} onChange={(e) => setEnvanterAra(e.target.value)} />
          </Alan>
          <button type="submit" className={DUGME_SARI} disabled={envanter.isPending || kart.isPending || kart.isError}>
            <Network aria-hidden className="size-4" />
            {t.envanterCiz}
          </button>
        </form>
        {v && v.adres_agaci ? (
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <Alan etiket={t.envIl} sinif="min-w-48">
              <select className={GIRDI} disabled={envanter.isPending} value={v.secim!.il} onChange={(e) => sec({ il: e.target.value, ilce: "", saha: "" })}>
                {v.adres_agaci.map((x) => (
                  <option key={x.il} value={x.il}>{`${x.il} (${x.ci})`}</option>
                ))}
              </select>
            </Alan>
            <Alan etiket={t.envIlce} sinif="min-w-48">
              <select className={GIRDI} disabled={envanter.isPending || !secilenIl} value={v.secim!.ilce} onChange={(e) => sec({ ilce: e.target.value, saha: "" })}>
                <option value="">{t.envTumIlceler}</option>
                {(secilenIl?.ilceler ?? []).map((x) => (
                  <option key={x.ilce} value={x.ilce}>{`${x.ilce} (${x.ci})`}</option>
                ))}
              </select>
            </Alan>
            <Alan etiket={t.envSaha} sinif="min-w-[16rem] flex-1">
              <select className={GIRDI} disabled={envanter.isPending || !secilenIlce} value={v.secim!.saha} onChange={(e) => sec({ saha: e.target.value })}>
                <option value="">{secilenIlce ? t.envTumSahalar : t.envOnceIlce}</option>
                {(secilenIlce?.sahalar ?? []).map((x) => (
                  <option key={x.anahtar} value={x.anahtar} title={x.adres}>{`${x.baslik} (${x.ci})`}</option>
                ))}
              </select>
            </Alan>
          </div>
        ) : null}
        {v && v.kurallar ? (
          <div className="mt-3 grid gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-black text-tl-navy" title={t.envKuralIpucu}>
                {t.envKural}
              </span>
              {...v.kurallar
                .filter((k) => k.ci > 0 || v.kural_duzenler)
                .map((k) => (
                  <span
                    key={k.onek}
                    className="flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-bold"
                    style={k.secili ? { borderColor: "#003DA5", background: "#EEF4FF", color: "#003DA5" } : { borderColor: "#CBD5E1", color: "#64748B" }}
                    title={k.sabit ? t.envKuralDiger : `${k.onek}*`}
                  >
                    <label className="flex cursor-pointer items-center gap-1.5">
                      <input type="checkbox" checked={k.secili} disabled={envanter.isPending} onChange={() => kuralSec(k.onek)} />
                      {`${k.ad} (${k.ci.toLocaleString(dil)})`}
                    </label>
                    {v.kural_duzenler && !k.sabit ? (
                      <button
                        type="button"
                        aria-label={`${t.envKuralSil}: ${k.onek}`}
                        title={t.envKuralSil}
                        disabled={envanter.isPending}
                        onClick={() =>
                          void kurallariKaydet(
                            v.kurallar!.filter((x) => x.onek !== k.onek),
                            { kural: v.kurallar!.filter((x) => x.secili && x.onek !== k.onek).map((x) => x.onek).join(",") || "-" },
                          )
                        }
                        className="font-black"
                        style={{ color: "#94A3B8" }}
                      >
                        ×
                      </button>
                    ) : null}
                  </span>
                ))}
            </div>
            {v.kural_duzenler ? (
              <div className="flex flex-wrap items-center gap-2">
                <input className={GIRDI} style={{ width: "10rem" }} placeholder={t.envKuralOnek} aria-label={t.envKuralOnek} value={yeniOnek} maxLength={40} onChange={(e) => setYeniOnek(e.target.value)} />
                <input className={GIRDI} style={{ width: "13rem" }} placeholder={t.envKuralAd} aria-label={t.envKuralAd} value={yeniKuralAdi} maxLength={40} onChange={(e) => setYeniKuralAdi(e.target.value)} />
                <button
                  type="button"
                  className={DUGME_SARI}
                  disabled={envanter.isPending || !yeniOnek.trim()}
                  onClick={() => {
                    const onek = yeniOnek.trim().toLowerCase()
                    void kurallariKaydet([...v.kurallar!, { onek, ad: yeniKuralAdi.trim() || onek, ciz: true }], {
                      kural: [...v.kurallar!.filter((x) => x.secili).map((x) => x.onek), onek].join(","),
                    })
                    setYeniOnek("")
                    setYeniKuralAdi("")
                  }}
                >
                  {t.envKuralEkle}
                </button>
                <button
                  type="button"
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-bold text-tl-navy"
                  disabled={envanter.isPending}
                  onClick={() => void kurallariKaydet(v.kurallar!.map((x) => ({ ...x, ciz: x.secili })))}
                >
                  {t.envKuralKaydet}
                </button>
              </div>
            ) : null}
            <p className="text-xs font-bold text-slate-500">{envanterOzeti(v)}</p>
          </div>
        ) : null}
        {uyari ? (
          <div className="mt-3">
            <Bildirim ton="amber">{uyari}</Bildirim>
          </div>
        ) : null}
      </Panel>

      {sonuc.isPending ? (
        <Panel>
          <Yukleniyor metin={t.hesaplaniyor} />
        </Panel>
      ) : sonuc.isError ? (
        <HataKutu metin={hataMesaji(sonuc.error, t.hata)} />
      ) : v ? (
        <>
          {v.spof ? (
            <section role="alert" className="rounded-xl border border-rose-200 border-l-4 border-l-rose-500 bg-rose-50/50 p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-black text-rose-600">
                <TriangleAlert aria-hidden className="size-4" />
                {t.spofBaslik}
              </div>
              <p className="text-xs font-medium text-slate-600">{t.spofAciklama}</p>
              <ul className="mt-2 list-inside list-disc text-xs font-bold text-slate-700">
                {v.spof_noktalari.map((p) => (
                  <li key={`${p.lokasyon}|${p.neden}|${p.bb}`}>{t.spofSatir(p.lokasyon, p.neden, p.bb, p.devreler.join(", "))}</li>
                ))}
              </ul>
            </section>
          ) : (
            <Bildirim ton="yesil">{t.spofYok}</Bildirim>
          )}
          {v.uyarilar.length ? <Bildirim ton="amber">{v.uyarilar.join(" · ")}</Bildirim> : null}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Kpi etiket={t.satir} deger={sayi(v.satir)} />
            <Kpi etiket={t.lokasyon} deger={sayi(v.lokasyon)} ton="sari" />
            <Kpi etiket={t.cihaz} deger={sayi(v.dugumler.length - 1)} ton="gri" />
            <Kpi etiket={t.spof} deger={sayi(v.spof_noktalari.length)} ton={v.spof ? "kirmizi" : "yesil"} />
          </div>
          <Panel
            sag={
              <Sekmeler
                etiket={t.sekmeler}
                deger={sekme}
                onDegis={setSekme}
                secenekler={[
                  { id: "topoloji", etiket: t.sekmeTopoloji, ikon: Network },
                  { id: "harita", etiket: t.sekmeHarita, ikon: HaritaIkon, sayi: v.sehirler.length },
                ]}
              />
            }
            baslik={sekme === "topoloji" ? t.sekmeTopoloji : t.sekmeHarita}
          >
            {sekme === "topoloji" ? (
              <TopolojiCizimi veri={v} t={t} />
            ) : (
              <IlHaritasi
                veri={v}
                t={t}
                dil={dil}
                // Envanter ciziminde ile tiklamak o ili secip topolojiye doner.
                onIl={
                  v.kaynak === "envanter"
                    ? (il) => {
                        setSekme("topoloji")
                        sec({ il, ilce: "", saha: "" })
                      }
                    : undefined
                }
              />
            )}
            <p className="mt-3 text-[0.6875rem] font-bold text-slate-400">
              {t.eslesenKolonlar}:{" "}
              {Object.values(v.kolonlar).join(", ")}
            </p>
          </Panel>
        </>
      ) : (
        <Panel>
          <BosKutu ikon={Network} baslik={t.bekleniyor} aciklama={t.bekleniyorAciklama} />
        </Panel>
      )}
    </div>
  )
}
