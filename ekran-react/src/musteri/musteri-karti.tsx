import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import type { FormEvent, ReactNode } from "react"
import { Activity, Building2, FileText, ListChecks, Mail, Network, Pencil, Phone, Plus, Trash2 } from "lucide-react"
import { adaGoreSirala, sayi } from "@/lib/bicim"
import { ApiHata, hataMesaji, oku, yaz } from "@/lib/sorgu"
import { Cekmece } from "@/components/cekmece"
import { Alan, Bolum, Bos, DUGME, DUGME_ANA, GIRDI, Rozet, Satir, VeriTablosu } from "@/components/sayfa-ui"
import type { Dil } from "@/shell/metin"
import { KartKayitlari } from "@/musteri/kayitlar"
import type { KayitDurumu, KayitTuru } from "@/musteri/kayitlar"
import { musteriMetin } from "@/musteri/musteri-metin"
import { modulYolu, useMusteriYolu } from "@/musteri/musteri-yolu"
import { sorguAyarla } from "@/shell/rota"

type Sayilar = { envanter: number; alarm: number; sikayet: number; talep: number; alarm_kapanan: number; sikayet_kapanan: number; talep_kapanan: number }
type Matris = { basliklar: string[]; satirlar: string[][] }
export type Kart = {
  /** Kartin modulunde secilebilir segmentler (Toptan: yalniz WHOLESALE; digerleri WHOLESALE'siz). */
  segmentler?: string[]
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
    rapor_muaf: boolean
    cati: { id: number; unvan: string } | null
    istirakler: { id: number; unvan: string; ncst: string; tam: string | null }[]
  }
  operasyon: { ft_hacim: string; tam_ft: string; final_skor: number | null; skor_talebi_bekliyor: boolean; kendi: Sayilar; istirak_dahil: Sayilar | null }
  iletisim: Record<string, string>
  kritik_ci: Matris
  raporlar?: { toplam: number; son: { donem: string; gonderildi: boolean; duzenleyen: string | null; tarih: string | null; bayrak: number }[] }
  erisim: { rapor: boolean; gelir: boolean; kimlik_duzenle: boolean; iletisim_duzenle: boolean; sil: boolean; tam_degistir: boolean; rapor_geri_al: boolean; ayri_rapor_sec: boolean; rapor_muaf_sec: boolean; istirak_ekle: boolean }
  tam_secenekleri?: { id: number; ad: string }[]
  cati_secenekleri?: { id: number; ad: string }[]
}

const ILETISIM_GRUPLARI = [
  { baslik: "satisEkibi", alanlar: [["sales_manager", "satis", 100], ["presales_manager", "presales", 100]] },
  { baslik: "tac", alanlar: [["tac_name", "adSoyad", 100], ["tac_gsm", "gsm", 50], ["tac_email", "eposta", 100]] },
  { baslik: "cozumKmt", alanlar: [["sol_kmt_name", "adSoyad", 100], ["sol_kmt_gsm", "gsm", 50], ["sol_kmt_email", "eposta", 100]] },
  { baslik: "mobilKmt", alanlar: [["mobil_kmt_name", "adSoyad", 100], ["mobil_kmt_gsm", "gsm", 50], ["mobil_kmt_email", "eposta", 100]] },
] as const

type Metin = ReturnType<typeof musteriMetin>

function Girdi({ id, etiket, ad, deger, onChange, uzun = 150, tip = "text", kapali = false }: { id: string; etiket: string; ad?: string; deger: string; onChange: (v: string) => void; uzun?: number; tip?: string; kapali?: boolean }) {
  return (
    <Alan etiket={etiket} sinif="min-w-0">
      <input id={id} aria-label={ad ?? etiket} type={tip} value={deger} maxLength={uzun} disabled={kapali} onChange={(e) => onChange(e.target.value)} className={GIRDI} />
    </Alan>
  )
}

function MatrisTablo({ baslik, m, bos }: { baslik: string; m: Matris; bos: string }) {
  const kolonlar = m.basliklar.map((b, i) => ({ baslik: b, hucre: (s: string[]) => s[i], sinif: "whitespace-nowrap" }))
  return <VeriTablosu baslik={baslik} kolonlar={kolonlar} satirlar={m.satirlar} bos={<Bos>{bos}</Bos>} />
}

function Kutu({ children, ek = "" }: { children: ReactNode; ek?: string }) {
  return <div className={`rounded-xl border border-white/60 bg-white/95 p-3 text-tl-navy shadow-sm ${ek}`}>{children}</div>
}

