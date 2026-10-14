import { useState } from "react"
import type { ReactNode } from "react"
import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { CalendarRange, FileSpreadsheet, ListChecks, Plus, Search, SearchX, Timer, TrendingUp, Upload, Users, Wallet, X } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { Alan, BosKutu, DUGME, DUGME_SARI, GIRDI, HataKutu, Kpi, Rozet, SayfaKabi } from "@/components/sayfa-ui"
import { Skeleton } from "@/components/ui/skeleton"
import { para, sayi } from "@/lib/bicim"
import { apiYolu } from "@/lib/http"
import { useGecikmeli } from "@/lib/kanca"
import { oku, sorguMetni } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"
import { Ayrinti } from "@/gelir-uretim/ayrinti"
import { DURUMLAR, FAYDALAR, PARALAR, TURLER, gelirUretimMetin } from "@/gelir-uretim/gelir-uretim-metin"
import type { Kayit, Liste, Para } from "@/gelir-uretim/gelir-uretim-metin"
import { IceAktar } from "@/gelir-uretim/ice-aktar"
import { KayitFormu } from "@/gelir-uretim/kayit-formu"
import { ANAHTAR, DURUM_TON, FaydaRozeti, TABAN, kisilerMetni, saatMetni, tarihAraligi, tutarMetni } from "@/gelir-uretim/ortak"
import type { Metin } from "@/gelir-uretim/ortak"

const SEMBOL: Record<Para, string> = { TRY: "₺", USD: "$", EUR: "€" }
/** KPI tutarlari tam sayi gosterilir (dar kutuya sigsin); kart ve ayrintida kurus da gorunur. */
const tamPara = (n: number, birim: Para) => `${sayi(Math.round(n))} ${SEMBOL[birim]}`

/** Tutar satirinin yazi boyu: en uzun satira gore secilir, 390 px'lik dar kutuda (yaklasik 140 px) simge alt satira kaymasin. */
const tutarBoyu = (uzunluk: number, satirSayisi: number) => {
  const boy = uzunluk <= 8 ? "text-2xl" : uzunluk <= 10 ? "text-xl" : uzunluk <= 11 ? "text-lg" : uzunluk <= 12 ? "text-base" : "text-sm"
  return satirSayisi > 1 && boy === "text-2xl" ? "text-xl" : boy
}

/** KPI degeri: para birimi basina bir satir, hepsi ayni boyda ve tek satirda. */
function ParaDegeri({ toplamlar }: { toplamlar: Partial<Record<Para, number>> }) {
  const satirlar = PARALAR.filter((p) => toplamlar[p] !== undefined).map((p) => tamPara(toplamlar[p] ?? 0, p))
  if (satirlar.length === 0) return <>—</>
  const boy = tutarBoyu(Math.max(...satirlar.map((s) => s.length)), satirlar.length)
  return (
    <span className="grid gap-1">
      {satirlar.map((s) => (
        <span key={s} className={`whitespace-nowrap ${boy}`}>
          {s}
        </span>
      ))}
    </span>
  )
}

/** "yillik 120.000 ₺ · tek seferlik 50.000 ₺" gibi ikincil gelir toplamlari. */
function digerGelirler(v: Liste["ozet"], t: Metin): string {
  const parca = (etiket: string, toplamlar: Partial<Record<Para, number>>) => {
    const metin = PARALAR.filter((p) => toplamlar[p] !== undefined)
      .map((p) => tamPara(toplamlar[p] ?? 0, p))
      .join(" + ")
    return metin ? `${etiket}: ${metin}` : ""
  }
  return [parca(t.donem_.yil, v.yillik_gelir), parca(t.donem_.tek_sefer, v.tek_seferlik_gelir)].filter(Boolean).join(" · ")
}

function KpiSeridi({ v, dil }: { v: Liste["ozet"] | undefined; dil: Dil }) {
  const t = gelirUretimMetin(dil)
  const suzulu = v !== undefined && v.is_sayisi !== v.toplam_is
  const diger = v ? digerGelirler(v, t) : ""
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Kpi
        sans
        etiket={t.kpiIs}
        deger={v ? sayi(v.is_sayisi) : "—"}
        ikon={ListChecks}
        ton="mavi"
        alt={
          v ? (
            <>
              {t.kpiIsAlt(v.durum_sayilari.devam, v.durum_sayilari.tamamlandi)}
              {suzulu ? <span className="block">{t.kpiIsSuzulu(v.toplam_is)}</span> : null}
            </>
          ) : undefined
        }
      />
      <Kpi sans etiket={t.kpiAylik} deger={v ? <ParaDegeri toplamlar={v.aylik_gelir} /> : "—"} ikon={Wallet} ton="yesil" alt={diger || undefined} />
      <Kpi sans etiket={t.kpiYilIci} deger={v ? (v.yil_ici_gelir > 0 ? <ParaDegeri toplamlar={{ TRY: v.yil_ici_gelir }} /> : "—") : "—"} ikon={CalendarRange} ton="sari" />
      <Kpi sans etiket={t.kpiSaat} deger={v ? sayi(v.aylik_saat) : "—"} ikon={Timer} ton="amber" alt={t.saatAy} />
    </div>
  )
}

