import { useEffect, useMemo, useRef, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import type { FormEvent, ReactNode } from "react"
import { ApiHata, hataMesaji, oku, yaz } from "@/lib/sorgu"
import { Bos, DUGME, DUGME_ANA, DUGME_SARI, GIRDI, Rozet } from "@/components/sayfa-ui"
import type { Dil } from "@/shell/metin"
import { musteriMetin } from "@/musteri/musteri-metin"
import { RaporOnizleme } from "@/musteri/rapor-onizleme"
import type { RaporGrafigi } from "@/musteri/rapor-onizleme"
import { blobBase64, dosyaIndir, raporPdfOlustur, seriGrafigi } from "@/musteri/rapor-pdf"
import { EkDosyaKarti, GalapagosKarti, SlaKarti } from "@/musteri/sla-paneli"
import type { SlaVeri } from "@/musteri/sla-paneli"
import { SlaAnalizi } from "@/musteri/sla-analizi"
import { CactiKarti, useCacti } from "@/musteri/cacti-paneli"
import type { AnalizMetni } from "@/musteri/sla-analizi"

type Gonderim = { id: number; yil: number; ay: number; gonderen: string; zaman: string; konu: string; durum: string; pdf: boolean; geri_alan: string | null }
type Taslak = {
  yil: number
  ay: number
  birim: boolean
  alanlar: Record<string, string>
  /** Hazir metinler iki dilde: rapor dili degisince personelin degistirmedigi alanlar karsiligiyla degisir. */
  varsayilanlar: Record<"tr" | "en", Record<string, string>>
  kayitli: boolean
  guncelleyen: string | null
  zaman: string | null
  alicilar: { kime: string; bilgi: string }
  gonderim: Gonderim | null
  /** Bu donemin taslagi yokken onceki ayin gonderilmis raporundan tasinan takip alanlari. */
  devreden?: { donem: string; alanlar: string[] } | null
  /** eml: Outlook taslagi iner (varsayilan); smtp: ileti sunucudan TAMLIFE@ kutusundan gider (rapor/smtp_gonderim.py). */
  gonderim_kipi?: "eml" | "smtp"
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

type GonderSonuc = { kip?: "eml" | "smtp"; eml_adi?: string; eml_base64?: string; reddedilen?: string[] }
type RaporDili = "tr" | "en"

/** Sunucunun urettigi Outlook taslagini indirir; tarayici ayarliysa Outlook dogrudan acar (X-Unsent: gonderilmemis ileti). */
function emlIndir(eml_base64: string, eml_adi: string) {
  const bayt = Uint8Array.from(atob(eml_base64), (c) => c.charCodeAt(0))
  dosyaIndir(new Blob([bayt], { type: "message/rfc822" }), eml_adi)
}

/** Sunucudaki eposta.dosya_adi ile ayni kok: TAM_Aylik_Rapor_<unvan>. */
function pdfAdi(unvan: string): string {
  const temiz = unvan.replace(/[^\p{L}\p{N}_\s-]/gu, "").trim().replace(/ /g, "_") || "musteri"
  return `TAM_Aylik_Rapor_${temiz.slice(0, 80)}.pdf`
}

/** Rapor dilini degistirir: bos ya da eski dilin hazir metniyle ayni alanlar yeni dilin karsiligini alir; personelin yazdigi metne dokunulmaz. */
export function dilUygula(alanlar: Record<string, string>, varsayilanlar: Taslak["varsayilanlar"], yeni: RaporDili): Record<string, string> {
  const eski: RaporDili = alanlar.dil === "en" ? "en" : "tr"
  if (eski === yeni) return alanlar
  const sonuc: Record<string, string> = { ...alanlar, dil: yeni }
  for (const [anahtar, deger] of Object.entries(varsayilanlar[eski] ?? {})) {
    const simdiki = alanlar[anahtar] ?? ""
    if (!simdiki.trim() || simdiki === deger) sonuc[anahtar] = varsayilanlar[yeni]?.[anahtar] ?? simdiki
  }
  return sonuc
}

/** Elle yazilmis (hazir metinden farkli, bos olmayan) alanlar: ceviriye yalniz bunlar gider. */
/**
 * SLA ozetini alana yazar: alan bos ya da hazir metinse ozet yerine gecer; onceki ozet hala alandaysa yenisiyle degisir
 * (tekrar basinca cogalmaz); personel baska metin yazdiysa altina eklenir.
 */
export function ozetiYerlestir(simdiki: string, yeni: string, onceki: string | undefined, varsayilanlar: string[]): string {
  const metin = simdiki.trim()
  if (!yeni.trim()) return simdiki
  if (!metin || varsayilanlar.includes(metin)) return yeni.trim()
  if (onceki && simdiki.includes(onceki)) return simdiki.replace(onceki, yeni.trim())
  if (simdiki.includes(yeni.trim())) return simdiki
  return [simdiki.trimEnd(), yeni.trim()].join("\n\n")
}

export function elleYazilanlar(alanlar: Record<string, string>, varsayilanlar: Taslak["varsayilanlar"]): Record<string, string> {
  const sonuc: Record<string, string> = {}
  for (const [anahtar, deger] of Object.entries(alanlar)) {
    if (anahtar === "dil" || !deger.trim()) continue
    if (deger === varsayilanlar.en?.[anahtar] || deger === varsayilanlar.tr?.[anahtar]) continue
    sonuc[anahtar] = deger
  }
  return sonuc
}

const LEJANT = {
  tr: { ilk: "Çağrı Ortalama İlk Müdahale Süresi (dk)", cozum: "Çağrı Ortalama Çözüm Süresi (dk)" },
  en: { ilk: "Average First Response Time (min)", cozum: "Average Resolution Time (min)" },
}

/** Musteri kartinin arkasindaki aylik rapor: sol 2/3 rapor formu, sag 1/3 gecmis ve alicilar (eski panel duzeni). */
export function AylikRapor({ musteriId, musteriAdi, dil, geriAlabilir }: { musteriId: number; musteriAdi: string; dil: Dil; geriAlabilir: boolean }) {
  const t = musteriMetin(dil)
  const taban = `/api/v1/musteri/${musteriId}/rapor`
  const istemci = useQueryClient()
  const cacti = useCacti(taban)
  const slaAnahtari = ["musteri", "rapor", musteriId, "sla"]
  const taslakQ = useQuery({ queryKey: ["musteri", "rapor", musteriId, "taslak"], queryFn: () => oku<Taslak>(`${taban}/taslak`) })
  const gecmisQ = useQuery({ queryKey: ["musteri", "rapor", musteriId, "gecmis"], queryFn: () => oku<Gonderim[]>(`${taban}/gecmis`) })
  const slaQ = useQuery({ queryKey: slaAnahtari, queryFn: () => oku<SlaVeri>(`${taban}/sla`) })
  const taslak = taslakQ.data
  const gecmis = gecmisQ.data ?? []
  const sla = slaQ.data
  const [alanlar, setAlanlar] = useState<Record<string, string>>({})
  const [alici, setAlici] = useState({ kime: "", bilgi: "" })
  const [mesaj, setMesaj] = useState<Record<string, string>>({})
  const [onizlemeAcik, setOnizlemeAcik] = useState(false)
  const [pdfMesgul, setPdfMesgul] = useState(false)
  const [ceviriMesgul, setCeviriMesgul] = useState(false)
  const sablon = useRef<HTMLDivElement>(null)
  const yuklenen = useRef("")
  const oncekiDil = useRef(dil)
  const sonOzet = useRef<Partial<AnalizMetni>>({})

  // Sunucudaki taslak yalniz yeni bir surum geldiginde forma yazilir: panel dili degisince sorgu yenilenir, yazilan metin kaybolmasin.
  useEffect(() => {
    if (!taslak) return
    const surum = `${taslak.yil}-${taslak.ay}|${taslak.zaman ?? ""}|${taslak.gonderim?.id ?? ""}`
    if (yuklenen.current === surum) return
    yuklenen.current = surum
    setAlanlar(taslak.alanlar)
    setAlici({ kime: taslak.alicilar.kime, bilgi: taslak.alicilar.bilgi })
  }, [taslak])

  // Panel Ingilizceye (ya da Turkceye) alininca rapor da o dile gecer; hazir metinler karsiliklariyla degisir.
  useEffect(() => {
    if (oncekiDil.current === dil) return
    oncekiDil.current = dil
    if (taslak && !taslak.gonderim) setAlanlar((a) => dilUygula(a, taslak.varsayilanlar, dil === "en" ? "en" : "tr"))
  }, [dil, taslak])

  const raporDili: RaporDili = (alanlar.dil ?? "tr") === "en" ? "en" : "tr"
  const grafikler = useMemo<RaporGrafigi[]>(
    () =>
      (sla?.analiz?.grafikler ?? []).flatMap((g) => {
        const gorsel = g.gorsel ?? seriGrafigi(g, LEJANT[raporDili])
        return gorsel ? [{ anahtar: g.anahtar, baslik: g.baslik[raporDili] || g.pivot || "", gorsel }] : []
      }),
    [sla, raporDili],
  )
  const ekGorseller = useMemo<RaporGrafigi[]>(() => [...cacti.grafikler, ...(sla?.ekler ?? []).map((e) => ({ anahtar: `ek-${e.no}`, baslik: e.baslik, gorsel: e.gorsel }))], [sla, cacti.grafikler])

  const yukle = () => Promise.all([taslakQ.refetch(), gecmisQ.refetch()])
  const bildir = (anahtar: string, metin: string) => setMesaj((m) => ({ ...m, [anahtar]: metin }))
  /** Sonucu ilgili alana yazar; `kilit`: 409 (gonderilmis donem) icin ozel mesaj. */
  async function dene(anahtar: string, istek: () => Promise<unknown>, basari: string, kilit = false): Promise<boolean> {
    try {
      await istek()
      bildir(anahtar, basari)
      return true
    } catch (h) {
      bildir(anahtar, kilit && h instanceof ApiHata && h.durum === 409 ? t.gonderimKilitli : hataMesaji(h, t.kaydedilemedi))
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
  const ingilizce = raporDili === "en"
  const smtpKipi = taslak.gonderim_kipi === "smtp"
  const varsayilanlar = taslak.varsayilanlar
  const donemAdi = (d: Dil) => `${musteriMetin(d).aylar[taslak.ay - 1]} ${taslak.yil}`
  const donemYaz = (donem: string, d: Dil) => `${musteriMetin(d).aylar[Number(donem.slice(5, 7)) - 1] ?? ""} ${donem.slice(0, 4)}`

  async function pdfUret(): Promise<Blob> {
    if (!sablon.current || cacti.engel) throw new Error("pdf")
    return raporPdfOlustur(sablon.current)
  }

  async function pdfIndir() {
    setPdfMesgul(true)
    try {
      dosyaIndir(await pdfUret(), pdfAdi(musteriAdi))
      bildir("pdf", "")
    } catch {
      bildir("pdf", t.pdfHata)
    } finally {
      setPdfMesgul(false)
    }
  }

  async function taslagiKaydet(olay?: FormEvent) {
    olay?.preventDefault()
    if (await dene("taslak", () => yaz("PUT", `${taban}/taslak`, { alanlar }), t.kaydedildi, true)) await yukle()
  }

  async function alicilariKaydet(olay: FormEvent) {
    olay.preventDefault()
    await dene("alici", () => yaz("PUT", `${taban}/alicilar`, alici), t.kaydedildi)
  }

  /** Rapor PDF'i panelde uretilir ve SLA Excel'iyle birlikte iletiye eklenir (SLA ekini sunucu koyar). */
  async function gonder() {
    const onay = t.gonderOnay(donemAdi(dil), !!sla?.ozet?.dosya, sla?.dosyalar.length ?? 0)
    if (!window.confirm(smtpKipi ? `${onay}\n\n${t.smtpOnay}` : onay)) return
    setPdfMesgul(true)
    let pdfVeri: string
    try {
      pdfVeri = await blobBase64(await pdfUret())
    } catch {
      bildir("gonder", t.pdfHata)
      setPdfMesgul(false)
      return
    }
    const govde = { onay: true, subject: alanlar.konu, body_text: alanlar.govde, signature: alanlar.imza, lang: raporDili, pdf_base64: pdfVeri, alanlar }
    let sonuc: GonderSonuc = {}
    const tamam = await dene("gonder", async () => {
      sonuc = await yaz<GonderSonuc>("POST", `${taban}/gonder`, govde)
      if (sonuc.eml_base64 && sonuc.eml_adi) emlIndir(sonuc.eml_base64, sonuc.eml_adi)
    }, t.emlIndi, true)
    if (tamam && sonuc.kip === "smtp") bildir("gonder", t.epostaGitti(sonuc.reddedilen ?? []))
    setPdfMesgul(false)
    await yukle()
  }

  async function geriAl(id: number) {
    if (!window.confirm(t.geriAlOnay)) return
    await dene("gecmis", () => yaz("POST", `/api/v1/rapor/gonderim/${id}/geri-al`), "")
    await yukle()
  }

  /** Personelin yazdigi metinler Ingilizceye (sunucu: cevrimdisi model, yoksa YZ). Yalniz cevrilen alanlar degisir. */
  async function metinleriCevir() {
    const kaynak = elleYazilanlar(alanlar, varsayilanlar)
    if (!Object.keys(kaynak).length) {
      bildir("taslak", t.cevrilecekYok)
      return
    }
    setCeviriMesgul(true)
    try {
      const sonuc = await yaz<{ alanlar: Record<string, string> }>("POST", `${taban}/cevir`, { alanlar: kaynak })
      setAlanlar((a) => {
        const yeni = { ...a }
        // Ceviri surerken alan degistiyse personelin son hali korunur.
        for (const [k, v] of Object.entries(sonuc.alanlar)) if (a[k] === kaynak[k]) yeni[k] = v
        return yeni
      })
      bildir("taslak", t.cevrildi(Object.keys(sonuc.alanlar).length))
    } catch (h) {
      bildir("taslak", hataMesaji(h, t.kaydedilemedi))
    } finally {
      setCeviriMesgul(false)
    }
  }

  const alanYaz = (anahtar: string, deger: string) => setAlanlar((a) => ({ ...a, [anahtar]: deger }))
  function ozetiYaz(metin: AnalizMetni) {
    setAlanlar((a) => {
      const sonuc = { ...a }
      for (const anahtar of ["bilgi", "devam"] as const) {
        const hazir = [varsayilanlar.tr?.[anahtar], varsayilanlar.en?.[anahtar]].filter((v): v is string => !!v).map((v) => v.trim())
        sonuc[anahtar] = ozetiYerlestir(a[anahtar] ?? "", metin[anahtar], sonOzet.current[anahtar], hazir)
      }
      return sonuc
    })
    sonOzet.current = { bilgi: metin.bilgi.trim(), devam: metin.devam.trim() }
  }
  const g = taslak.gonderim
  const slaOrtak = { taban, t, veri: sla, kilitli: !!g, onDegisti: (v: SlaVeri) => istemci.setQueryData(slaAnahtari, v) }

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
            {taslak.devreden && !g ? (
              <p role="status" className="rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-bold text-amber-800">
                {t.devreden(donemYaz(taslak.devreden.donem, dil))}
              </p>
            ) : null}
            {!taslak.birim ? <p className="rounded-xl border bg-slate-50 p-3 text-xs text-slate-600">{t.rapordaBirimDegil}</p> : null}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <label className="flex cursor-pointer select-none items-center gap-2">
                <input type="checkbox" className="size-4 accent-tl-navy" disabled={!!g} checked={ingilizce} onChange={(ev) => setAlanlar((a) => dilUygula(a, taslak.varsayilanlar, ev.target.checked ? "en" : "tr"))} />
                <span className="text-xs font-black text-tl-navy">{t.ingilizceRapor}</span>
              </label>
              <span className="rounded-lg bg-tl-yellow/30 px-2 py-1 text-xs font-black text-tl-navy">
                {t.raporDonemi}: {donemAdi(dil)}
              </span>
              {ingilizce && !g ? (
                <button type="button" className={`${DUGME} px-2 py-1 text-[0.6875rem]`} disabled={ceviriMesgul} onClick={() => void metinleriCevir()}>
                  {ceviriMesgul ? t.ceviriyor : t.cevir}
                </button>
              ) : null}
              <div className="ml-auto flex items-center gap-2">
                <button type="button" className={`${DUGME} border-tl-navy/30 font-black`} disabled={!!g} onClick={() => void taslagiKaydet()}>
                  {t.taslagiKaydet}
                </button>
                <button type="button" className={DUGME_SARI} disabled={!!g || pdfMesgul || cacti.engel} onClick={() => void gonder()}>
                  {t.gonder}
                </button>
              </div>
            </div>
            <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
              <span role="status" className="min-h-[14px] text-[0.625rem] font-bold text-slate-400">
                {(pdfMesgul ? t.pdfHazirlaniyor : "") || mesaj.taslak || mesaj.gonder || (taslak.kayitli ? `${t.taslakBilgi}: ${(taslak.zaman ?? "").slice(0, 16).replace("T", " ")} · ${taslak.guncelleyen ?? ""}` : "")}
              </span>
              <p className="text-[0.625rem] font-bold text-slate-400 sm:max-w-[60%] sm:text-right">{smtpKipi ? t.smtpNot : t.emlNot}</p>
            </div>
            {cacti.engel && !g && !cacti.ayar.isPending && !cacti.grafik.isFetching ? (
              <p role="status" className="rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-bold text-amber-800">
                {t.cactiBekliyor}
              </p>
            ) : null}
          </div>

          <form onSubmit={taslagiKaydet} className="space-y-5 text-xs font-bold" aria-label={t.raporIcerigi}>
            <div className="space-y-3 rounded-xl border border-tl-blue/20 bg-slate-50 p-4">
              <p className="text-[0.625rem] font-black uppercase tracking-wider text-tl-navy">{t.mailBlogu}</p>
              <div className="grid gap-1.5">
                <label htmlFor="r-konu" className="text-[0.625rem] font-extrabold uppercase tracking-wider text-tl-navy">
                  {t.konu}
                </label>
                <input id="r-konu" disabled={!!g} maxLength={200} value={alanlar.konu ?? ""} onChange={(ev) => alanYaz("konu", ev.target.value)} className={GIRDI} />
              </div>
              <div className="grid gap-1.5">
                <label htmlFor="r-govde" className="text-[0.625rem] font-extrabold uppercase tracking-wider text-tl-navy">
                  {t.govde}
                </label>
                <textarea id="r-govde" rows={8} maxLength={10000} disabled={!!g} value={alanlar.govde ?? ""} onChange={(ev) => alanYaz("govde", ev.target.value)} className={GIRDI} />
              </div>
              <div className="grid gap-1.5">
                <label htmlFor="r-imza" className="text-[0.625rem] font-extrabold uppercase tracking-wider text-tl-navy">
                  {t.imza}
                </label>
                <textarea id="r-imza" rows={3} maxLength={2000} disabled={!!g} value={alanlar.imza ?? ""} onChange={(ev) => alanYaz("imza", ev.target.value)} className={GIRDI} />
              </div>
            </div>

            {METINLER.map((m) => (
              <div key={m.alan} className="space-y-1.5">
                <label htmlFor={`r-${m.alan}`} className={`flex items-center gap-2 text-[0.6875rem] font-extrabold uppercase tracking-wider ${m.renk}`}>
                  <span aria-hidden className="size-1.5 rounded-full bg-current" />
                  {t[m.alan]}
                </label>
                <textarea id={`r-${m.alan}`} rows={m.satir} maxLength={m.uzun} disabled={!!g} value={alanlar[m.alan] ?? ""} onChange={(ev) => alanYaz(m.alan, ev.target.value)} className={GIRDI} />
              </div>
            ))}
          </form>

        </Kart>

        <Kart ek="space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <Baslik baslik={t.onizleme} alt={t.onizlemeAlt} />
            <div className="flex items-center gap-2">
              <button type="button" className={DUGME} aria-expanded={onizlemeAcik} onClick={() => setOnizlemeAcik((a) => !a)}>
                {onizlemeAcik ? t.onizlemeKapat : t.onizlemeAc}
              </button>
              <button type="button" className={DUGME_ANA} disabled={pdfMesgul || cacti.engel} onClick={() => void pdfIndir()}>
                {pdfMesgul ? t.pdfHazirlaniyor : t.pdfIndir}
              </button>
            </div>
          </div>
          {mesaj.pdf ? (
            <p role="alert" className="text-xs font-bold text-destructive">
              {mesaj.pdf}
            </p>
          ) : null}
          {/* Sablon hep cizilir (PDF kapali onizlemede de uretilir); kapaliyken ekran disinda durur. */}
          <div
            className={onizlemeAcik ? "overflow-x-auto rounded-xl bg-slate-200 p-4" : "pointer-events-none fixed top-0 -left-[10000px]"}
            aria-hidden={!onizlemeAcik}
          >
            <div className="flex justify-center">
              <div className="shadow-2xl">
                <RaporOnizleme
                  ref={sablon}
                  musteriAdi={musteriAdi}
                  donem={donemAdi(raporDili)}
                  dil={raporDili}
                  alanlar={alanlar}
                  grafikler={grafikler}
                  ekler={ekGorseller}
                />
              </div>
            </div>
          </div>
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
                  {t.aylar[x.ay - 1]} / {x.yil}
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
            <p className="text-[0.625rem] text-slate-400">{t.alicilarAyrac}</p>
            <div className="flex items-center gap-3">
              <button type="submit" className={DUGME_ANA}>
                {t.alicilariKaydet}
              </button>
              {mesaj.alici ? <span role="status" className="text-xs font-bold text-slate-500">{mesaj.alici}</span> : null}
            </div>
          </form>
        </Kart>

        <SlaKarti {...slaOrtak} />
        <SlaAnalizi taban={taban} t={t} dil={raporDili} slaVar={!!sla?.ozet?.dosya} yzHazir={!!sla?.araclar?.yz} kilitli={!!g} onYaz={ozetiYaz} />
        <CactiKarti cacti={cacti} ingilizce={dil === "en"} />
        <GalapagosKarti {...slaOrtak} />
        <EkDosyaKarti {...slaOrtak} />
      </div>
    </div>
  )
}