/** Cerceve icindeki alt baslik (sari serit + lacivert buyuk harf). */
function CerceveBasligi({ children }: { children: ReactNode }) {
  return (
    <h3 className="mb-1.5 flex items-center gap-2 text-[0.6875rem] font-black uppercase tracking-widest text-tl-navy">
      <span aria-hidden className="h-4 w-1 rounded-full bg-tl-yellow" />
      {children}
    </h3>
  )
}

/** Ekip & iletisim bilgisinin okuma gorunumu: grup basina bir kutu; telefon ve e-posta tiklanabilir. */
function IletisimKutusu({ g, ilet, t }: { g: (typeof ILETISIM_GRUPLARI)[number]; ilet: Record<string, string>; t: Metin }) {
  const deger = (alan: string) => (ilet[alan] ?? "").trim()
  const satis = g.baslik === "satisEkibi"
  const [adAlani, gsmAlani, epostaAlani] = g.alanlar.map(([alan]) => alan)
  const ad = deger(adAlani ?? "")
  const gsm = deger(gsmAlani ?? "")
  const eposta = deger(epostaAlani ?? "")
  return (
    <div className="min-w-0 rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2">
      <div className="mb-1 text-[0.625rem] font-black uppercase tracking-wide text-tl-blue">{t[g.baslik]}</div>
      {satis ? (
        <div className="grid gap-0.5">
          {g.alanlar.map(([alan, etiket]) => (
            <div key={alan} className="break-words text-xs">
              <span className="font-bold text-slate-400">{t[etiket]}: </span>
              <span className="font-black text-slate-700">{deger(alan) || "—"}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="grid gap-0.5">
          <div className="break-words text-xs font-black text-tl-navy">{ad || "—"}</div>
          {gsm ? (
            <a href={`tel:${gsm}`} className="flex items-center gap-1.5 break-all text-xs font-bold text-slate-600 hover:text-tl-blue">
              <Phone aria-hidden className="size-3.5 shrink-0 text-tl-blue" />
              {gsm}
            </a>
          ) : null}
          {eposta ? (
            <a href={`mailto:${eposta}`} className="flex items-center gap-1.5 break-all text-xs font-bold text-slate-600 hover:text-tl-blue">
              <Mail aria-hidden className="size-3.5 shrink-0 text-tl-blue" />
              {eposta}
            </a>
          ) : null}
        </div>
      )}
    </div>
  )
}

/** Operasyon penceresi: yuvarlak koseli, mavi zeminli musteri karti bicimi; Alarm / Talep / Sikayet yil ici kapanan adetleri. */
type Secim = { tur: KayitTuru; durum: KayitDurumu } | null

/** Operasyon: Alarm / Talep / Sikayet "acik / yil ici kapanan"; her sayi bir dugme: o tur + durumdaki kayitlari kartin altinda listeler. */
function Operasyon({ kart, t, secim, onSec }: { kart: Kart; t: Metin; secim: Secim; onSec: (s: Secim) => void }) {
  const s = kart.operasyon.kendi
  const d = kart.operasyon.istirak_dahil
  const kutular = [
    ["alarm", t.alarm, s.alarm, s.alarm_kapanan, "bg-rose-500", "text-rose-600"],
    ["talep", t.talep, s.talep, s.talep_kapanan, "bg-tl-accent", "text-tl-blue"],
    ["sikayet", t.sikayet, s.sikayet, s.sikayet_kapanan, "bg-amber-500", "text-amber-600"],
  ] as const
  const dugme = (tur: KayitTuru, durum: KayitDurumu, deger: number, etiket: string, renk: string) => {
    const secili = secim?.tur === tur && secim.durum === durum
    return (
      <button
        type="button"
        aria-pressed={secili}
        aria-label={`${etiket}: ${durum === "acik" ? t.acik : t.yilIciKapanan} ${deger}`}
        title={durum === "acik" ? t.acik : t.yilIciKapanan}
        onClick={() => onSec(secili ? null : { tur, durum })}
        className={`rounded-lg px-1.5 font-mono text-2xl font-black leading-tight transition-colors hover:bg-slate-100 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow ${
          secili ? "bg-tl-yellow/40 ring-2 ring-tl-yellow" : ""
        } ${durum === "acik" ? renk : "text-slate-500"}`}
      >
        {sayi(deger)}
      </button>
    )
  }
  return (
    <section aria-label={t.operasyon} className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-tl-navy via-[#003a7a] to-tl-blue px-4 py-3 text-white shadow-md ring-1 ring-tl-navy/20">
      <span aria-hidden className="pointer-events-none absolute -right-10 -top-12 size-48 rounded-full bg-tl-yellow/20 blur-3xl" />
      <span aria-hidden className="pointer-events-none absolute -bottom-16 left-1/4 size-44 rounded-full bg-tl-accent/25 blur-3xl" />
      <div className="relative">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-tl-yellow text-tl-navy shadow-md">
            <Activity aria-hidden className="size-4" />
          </span>
          <h3 className="text-xs font-black uppercase tracking-widest">{t.operasyon}</h3>
          <span className="text-[0.6875rem] font-bold text-white/70">
            · {t.acik} / {t.yilIciKapanan.toLocaleLowerCase("tr")}
          </span>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {kutular.map(([tur, etiket, acik, kapanan, serit, yazi]) => (
            <div key={tur} className="relative flex items-center justify-between gap-2 overflow-hidden rounded-xl border border-white/60 bg-white/95 py-1.5 pl-4 pr-2 text-tl-navy shadow-sm">
              <span aria-hidden className={`absolute inset-y-0 left-0 w-1.5 ${serit}`} />
              <span className="text-[0.6875rem] font-black uppercase tracking-wide text-slate-500">{etiket}</span>
              <span className="flex items-center gap-0.5">
                {dugme(tur, "acik", acik, etiket, yazi)}
                <span aria-hidden className="text-lg font-black text-slate-300">/</span>
                {dugme(tur, "kapali", kapanan, etiket, yazi)}
              </span>
            </div>
          ))}
        </div>
        {d ? (
          <p className="mt-2 text-xs font-bold text-white/80">
            {t.istirakDahil}:{" "}
            <span className="font-mono text-white">
              {t.envanter} {sayi(d.envanter)} · {t.alarm} {sayi(d.alarm_kapanan)} · {t.talep} {sayi(d.talep_kapanan)} · {t.sikayet} {sayi(d.sikayet_kapanan)}
            </span>
          </p>
        ) : null}
      </div>
    </section>
  )
}

export function MusteriKarti({ id, dil }: { id: number; dil: Dil }) {
  const t = musteriMetin(dil)
  const yol = useMusteriYolu()
  const q = useQuery({ queryKey: ["musteri", "kart", id], queryFn: () => oku<Kart>(`/api/v1/musteri/${id}`) })
  const kart = q.data
  const [duzenle, setDuzenle] = useState(false)
  const [kim, setKim] = useState<Record<string, string>>({})
  const [ilet, setIlet] = useState<Record<string, string>>({})
  const [tam, setTam] = useState("")
  const [tur, setTur] = useState<"cati" | "istirak">("cati")
  const [catiId, setCatiId] = useState("")
  const [mesaj, setMesaj] = useState<Record<string, string>>({})
  const [yeniIstirak, setYeniIstirak] = useState<string | null>(null)
  const [ciAcik, setCiAcik] = useState(false)
  const [istirakAcik, setIstirakAcik] = useState(false)
  const [secim, setSecim] = useState<Secim>(null)

  /** Form sunucu verisiyle YALNIZ duzenleme acilirken doldurulur: arka plan yenilemesi yazilani ezmez, Vazgec sonrasi eski deger donmez. */
  function duzenlemeyiAc() {
    if (!kart) return
    setKim({
      name: kart.kimlik.unvan,
      customer_no: kart.kimlik.musteri_no ?? "",
      ncst: kart.kimlik.ncst,
      segment: kart.kimlik.segment,
      sector: kart.kimlik.sektor ?? "",
      ft_volume: kart.operasyon.ft_hacim,
      tam_ft: kart.operasyon.tam_ft,
      inventory: String(kart.kimlik.envanter),
    })
    setIlet({ ...kart.iletisim })
    setTam(kart.kimlik.tam_id ? String(kart.kimlik.tam_id) : "")
    setTur(kart.kimlik.cati ? "istirak" : "cati")
    setCatiId(kart.kimlik.cati ? String(kart.kimlik.cati.id) : "")
    setDuzenle(true)
  }

  const bildir = (anahtar: string, metin: string) => setMesaj((m) => ({ ...m, [anahtar]: metin }))
  /** Istek basarisizsa hatayi ilgili alana yazar; basariyi dondurur. */
  async function dene(anahtar: string, istek: () => Promise<unknown>): Promise<boolean> {
    try {
      await istek()
      return true
    } catch (h) {
      bildir(anahtar, hataMesaji(h, t.kaydedilemedi))
      return false
    }
  }

  /** Tek cerceve, tek Kaydet: iletisim (yetki varsa) once, sonra kimlik ve sorumlu TAM. */
  async function kaydet(olay: FormEvent) {
    olay.preventDefault()
    if (!kart) return
    if (kart.erisim.kimlik_duzenle && tur === "istirak" && !catiId) {
      bildir("duzenle", t.catiSeciniz)
      return
    }
    const tamDegisti = kart.erisim.tam_degistir && tam && Number(tam) !== kart.kimlik.tam_id
    let tamam = true
    let modul: string | undefined
    if (kart.erisim.iletisim_duzenle) tamam = await dene("duzenle", () => yaz("PUT", `/api/v1/musteri/${id}/iletisim`, ilet))
    if (tamam && kart.erisim.kimlik_duzenle) {
      tamam = await dene("duzenle", async () => {
        if (tamDegisti) await yaz("PUT", `/api/v1/musteri/${id}/sorumlu`, { owner_id: Number(tam) }) // modul degismeden once (kart bu ekranda)
        modul = (await yaz<{ modul?: string }>("PUT", `/api/v1/musteri/${id}/kimlik`, { ...kim, inventory: kim.inventory === "" ? 0 : Number(kim.inventory), parent_id: tur === "istirak" ? Number(catiId) : null })).modul
      })
    }
    if (!tamam) return
    if (modulYolu(modul, yol) !== yol) {
      setDuzenle(false)
      sorguAyarla(modulYolu(modul, yol), { m: String(id) }) // segment WHOLESALE: kart Toptan'a gecti
      return
    }
    bildir("duzenle", t.kaydedildi)
    setDuzenle(false)
    await q.refetch()
  }

  async function ayriRapor(deger: boolean) {
    if (await dene("ayri", () => yaz("PUT", `/api/v1/musteri/${id}/ayri-rapor`, { ayri_rapor: deger }))) await q.refetch()
  }

  async function raporMuaf(deger: boolean) {
    if (await dene("ayri", () => yaz("PUT", `/api/v1/musteri/${id}/rapor-muaf`, { rapor_muaf: deger }))) await q.refetch()
  }

  async function sil() {
    if (!window.confirm(t.silOnay)) return
    if (await dene("sil", () => yaz("DELETE", `/api/v1/musteri/${id}`))) sorguAyarla(yol, {})
  }

  async function istirakEkle(olay: FormEvent) {
    olay.preventDefault()
    let yeni = 0
    const tamam = await dene("istirak", async () => {
      yeni = (await yaz<{ id: number }>("POST", "/api/v1/musteri", { name: yeniIstirak ?? "", parent_id: id })).id
    })
    if (!tamam) return
    setYeniIstirak(null)
    sorguAyarla(yol, { m: String(yeni) })
  }

  if (q.isPending) return <p className="text-sm text-muted-foreground">…</p>
  if (!kart) {
    const durum = q.error instanceof ApiHata ? q.error.durum : 0
    return (
      <p role="alert" className="text-sm text-destructive">
        {durum === 404 || durum === 403 ? t.bulunamadi : t.yuklenemedi}
      </p>
    )
  }
  const e = kart.erisim
  const k = kart.kimlik
  const o = kart.operasyon
  const duzenlenebilir = e.kimlik_duzenle || e.iletisim_duzenle
  const mobilNot = (kart.iletisim.mobil_kmt_detail ?? "").trim()
  const catiSecenekleri = adaGoreSirala(
    (kart.cati_secenekleri ?? (k.cati ? [{ id: k.cati.id, ad: k.cati.unvan }] : [])).filter((c) => c.id !== id),
    (c) => c.ad,
  )
  const tamSecenekleri = adaGoreSirala(kart.tam_secenekleri ?? [], (u) => u.ad)

  return (
    <div className="space-y-3 font-sans">
      {/* KIMLIK: lacivert hero, sari sol vurgu */}
      <section aria-label={k.unvan} className="relative overflow-hidden rounded-2xl border border-slate-200 bg-gradient-to-br from-tl-navy to-[#003b80] text-white shadow-sm">
        <span aria-hidden className="absolute inset-y-0 left-0 w-1.5 bg-tl-yellow" />
        <div className="space-y-3 p-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
            <div className="flex min-w-0 flex-1 items-start gap-3.5">
              <div className="flex size-11 shrink-0 items-center justify-center rounded-xl border border-tl-yellow/30 bg-white/10 text-tl-yellow shadow-md">
                <Building2 aria-hidden className="size-5" />
              </div>
              <div className="min-w-0 flex-1">
                <h2 className="break-words text-lg font-black leading-tight sm:text-xl">{k.unvan}</h2>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {k.segment ? <Rozet ton="sari">{k.segment}</Rozet> : null}
                  {k.sektor ? <span className="rounded-md border border-white/20 bg-white/10 px-2 py-0.5 text-[0.625rem] font-bold text-white">{k.sektor}</span> : null}
                  {k.cati ? <Rozet ton="amber">{t.istirak}</Rozet> : null}
                </div>
              </div>
            </div>
            <div className="flex shrink-0 flex-col items-stretch gap-2 sm:items-end">
              <div className="flex flex-wrap items-stretch gap-3 lg:justify-end">
                {/* AYLIK RAPOR: panelin en onemli ogelerinden biri; sari, buyuk, parlayan dugme */}
                <a
                  href={`#/${yol}?m=${k.id}&sekme=rapor`}
                  title={t.aylikRaporGonder}
                  className="group relative flex min-w-[17rem] flex-1 items-center gap-3 overflow-hidden rounded-2xl bg-gradient-to-br from-tl-yellow to-amber-400 px-4 py-2.5 text-tl-navy shadow-[0_10px_28px_-8px_rgba(255,199,44,0.85)] ring-2 ring-white/70 transition-all hover:-translate-y-0.5 hover:shadow-[0_14px_32px_-8px_rgba(255,199,44,1)] focus-visible:outline-hidden focus-visible:ring-4 focus-visible:ring-white"
                >
                  <span aria-hidden className="tl-hareket pointer-events-none absolute inset-y-0 left-0 w-1/4 bg-gradient-to-r from-transparent via-white/60 to-transparent" style={{ animation: "tl-parilti 3.4s ease-in-out infinite" }} />
                  <span className="relative flex size-10 shrink-0 items-center justify-center rounded-xl bg-tl-navy text-tl-yellow shadow-lg">
                    <FileText aria-hidden className="size-5" />
                  </span>
                  <span className="relative grid min-w-0 flex-1 leading-tight">
                    <span className="text-sm font-black uppercase tracking-wide">{t.aylikRaporGonder}</span>
                    <span className="mt-0.5 text-xs font-bold text-tl-navy/75">{t.aylikRaporAlt}</span>
                  </span>
                  <span aria-hidden className="relative text-2xl font-black transition-transform group-hover:translate-x-0.5">
                    ›
                  </span>
                </a>
                <Kutu ek="flex min-w-[8.5rem] flex-col justify-center !py-2">
                  <div className="text-[0.625rem] font-black uppercase tracking-wide text-slate-400">{t.finalSkor}</div>
                  {o.final_skor === null ? (
                    <div className="text-xs font-bold text-slate-400">{t.skorCatida}</div>
                  ) : (
                    <>
                      <div className="font-mono text-2xl font-black">%{o.final_skor.toFixed(1)}</div>
                      {o.skor_talebi_bekliyor ? <div className="text-[0.625rem] font-bold text-amber-600">{t.skorBekliyor}</div> : null}
                    </>
                  )}
                </Kutu>
              </div>
              {k.cati ? (
                e.ayri_rapor_sec ? (
                  <label className="flex cursor-pointer select-none items-center gap-2 rounded-lg border border-white/30 bg-white/10 px-2.5 py-1.5">
                    <input type="checkbox" className="size-4 accent-tl-yellow" checked={!!k.ayri_rapor} onChange={(ev) => void ayriRapor(ev.target.checked)} />
                    <span className="text-[0.625rem] font-black">{t.ayriRapor}</span>
                    <span className="text-[0.625rem] font-bold text-white/70">{k.ayri_rapor ? t.ayriRaporVar : t.catiRaporunaDahil}</span>
                  </label>
                ) : (
                  <span className="text-[0.625rem] font-bold text-white/70">{k.ayri_rapor ? t.ayriRaporVar : t.catiRaporunaDahil}</span>
                )
              ) : null}
              {e.rapor_muaf_sec ? (
                <label className="flex cursor-pointer select-none items-center gap-2 rounded-lg border border-white/30 bg-white/10 px-2.5 py-1.5">
                  <input type="checkbox" className="size-4 accent-tl-yellow" checked={k.rapor_muaf} onChange={(ev) => void raporMuaf(ev.target.checked)} />
                  <span className="text-[0.625rem] font-black">{t.raporMuaf}</span>
                </label>
              ) : k.rapor_muaf ? (
                <span className="text-[0.625rem] font-black text-white/70">{t.raporMuaf}</span>
              ) : null}
            </div>
          </div>
          {mesaj.ayri ? <p role="alert" className="text-xs font-bold text-rose-200">{mesaj.ayri}</p> : null}

          {/* TEK CERCEVE: musteri detayi, sorumlu TAM, FT/envanter ve ekip & iletisim bir arada */}
          <div className="rounded-xl bg-white/95 text-tl-navy">
            {duzenle ? (
              <form onSubmit={kaydet} aria-label={t.duzenle} className="grid gap-5 p-4">
                {e.kimlik_duzenle ? (
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <div className="col-span-full grid gap-3 sm:grid-cols-2">
                      <Alan etiket={t.musteriTuru} sinif="min-w-0">
                        <select id="k-tur" aria-label={t.musteriTuru} className={GIRDI} value={tur} onChange={(ev) => setTur(ev.target.value as "cati" | "istirak")}>
                          <option value="cati">{t.cati}</option>
                          <option value="istirak" disabled={k.istirakler.length > 0}>{t.istirak}</option>
                        </select>
                      </Alan>
                      {tur === "istirak" ? (
                        <Alan etiket={t.cati} sinif="min-w-0">
                          <select id="k-cati" aria-label={t.cati} className={GIRDI} value={catiId} onChange={(ev) => setCatiId(ev.target.value)} required>
                            <option value="">{t.catiSeciniz}</option>
                        {catiSecenekleri.map((c) => (
                              <option key={c.id} value={c.id}>{c.ad}</option>
                            ))}
                          </select>
                        </Alan>
                      ) : null}
                      {k.istirakler.length > 0 ? <p className="col-span-full text-xs text-slate-500">{t.istirakleriTasi}</p> : null}
                    </div>
                    <Girdi id="k-name" etiket={t.unvan} deger={kim.name ?? ""} onChange={(v) => setKim({ ...kim, name: v })} />
                    <Alan etiket={t.segment} sinif="min-w-0">
                      <select id="k-segment" value={kim.segment ?? ""} onChange={(ev) => setKim({ ...kim, segment: ev.target.value })} className={GIRDI}>
                        <option value="">{t.seciniz}</option>
                        {[...new Set([...(kart.segmentler ?? []), kim.segment ?? ""])]
                          .filter(Boolean)
                          .map((s) => (
                            <option key={s} value={s}>
                              {s}
                            </option>
                          ))}
                      </select>
                    </Alan>
                    <Girdi id="k-customer_no" etiket={t.musteriNo} deger={kim.customer_no ?? ""} uzun={50} onChange={(v) => setKim({ ...kim, customer_no: v })} />
                    <Girdi id="k-ncst" etiket={t.ncst} deger={kim.ncst ?? ""} uzun={50} onChange={(v) => setKim({ ...kim, ncst: v })} />
                    <Girdi id="k-sector" etiket={t.sektor} deger={kim.sector ?? ""} uzun={100} onChange={(v) => setKim({ ...kim, sector: v })} />
                    <Girdi id="k-inventory" etiket={t.envanter} deger={kim.inventory ?? ""} uzun={12} onChange={(v) => setKim({ ...kim, inventory: v.replace(/\D/g, "") })} />
                    <Girdi id="k-ft_volume" etiket={t.ftHacim} deger={kim.ft_volume ?? ""} uzun={100} onChange={(v) => setKim({ ...kim, ft_volume: v })} />
                    <Girdi id="k-tam_ft" etiket={t.tamFt} deger={kim.tam_ft ?? ""} uzun={100} onChange={(v) => setKim({ ...kim, tam_ft: v })} />
                    {e.tam_degistir && kart.tam_secenekleri ? (
                      <Alan etiket={t.sorumluTam} sinif="min-w-0">
                        <select id="k-tam" value={tam} onChange={(ev) => setTam(ev.target.value)} className={GIRDI}>
                      {tamSecenekleri.map((u) => (
                            <option key={u.id} value={u.id}>
                              {u.ad}
                            </option>
                          ))}
                        </select>
                      </Alan>
                    ) : null}
                  </div>
                ) : null}
                {e.iletisim_duzenle ? (
                  <div>
                    <CerceveBasligi>{t.iletisim}</CerceveBasligi>
                    <div className="grid grid-cols-1 gap-x-6 gap-y-4 lg:grid-cols-2">
                      {ILETISIM_GRUPLARI.map((g) => (
                        <div key={g.baslik} className="min-w-0">
                          <div className="mb-2 border-b border-slate-100 pb-1 text-[0.625rem] font-black uppercase tracking-wide text-tl-navy/70">{t[g.baslik]}</div>
                          <div className={`grid grid-cols-1 gap-2 ${g.alanlar.length === 2 ? "sm:grid-cols-2" : "sm:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)_minmax(0,1.5fr)]"}`}>
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
                    <div className="mt-4">
                      <Alan etiket={`${t.mobilKmt} · ${t.not}`}>
                        <textarea id="i-mobil_kmt_detail" rows={2} maxLength={2000} value={ilet.mobil_kmt_detail ?? ""} onChange={(ev) => setIlet({ ...ilet, mobil_kmt_detail: ev.target.value })} className={GIRDI} />
                      </Alan>
                    </div>
                  </div>
                ) : null}
                <div className="flex flex-wrap items-center gap-2">
                  <button type="submit" className={DUGME_ANA}>
                    {t.kaydet}
                  </button>
                  <button type="button" className={DUGME} onClick={() => setDuzenle(false)}>
                    {t.vazgec}
                  </button>
                  {mesaj.duzenle ? (
                    <span role="status" className="text-xs font-bold text-slate-500">
                      {mesaj.duzenle}
                    </span>
                  ) : null}
                </div>
              </form>
            ) : (
              <>
                <div className="grid grid-cols-1 gap-x-6 px-4 py-1 sm:grid-cols-2 lg:grid-cols-3 [&_div.flex]:!py-1">
                  <div>
                    <Satir etiket={t.musteriNo}>{k.musteri_no || "—"}</Satir>
                    <Satir etiket={t.ncst}>{k.ncst || "—"}</Satir>
                    <Satir etiket={t.segment}>{k.segment || "—"}</Satir>
                  </div>
                  <div>
                    <Satir etiket={t.sektor}>{k.sektor || "—"}</Satir>
                    <Satir etiket={t.sorumluTam}>{k.tam || "—"}</Satir>
                    <Satir etiket={t.cati}>
                      {k.cati ? (
                        <a className="text-tl-blue hover:underline" href={`#/${yol}?m=${k.cati.id}`}>
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
                      <span className="font-mono">{sayi(k.envanter)}</span>
                    </Satir>
                  </div>
                </div>
                <div className="border-t border-slate-200 px-4 pb-3 pt-2">
                  <CerceveBasligi>{t.iletisim}</CerceveBasligi>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    {ILETISIM_GRUPLARI.map((g) => (
                      <IletisimKutusu key={g.baslik} g={g} ilet={kart.iletisim} t={t} />
                    ))}
                  </div>
                  {mobilNot ? (
                    <p className="mt-2 whitespace-pre-line break-words text-xs font-bold text-slate-600">
                      <span className="text-slate-400">
                        {t.mobilKmt} · {t.not}:{" "}
                      </span>
                      {mobilNot}
                    </p>
                  ) : null}
                </div>
              </>
            )}
          </div>

          {/* Istirakler en fazla 2 satir (kart tek ekrana sigsin); "Tumunu goster" acinca sayfa uzar */}
          <div className="flex items-start gap-2">
          <div className={`flex min-w-0 flex-1 flex-wrap items-center gap-1 ${istirakAcik ? "" : "max-h-[3.25rem] overflow-hidden"}`}>
            <span className="mr-1 text-[0.625rem] font-black uppercase tracking-wide text-white/70">
              {t.istirakler} ({k.istirakler.length})
            </span>
            <div className="contents">
              {k.istirakler.length === 0 ? <span className="text-white/60">—</span> : null}
              {k.istirakler.map((i) => (
                <a
                  key={i.id}
                  href={`#/${yol}?m=${i.id}`}
                  className="rounded-md border border-slate-200 bg-white/90 px-2 py-0.5 text-[0.6875rem] font-bold text-tl-navy transition-colors hover:bg-white focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
                >
                  {i.unvan}
                </a>
              ))}
            </div>
          </div>
          {k.istirakler.length > 8 ? (
            <button
              type="button"
              aria-expanded={istirakAcik}
              onClick={() => setIstirakAcik((v) => !v)}
              className="shrink-0 rounded-md border border-tl-yellow/60 bg-tl-yellow/15 px-2 py-0.5 text-[0.6875rem] font-black text-tl-yellow hover:bg-tl-yellow/25 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
            >
              {istirakAcik ? t.istirakDaralt : t.istirakTumu(k.istirakler.length)}
            </button>
          ) : null}
          </div>
        </div>
      </section>

      {/* ISLEMLER: Duzenle, Istirak ekle, Kritik CI, Topo Maker ve Sil ayni satirda */}
      <div className="flex flex-wrap items-center justify-end gap-2">
        {mesaj.istirak ? <span role="alert" className="text-xs font-bold text-destructive">{mesaj.istirak}</span> : null}
        {mesaj.sil ? <span role="alert" className="text-xs font-bold text-destructive">{mesaj.sil}</span> : null}
        {!duzenle && mesaj.duzenle ? <span role="status" className="text-xs font-bold text-slate-500">{mesaj.duzenle}</span> : null}
        {duzenlenebilir && !duzenle ? (
          <button type="button" onClick={duzenlemeyiAc} className={DUGME}>
            <Pencil aria-hidden className="size-3.5" />
            {t.duzenle}
          </button>
        ) : null}
        {e.istirak_ekle && !k.cati ? (
          yeniIstirak === null ? (
            <button type="button" className={DUGME} onClick={() => setYeniIstirak("")}>
              <Plus aria-hidden className="size-3.5" />
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
        <button type="button" className={DUGME} aria-haspopup="dialog" onClick={() => setCiAcik(true)}>
          <ListChecks aria-hidden className="size-3.5" />
          {t.kritikCi}
          <span className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[0.625rem] text-slate-500">{kart.kritik_ci.satirlar.length}</span>
        </button>
        <a href={`#/${yol}?m=${k.id}&sekme=topoloji`} className={DUGME} title={t.topoAciklama}>
          <Network aria-hidden className="size-3.5" />
          {t.topoMaker}
        </a>
        {e.sil ? (
          <button type="button" onClick={() => void sil()} className="inline-flex items-center gap-1.5 rounded-xl border border-rose-200 bg-rose-500/10 px-4 py-2 text-xs font-bold text-rose-600 hover:bg-rose-500/20 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-rose-400">
            <Trash2 aria-hidden className="size-3.5" />
            {t.sil}
          </button>
        ) : null}
      </div>

      {/* OPERASYON (acik / yil ici kapanan dugmeleri) ve son raporlar yan yana: kart tek ekrana sigar */}
      <div className={`grid gap-3 ${kart.raporlar ? "lg:grid-cols-3" : ""}`}>
      <div className="lg:col-span-2">
        <Operasyon kart={kart} t={t} secim={secim} onSec={setSecim} />
      </div>
      {kart.raporlar ? (
        <Bolum anahtar="raporlar" baslik={`${t.raporlar} (${kart.raporlar.toplam})`} ek="[&>div]:!py-2">
          {kart.raporlar.son.length === 0 ? <Bos>{t.raporYok}</Bos> : null}
          {kart.raporlar.son.slice(0, 3).map((r, i) => (
            <div key={i} className="flex items-center justify-between gap-2 border-b border-slate-100 py-1.5 text-xs last:border-0">
              <span className="font-mono font-black text-slate-700">{r.donem}</span>
              <span className="truncate text-slate-400">{r.duzenleyen ?? ""}</span>
              {r.bayrak ? <span className="font-bold text-rose-600">⚑ {r.bayrak}</span> : null}
              <Rozet ton={r.gonderildi ? "yesil" : "gri"}>{r.gonderildi ? t.gonderildi : t.taslak}</Rozet>
            </div>
          ))}
        </Bolum>
      ) : null}
      </div>

      {/* Operasyon dugmesiyle acilan kayit listesi (secilen tur + acik / kapanan); acilinca sayfa uzar */}
      {secim ? <KartKayitlari key={`${secim.tur}-${secim.durum}`} dil={dil} id={k.id} tur={secim.tur} durum={secim.durum} onKapat={() => setSecim(null)} /> : null}

      <Cekmece acik={ciAcik} onKapat={() => setCiAcik(false)} baslik={t.kritikCi} aciklama={k.unvan} kapatEtiketi={t.kapat} genis>
        <MatrisTablo baslik={t.kritikCi} m={kart.kritik_ci} bos={t.satirYok} />
      </Cekmece>
    </div>
  )
}