/** Kart satiri (buton icinde oldugundan yalniz span): simge + metin; `kisalt` uzun notlari iki satira kirpar. */
function Bilgi({ ikon: Ikon, children, soluk = false, kisalt = false }: { ikon: LucideIcon; children: ReactNode; soluk?: boolean; kisalt?: boolean }) {
  return (
    <span className={`flex min-w-0 items-start gap-1.5 ${soluk ? "text-slate-500" : ""}`}>
      <Ikon aria-hidden className="mt-0.5 size-3.5 shrink-0 text-slate-400" />
      <span className={`min-w-0 break-words ${kisalt ? "line-clamp-2" : ""}`}>{children}</span>
    </span>
  )
}

function Kart({ k, dil, onSec }: { k: Kayit; dil: Dil; onSec: () => void }) {
  const t = gelirUretimMetin(dil)
  const tutar = tutarMetni(k, t)
  const saat = saatMetni(k.hours_per_month, t)
  const kisiler = kisilerMetni(
    k.people.map((p) => p.name),
    k.other_people,
  )
  // Sayiya cevrilemeyen tutar/efor bilgisi notta durur; kartta da (kirpilmis) gorunsun.
  const gelirMetni = tutar || k.revenue_note
  const eforMetni = saat || k.hours_note
  const faydaYok = !gelirMetni && !eforMetni && k.year_revenue === null
  return (
    <button
      type="button"
      onClick={onSec}
      aria-haspopup="dialog"
      className="group flex min-w-0 flex-col gap-2 rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-px hover:border-tl-blue/40 hover:shadow-md focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
    >
      <span className="flex flex-wrap items-center gap-1.5">
        <Rozet ton={k.kind === "inisiyatif" ? "sari" : "gri"}>{t.tur_[k.kind]}</Rozet>
        <Rozet ton={DURUM_TON[k.status]}>{t.durum_[k.status]}</Rozet>
        <FaydaRozeti fayda={k.benefit_type} dil={dil} />
      </span>
      <span className="break-words text-sm font-black leading-snug text-tl-navy">{k.title}</span>
      {k.customers ? <span className="line-clamp-2 break-words text-xs font-bold text-slate-500">{k.customers}</span> : null}
      <span className="mt-auto grid gap-1 border-t border-slate-100 pt-2 text-xs font-bold text-slate-600">
        {gelirMetni ? (
          <Bilgi ikon={Wallet} soluk={!tutar} kisalt={!tutar}>
            {gelirMetni}
          </Bilgi>
        ) : null}
        {k.year_revenue !== null ? <Bilgi ikon={CalendarRange}>{`${t.yilIciKisa}: ${para(k.year_revenue)}`}</Bilgi> : null}
        {eforMetni ? (
          <Bilgi ikon={Timer} soluk={!saat} kisalt={!saat}>
            {eforMetni}
          </Bilgi>
        ) : null}
        {faydaYok ? (
          <Bilgi ikon={Wallet} soluk>
            {t.tutarYok}
          </Bilgi>
        ) : null}
        <Bilgi ikon={CalendarRange}>{tarihAraligi(k, t)}</Bilgi>
        {kisiler ? <Bilgi ikon={Users}>{kisiler}</Bilgi> : null}
      </span>
    </button>
  )
}

type Form = { kayit: Kayit | null }

