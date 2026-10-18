import { Fragment, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { FileSpreadsheet, FolderKanban, Pencil, Printer, Trash2 } from "lucide-react"
import { Bildirim, Bolum, DUGME, DUGME_ANA, GIRDI, HataKutu, SayfaKabi, Yukleniyor } from "@/components/sayfa-ui"
import { adaGoreSirala, zaman } from "@/lib/bicim"
import { apiYolu } from "@/lib/http"
import { hataMesaji, oku, sorguMetni, yaz } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"
import { DURUMLAR, KATEGORILER, ONCELIKLER, projeMetin } from "@/proje/proje-metin"
import type { Durum, Kategori, Oncelik } from "@/proje/proje-metin"

type Ozet = Record<Kategori, number> & { tam: string; kapanan: number; devam_eden: number; toplam: number }
type Aksiyon = { id: number; metin: string; yapan: string; zaman: string | null }
type Kalem = {
  id: number
  tam_id: number
  tam: string
  kategori: Kategori
  baslik: string
  aciklama: string
  durum: Durum
  oncelik: Oncelik
  baslangic: string | null
  hedef: string | null
  kapanis: string | null
  aksiyonlar: Aksiyon[]
}
type Ekran = { yonetici: boolean; kendi_id: number; varsayilan_sorumlu?: number; ozet: Ozet[]; genel_toplam: number; tamlar: { id: number; ad: string }[]; kalemler: Kalem[] }
type Musteri = { id: number; ad: string; tam: string; tam_id: number | null; istirak: boolean }
type Isaret = { yapildi: boolean; detay: string; guncelleyen: string; zaman: string | null }
type Calisma = { musteriler: Musteri[]; isaretler: Record<string, Partial<Record<Kategori, Isaret>>> }

const ANAHTAR = ["proje"] as const
const DURUM_RENK: Record<Durum, string> = {
  acik: "bg-blue-500/10 text-blue-700",
  devam: "bg-amber-500/10 text-amber-700",
  beklemede: "bg-slate-400/10 text-slate-600",
  kapandi: "bg-emerald-500/10 text-emerald-700",
}
const ONCELIK_RENK: Record<Oncelik, string> = {
  dusuk: "bg-slate-400/10 text-slate-600",
  orta: "bg-blue-500/10 text-blue-700",
  yuksek: "bg-amber-500/10 text-amber-700",
  kritik: "bg-rose-500/10 text-rose-700",
}
const ROZET_SECIM = "cursor-pointer rounded-md border-0 px-2 py-1 text-[0.6875rem] font-black outline-none focus-visible:ring-2 focus-visible:ring-tl-yellow"
const tarihTr = (iso: string | null) => (iso ? iso.split("-").reverse().join(".") : "")

function OzetTablosu({ v, dil }: { v: Ekran; dil: Dil }) {
  const t = projeMetin(dil)
  if (v.ozet.length === 0) return <p className="p-2 text-xs font-bold text-slate-400">{t.kayitYok}</p>
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full text-xs">
        <caption className="sr-only">{t.ozet}</caption>
        <thead className="bg-tl-navy text-white">
          <tr>
            <th scope="col" className="px-3 py-2 text-left font-black">
              {t.kolTam}
            </th>
            {KATEGORILER.map((k) => (
              <th key={k} scope="col" className="whitespace-nowrap px-3 py-2 text-center font-black">
                {t.kategoriKisa[k]}
              </th>
            ))}
            <th scope="col" className="px-3 py-2 text-center font-black">
              {t.kolKapanan}
            </th>
            <th scope="col" className="px-3 py-2 text-center font-black">
              {t.kolDevam}
            </th>
            <th scope="col" className="px-3 py-2 text-center font-black">
              {t.kolToplam}
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 font-bold text-slate-700">
          {v.ozet.map((d) => (
            <tr key={d.tam} className="hover:bg-slate-50">
              <td className="px-3 py-2 font-black text-tl-navy">{d.tam}</td>
              {KATEGORILER.map((k) => (
                <td key={k} className="px-3 py-2 text-center font-mono">
                  {d[k]}
                </td>
              ))}
              <td className="px-3 py-2 text-center font-mono text-emerald-700">{d.kapanan}</td>
              <td className="px-3 py-2 text-center font-mono text-amber-700">{d.devam_eden}</td>
              <td className="px-3 py-2 text-center font-mono font-black text-tl-navy">{d.toplam}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-tl-yellow bg-slate-50 font-black text-tl-navy">
            <td className="px-3 py-2">{t.genelToplam}</td>
            <td colSpan={KATEGORILER.length + 2} />
            <td className="px-3 py-2 text-center font-mono">{v.genel_toplam}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function YeniProje({ v, dil, kapat }: { v: Ekran; dil: Dil; kapat: () => void }) {
  const t = projeMetin(dil)
  const qc = useQueryClient()
  const [f, setF] = useState({ owner_id: v.varsayilan_sorumlu ?? v.kendi_id, category: "proje" as Kategori, priority: "orta" as Oncelik, target_date: "", title: "", description: "" })
  const [uyari, setUyari] = useState("")
  const ekle = useMutation({
    mutationFn: () => yaz("POST", "/api/v1/proje/kalem", { ...f, target_date: f.target_date || null }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ANAHTAR })
      kapat()
    },
  })
  return (
    <form
      className="mb-3 grid gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3"
      onSubmit={(e) => {
        e.preventDefault()
        if (!f.title.trim()) return setUyari(t.baslikZorunlu)
        setUyari("")
        ekle.mutate()
      }}
    >
      <div className="grid gap-2 sm:grid-cols-4">
        <select aria-label={t.sorumlu} className={GIRDI} value={f.owner_id} disabled={!v.yonetici} onChange={(e) => setF({ ...f, owner_id: Number(e.target.value) })}>
          {adaGoreSirala(v.tamlar, (k) => k.ad).map((k) => (
            <option key={k.id} value={k.id}>
              {k.ad}
            </option>
          ))}
        </select>
        <select aria-label={t.kategori} className={GIRDI} value={f.category} onChange={(e) => setF({ ...f, category: e.target.value as Kategori })}>
          {KATEGORILER.map((k) => (
            <option key={k} value={k}>
              {t.kategori_[k]}
            </option>
          ))}
        </select>
        <select aria-label={t.oncelik} className={GIRDI} value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value as Oncelik })}>
          {ONCELIKLER.map((k) => (
            <option key={k} value={k}>
              {t.oncelik_[k]}
            </option>
          ))}
        </select>
        <input aria-label={t.hedef} type="date" className={GIRDI} value={f.target_date} onChange={(e) => setF({ ...f, target_date: e.target.value })} />
      </div>
      <input aria-label={t.projeBasligi} className={GIRDI} maxLength={200} placeholder={t.projeBasligi} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
      <textarea aria-label={t.aciklamaAlani} className={`${GIRDI} font-normal`} rows={2} maxLength={5000} placeholder={t.aciklamaAlani} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
      <div className="flex flex-wrap items-center justify-end gap-2">
        {uyari ? <Bildirim ton="amber">{uyari}</Bildirim> : null}
        {ekle.isError ? <Bildirim ton="kirmizi">{hataMesaji(ekle.error, t.kaydedilemedi)}</Bildirim> : null}
        <button type="button" className={DUGME} onClick={kapat}>
          {t.vazgec}
        </button>
        <button type="submit" className={DUGME_ANA} disabled={ekle.isPending}>
          {t.kaydet}
        </button>
      </div>
    </form>
  )
}

