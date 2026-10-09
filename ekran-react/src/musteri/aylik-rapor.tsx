import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import type { FormEvent, ReactNode } from "react"
import { ApiHata, oku, yaz } from "@/lib/sorgu"
import { Bos, DUGME, DUGME_ANA, DUGME_SARI, GIRDI, Rozet } from "@/components/sayfa-ui"
import type { Dil } from "@/shell/metin"
import { musteriMetin } from "@/musteri/musteri-metin"

type Gonderim = { id: number; yil: number; ay: number; gonderen: string; zaman: string; konu: string; durum: string; pdf: boolean; geri_alan: string | null }
type Taslak = {
  yil: number
  ay: number
  birim: boolean
  alanlar: Record<string, string>
  kayitli: boolean
  guncelleyen: string | null
  zaman: string | null
  alicilar: { kime: string; bilgi: string }
  gonderim: Gonderim | null
}

/** Eski aylik rapor sayfasinin renkli etiketleri: olumlu (teal), devam (lacivert), kritik (kirmizi), bilgi (mavi), oneri (yesil). */
const METINLER = [
  { alan: "olumlu", renk: "text-teal-600", satir: 3, uzun: 10000 },
  { alan: "devam", renk: "text-tl-navy", satir: 3, uzun: 10000 },
  { alan: "kritik", renk: "text-rose-600", satir: 3, uzun: 10000 },
  { alan: "bilgi", renk: "text-blue-600", satir: 7, uzun: 20000 },
  { alan: "oneri", renk: "text-emerald-600", satir: 7, uzun: 20000 },
] as const

function Kart({ children, ek = "" }: { children: ReactNode; ek?: string }) {
  return <div className={`rounded-2xl border border-slate-200 bg-white p-6 shadow-sm ${ek}`}>{children}</div>
}

function Baslik({ baslik, alt }: { baslik: string; alt?: string }) {
  return (
    <div className="flex min-w-0 items-start gap-2">
      <span aria-hidden className="mt-1 h-5 w-1 shrink-0 rounded-full bg-tl-yellow" />
      <div className="min-w-0">
        <h3 className="text-base font-black text-tl-navy">{baslik}</h3>
        {alt ? <p className="mt-0.5 text-xs text-slate-500">{alt}</p> : null}
      </div>
    </div>
  )
}

function dosyaOku(dosya: File): Promise<string> {
  return new Promise((coz, reddet) => {
    const okuyucu = new FileReader()
    okuyucu.onload = () => coz(String(okuyucu.result))
    okuyucu.onerror = () => reddet(new Error("okunamadi"))
    okuyucu.readAsDataURL(dosya)
  })
}

