import { useId, useState } from "react"
import type { KeyboardEvent, ReactNode } from "react"
import { Check, Pencil, Plus, Trash2, X } from "lucide-react"
import { Bildirim, DUGME, GIRDI } from "@/components/sayfa-ui"
import { para, tarih } from "@/lib/bicim"

/**
 * Sade, satir ici duzenlenebilir tablo (ICT SMS ve APN ekranlari). Okuma: duz tablo. Ekle/Duzenle: satir giris alanlarina doner;
 * Enter kaydeder, Esc vazgecer. Dogrulama sunucuda; hata mesaji satirin altinda gosterilir.
 */

export type Kolon = {
  anahtar: string
  baslik: string
  tip: "metin" | "musteri" | "tarih" | "tutar" | "tutarPara"
  zorunlu?: boolean
  yer?: string
  /** metin/musteri icin azami uzunluk */
  azami?: number
  sag?: boolean
  /** okuma gorunumu (varsayilan: tipe gore bicim) */
  goster?: (satir: Record<string, unknown>) => ReactNode
}

export type Metinler = { ekle: string; kaydet: string; vazgec: string; duzenle: string; sil: string; silOnay: string; islemSutunu: string; hata: string; paraBirimi: string }

type Taslak = Record<string, string>
type Satir = { id: number } & Record<string, unknown>

const PARA_BIRIMLERI = ["TRY", "USD", "EUR"] as const

function bos(kolonlar: Kolon[]): Taslak {
  const t: Taslak = {}
  for (const k of kolonlar) {
    t[k.anahtar] = ""
    if (k.tip === "tutarPara") t.para_birimi = "TRY"
  }
  return t
}

function doldur(kolonlar: Kolon[], s: Satir): Taslak {
  const t = bos(kolonlar)
  for (const k of kolonlar) {
    const d = s[k.anahtar]
    t[k.anahtar] = d === null || d === undefined ? "" : String(d)
    if (k.tip === "tutarPara") t.para_birimi = String(s.para_birimi ?? "TRY")
  }
  return t
}

function okuma(k: Kolon, s: Satir): ReactNode {
  if (k.goster) return k.goster(s)
  const d = s[k.anahtar]
  if (k.tip === "tarih") return tarih(typeof d === "string" ? d : null)
  if (k.tip === "tutar") return para(typeof d === "number" ? d : null)
  if (k.tip === "tutarPara") return para(typeof d === "number" ? d : null, String(s.para_birimi ?? "TRY"))
  return d === null || d === undefined || d === "" ? "—" : String(d)
}