function ProjeKalemi({ k, dil, yazabilir }: { k: Kalem; dil: Dil; yazabilir: boolean }) {
  const t = projeMetin(dil)
  const qc = useQueryClient()
  const [aksiyon, setAksiyon] = useState("")
  const yenile = () => void qc.invalidateQueries({ queryKey: ANAHTAR })
  const guncelle = useMutation({ mutationFn: (d: Partial<{ status: Durum; priority: Oncelik }>) => yaz("PATCH", `/api/v1/proje/kalem/${k.id}`, d), onSuccess: yenile })
  const ekle = useMutation({
    mutationFn: () => yaz("POST", `/api/v1/proje/kalem/${k.id}/aksiyon`, { metin: aksiyon }),
    onSuccess: () => {
      setAksiyon("")
      yenile()
    },
  })
  const sil = useMutation({ mutationFn: () => yaz("DELETE", `/api/v1/proje/kalem/${k.id}`), onSuccess: yenile })
  const hata = guncelle.error ?? ekle.error ?? sil.error

  return (
    <details className="group rounded-xl border border-slate-200 bg-white">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 px-3 py-2 hover:bg-slate-50 [&::-webkit-details-marker]:hidden">
        <span className="rounded-md bg-tl-navy/10 px-2 py-0.5 text-[0.625rem] font-black uppercase text-tl-navy">{t.kategori_[k.kategori] ?? k.kategori}</span>
        <span className="min-w-0 flex-1 truncate text-sm font-black text-tl-navy">{k.baslik}</span>
        <span className="text-[0.6875rem] font-bold text-slate-500">{k.tam}</span>
        {yazabilir ? (
          <select
            aria-label={`${t.durum}: ${k.baslik}`}
            className={`${ROZET_SECIM} ${DURUM_RENK[k.durum]}`}
            value={k.durum}
            disabled={guncelle.isPending}
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => guncelle.mutate({ status: e.target.value as Durum })}
          >
            {DURUMLAR.map((d) => (
              <option key={d} value={d}>
                {t.durum_[d]}
              </option>
            ))}
          </select>
        ) : (
          <span className={`${ROZET_SECIM} !cursor-default ${DURUM_RENK[k.durum]}`}>{t.durum_[k.durum]}</span>
        )}
        {yazabilir ? (
          <select
            aria-label={`${t.oncelik}: ${k.baslik}`}
            className={`${ROZET_SECIM} ${ONCELIK_RENK[k.oncelik]}`}
            value={k.oncelik}
            disabled={guncelle.isPending}
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => guncelle.mutate({ priority: e.target.value as Oncelik })}
          >
            {ONCELIKLER.map((d) => (
              <option key={d} value={d}>
                {t.oncelik_[d]}
              </option>
            ))}
          </select>
        ) : (
          <span className={`${ROZET_SECIM} !cursor-default ${ONCELIK_RENK[k.oncelik]}`}>{t.oncelik_[k.oncelik]}</span>
        )}
        {k.hedef ? <span className="font-mono text-[0.6875rem] font-bold text-slate-500" title={t.hedef}>🎯 {tarihTr(k.hedef)}</span> : null}
        {k.kapanis ? <span className="font-mono text-[0.6875rem] font-bold text-emerald-600" title={t.kapanis}>✓ {tarihTr(k.kapanis)}</span> : null}
        {yazabilir ? (
          <button
            type="button"
            aria-label={`${t.sil}: ${k.baslik}`}
            className="rounded-lg p-1.5 text-rose-500 hover:bg-rose-50 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
            disabled={sil.isPending}
            onClick={(e) => {
              e.preventDefault()
              if (window.confirm(t.silOnay(k.baslik))) sil.mutate()
            }}
          >
            <Trash2 aria-hidden className="size-3.5" />
          </button>
        ) : null}
      </summary>
      <div className="grid gap-2 border-t border-slate-100 px-3 py-3">
        {k.aciklama ? <p className="whitespace-pre-wrap text-xs text-slate-600">{k.aciklama}</p> : null}
        <ul className="grid gap-1">
          {k.aksiyonlar.map((a) => (
            <li key={a.id} className="flex flex-wrap gap-1.5 text-[0.6875rem]">
              <span className="font-mono text-slate-400">{zaman(a.zaman)}</span>
              <span className="font-black text-tl-navy">{a.yapan || "-"}:</span>
              <span className="text-slate-600">{a.metin}</span>
            </li>
          ))}
        </ul>
        {yazabilir ? (
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              if (aksiyon.trim()) ekle.mutate()
            }}
          >
            <input aria-label={`${t.aksiyonIpucu} ${k.baslik}`} className={`${GIRDI} font-normal`} maxLength={2000} placeholder={t.aksiyonIpucu} value={aksiyon} onChange={(e) => setAksiyon(e.target.value)} />
            <button type="submit" className={DUGME} disabled={ekle.isPending || !aksiyon.trim()}>
              {t.ekle}
            </button>
          </form>
        ) : null}
        {hata ? <Bildirim ton="kirmizi">{hataMesaji(hata, t.kaydedilemedi)}</Bildirim> : null}
      </div>
    </details>
  )
}