/** Musteri kartinin arkasindaki aylik rapor: sol 2/3 rapor formu, sag 1/3 gecmis ve alicilar (eski panel duzeni). */
export function AylikRapor({ musteriId, dil, geriAlabilir }: { musteriId: number; dil: Dil; geriAlabilir: boolean }) {
  const t = musteriMetin(dil)
  const taban = `/api/v1/musteri/${musteriId}/rapor`
  const taslakQ = useQuery({ queryKey: ["musteri", "rapor", musteriId, "taslak"], queryFn: () => oku<Taslak>(`${taban}/taslak`) })
  const gecmisQ = useQuery({ queryKey: ["musteri", "rapor", musteriId, "gecmis"], queryFn: () => oku<Gonderim[]>(`${taban}/gecmis`) })
  const taslak = taslakQ.data
  const gecmis = gecmisQ.data ?? []
  const [alanlar, setAlanlar] = useState<Record<string, string>>({})
  const [alici, setAlici] = useState({ kime: "", bilgi: "" })
  const [pdf, setPdf] = useState<File | null>(null)
  const [mesaj, setMesaj] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!taslak) return
    setAlanlar(taslak.alanlar)
    setAlici({ kime: taslak.alicilar.kime, bilgi: taslak.alicilar.bilgi })
  }, [taslak])

  const yukle = () => Promise.all([taslakQ.refetch(), gecmisQ.refetch()])
  const bildir = (anahtar: string, metin: string) => setMesaj((m) => ({ ...m, [anahtar]: metin }))
  /** Sonucu ilgili alana yazar; `kilit`: 409 (gonderilmis donem) icin ozel mesaj. */
  async function dene(anahtar: string, istek: () => Promise<unknown>, basari: string, kilit = false): Promise<boolean> {
    try {
      await istek()
      bildir(anahtar, basari)
      return true
    } catch (h) {
      bildir(anahtar, kilit && h instanceof ApiHata && h.durum === 409 ? t.gonderimKilitli : `${t.kaydedilemedi}: ${(h as Error).message}`)
      return false
    }
  }

  if (taslakQ.isPending) return <p className="text-sm text-muted-foreground">…</p>
  if (!taslak) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t.yuklenemedi}
      </p>
    )
  }
  const ingilizce = (alanlar.dil ?? "tr") === "en"

  async function taslagiKaydet(olay?: FormEvent) {
    olay?.preventDefault()
    if (await dene("taslak", () => yaz("PUT", `${taban}/taslak`, { alanlar }), t.kaydedildi, true)) await yukle()
  }

  async function alicilariKaydet(olay: FormEvent) {
    olay.preventDefault()
    await dene("alici", () => yaz("PUT", `${taban}/alicilar`, alici), t.kaydedildi)
  }

  async function gonder() {
    if (!window.confirm(t.gonderOnay)) return
    let pdfVeri: string | undefined
    if (pdf) {
      try {
        pdfVeri = await dosyaOku(pdf)
      } catch {
        bildir("gonder", t.kaydedilemedi)
        return
      }
    }
    await dene("gonder", () => yaz("POST", `${taban}/gonder`, { onay: true, subject: alanlar.konu, ...(pdfVeri ? { pdf_base64: pdfVeri } : {}) }), t.gonderildi, true)
    setPdf(null)
    await yukle()
  }

  async function geriAl(id: number) {
    if (!window.confirm(t.geriAlOnay)) return
    await dene("gecmis", () => yaz("POST", `/api/v1/rapor/gonderim/${id}/geri-al`), "")
    await yukle()
  }

  const alanYaz = (anahtar: string, deger: string) => setAlanlar((a) => ({ ...a, [anahtar]: deger }))
  const g = taslak.gonderim

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      {/* SOL KOLON: rapor formu */}
      <div className="space-y-6 lg:col-span-2">
        <Kart ek="space-y-6">
          <div className="space-y-3 border-b border-slate-100 pb-4">
            <Baslik baslik={t.raporIcerigi} alt={t.raporAltBasligi} />
            {g ? (
              <div role="status" className="flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded-xl border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-800">
                <span>✓ {t.buAyGonderildi}</span>
                <span className="font-mono">{g.zaman.slice(0, 16).replace("T", " ")}</span>
                <span>· {g.gonderen || "-"}</span>
                <span className="font-semibold text-emerald-700/80 sm:ml-auto">{t.aydaTek}</span>
              </div>
            ) : null}
            {!taslak.birim ? <p className="rounded-xl border bg-slate-50 p-3 text-xs text-slate-600">{t.rapordaBirimDegil}</p> : null}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <label className="flex cursor-pointer select-none items-center gap-2">
                <input type="checkbox" className="size-4 accent-tl-navy" disabled={!!g} checked={ingilizce} onChange={(ev) => alanYaz("dil", ev.target.checked ? "en" : "tr")} />
                <span className="text-xs font-black text-tl-navy">{t.ingilizceRapor}</span>
              </label>
              <div className="ml-auto flex items-center gap-2">
                <button type="button" className={`${DUGME} border-tl-navy/30 font-black`} disabled={!!g} onClick={() => void taslagiKaydet()}>
                  {t.taslagiKaydet}
                </button>
                <button type="button" className={DUGME_SARI} disabled={!!g} onClick={() => void gonder()}>
                  {t.gonder}
                </button>
              </div>
            </div>
            <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
              <span role="status" className="min-h-[14px] text-[10px] font-bold text-slate-400">
                {mesaj.taslak || mesaj.gonder || (taslak.kayitli ? `${t.taslakBilgi}: ${(taslak.zaman ?? "").slice(0, 16).replace("T", " ")} · ${taslak.guncelleyen ?? ""}` : "")}
              </span>
              <p className="text-[10px] font-bold text-slate-400 sm:max-w-[60%] sm:text-right">{t.emlNot}</p>
            </div>
          </div>

          <form onSubmit={taslagiKaydet} className="space-y-5 text-xs font-bold" aria-label={t.raporIcerigi}>
            <div className="space-y-3 rounded-xl border border-tl-blue/20 bg-slate-50 p-4">
              <p className="text-[10px] font-black uppercase tracking-wider text-tl-navy">{t.mailBlogu}</p>
              <div className="grid gap-1.5">
                <label htmlFor="r-konu" className="text-[10px] font-extrabold uppercase tracking-wider text-tl-navy">
                  {t.konu}
                </label>
                <input id="r-konu" disabled={!!g} maxLength={200} value={alanlar.konu ?? ""} onChange={(ev) => alanYaz("konu", ev.target.value)} className={GIRDI} />
              </div>
              <div className="grid gap-1.5">
                <label htmlFor="r-govde" className="text-[10px] font-extrabold uppercase tracking-wider text-tl-navy">
                  {t.govde}
                </label>
                <textarea id="r-govde" rows={8} maxLength={10000} disabled={!!g} value={alanlar.govde ?? ""} onChange={(ev) => alanYaz("govde", ev.target.value)} className={GIRDI} />
              </div>
              <div className="grid gap-1.5">
                <label htmlFor="r-imza" className="text-[10px] font-extrabold uppercase tracking-wider text-tl-navy">
                  {t.imza}
                </label>
                <textarea id="r-imza" rows={3} maxLength={2000} disabled={!!g} value={alanlar.imza ?? ""} onChange={(ev) => alanYaz("imza", ev.target.value)} className={GIRDI} />
              </div>
            </div>

            {METINLER.map((m) => (
              <div key={m.alan} className="space-y-1.5">
                <label htmlFor={`r-${m.alan}`} className={`flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-wider ${m.renk}`}>
                  <span aria-hidden className="size-1.5 rounded-full bg-current" />
                  {t[m.alan]}
                </label>
                <textarea id={`r-${m.alan}`} rows={m.satir} maxLength={m.uzun} disabled={!!g} value={alanlar[m.alan] ?? ""} onChange={(ev) => alanYaz(m.alan, ev.target.value)} className={GIRDI} />
              </div>
            ))}
          </form>

          {!g ? (
            <div className="grid gap-1.5 border-t border-slate-100 pt-4 sm:max-w-sm">
              <label htmlFor="r-pdf" className="text-[10px] font-extrabold uppercase tracking-wider text-tl-navy">
                {t.pdfEkle}
              </label>
              <input id="r-pdf" type="file" accept="application/pdf" onChange={(ev) => setPdf(ev.target.files?.[0] ?? null)} className={GIRDI} />
            </div>
          ) : null}
        </Kart>
      </div>

      {/* SAG KOLON: gecmis ve alicilar */}
      <div className="space-y-6">
        <Kart ek="space-y-3">
          <Baslik baslik={t.gecmis} />
          {gecmis.length === 0 ? <Bos>{t.gecmisYok}</Bos> : null}
          <ul className="grid gap-1">
            {gecmis.map((x) => (
              <li key={x.id} className="flex flex-wrap items-center gap-2 border-b border-slate-100 py-1.5 text-xs last:border-0">
                <span className="font-mono font-black text-slate-700">
                  {String(x.ay).padStart(2, "0")}.{x.yil}
                </span>
                <span className="min-w-0 flex-1 truncate text-slate-500" title={x.konu}>
                  {x.konu}
                </span>
                <span className="text-slate-400">{x.gonderen}</span>
                {x.durum === "reverted" ? <Rozet>{t.geriAlindi}</Rozet> : <Rozet ton="yesil">{t.gonderildi}</Rozet>}
                {x.durum === "sent" && geriAlabilir ? (
                  <button type="button" className={`${DUGME} px-2 py-1`} onClick={() => void geriAl(x.id)}>
                    {t.geriAl}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
          {mesaj.gecmis ? <p role="alert" className="text-xs font-bold text-destructive">{mesaj.gecmis}</p> : null}
        </Kart>

        <Kart ek="space-y-3">
          <h4 className="text-sm font-black text-tl-navy">{t.alicilar}</h4>
          <form onSubmit={alicilariKaydet} className="grid gap-3" aria-label={t.alicilar}>
            <div className="grid gap-1.5">
              <label htmlFor="r-kime" className="block text-xs font-extrabold text-slate-600">
                {t.kime}
              </label>
              <input id="r-kime" value={alici.kime} maxLength={5000} onChange={(ev) => setAlici({ ...alici, kime: ev.target.value })} className={GIRDI} />
            </div>
            <div className="grid gap-1.5">
              <label htmlFor="r-cc" className="block text-xs font-extrabold text-slate-600">
                {t.bilgiCc}
              </label>
              <input id="r-cc" value={alici.bilgi} maxLength={5000} onChange={(ev) => setAlici({ ...alici, bilgi: ev.target.value })} className={GIRDI} />
            </div>
            <p className="text-[10px] text-slate-400">{t.alicilarAyrac}</p>
            <div className="flex items-center gap-3">
              <button type="submit" className={DUGME_ANA}>
                {t.alicilariKaydet}
              </button>
              {mesaj.alici ? <span role="status" className="text-xs font-bold text-slate-500">{mesaj.alici}</span> : null}
            </div>
          </form>
        </Kart>
      </div>
    </div>
  )
}