/** Gelir Faydasi Saglanan Isler: KPI seridi, suzgecler, is kartlari, ayrinti cekmecesi. Admin: yeni/duzenle/sil ve Excel'den ice aktarma. */
export function GelirUretimSayfasi({ dil, yazabilir }: { dil: Dil; yazabilir: boolean }) {
  const t = gelirUretimMetin(dil)
  const [arama, setArama] = useState("")
  const [tur, setTur] = useState("")
  const [durum, setDurum] = useState("")
  const [fayda, setFayda] = useState("")
  const [tam, setTam] = useState("")
  const [yil, setYil] = useState("")
  const [secili, setSecili] = useState<Kayit | null>(null)
  const [form, setForm] = useState<Form | null>(null)
  const [ice, setIce] = useState(false)
  const q = useGecikmeli(arama.trim())

  const sorgu = { q, tur, durum, fayda, tam, yil }
  const liste = useQuery({
    queryKey: [...ANAHTAR, sorgu],
    queryFn: () => oku<Liste>(`${TABAN}${sorguMetni(sorgu)}`),
    placeholderData: keepPreviousData,
  })
  const veri = liste.data
  const admin = veri?.yazabilir ?? yazabilir
  const filtreVar = Boolean(arama.trim() || tur || durum || fayda || tam || yil)

  function temizle() {
    setArama("")
    setTur("")
    setDurum("")
    setFayda("")
    setTam("")
    setYil("")
  }

  return (
    <div className="grid grid-cols-1 gap-4">
      <SayfaKabi ikon={TrendingUp} baslik={t.baslik} aciklama={t.aciklama}>
        {admin ? (
          <>
            <button type="button" className={DUGME_SARI} onClick={() => setForm({ kayit: null })}>
              <Plus aria-hidden className="size-4" />
              {t.yeniKayit}
            </button>
            <button type="button" className={DUGME} onClick={() => setIce(true)}>
              <Upload aria-hidden className="size-4" />
              {t.excelIceAktar}
            </button>
          </>
        ) : null}
        <a className={DUGME} href={apiYolu(`${TABAN}/excel`)} download>
          <FileSpreadsheet aria-hidden className="size-4" />
          {t.excelAktar}
        </a>
      </SayfaKabi>

      <KpiSeridi v={veri?.ozet} dil={dil} />

      <section aria-label={t.suzgecler} className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
        <div className="flex flex-wrap items-center gap-3">
          <label className="relative min-w-56 flex-1">
            <span className="sr-only">{t.ara}</span>
            <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
            <input type="search" value={arama} onChange={(e) => setArama(e.target.value)} placeholder={t.ara} maxLength={100} className={`${GIRDI} !py-2.5 pl-9`} />
          </label>
          {filtreVar ? (
            <button type="button" className={DUGME} onClick={temizle}>
              <X aria-hidden className="size-3.5" />
              {t.temizle}
            </button>
          ) : null}
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
          <Alan etiket={t.tur}>
            <select className={GIRDI} value={tur} onChange={(e) => setTur(e.target.value)}>
              <option value="">{t.tumTurler}</option>
              {TURLER.map((id) => (
                <option key={id} value={id}>
                  {t.tur_[id]}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t.durum}>
            <select className={GIRDI} value={durum} onChange={(e) => setDurum(e.target.value)}>
              <option value="">{t.tumDurumlar}</option>
              {DURUMLAR.map((id) => (
                <option key={id} value={id}>
                  {t.durum_[id]}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t.fayda}>
            <select className={GIRDI} value={fayda} onChange={(e) => setFayda(e.target.value)}>
              <option value="">{t.tumFaydalar}</option>
              {FAYDALAR.map((id) => (
                <option key={id} value={id}>
                  {t.fayda_[id]}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t.tam}>
            <select className={GIRDI} value={tam} onChange={(e) => setTam(e.target.value)}>
              <option value="">{t.tumTam}</option>
              {(veri?.secenekler.personel ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.ad}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t.yil}>
            <select className={GIRDI} value={yil} onChange={(e) => setYil(e.target.value)}>
              <option value="">{t.tumYillar}</option>
              {(veri?.secenekler.yillar ?? []).map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </Alan>
        </div>
        <p className="text-xs font-bold text-slate-400">
          {veri ? t.toplamKayit(veri.items.length) : ""}
          {yil ? ` · ${t.yilIpucu}` : ""}
        </p>
      </section>

      {liste.isPending ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-hidden>
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-44 rounded-2xl" />
          ))}
        </div>
      ) : liste.isError ? (
        <HataKutu metin={t.yuklenemedi} tekrar={() => void liste.refetch()} tekrarEtiket={t.tekrar} />
      ) : veri && veri.items.length === 0 ? (
        <BosKutu
          ikon={filtreVar ? SearchX : TrendingUp}
          baslik={filtreVar ? t.sonucYok : t.hicKayit}
          aciklama={filtreVar ? t.sonucYokAlt : admin ? t.hicKayitAlt : t.hicKayitAltOkur}
        />
      ) : veri ? (
        <div className={`grid gap-3 sm:grid-cols-2 xl:grid-cols-3 ${liste.isPlaceholderData ? "opacity-60" : ""}`}>
          {veri.items.map((k) => (
            <Kart key={k.id} k={k} dil={dil} onSec={() => setSecili(k)} />
          ))}
        </div>
      ) : null}

      {secili ? (
        <Ayrinti
          k={secili}
          dil={dil}
          yazabilir={admin}
          onKapat={() => setSecili(null)}
          onDuzenle={() => {
            setForm({ kayit: secili })
            setSecili(null)
          }}
        />
      ) : null}
      {admin && form ? <KayitFormu dil={dil} kayit={form.kayit} personel={veri?.secenekler.personel ?? []} onKapat={() => setForm(null)} /> : null}
      {admin && ice ? <IceAktar dil={dil} onKapat={() => setIce(false)} /> : null}
    </div>
  )
}