/** Uretim "Musteri Bazli Calismalar": kutu ve detay degisince aninda kaydedilir; Excel sunucuda, PDF tarayicinin yazdir penceresiyle. */
function MusteriCalismalari({ dil }: { dil: Dil }) {
  const t = projeMetin(dil)
  const qc = useQueryClient()
  const [tam, setTam] = useState("")
  const [ara, setAra] = useState("")
  const [acik, setAcik] = useState<Record<number, boolean>>({})
  const [durum, setDurum] = useState("")
  const q = useQuery({ queryKey: [...ANAHTAR, "musteri"], queryFn: () => oku<Calisma>("/api/v1/proje/musteri") })
  const kaydet = useMutation({
    mutationFn: (d: { id: number; kategori: Kategori; yapildi: boolean; detay: string }) =>
      yaz<{ zaman: string | null }>("PUT", `/api/v1/proje/musteri/${d.id}/${d.kategori}`, { yapildi: d.yapildi, detay: d.detay }),
    onMutate: () => setDurum(t.kaydediliyor),
    onSuccess: (r, d) => {
      setDurum(r.zaman ? t.kaydedildiZaman(zaman(r.zaman)) : t.kaydedildiZaman(""))
      qc.setQueryData<Calisma>([...ANAHTAR, "musteri"], (eski) => {
        if (!eski) return eski
        const mevcut = eski.isaretler[String(d.id)] ?? {}
        return { ...eski, isaretler: { ...eski.isaretler, [String(d.id)]: { ...mevcut, [d.kategori]: { yapildi: d.yapildi, detay: d.detay, guncelleyen: "", zaman: r.zaman } } } }
      })
    },
    onError: (e) => setDurum(`⚠ ${hataMesaji(e, t.kaydedilemedi)}`),
  })
  const v = q.data
  // Liste sunucuda cati, altinda istirakleri diye sirali: istirak catisinin TAM'iyla suzulur (uretim: rapor cati TAM'ina gore).
  const { catiTam, tamlar } = useMemo(() => {
    const catiTam = new Map<number, number | null>()
    const tamlar = new Map<number, string>()
    let son: number | null = null
    for (const m of v?.musteriler ?? []) {
      if (!m.istirak) son = m.tam_id
      catiTam.set(m.id, m.istirak ? son : m.tam_id)
      if (!m.istirak && m.tam_id) tamlar.set(m.tam_id, m.tam)
    }
    return { catiTam, tamlar: adaGoreSirala([...tamlar.entries()], (k) => k[1]) }
  }, [v])
  const aranan = ara.trim().toLocaleLowerCase("tr-TR")
  const gorunen = (v?.musteriler ?? []).filter((m) => (!tam || String(catiTam.get(m.id)) === tam) && (!aranan || m.ad.toLocaleLowerCase("tr-TR").includes(aranan)))
  const isaret = (id: number, k: Kategori) => v?.isaretler[String(id)]?.[k]

  function yazdir() {
    const pencere = window.open("", "_blank")
    if (!pencere || !v) return
    const kacis = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] ?? c)
    const yapilan = gorunen.reduce((n, m) => n + KATEGORILER.filter((k) => isaret(m.id, k)?.yapildi).length, 0)
    const satirlar = gorunen
      .map((m) => {
        const detay = KATEGORILER.filter((k) => isaret(m.id, k)?.detay).map((k) => `${t.kategori_[k]}: ${isaret(m.id, k)?.detay}`).join("; ")
        return `<tr><td>${m.istirak ? "&nbsp;&nbsp;↳ " : ""}${kacis(m.ad)}</td><td>${kacis(m.tam)}</td>${KATEGORILER.map((k) => `<td class="o">${isaret(m.id, k)?.yapildi ? "✓" : ""}</td>`).join("")}<td>${kacis(detay)}</td></tr>`
      })
      .join("")
    pencere.document.write(
      `<!doctype html><html lang="${dil}"><head><meta charset="utf-8"><title>${kacis(t.raporBaslik)}</title><style>body{font:11px 'Segoe UI',Arial,sans-serif;color:#243447;margin:16px}h1{font-size:16px;color:#002855;margin:0}p{color:#64748b;margin:4px 0 12px}table{border-collapse:collapse;width:100%}th{background:#002855;color:#fff;text-align:left}th,td{border:1px solid #cbd5e1;padding:4px 6px;vertical-align:top}td.o{text-align:center}@page{size:A4 landscape;margin:10mm}</style></head><body><h1>${kacis(t.raporBaslik)}</h1><p>${kacis(t.raporAlt(gorunen.length, yapilan))}</p><table><thead><tr><th>${kacis(t.kolMusteri)}</th><th>TAM</th>${KATEGORILER.map((k) => `<th>${kacis(t.kategoriKisa[k])}</th>`).join("")}<th>${kacis(t.kolDetay)}</th></tr></thead><tbody>${satirlar}</tbody></table></body></html>`,
    )
    pencere.document.close()
    pencere.focus()
    pencere.print()
  }

  if (q.isPending) return <Yukleniyor metin={t.yukleniyor} />
  if (q.isError) return <HataKutu metin={hataMesaji(q.error, t.yuklenemedi)} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
  return (
    <div className="grid gap-3">
      <p className="text-xs font-bold text-slate-500">{t.musteriCalismaAciklama}</p>
      <div className="flex flex-wrap items-center gap-2">
        {tamlar.length > 1 ? (
          <select aria-label={t.kolTam} className={`${GIRDI} !w-auto`} value={tam} onChange={(e) => setTam(e.target.value)}>
            <option value="">{t.tumPersonel}</option>
            {tamlar.map(([id, ad]) => (
              <option key={id} value={id}>
                {ad}
              </option>
            ))}
          </select>
        ) : null}
        <input type="search" aria-label={t.musteriAra} className={`${GIRDI} !w-56`} placeholder={t.musteriAra} value={ara} onChange={(e) => setAra(e.target.value)} />
        <span className="ml-auto flex gap-2">
          <a className={DUGME} href={apiYolu(`/api/v1/proje/rapor.xlsx${sorguMetni({ tam_id: tam })}`)} download>
            <FileSpreadsheet aria-hidden className="size-3.5" />
            {t.excel}
          </a>
          <button type="button" className={DUGME} onClick={yazdir}>
            <Printer aria-hidden className="size-3.5" />
            {t.yazdir}
          </button>
        </span>
      </div>
      <div className="max-h-[32rem] overflow-auto rounded-xl border border-slate-200">
        <table className="w-full text-xs">
          <caption className="sr-only">{t.musteriCalisma}</caption>
          <thead className="sticky top-0 bg-tl-navy text-white">
            <tr>
              <th scope="col" className="px-3 py-2 text-left font-black">
                {t.kolMusteri}
              </th>
              <th scope="col" className="px-3 py-2 text-left font-black">
                {t.kolTam}
              </th>
              {KATEGORILER.map((k) => (
                <th key={k} scope="col" className="whitespace-nowrap px-2 py-2 text-center font-black">
                  {t.kategoriKisa[k]}
                </th>
              ))}
              <th scope="col" className="px-3 py-2 text-center font-black">
                {t.kolDetay}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 font-bold text-slate-700">
            {gorunen.length === 0 ? (
              <tr>
                <td colSpan={KATEGORILER.length + 3} className="p-6 text-center text-slate-400">
                  {t.musteriYok}
                </td>
              </tr>
            ) : null}
            {gorunen.map((m) => {
              const detaySayisi = KATEGORILER.filter((k) => isaret(m.id, k)?.detay).length
              return (
                <Fragment key={m.id}>
                  <tr className="hover:bg-slate-50">
                    <td className={`px-3 py-1.5 ${m.istirak ? "pl-6 text-slate-500" : "font-black text-tl-navy"}`}>
                      {m.istirak ? `↳ ${m.ad}` : m.ad}
                    </td>
                    <td className="px-3 py-1.5 text-slate-500">{m.tam}</td>
                    {KATEGORILER.map((k) => (
                      <td key={k} className="px-2 py-1.5 text-center">
                        <input
                          type="checkbox"
                          aria-label={`${m.ad}: ${t.kategori_[k]}`}
                          className="size-4 cursor-pointer accent-tl-blue"
                          checked={Boolean(isaret(m.id, k)?.yapildi)}
                          onChange={(e) => kaydet.mutate({ id: m.id, kategori: k, yapildi: e.target.checked, detay: isaret(m.id, k)?.detay ?? "" })}
                        />
                      </td>
                    ))}
                    <td className="px-3 py-1.5 text-center">
                      <button type="button" className={`${DUGME} !px-2 !py-1`} aria-label={t.detayAc(m.ad)} aria-expanded={Boolean(acik[m.id])} onClick={() => setAcik({ ...acik, [m.id]: !acik[m.id] })}>
                        <Pencil aria-hidden className="size-3" />
                        {detaySayisi || ""}
                      </button>
                    </td>
                  </tr>
                  {acik[m.id] ? (
                    <tr className="bg-slate-50">
                      <td colSpan={KATEGORILER.length + 3} className="px-3 py-2">
                        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
                          {KATEGORILER.map((k) => (
                            <label key={k} className="grid gap-1">
                              <span className="text-[0.625rem] font-black uppercase text-slate-500">{t.kategori_[k]}</span>
                              <textarea
                                rows={2}
                                maxLength={2000}
                                className={`${GIRDI} font-normal`}
                                defaultValue={isaret(m.id, k)?.detay ?? ""}
                                onBlur={(e) => {
                                  if (e.target.value !== (isaret(m.id, k)?.detay ?? "")) kaydet.mutate({ id: m.id, kategori: k, yapildi: Boolean(isaret(m.id, k)?.yapildi), detay: e.target.value })
                                }}
                              />
                            </label>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
      <span role="status" className="text-[0.6875rem] font-bold text-slate-500">
        {durum}
      </span>
    </div>
  )
}

/** Takip Edilen Projeler (uretim projeModal): TAM ozeti, Jira/ITIL tarzi proje detay takibi ve musteri bazli calismalar. */
export function ProjeSayfasi({ dil, yazabilir }: { dil: Dil; yazabilir: boolean }) {
  const t = projeMetin(dil)
  const [form, setForm] = useState(false)
  const q = useQuery({ queryKey: ANAHTAR, queryFn: () => oku<Ekran>("/api/v1/proje") })
  const v = q.data

  return (
    <div className="grid grid-cols-1 gap-4">
      <SayfaKabi ikon={FolderKanban} baslik={t.baslik} aciklama={t.aciklama} />
      {q.isPending ? (
        <Yukleniyor metin={t.yukleniyor} />
      ) : q.isError ? (
        <HataKutu metin={hataMesaji(q.error, t.yuklenemedi)} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
      ) : v ? (
        <>
          <Bolum anahtar="proje-ozet" baslik={t.ozet}>
            <OzetTablosu v={v} dil={dil} />
          </Bolum>
          <Bolum anahtar="proje-detay" baslik={t.detayTakibi}>
            {yazabilir ? (
              <div className="mb-2 flex justify-end">
                <button type="button" className={DUGME_ANA} aria-expanded={form} onClick={() => setForm(!form)}>
                  {t.yeniProje}
                </button>
              </div>
            ) : null}
            {yazabilir && form ? <YeniProje v={v} dil={dil} kapat={() => setForm(false)} /> : null}
            <div className="grid gap-2">
              {v.kalemler.length === 0 ? <p className="p-2 text-xs font-bold text-slate-400">{t.kayitYok}</p> : null}
              {v.kalemler.map((k) => (
                <ProjeKalemi key={k.id} k={k} dil={dil} yazabilir={yazabilir} />
              ))}
            </div>
          </Bolum>
        </>
      ) : null}
      <Bolum anahtar="proje-musteri" baslik={t.musteriCalisma}>
        <MusteriCalismalari dil={dil} />
      </Bolum>
    </div>
  )
}
