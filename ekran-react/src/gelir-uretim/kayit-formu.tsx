import { useMemo, useState } from "react"
import type { ReactNode } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Cekmece } from "@/components/cekmece"
import { ALT_BASLIK_BANDI, ALT_BASLIK_YAZISI, Alan, Bildirim, DUGME, DUGME_ANA, GIRDI } from "@/components/sayfa-ui"
import { hataMesaji, yaz } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"
import { DONEMLER, DURUMLAR, FAYDALAR, PARALAR, TURLER, gelirUretimMetin } from "@/gelir-uretim/gelir-uretim-metin"
import type { Donem, Durum, Fayda, Kayit, Para, Tur } from "@/gelir-uretim/gelir-uretim-metin"
import { ANAHTAR, TABAN } from "@/gelir-uretim/ortak"
import type { Metin } from "@/gelir-uretim/ortak"

type Form = {
  kind: Tur
  benefit_type: Fayda
  title: string
  status: Durum
  status_note: string
  description: string
  customers: string
  revenue_amount: string
  revenue_currency: Para
  revenue_period: Donem
  revenue_note: string
  year_revenue: string
  hours_per_month: string
  hours_note: string
  extra_note: string
  start_date: string
  end_date: string
  other_people: string
  person_ids: number[]
}
/** Serbest metin ya da sayi/tarih girdisi olan alanlar (numaralandirmalar ayri secim kutusudur). */
type Serbest = "title" | "status_note" | "description" | "customers" | "revenue_amount" | "revenue_note" | "year_revenue" | "hours_per_month" | "hours_note" | "extra_note" | "start_date" | "end_date" | "other_people"

const FORM_ID = "gelir-uretim-formu"
/** Sunucu sinirlariyla ayni: tutar 1e13, saat 1e6. */
const AZAMI_TUTAR = 1e13
const AZAMI_SAAT = 1e6
const SAYI = /^\d+([.,]\d+)?$/

const sayiMetni = (n: number | null | undefined) => (n === null || n === undefined ? "" : String(n))

function baslangic(k: Kayit | null): Form {
  return {
    kind: k?.kind ?? "proje",
    benefit_type: k?.benefit_type ?? "gelir",
    title: k?.title ?? "",
    status: k?.status ?? "devam",
    status_note: k?.status_note ?? "",
    description: k?.description ?? "",
    customers: k?.customers ?? "",
    revenue_amount: sayiMetni(k?.revenue_amount),
    revenue_currency: k?.revenue_currency ?? "TRY",
    revenue_period: k?.revenue_period ?? "ay",
    revenue_note: k?.revenue_note ?? "",
    year_revenue: sayiMetni(k?.year_revenue),
    hours_per_month: sayiMetni(k?.hours_per_month),
    hours_note: k?.hours_note ?? "",
    extra_note: k?.extra_note ?? "",
    start_date: k?.start_date ?? "",
    end_date: k?.end_date ?? "",
    other_people: k?.other_people ?? "",
    person_ids: k?.people.map((p) => p.id) ?? [],
  }
}

/** Bos -> null; gecerli -> sayi; gecersiz (ya da sinir disi) -> undefined. Ondalik ayraci virgul de olabilir. */
function sayiOku(metin: string, azami: number): number | null | undefined {
  const s = metin.trim()
  if (s === "") return null
  if (!SAYI.test(s)) return undefined
  const n = Number(s.replace(",", "."))
  return Number.isFinite(n) && n <= azami ? n : undefined
}

function govdeKur(f: Form, t: Metin): { govde: Record<string, unknown> } | { hata: string } {
  if (!f.title.trim()) return { hata: t.baslikZorunlu }
  const tutar = sayiOku(f.revenue_amount, AZAMI_TUTAR)
  if (tutar === undefined) return { hata: t.sayiHata(t.gelirTutari) }
  const yilIci = sayiOku(f.year_revenue, AZAMI_TUTAR)
  if (yilIci === undefined) return { hata: t.sayiHata(t.yilIciAlani) }
  const saat = sayiOku(f.hours_per_month, AZAMI_SAAT)
  if (saat === undefined) return { hata: t.sayiHata(t.eforAlani) }
  if (f.start_date && f.end_date && f.end_date < f.start_date) return { hata: t.tarihHata }
  return {
    govde: {
      kind: f.kind,
      benefit_type: f.benefit_type,
      title: f.title.trim(),
      status: f.status,
      status_note: f.status_note,
      description: f.description,
      customers: f.customers,
      revenue_amount: tutar,
      revenue_currency: f.revenue_currency,
      revenue_period: f.revenue_period,
      revenue_note: f.revenue_note,
      year_revenue: yilIci,
      hours_per_month: saat,
      hours_note: f.hours_note,
      extra_note: f.extra_note,
      start_date: f.start_date || null,
      end_date: f.end_date || null,
      other_people: f.other_people,
      person_ids: f.person_ids,
    },
  }
}

