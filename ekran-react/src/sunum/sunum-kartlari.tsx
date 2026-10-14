import { useId } from "react"
import type { ReactNode } from "react"
import { ChevronDown, ChevronUp } from "lucide-react"
import { Halka, Lejant } from "@/components/grafik"
import { BASLIK_BANDI, BASLIK_YAZISI, Kpi, VeriTablosu } from "@/components/sayfa-ui"
import { para, sayi } from "@/lib/bicim"
import { yerel } from "@/shell/metin"
import type { Dil } from "@/shell/metin"
import { sunumMetin } from "@/sunum/sunum-metin"
import { takvimMi, tanitimMi } from "@/sunum/sunum-tipleri"
import type { GenelVeri, Hucre, KpiVeri, Oge, TabloVeri, TakvimVeri } from "@/sunum/sunum-tipleri"
import { TakvimGrafigi, durumSerileri } from "@/takvim/takvim-grafigi"
import type { TakvimMetin } from "@/takvim/takvim-metin"

export const hucre = (v: Hucre | undefined, birim: string) => (v === null || v === undefined ? "—" : typeof v === "number" ? (birim ? para(v, birim) : sayi(v)) : v)
export const kpiDeger = (k: KpiVeri) => (k.birim ? para(k.deger, k.birim, true) : sayi(k.deger))
export const kpiAlt = (k: KpiVeri, dil: Dil) => (dil === "en" && k.alt_en ? k.alt_en : k.alt)

/** Kisa kartta gosterilecek bir sey yok mu: tum KPI'lar 0/bos (ya da takvimde kayitli gun yok). Boyle kaynaklar tek satirlik notta toplanir. */
export function bosMu(o: Oge): boolean {
  const v = o.veri
  if (o.durum === "hata" || !v || tanitimMi(v) || o.gonderen) return false // elle gonderilen oge her zaman kart olarak kalir (yonetici kaldirabilsin)
  if (takvimMi(o.kaynak, v)) return v.genel.kayitli_gun === 0 && v.genel.toplanti === 0
  return v.kpi.every((k) => !k.deger)
}

/** Ayrinti (acilir) bolumunun satir/kisi sayisi; 0 ise ayrinti dugmesi gosterilmez. */
export function ayrintiSayisi(o: Oge): number {
  const v = o.veri
  if (!v || tanitimMi(v)) return 0
  if (takvimMi(o.kaynak, v)) return v.uyeler.length
  return v.tablo?.satirlar.length ?? 0
}

/** Lacivert baslik bandinin ustunde okunur durum etiketi (Rozet acik zemin icindir). */
export function BantRozeti({ ton, children }: { ton: "yesil" | "sari" | "kirmizi" | "gri"; children: ReactNode }) {
  const sinif = { yesil: "bg-emerald-400 text-emerald-950", sari: "bg-tl-yellow text-tl-navy", kirmizi: "bg-rose-400 text-rose-950", gri: "bg-white/90 text-slate-600" }[ton]
  return <span className={`whitespace-nowrap rounded-md px-2 py-0.5 text-[0.625rem] font-black ${sinif}`}>{children}</span>
}

type KartProps = {
  baslik: string
  rozet: ReactNode
  /** altbilgide kisa durum (tarih / gonderen); uzun aciklamasi `zamanAciklama` olarak ipucunda */
  zaman: string
  zamanAciklama?: string
  eylem?: ReactNode
  /** acilir ayrinti: dugme etiketi ve icerik; yoksa dugme cikmaz */
  ayrinti?: { etiket: string; icerik: ReactNode }
  acik?: boolean
  onAc?: (acik: boolean) => void
  /** iki sutunu kaplar (Sayilarla TAM Ekibi, TAM Life tanitimi) */
  genis?: boolean
  /** baslik bandi yok: icerik kendi basligini cizer (TAM Life tanitimi); kabuk dolgu vermez */
  bantsiz?: boolean
  children: ReactNode
}

/** Sunumdaki her kaynagin ortak kabugu: lacivert baslik bandi + rozet, kisa icerik, altta Ayrinti dugmesi / zaman damgasi / yonetici dugmeleri. */
export function SunumKarti({ baslik, rozet, zaman, zamanAciklama, eylem, ayrinti, acik = false, onAc, genis = false, bantsiz = false, children }: KartProps) {
  const kimlik = useId()
  return (
    <section className={`flex min-w-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm ${genis ? "lg:col-span-2" : ""}`}>
      {bantsiz ? null : (
        <div className={`${BASLIK_BANDI} shrink-0 justify-between`}>
          <h3 className={`flex items-center gap-2 ${BASLIK_YAZISI}`}>
            <span aria-hidden className="h-4 w-1 shrink-0 rounded-full bg-tl-yellow" />
            {baslik}
          </h3>
          {rozet}
        </div>
      )}
      <div className={bantsiz ? "@container flex flex-1 flex-col" : "@container flex flex-1 flex-col gap-3 p-3 sm:p-4"}>{children}</div>
      {ayrinti && acik ? (
        <div id={kimlik} className="border-t border-slate-100 p-3 sm:p-4">
          {ayrinti.icerik}
        </div>
      ) : null}
      <footer className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-t border-slate-100 bg-slate-50/70 px-3 py-2 sm:px-4">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
          {ayrinti ? (
            <button
              type="button"
              aria-expanded={acik}
              aria-controls={kimlik}
              onClick={() => onAc?.(!acik)}
              className="inline-flex items-center gap-1 rounded-lg px-1.5 py-1 text-xs font-black text-tl-blue transition-colors hover:bg-tl-blue/10 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
            >
              {acik ? <ChevronUp aria-hidden className="size-4" /> : <ChevronDown aria-hidden className="size-4" />}
              {ayrinti.etiket}
            </button>
          ) : null}
          {zaman ? (
            <span className="text-[0.625rem] font-bold text-slate-400" title={zamanAciklama}>
              {zaman}
            </span>
          ) : null}
        </div>
        {eylem ? <div className="ml-auto flex flex-wrap items-center gap-2">{eylem}</div> : null}
      </footer>
    </section>
  )
}

