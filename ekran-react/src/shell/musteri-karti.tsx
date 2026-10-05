import { useCallback, useEffect, useState } from "react"
import type { FormEvent, ReactNode } from "react"
import { Building2, FileText, Pencil } from "lucide-react"
import { apiOku, apiYaz } from "@/lib/api-yaz"
import { Bolum, Bos, DUGME, DUGME_ANA, Etiket, GIRDI, KartTablo, Metrik, Rozet, Satir } from "@/shell/kart-ui"
import type { Dil } from "@/shell/metin"
import { musteriMetin } from "@/shell/musteri-metin"
import { sorguAyarla } from "@/shell/rota"

type Sayilar = { envanter: number; alarm: number; sikayet: number; talep: number; alarm_kapanan: number; sikayet_kapanan: number; talep_kapanan: number }
type Matris = { basliklar: string[]; satirlar: string[][] }
type Gelir = { toplam: Record<string, number>; son: { donem: string; tutar: number; para: string; musteri: string; installation_pct?: number }[] }
export type Kart = {
  kimlik: {
    id: number
    unvan: string
    musteri_no: string | null
    ncst: string
    segment: string
    sektor: string | null
    envanter: number
    tam: string | null
    tam_id: number | null
    ayri_rapor: boolean | null
    cati: { id: number; unvan: string } | null
    istirakler: { id: number; unvan: string; ncst: string; tam: string | null }[]
  }
  operasyon: { ft_hacim: string; tam_ft: string; final_skor: number | null; skor_talebi_bekliyor: boolean; kendi: Sayilar; istirak_dahil: Sayilar | null }
  ekip: Matris
  iletisim: Record<string, string>
  kritik_ci: Matris
  izleme: { cacti: string[]; son_kazima: string | null; kazima_adedi: number }
  raporlar?: { toplam: number; son: { donem: string; gonderildi: boolean; duzenleyen: string | null; tarih: string | null; bayrak: number }[] }
  gelirler?: { ict?: Gelir; apn?: Gelir }
  erisim: { rapor: boolean; gelir: boolean; kimlik_duzenle: boolean; sil: boolean; tam_degistir: boolean; rapor_geri_al: boolean; ayri_rapor_sec: boolean; istirak_ekle: boolean }
  tam_secenekleri?: { id: number; ad: string }[]
}

const SEGMENTLER = ["SMB", "SA", "MA", "PA", "WHOLESALE"]
const ILETISIM_GRUPLARI = [
  { baslik: "satisEkibi", alanlar: [["sales_manager", "satis", 100], ["presales_manager", "presales", 100]] },
  { baslik: "tac", alanlar: [["tac_name", "adSoyad", 100], ["tac_gsm", "gsm", 50], ["tac_email", "eposta", 100]] },
  { baslik: "cozumKmt", alanlar: [["sol_kmt_name", "adSoyad", 100], ["sol_kmt_gsm", "gsm", 50], ["sol_kmt_email", "eposta", 100]] },
  { baslik: "mobilKmt", alanlar: [["mobil_kmt_name", "adSoyad", 100], ["mobil_kmt_gsm", "gsm", 50], ["mobil_kmt_email", "eposta", 100]] },
] as const

type Metin = ReturnType<typeof musteriMetin>

function Girdi({ id, etiket, ad, deger, onChange, uzun = 150, tip = "text", kapali = false }: { id: string; etiket: string; ad?: string; deger: string; onChange: (v: string) => void; uzun?: number; tip?: string; kapali?: boolean }) {
  return (
    <label className="block min-w-0" htmlFor={id}>
      <Etiket>{etiket}</Etiket>
      <input id={id} aria-label={ad ?? etiket} type={tip} value={deger} maxLength={uzun} disabled={kapali} onChange={(e) => onChange(e.target.value)} className={GIRDI} />
    </label>
  )
}

function Kutu({ children, ek = "" }: { children: ReactNode; ek?: string }) {
  return <div className={`rounded-xl border border-white/60 bg-white/95 p-3 text-tl-navy shadow-sm ${ek}`}>{children}</div>
}