function Bolge({ baslik, children }: { baslik: string; children: ReactNode }) {
  return (
    <section className="grid gap-3">
      <div className={`${ALT_BASLIK_BANDI} rounded-lg`}>
        <span aria-hidden className="h-3.5 w-1 shrink-0 rounded-full bg-tl-yellow" />
        <h4 className={ALT_BASLIK_YAZISI}>{baslik}</h4>
      </div>
      {children}
    </section>
  )
}

function Secim<T extends string>({ etiket, deger, secenekler, onDegis }: { etiket: string; deger: T; secenekler: { id: T; ad: string }[]; onDegis: (d: T) => void }) {
  return (
    <Alan etiket={etiket}>
      <select className={GIRDI} value={deger} onChange={(e) => onDegis(e.target.value as T)}>
        {secenekler.map((s) => (
          <option key={s.id} value={s.id}>
            {s.ad}
          </option>
        ))}
      </select>
    </Alan>
  )
}

type KisiSecenegi = { id: number; ad: string }

/** Yeni kayit (kayit = null) ya da duzenleme cekmecesi. Yalniz admin acar; sunucu da ayni kurali uygular. */
export function KayitFormu({ dil, kayit, personel, onKapat }: { dil: Dil; kayit: Kayit | null; personel: KisiSecenegi[]; onKapat: () => void }) {
  const t = gelirUretimMetin(dil)
  const qc = useQueryClient()
  const [f, setF] = useState<Form>(() => baslangic(kayit))
  const [uyari, setUyari] = useState("")
  const ayarla = <A extends keyof Form>(alan: A, deger: Form[A]) => setF((onceki) => ({ ...onceki, [alan]: deger }))
  const kaydet = useMutation({
    mutationFn: (govde: Record<string, unknown>) => (kayit ? yaz("PUT", `${TABAN}/${kayit.id}`, govde) : yaz("POST", TABAN, govde)),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ANAHTAR })
      onKapat()
    },
  })
  // Kayda onceden bagli olup artik etkin personel olmayanlar da listelenir (kaldirilabilsin); yeni pasif kisi secilemez.
  const kisiler = useMemo(() => {
    const liste: (KisiSecenegi & { pasif: boolean })[] = personel.map((p) => ({ ...p, pasif: false }))
    for (const p of kayit?.people ?? []) if (!liste.some((x) => x.id === p.id)) liste.push({ id: p.id, ad: p.name, pasif: true })
    return liste
  }, [personel, kayit])

  const girdi = (alan: Serbest, etiket: string, azami: number, ek: { sayisal?: boolean; tarih?: boolean } = {}) => (
    <Alan etiket={etiket}>
      <input
        type={ek.tarih ? "date" : "text"}
        inputMode={ek.sayisal ? "decimal" : undefined}
        autoComplete="off"
        className={GIRDI}
        maxLength={ek.tarih ? undefined : azami}
        value={f[alan]}
        onChange={(e) => ayarla(alan, e.target.value)}
      />
    </Alan>
  )
  const kutu = (alan: Serbest, etiket: string, azami: number, satir = 3) => (
    <Alan etiket={etiket}>
      <textarea className={`${GIRDI} font-normal`} rows={satir} maxLength={azami} value={f[alan]} onChange={(e) => ayarla(alan, e.target.value)} />
    </Alan>
  )

  return (
    <Cekmece
      acik
      genis
      onKapat={onKapat}
      baslik={kayit ? t.formDuzenle : t.formYeni}
      aciklama={t.formAciklama}
      kapatEtiketi={t.kapat}
      alt={
        <div className="grid gap-2">
          {uyari ? <Bildirim ton="amber">{uyari}</Bildirim> : null}
          {kaydet.isError ? <Bildirim ton="kirmizi">{hataMesaji(kaydet.error, t.kaydedilemedi)}</Bildirim> : null}
          <div className="flex flex-wrap items-center justify-end gap-2">
            <button type="button" className={DUGME} onClick={onKapat}>
              {t.vazgec}
            </button>
            <button type="submit" form={FORM_ID} className={DUGME_ANA} disabled={kaydet.isPending}>
              {t.kaydet}
            </button>
          </div>
        </div>
      }
    >
      <form
        id={FORM_ID}
        noValidate
        className="grid gap-5"
        onSubmit={(e) => {
          e.preventDefault()
          const sonuc = govdeKur(f, t)
          if ("hata" in sonuc) return setUyari(sonuc.hata)
          setUyari("")
          kaydet.mutate(sonuc.govde)
        }}
      >
        <Bolge baslik={t.grupGenel}>
          <div className="grid gap-3 sm:grid-cols-3">
            <Secim etiket={t.tur} deger={f.kind} onDegis={(d) => ayarla("kind", d)} secenekler={TURLER.map((id) => ({ id, ad: t.tur_[id] }))} />
            <Secim etiket={t.fayda} deger={f.benefit_type} onDegis={(d) => ayarla("benefit_type", d)} secenekler={FAYDALAR.map((id) => ({ id, ad: t.fayda_[id] }))} />
            <Secim etiket={t.durum} deger={f.status} onDegis={(d) => ayarla("status", d)} secenekler={DURUMLAR.map((id) => ({ id, ad: t.durum_[id] }))} />
          </div>
          {girdi("title", t.baslikAlani, 300)}
          {kutu("status_note", t.durumNotu, 4000, 2)}
          {kutu("description", t.aciklamaAlani, 8000, 4)}
          {girdi("customers", t.musterilerAlani, 500)}
          <div className="grid gap-3 sm:grid-cols-2">
            {girdi("start_date", t.baslangicAlani, 10, { tarih: true })}
            {girdi("end_date", t.bitisAlani, 10, { tarih: true })}
          </div>
          <p className="-mt-1 text-[0.625rem] font-bold text-slate-400">{t.bitisIpucu}</p>
        </Bolge>

        <Bolge baslik={t.gelirBilgisi}>
          <p className="-mt-1 text-[0.625rem] font-bold text-slate-400">{t.sayiIpucu}</p>
          <div className="grid gap-3 sm:grid-cols-3">
            {girdi("revenue_amount", t.gelirTutari, 20, { sayisal: true })}
            <Secim etiket={t.paraBirimi} deger={f.revenue_currency} onDegis={(d) => ayarla("revenue_currency", d)} secenekler={PARALAR.map((id) => ({ id, ad: t.para_[id] }))} />
            <Secim etiket={t.donem} deger={f.revenue_period} onDegis={(d) => ayarla("revenue_period", d)} secenekler={DONEMLER.map((id) => ({ id, ad: t.donem_[id] }))} />
          </div>
          {girdi("revenue_note", t.tutarNotu, 500)}
          {girdi("year_revenue", t.yilIciAlani, 20, { sayisal: true })}
        </Bolge>

        <Bolge baslik={t.verimlilikBilgisi}>
          <div className="grid gap-3 sm:grid-cols-2">
            {girdi("hours_per_month", t.eforAlani, 20, { sayisal: true })}
            {girdi("hours_note", t.eforNotu, 500)}
          </div>
          {kutu("extra_note", t.ekAlani, 4000, 3)}
        </Bolge>

        <Bolge baslik={t.personel}>
          <fieldset className="grid gap-1.5">
            <legend className="sr-only">{t.personel}</legend>
            {kisiler.length === 0 ? (
              <p className="text-xs font-bold text-slate-400">{t.personelYok}</p>
            ) : (
              <div className="grid max-h-52 gap-1 overflow-y-auto rounded-lg border border-slate-300 p-2 sm:grid-cols-2">
                {kisiler.map((p) => (
                  <label key={p.id} className="flex min-h-8 cursor-pointer items-center gap-2 rounded-md px-1.5 text-xs font-bold text-slate-700 hover:bg-slate-50">
                    <input
                      type="checkbox"
                      className="size-4 shrink-0 accent-tl-blue"
                      checked={f.person_ids.includes(p.id)}
                      onChange={(e) => ayarla("person_ids", e.target.checked ? [...f.person_ids, p.id] : f.person_ids.filter((x) => x !== p.id))}
                    />
                    <span className="min-w-0 break-words">{p.pasif ? `${p.ad} ${t.pasif}` : p.ad}</span>
                  </label>
                ))}
              </div>
            )}
            <span className="text-[0.625rem] font-bold text-slate-400">{t.personelIpucu}</span>
          </fieldset>
          {girdi("other_people", t.digerAlani, 300)}
          <p className="-mt-1 text-[0.625rem] font-bold text-slate-400">{t.digerIpucu}</p>
        </Bolge>
      </form>
    </Cekmece>
  )
}