/** Acilir ayrintidaki tam tablo: uzun listeler kendi kutusunda kayar, sayfa uzamaz. */
export function AyrintiTablosu({ tablo, dil, baslik }: { tablo: TabloVeri; dil: Dil; baslik: string }) {
  const t = sunumMetin(dil)
  return (
    <div className="flex max-h-72 flex-col">
      <VeriTablosu
        baslik={baslik}
        kolonlar={tablo.sutunlar.map((s, i) => ({ baslik: yerel(dil, s.ad, s.ad_en), hucre: (satir: Hucre[]) => hucre(satir[i], s.birim) }))}
        satirlar={tablo.satirlar}
        kaydirmali
        bos={<p className="text-xs font-bold text-slate-400">{t.tabloBos}</p>}
      />
    </div>
  )
}

/** Kisa kartin ilk satirlari (siralama, en cok kayit oluslar, segmentler): sunucunun onizleme ipucuna gore etiket + deger + oransal cubuk. */
function OnizlemeListesi({ tablo, dil }: { tablo: TabloVeri; dil: Dil }) {
  const o = tablo.onizleme
  if (!o || o.etiket === undefined || o.deger === undefined || tablo.satirlar.length === 0) return null
  const { etiket, deger } = o
  const satirlar = tablo.satirlar.slice(0, o.adet ?? 3)
  const sayisal = (h: Hucre | undefined) => (typeof h === "number" ? h : 0)
  const enBuyuk = o.tavan ?? Math.max(1, ...satirlar.map((s) => sayisal(s[deger])))
  const birim = tablo.sutunlar[deger]?.birim ?? ""
  const baslik = (i: number) => {
    const s = tablo.sutunlar[i]
    return s ? yerel(dil, s.ad, s.ad_en) : ""
  }
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-3 text-[0.625rem] font-black uppercase tracking-wide text-slate-400">
        <span>{baslik(etiket)}</span>
        <span>{baslik(deger)}</span>
      </div>
      <ol className="grid gap-1.5">
        {satirlar.map((s, i) => (
          <li key={i} className="grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-x-2 text-xs">
            {o.sira !== undefined ? (
              <span className="grid size-6 place-items-center rounded-full bg-tl-navy text-[0.625rem] font-black tabular-nums text-white">{hucre(s[o.sira], "")}</span>
            ) : (
              <span aria-hidden className="mx-auto size-2 rounded-full bg-tl-yellow" />
            )}
            <span className="min-w-0">
              <span className="block truncate font-bold text-slate-700">{hucre(s[etiket], "")}</span>
              <span aria-hidden className="mt-0.5 block h-1 overflow-hidden rounded-full bg-slate-100">
                <span className="block h-full rounded-full bg-tl-blue" style={{ width: `${Math.max(2, (sayisal(s[deger]) / enBuyuk) * 100)}%` }} />
              </span>
            </span>
            <span className="font-black tabular-nums text-tl-navy">{hucre(s[deger], birim)}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

/** Modul/rapor kaynaklarinin kisa icerigi: KPI karolari + (varsa) ilk satirlar. Tablonun tamami kartin Ayrinti bolumunde. */
export function GenelOzet({ veri, dil }: { veri: GenelVeri; dil: Dil }) {
  return (
    <>
      <div className={`grid grid-cols-2 gap-2 ${veri.kpi.length <= 4 ? "@sm:grid-cols-4" : "@sm:grid-cols-3"}`}>
        {veri.kpi.map((k) => (
          <Kpi key={k.kod || k.ad} kucuk sans etiket={yerel(dil, k.ad, k.ad_en)} deger={kpiDeger(k)} alt={kpiAlt(k, dil) || undefined} />
        ))}
      </div>
      {veri.tablo ? <OnizlemeListesi tablo={veri.tablo} dil={dil} /> : null}
    </>
  )
}

/** TAM Takvim'in kisa hali: izin/tatil halkasi + toplanti sayilari. Kisi bazinda grafik Ayrinti bolumunde. */
export function TakvimOzet({ veri, t }: { veri: TakvimVeri; t: TakvimMetin }) {
  const seriler = durumSerileri(t).filter((s) => s.anahtar !== "calisiyor")
  const izinToplam = seriler.reduce((a, s) => a + (veri.genel.durumlar[s.anahtar] ?? 0), 0)
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
      <Halka dilimler={seriler.map((s) => ({ anahtar: s.anahtar, ad: s.ad, deger: veri.genel.durumlar[s.anahtar] ?? 0, renk: s.renk }))} baslik={sayi(izinToplam)} alt={t.izinTatilGunu} boyut={128} kalinlik={16} />
      <div className="grid min-w-[11rem] flex-1 gap-3">
        <Lejant seriler={seriler.filter((s) => (veri.genel.durumlar[s.anahtar] ?? 0) > 0)} sayilar={veri.genel.durumlar} />
        <div className="grid grid-cols-2 gap-2">
          <Kpi kucuk sans etiket={t.toplantiOnline} deger={sayi(veri.genel.online)} />
          <Kpi kucuk sans etiket={t.toplantiYuzYuze} deger={sayi(veri.genel.yuzyuze)} ton="sari" />
        </div>
      </div>
    </div>
  )
}

export function TakvimAyrinti({ veri, t }: { veri: TakvimVeri; t: TakvimMetin }) {
  return <TakvimGrafigi genel={veri.genel} uyeler={veri.uyeler} t={t} />
}