function GelirBlok({ baslik, g, apn }: { baslik: string; g: Gelir; apn?: boolean }) {
  const toplam =
    Object.entries(g.toplam)
      .map(([p, v]) => `${v.toLocaleString("tr-TR")} ${p}`)
      .join(" · ") || "—"
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-xs font-black text-slate-500">{baslik}</span>
        <span className="font-mono text-xs font-black text-emerald-600">{toplam}</span>
      </div>
      {g.son.length === 0 ? <Bos>—</Bos> : null}
      {g.son.map((k, i) => (
        <div key={i} className="flex justify-between gap-2 border-b border-slate-100 py-1 text-xs last:border-0">
          <span className="font-mono font-bold text-slate-500">{k.donem}</span>
          {apn && k.installation_pct !== undefined ? <span className="text-slate-400">%{k.installation_pct}</span> : null}
          <span className="font-mono font-black text-slate-700">
            {k.tutar.toLocaleString("tr-TR")} {k.para}
          </span>
        </div>
      ))}
    </div>
  )
}

function Operasyon({ kart, t }: { kart: Kart; t: Metin }) {
  const s = kart.operasyon.kendi
  const d = kart.operasyon.istirak_dahil
  return (
    <Bolum anahtar="operasyon" baslik={t.operasyon}>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <Metrik etiket={t.alarm} deger={s.alarm_kapanan} alt={t.yilIciKapanan} zemin="bg-rose-500/5" yazi="text-rose-600" />
        <Metrik etiket={t.sikayet} deger={s.sikayet_kapanan} alt={t.yilIciKapanan} zemin="bg-amber-500/5" yazi="text-amber-600" />
        <Metrik etiket={t.talep} deger={s.talep_kapanan} alt={t.yilIciKapanan} zemin="bg-blue-500/5" yazi="text-blue-600" />
      </div>
      {d ? (
        <p className="mt-3 text-xs font-bold text-slate-500">
          {t.istirakDahil}:{" "}
          <span className="font-mono text-slate-700">
            {t.envanter} {d.envanter.toLocaleString("tr-TR")} · {t.alarm} {d.alarm_kapanan.toLocaleString("tr-TR")} · {t.sikayet} {d.sikayet_kapanan.toLocaleString("tr-TR")} · {t.talep}{" "}
            {d.talep_kapanan.toLocaleString("tr-TR")}
          </span>
        </p>
      ) : null}
      <p className="mt-2 text-[10px] text-slate-400">{t.acikAciklama}</p>
    </Bolum>
  )
}