export function DuzenlenebilirTablo({
  kolonlar,
  satirlar,
  bosKutu,
  metin,
  musteriAdlari = [],
  onKaydet,
  onSil,
  alt,
  rowClass,
}: {
  kolonlar: Kolon[]
  satirlar: Satir[]
  bosKutu: ReactNode
  metin: Metinler
  musteriAdlari?: string[]
  onKaydet: (govde: Record<string, unknown>, id: number | null) => Promise<void>
  onSil: (id: number) => Promise<void>
  alt?: ReactNode
  rowClass?: (satir: Satir) => string
}) {
  const liste = useId()
  const [duzenle, setDuzenle] = useState<number | "yeni" | null>(null)
  const [taslak, setTaslak] = useState<Taslak>(() => bos(kolonlar))
  const [hata, setHata] = useState("")
  const [calisiyor, setCalisiyor] = useState(false)

  function ac(hedef: number | "yeni", s?: Satir) {
    setTaslak(s ? doldur(kolonlar, s) : bos(kolonlar))
    setHata("")
    setDuzenle(hedef)
  }
  async function kaydet() {
    setCalisiyor(true)
    setHata("")
    try {
      const govde: Record<string, unknown> = {}
      for (const k of kolonlar) govde[k.anahtar] = taslak[k.anahtar] === "" && k.tip !== "tutar" && k.tip !== "tutarPara" ? null : taslak[k.anahtar]
      if (kolonlar.some((k) => k.tip === "tutarPara")) govde.para_birimi = taslak.para_birimi
      await onKaydet(govde, duzenle === "yeni" ? null : duzenle)
      setDuzenle(null)
    } catch (e) {
      setHata(e instanceof Error && e.message ? e.message : metin.hata)
    } finally {
      setCalisiyor(false)
    }
  }
  async function sil(id: number) {
    if (!window.confirm(metin.silOnay)) return
    setHata("")
    try {
      await onSil(id)
    } catch (e) {
      setHata(e instanceof Error && e.message ? e.message : metin.hata)
    }
  }
  function tus(olay: KeyboardEvent) {
    if (olay.key === "Enter") {
      olay.preventDefault()
      void kaydet()
    } else if (olay.key === "Escape") setDuzenle(null)
  }
  const set = (a: string, d: string) => setTaslak((t) => ({ ...t, [a]: d }))

  function girdi(k: Kolon) {
    const ortak = { "aria-label": k.baslik, onKeyDown: tus, required: k.zorunlu, className: `${GIRDI} !py-1.5` }
    if (k.tip === "tarih") return <input type="date" {...ortak} value={taslak[k.anahtar] ?? ""} onChange={(e) => set(k.anahtar, e.target.value)} />
    if (k.tip === "tutar" || k.tip === "tutarPara")
      return (
        <span className="flex gap-1">
          <input inputMode="decimal" placeholder="0,00" {...ortak} className={`${GIRDI} !py-1.5 text-right font-mono`} value={taslak[k.anahtar] ?? ""} onChange={(e) => set(k.anahtar, e.target.value)} />
          {k.tip === "tutarPara" ? (
            <select aria-label={metin.paraBirimi} className={`${GIRDI} !w-20 !py-1.5`} value={taslak.para_birimi} onChange={(e) => set("para_birimi", e.target.value)} onKeyDown={tus}>
              {PARA_BIRIMLERI.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          ) : null}
        </span>
      )
    return (
      <input
        {...ortak}
        list={k.tip === "musteri" ? liste : undefined}
        maxLength={k.azami ?? 200}
        placeholder={k.yer}
        value={taslak[k.anahtar] ?? ""}
        onChange={(e) => set(k.anahtar, e.target.value)}
      />
    )
  }

  const duzenleniyor = (id: number) => duzenle === id
  const girisSatiri = (
    <>
      {kolonlar.map((k) => (
        <td key={k.anahtar} className="px-2 py-2 align-top">
          {girdi(k)}
        </td>
      ))}
      <td className="whitespace-nowrap px-2 py-2 text-right align-top">
        <button type="button" className={`${DUGME} !px-2`} onClick={() => void kaydet()} disabled={calisiyor} aria-label={metin.kaydet} title={metin.kaydet}>
          <Check aria-hidden className="size-4 text-emerald-600" />
        </button>{" "}
        <button type="button" className={`${DUGME} !px-2`} onClick={() => setDuzenle(null)} aria-label={metin.vazgec} title={metin.vazgec}>
          <X aria-hidden className="size-4" />
        </button>
      </td>
    </>
  )

  return (
    <div className="grid grid-cols-1 gap-3">
      <datalist id={liste}>
        {musteriAdlari.map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>
      <div className="flex justify-end">
        <button type="button" className={DUGME} onClick={() => ac("yeni")} disabled={duzenle === "yeni"}>
          <Plus aria-hidden className="size-3.5" />
          {metin.ekle}
        </button>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-left text-xs">
          <thead className="bg-tl-navy text-white">
            <tr>
              {kolonlar.map((k) => (
                <th key={k.anahtar} scope="col" className={`whitespace-nowrap px-3 py-2.5 font-black ${k.sag ? "text-right" : ""}`}>
                  {k.baslik}
                </th>
              ))}
              <th scope="col" className="w-24 px-3 py-2.5 text-right font-black">
                <span className="sr-only">{metin.islemSutunu}</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {duzenle === "yeni" ? <tr className="bg-tl-yellow/10">{girisSatiri}</tr> : null}
            {satirlar.map((s) =>
              duzenleniyor(s.id) ? (
                <tr key={s.id} className="bg-tl-yellow/10">
                  {girisSatiri}
                </tr>
              ) : (
                <tr key={s.id} className={`hover:bg-slate-50 ${rowClass?.(s) ?? ""}`}>
                  {kolonlar.map((k) => (
                    <td key={k.anahtar} className={`px-3 py-2.5 font-bold text-slate-700 ${k.sag ? "whitespace-nowrap text-right font-mono" : ""}`}>
                      {okuma(k, s)}
                    </td>
                  ))}
                  <td className="whitespace-nowrap px-3 py-2.5 text-right">
                    <button type="button" className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-tl-blue focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow" onClick={() => ac(s.id, s)} aria-label={`${metin.duzenle}`} title={metin.duzenle}>
                      <Pencil aria-hidden className="size-4" />
                    </button>
                    <button type="button" className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow" onClick={() => void sil(s.id)} aria-label={metin.sil} title={metin.sil}>
                      <Trash2 aria-hidden className="size-4" />
                    </button>
                  </td>
                </tr>
              ),
            )}
          </tbody>
          {alt ? <tfoot className="border-t-2 border-slate-200 bg-slate-50">{alt}</tfoot> : null}
        </table>
      </div>
      {satirlar.length === 0 && duzenle !== "yeni" ? bosKutu : null}
      {hata ? <Bildirim ton="kirmizi">{hata}</Bildirim> : null}
    </div>
  )
}