export function MusteriKarti({ id, dil }: { id: number; dil: Dil }) {
  const t = musteriMetin(dil)
  const [kart, setKart] = useState<Kart | null | undefined>(undefined)
  const [durum, setDurum] = useState(0)
  const [duzenle, setDuzenle] = useState(false)
  const [kim, setKim] = useState<Record<string, string>>({})
  const [ilet, setIlet] = useState<Record<string, string>>({})
  const [tam, setTam] = useState("")
  const [mesaj, setMesaj] = useState<Record<string, string>>({})
  const [yeniIstirak, setYeniIstirak] = useState<string | null>(null)

  const yukle = useCallback(async () => {
    const sonuc = await apiOku<Kart>(`/api/v1/musteri/${id}`)
    setDurum(sonuc.durum)
    const k = sonuc.ok ? sonuc.veri : null
    setKart(k)
    if (k) {
      setKim({
        name: k.kimlik.unvan,
        customer_no: k.kimlik.musteri_no ?? "",
        ncst: k.kimlik.ncst,
        segment: k.kimlik.segment,
        sector: k.kimlik.sektor ?? "",
        ft_volume: k.operasyon.ft_hacim,
        tam_ft: k.operasyon.tam_ft,
        inventory: String(k.kimlik.envanter),
      })
      setIlet({ ...k.iletisim })
      setTam(k.kimlik.tam_id ? String(k.kimlik.tam_id) : "")
    }
  }, [id])

  useEffect(() => {
    setKart(undefined)
    setDuzenle(false)
    void yukle()
  }, [yukle])

  const bildir = (anahtar: string, metin: string) => setMesaj((m) => ({ ...m, [anahtar]: metin }))

  async function kimligiKaydet(olay: FormEvent) {
    olay.preventDefault()
    const sonuc = await apiYaz("PUT", `/api/v1/musteri/${id}/kimlik`, { ...kim, inventory: kim.inventory === "" ? 0 : Number(kim.inventory) })
    if (!sonuc.ok) {
      bildir("kimlik", `${t.kaydedilemedi}: ${sonuc.hata}`)
      return
    }
    if (kart?.erisim.tam_degistir && tam && Number(tam) !== kart.kimlik.tam_id) {
      const t2 = await apiYaz("PUT", `/api/v1/musteri/${id}/sorumlu`, { owner_id: Number(tam) })
      if (!t2.ok) {
        bildir("kimlik", `${t.kaydedilemedi}: ${t2.hata}`)
        return
      }
    }
    bildir("kimlik", t.kaydedildi)
    setDuzenle(false)
    await yukle()
  }

  async function iletisimiKaydet(olay: FormEvent) {
    olay.preventDefault()
    const sonuc = await apiYaz("PUT", `/api/v1/musteri/${id}/iletisim`, ilet)
    bildir("iletisim", sonuc.ok ? t.kaydedildi : `${t.kaydedilemedi}: ${sonuc.hata}`)
    if (sonuc.ok) await yukle()
  }

  async function ayriRapor(deger: boolean) {
    const sonuc = await apiYaz("PUT", `/api/v1/musteri/${id}/ayri-rapor`, { ayri_rapor: deger })
    if (sonuc.ok) await yukle()
    else bildir("ayri", `${t.kaydedilemedi}: ${sonuc.hata}`)
  }

  async function sil() {
    if (!window.confirm(t.silOnay)) return
    const sonuc = await apiYaz("DELETE", `/api/v1/musteri/${id}`)
    if (sonuc.ok) sorguAyarla("musteri", {})
    else bildir("sil", `${t.kaydedilemedi}: ${sonuc.hata}`)
  }

  async function istirakEkle(olay: FormEvent) {
    olay.preventDefault()
    const sonuc = await apiYaz<{ id: number }>("POST", "/api/v1/musteri", { name: yeniIstirak ?? "", parent_id: id })
    if (sonuc.ok && sonuc.veri) {
      setYeniIstirak(null)
      sorguAyarla("musteri", { m: String(sonuc.veri.id) })
    } else bildir("istirak", `${t.kaydedilemedi}: ${sonuc.hata}`)
  }

  if (kart === undefined) return <p className="text-sm text-muted-foreground">…</p>
  if (kart === null) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {durum === 404 || durum === 403 ? t.bulunamadi : t.yuklenemedi}
      </p>
    )
  }
  const e = kart.erisim
  const k = kart.kimlik
  const o = kart.operasyon

  return (
    <div className="space-y-4 font-sans">
      {/* KIMLIK: lacivert hero, sari sol vurgu */}
      <section aria-label={k.unvan} className="relative overflow-hidden rounded-2xl border border-slate-200 bg-gradient-to-br from-tl-navy to-[#003b80] text-white shadow-sm">
        <span aria-hidden className="absolute inset-y-0 left-0 w-1.5 bg-tl-yellow" />
        <div className="space-y-4 p-5">
          <div className="flex flex-col gap-4 md:flex-row md:items-start">
            <div className="flex min-w-0 flex-1 items-start gap-3.5">
              <div className="flex size-11 shrink-0 items-center justify-center rounded-xl border border-tl-yellow/30 bg-white/10 text-tl-yellow shadow-md">
                <Building2 aria-hidden className="size-5" />
              </div>
              <div className="min-w-0 flex-1">
                <h2 className="break-words text-xl font-black leading-tight sm:text-2xl">{k.unvan}</h2>
                <p className="mt-1 text-xs font-bold text-white/70">{t.musteriKarti}</p>
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {k.segment ? <Rozet ton="sari">{k.segment}</Rozet> : null}
                  {k.sektor ? <span className="rounded-md border border-white/20 bg-white/10 px-2 py-0.5 text-[10px] font-bold text-white">{k.sektor}</span> : null}
                  {k.cati ? <Rozet ton="amber">{t.istirak}</Rozet> : null}
                </div>
              </div>
            </div>
            <div className="flex shrink-0 flex-wrap items-start gap-2 md:justify-end">
              <div className="flex flex-col items-end gap-1.5">
                <div className="flex items-stretch gap-2">
                  <a
                    href={`#/musteri?m=${k.id}&sekme=rapor`}
                    className="flex min-w-[8rem] flex-col rounded-xl border border-white/60 bg-white/95 p-3 text-tl-navy shadow-sm transition-colors hover:border-tl-yellow hover:bg-white focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
                    title={t.aylikRaporGonder}
                  >
                    <span className="text-[10px] font-black uppercase tracking-wide text-slate-400">{t.aylikRaporGonder}</span>
                    <FileText aria-hidden className="ml-auto size-8 text-tl-navy" />
                    <span className="text-[10px] font-bold text-tl-blue">{t.ac} ›</span>
                  </a>
                  <Kutu ek="min-w-[8rem]">
                    <div className="text-[10px] font-black uppercase tracking-wide text-slate-400">{t.finalSkor}</div>
                    {o.final_skor === null ? (
                      <div className="text-xs font-bold text-slate-400">{t.skorCatida}</div>
                    ) : (
                      <>
                        <div className="font-mono text-3xl font-black">%{o.final_skor.toFixed(1)}</div>
                        {o.skor_talebi_bekliyor ? <div className="text-[10px] font-bold text-amber-600">{t.skorBekliyor}</div> : null}
                      </>
                    )}
                  </Kutu>
                </div>
                {k.cati ? (
                  e.ayri_rapor_sec ? (
                    <label className="flex cursor-pointer select-none items-center gap-2 rounded-lg border border-white/30 bg-white/10 px-2.5 py-1.5">
                      <input type="checkbox" className="size-4 accent-tl-yellow" checked={!!k.ayri_rapor} onChange={(ev) => void ayriRapor(ev.target.checked)} />
                      <span className="text-[10px] font-black">{t.ayriRapor}</span>
                      <span className="text-[10px] font-bold text-white/70">{k.ayri_rapor ? t.ayriRaporVar : t.catiRaporunaDahil}</span>
                    </label>
                  ) : (
                    <span className="text-[10px] font-bold text-white/70">{k.ayri_rapor ? t.ayriRaporVar : t.catiRaporunaDahil}</span>
                  )
                ) : null}
              </div>
            </div>
          </div>
          {mesaj.ayri ? <p role="alert" className="text-xs font-bold text-rose-200">{mesaj.ayri}</p> : null}

          {duzenle ? (
            <form onSubmit={kimligiKaydet} aria-label={t.duzenle} className="grid gap-3 rounded-xl bg-white/95 p-4 text-tl-navy sm:grid-cols-2 lg:grid-cols-4">
              <Girdi id="k-name" etiket={t.unvan} deger={kim.name ?? ""} onChange={(v) => setKim({ ...kim, name: v })} />
              <label className="block min-w-0" htmlFor="k-segment">
                <Etiket>{t.segment}</Etiket>
                <select id="k-segment" value={kim.segment ?? ""} onChange={(ev) => setKim({ ...kim, segment: ev.target.value })} className={GIRDI}>
                  <option value="">{t.seciniz}</option>
                  {[...new Set([...SEGMENTLER, kim.segment ?? ""])]
                    .filter(Boolean)
                    .map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                </select>
              </label>
              <Girdi id="k-customer_no" etiket={t.musteriNo} deger={kim.customer_no ?? ""} uzun={50} onChange={(v) => setKim({ ...kim, customer_no: v })} />
              <Girdi id="k-ncst" etiket={t.ncst} deger={kim.ncst ?? ""} uzun={50} onChange={(v) => setKim({ ...kim, ncst: v })} />
              <Girdi id="k-sector" etiket={t.sektor} deger={kim.sector ?? ""} uzun={100} onChange={(v) => setKim({ ...kim, sector: v })} />
              <Girdi id="k-inventory" etiket={t.envanter} deger={kim.inventory ?? ""} uzun={12} onChange={(v) => setKim({ ...kim, inventory: v.replace(/\D/g, "") })} />
              <Girdi id="k-ft_volume" etiket={t.ftHacim} deger={kim.ft_volume ?? ""} uzun={100} onChange={(v) => setKim({ ...kim, ft_volume: v })} />
              <Girdi id="k-tam_ft" etiket={t.tamFt} deger={kim.tam_ft ?? ""} uzun={100} onChange={(v) => setKim({ ...kim, tam_ft: v })} />
              {e.tam_degistir && kart.tam_secenekleri ? (
                <label className="block min-w-0" htmlFor="k-tam">
                  <Etiket>{t.sorumluTam}</Etiket>
                  <select id="k-tam" value={tam} onChange={(ev) => setTam(ev.target.value)} className={GIRDI}>
                    {kart.tam_secenekleri.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.ad}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <div className="flex flex-wrap items-center gap-2 sm:col-span-2 lg:col-span-4">
                <button type="submit" className={DUGME_ANA}>
                  {t.kaydet}
                </button>
                <button type="button" className={DUGME} onClick={() => setDuzenle(false)}>
                  {t.vazgec}
                </button>
                {mesaj.kimlik ? <span role="status" className="text-xs font-bold text-slate-500">{mesaj.kimlik}</span> : null}
              </div>
            </form>
          ) : (
            <div className="grid grid-cols-1 gap-x-4 rounded-xl bg-white/95 px-4 py-2 text-tl-navy sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <Satir etiket={t.musteriNo}>{k.musteri_no || "—"}</Satir>
                <Satir etiket={t.ncst}>{k.ncst || "—"}</Satir>
                <Satir etiket={t.segment}>{k.segment || "—"}</Satir>
                <Satir etiket={t.sektor}>{k.sektor || "—"}</Satir>
              </div>
              <div>
                <Satir etiket={t.sorumluTam}>{k.tam || "—"}</Satir>
                <Satir etiket={t.cati}>
                  {k.cati ? (
                    <a className="text-tl-blue hover:underline" href={`#/musteri?m=${k.cati.id}`}>
                      {k.cati.unvan}
                    </a>
                  ) : (
                    "—"
                  )}
                </Satir>
              </div>
              <div>
                <Satir etiket={t.ftHacim}>
                  <span className="font-mono text-emerald-600">{o.ft_hacim}</span>
                </Satir>
                <Satir etiket={t.tamFt}>
                  <span className="font-mono text-tl-blue">{o.tam_ft}</span>
                </Satir>
                <Satir etiket={t.envanter}>
                  <span className="font-mono">{k.envanter.toLocaleString("tr-TR")}</span>
                </Satir>
              </div>
            </div>
          )}

          <div>
            <div className="mb-1.5 text-[10px] font-black uppercase tracking-wide text-white/70">
              {t.istirakler} ({k.istirakler.length})
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {k.istirakler.length === 0 ? <span className="text-white/60">—</span> : null}
              {k.istirakler.map((i) => (
                <a
                  key={i.id}
                  href={`#/musteri?m=${i.id}`}
                  className="rounded-lg border border-slate-200 bg-white/90 px-2.5 py-1 text-xs font-bold text-tl-navy transition-colors hover:bg-white focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
                >
                  {i.unvan}
                </a>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* kucuk islemler */}
      <div className="flex flex-wrap items-center justify-end gap-2">
        {mesaj.istirak ? <span role="alert" className="text-xs font-bold text-destructive">{mesaj.istirak}</span> : null}
        {mesaj.sil ? <span role="alert" className="text-xs font-bold text-destructive">{mesaj.sil}</span> : null}
        {e.kimlik_duzenle && !duzenle ? (
          <button type="button" onClick={() => setDuzenle(true)} className={DUGME}>
            <Pencil aria-hidden className="size-3.5" />
            {t.duzenle}
          </button>
        ) : null}
        {e.istirak_ekle && !k.cati ? (
          yeniIstirak === null ? (
            <button type="button" className={DUGME} onClick={() => setYeniIstirak("")}>
              {t.istirakEkle}
            </button>
          ) : (
            <form onSubmit={istirakEkle} className="flex items-center gap-2" aria-label={t.istirakEkle}>
              <input aria-label={t.istirakUnvani} placeholder={t.istirakUnvani} value={yeniIstirak} maxLength={150} required onChange={(ev) => setYeniIstirak(ev.target.value)} className={`${GIRDI} w-64`} />
              <button type="submit" className={DUGME_ANA}>
                {t.kaydet}
              </button>
              <button type="button" className={DUGME} onClick={() => setYeniIstirak(null)}>
                {t.vazgec}
              </button>
            </form>
          )
        ) : null}
        {e.sil ? (
          <button type="button" onClick={() => void sil()} className="inline-flex items-center rounded-xl border border-rose-200 bg-rose-500/10 px-4 py-2 text-xs font-bold text-rose-600 hover:bg-rose-500/20 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-rose-400">
            {t.sil}
          </button>
        ) : null}
      </div>

      {/* EKIP & ILETISIM */}
      <Bolum anahtar="ekip" baslik={t.iletisim}>
        <form onSubmit={iletisimiKaydet} aria-label={t.iletisim} className="space-y-4">
          <div className="grid grid-cols-1 gap-x-6 gap-y-4 lg:grid-cols-2">
            {ILETISIM_GRUPLARI.map((g) => (
              <div key={g.baslik} className="min-w-0">
                <div className="mb-2 border-b border-slate-100 pb-1 text-[10px] font-black uppercase tracking-wide text-tl-navy/70">{t[g.baslik]}</div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                  {g.alanlar.map(([alan, etiket, azami]) => (
                    <Girdi
                      key={alan}
                      id={`i-${alan}`}
                      etiket={t[etiket]}
                      ad={`${t[g.baslik]} · ${t[etiket]}`}
                      deger={ilet[alan] ?? ""}
                      uzun={azami}
                      tip={alan.endsWith("_email") ? "email" : alan.endsWith("_gsm") ? "tel" : "text"}
                      onChange={(v) => setIlet({ ...ilet, [alan]: v })}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
          <label className="block" htmlFor="i-mobil_kmt_detail">
            <Etiket>{`${t.mobilKmt} · ${t.not}`}</Etiket>
            <textarea id="i-mobil_kmt_detail" rows={2} maxLength={2000} value={ilet.mobil_kmt_detail ?? ""} onChange={(ev) => setIlet({ ...ilet, mobil_kmt_detail: ev.target.value })} className={GIRDI} />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <button type="submit" className={DUGME_ANA}>
              {t.kaydet}
            </button>
            {mesaj.iletisim ? <span role="status" className="text-xs font-bold text-slate-500">{mesaj.iletisim}</span> : null}
          </div>
        </form>
      </Bolum>

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Operasyon kart={kart} t={t} />
          <Bolum anahtar="ekip_destech" baslik={t.ekip}>
            {kart.ekip.satirlar.length ? <KartTablo basliklar={kart.ekip.basliklar} satirlar={kart.ekip.satirlar} /> : <Bos>{t.satirYok}</Bos>}
          </Bolum>
          <Bolum anahtar="kritik_ci" baslik={t.kritikCi}>
            {kart.kritik_ci.satirlar.length ? <KartTablo basliklar={kart.kritik_ci.basliklar} satirlar={kart.kritik_ci.satirlar} /> : <Bos>{t.satirYok}</Bos>}
          </Bolum>
        </div>
        <div className="space-y-4">
          {kart.raporlar ? (
            <Bolum anahtar="raporlar" baslik={`${t.raporlar} (${kart.raporlar.toplam})`}>
              {kart.raporlar.son.length === 0 ? <Bos>{t.raporYok}</Bos> : null}
              {kart.raporlar.son.map((r, i) => (
                <div key={i} className="flex items-center justify-between gap-2 border-b border-slate-100 py-1.5 text-xs last:border-0">
                  <span className="font-mono font-black text-slate-700">{r.donem}</span>
                  <span className="truncate text-slate-400">{r.duzenleyen ?? ""}</span>
                  {r.bayrak ? <span className="font-bold text-rose-600">⚑ {r.bayrak}</span> : null}
                  <Rozet ton={r.gonderildi ? "yesil" : "gri"}>{r.gonderildi ? t.gonderildi : t.taslak}</Rozet>
                </div>
              ))}
            </Bolum>
          ) : null}
          {kart.gelirler ? (
            <Bolum anahtar="gelirler" baslik={t.gelirler}>
              <div className="grid grid-cols-1 gap-4">
                {kart.gelirler.ict ? <GelirBlok baslik={t.ictGelir} g={kart.gelirler.ict} /> : null}
                {kart.gelirler.apn ? <GelirBlok baslik={t.apnGelir} g={kart.gelirler.apn} apn /> : null}
              </div>
            </Bolum>
          ) : null}
          <Bolum anahtar="izleme" baslik={t.izleme}>
            {kart.izleme.cacti.length === 0 ? <Bos>{t.izlemeYok}</Bos> : null}
            {kart.izleme.cacti.map((u) => (
              <span key={u} className="block truncate text-xs font-bold text-slate-500" title={u}>
                {u}
              </span>
            ))}
            <div className="mt-3 text-xs font-bold text-slate-500">
              {t.sonKazima}: <span className="font-mono text-slate-700">{kart.izleme.son_kazima ?? "—"}</span> ({kart.izleme.kazima_adedi})
            </div>
          </Bolum>
        </div>
      </div>
    </div>
  )
}
