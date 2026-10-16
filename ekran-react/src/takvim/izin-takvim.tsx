import { useLayoutEffect, useRef, useState } from "react"
import type { FormEvent } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CalendarDays, CalendarRange, ChevronLeft, ChevronRight, ClipboardList, FileText, Umbrella, Users, Video } from "lucide-react"
import { Cekmece } from "@/components/cekmece"
import { Alan, Bildirim, DUGME, DUGME_SARI, GIRDI, HataKutu, SayfaKabi, Yukleniyor } from "@/components/sayfa-ui"
import { bugunYerel, sayi } from "@/lib/bicim"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"
import type { Ozet } from "@/takvim/takvim-grafigi"
import { DURUM_RENK, DURUM_SIRASI, gunZemini, takvimMetin } from "@/takvim/takvim-metin"
import { ILK_TARIH, ILK_YIL } from "@/lib/yillar"

/** kurum: ekipte herkeste ayni gun (Turkcell'li Takvimi; sunucu takvim/kurum_takvimi.py), "Varsayilana don" bu duruma doner. */
type Gun = {
  tarih: string
  durum: string
  durum2?: string // yarim gun: gunun ikinci yarisi (her yari 0,5 gun)
  online: number
  yuzyuze: number
  toplanti_ozeti?: string
  yapilan_isler?: string
  kurum?: { durum: string; aciklama: string; durum2?: string | null }
}

const EN_COK_OZET = 4000 // sunucudaki sinirla ayni (takvim/servis.py EN_COK_OZET); yapilan isler icin de
/** yil_ozet: ustteki sayilar kisinin YIL toplamidir (2026-10-15 kullanici istegi); gorunen = her gunun ekranda gorunen durumu. */
type Ay = { yil: number; ay: number; gunler: Gun[]; ozet: Ozet; yil_ozet?: Ozet & { gorunen: Record<string, number>; ozet_gunu?: number } }

function iso(y: number, a: number, g: number): string {
  return `${y}-${String(a).padStart(2, "0")}-${String(g).padStart(2, "0")}`
}

/** Gun durumu: tiklama tek durum secer; ikiYari iken Ctrl/⌘ ile tiklama ikinci yariyi ekler ya da kaldirir (yarim gun, kutu ikiye bolunur). */
function DurumSecici({
  deger,
  deger2 = null,
  onDegis,
  dil,
  etiket,
  ikiYari = false,
}: {
  deger: string
  deger2?: string | null
  onDegis: (d: string, d2: string | null) => void
  dil: Dil
  etiket: string
  ikiYari?: boolean
}) {
  const t = takvimMetin(dil)
  function sec(k: string, cift: boolean) {
    if (!cift || !ikiYari) return onDegis(k, null)
    if (k === deger2) return onDegis(deger, null)
    if (k === deger) return deger2 ? onDegis(deger2, null) : undefined
    onDegis(deger, k)
  }
  return (
    <fieldset className="grid gap-1.5">
      <legend className="mb-1 text-[0.625rem] font-black uppercase tracking-wide text-slate-500">{etiket}</legend>
      <div className="grid grid-cols-2 gap-2">
        {DURUM_SIRASI.map((k) => {
          const secili = deger === k || deger2 === k
          return (
            <button
              key={k}
              type="button"
              aria-pressed={secili}
              onClick={(e) => sec(k, e.ctrlKey || e.metaKey)}
              className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-left text-xs font-black transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow ${
                secili ? "border-tl-navy bg-tl-navy/5 text-tl-navy ring-1 ring-tl-navy" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
              }`}
            >
              <span aria-hidden className="size-3 shrink-0 rounded-full" style={{ background: DURUM_RENK[k] }} />
              {t.durumlar[k]}
              {secili && deger2 ? <span className="ml-auto font-mono text-[0.625rem]">½</span> : null}
            </button>
          )
        })}
      </div>
      {ikiYari ? <p className="text-[0.6875rem] font-semibold text-slate-500">{t.ikinciYari}</p> : null}
    </fieldset>
  )
}

/** Yazdikca ve Enter'a basildikca asagi uzayan metin kutusu (kaydiran cekmecenin icinde: kutu buyur, Kaydet yerinde kalir). */
function BuyuyenKutu({ deger, onDegis, ornek }: { deger: string; onDegis: (d: string) => void; ornek: string }) {
  const kutu = useRef<HTMLTextAreaElement>(null)
  useLayoutEffect(() => {
    const el = kutu.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${el.scrollHeight}px`
  }, [deger])
  return (
    <textarea
      ref={kutu}
      rows={3}
      maxLength={EN_COK_OZET}
      placeholder={ornek}
      className={`${GIRDI} resize-none overflow-hidden !py-2.5 !font-medium leading-relaxed`}
      value={deger}
      onChange={(e) => onDegis(e.target.value)}
    />
  )
}

function GunFormu({ tarih, gun, dil, onBitti }: { tarih: string; gun: Gun | undefined; dil: Dil; onBitti: () => void }) {
  const t = takvimMetin(dil)
  const qc = useQueryClient()
  const [durum, setDurum] = useState(gun?.durum ?? "calisiyor")
  const [durum2, setDurum2] = useState<string | null>(gun?.durum2 ?? null)
  const [online, setOnline] = useState(String(gun?.online ?? 0))
  const [yuzyuze, setYuzyuze] = useState(String(gun?.yuzyuze ?? 0))
  const [ozet, setOzet] = useState(gun?.toplanti_ozeti ?? "")
  const [isler, setIsler] = useState(gun?.yapilan_isler ?? "")
  const kaydet = useMutation({
    mutationFn: (govde: { durum: string; durum2: string | null; online: number; yuzyuze: number; toplanti_ozeti: string; yapilan_isler: string }) => yaz("PUT", "/api/v1/takvim/gun", { tarih, ...govde }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["takvim"] })
      onBitti()
    },
  })
  function gonder(olay: FormEvent) {
    olay.preventDefault()
    kaydet.mutate({ durum, durum2, online: Number(online) || 0, yuzyuze: Number(yuzyuze) || 0, toplanti_ozeti: ozet, yapilan_isler: isler })
  }
  return (
    <form onSubmit={gonder} className="grid gap-5">
      <DurumSecici
        deger={durum}
        deger2={durum2}
        ikiYari
        onDegis={(d, d2) => {
          setDurum(d)
          setDurum2(d2)
        }}
        dil={dil}
        etiket={t.durum}
      />
      <div className="grid grid-cols-2 gap-3">
        <Alan etiket={t.online}>
          <input type="number" min={0} max={50} className={`${GIRDI} !py-2.5 font-mono`} value={online} onChange={(e) => setOnline(e.target.value)} />
        </Alan>
        <Alan etiket={t.yuzyuze}>
          <input type="number" min={0} max={50} className={`${GIRDI} !py-2.5 font-mono`} value={yuzyuze} onChange={(e) => setYuzyuze(e.target.value)} />
        </Alan>
      </div>
      {kaydet.isError ? <Bildirim ton="kirmizi">{hataMesaji(kaydet.error, t.kaydedilemedi)}</Bildirim> : null}
      <div className="flex gap-2 border-t border-slate-100 pt-4">
        <button type="submit" className={`${DUGME_SARI} !min-w-0 flex-1`} disabled={kaydet.isPending}>
          {kaydet.isPending ? t.kaydediliyor : t.kaydet}
        </button>
        <button type="button" className={DUGME} disabled={kaydet.isPending} onClick={() => kaydet.mutate({ durum: gun?.kurum?.durum ?? "calisiyor", durum2: gun?.kurum?.durum2 ?? null, online: 0, yuzyuze: 0, toplanti_ozeti: "", yapilan_isler: "" })}>
          {t.varsayilanaDon}
        </button>
      </div>
      <Alan etiket={t.yapilanIsler} ipucu={t.yapilanIslerIpucu}>
        <BuyuyenKutu deger={isler} onDegis={setIsler} ornek={t.yapilanIslerOrnek} />
      </Alan>
      <Alan etiket={t.toplantiOzeti} ipucu={t.toplantiOzetiIpucu}>
        <BuyuyenKutu deger={ozet} onDegis={setOzet} ornek={t.toplantiOzetiOrnek} />
      </Alan>
    </form>
  )
}

function TopluFormu({ dil, baslangic, onBitti }: { dil: Dil; baslangic: string; onBitti: () => void }) {
  const t = takvimMetin(dil)
  const qc = useQueryClient()
  const [bas, setBas] = useState(baslangic)
  const [son, setSon] = useState(baslangic)
  const [durum, setDurum] = useState("yillik_izin")
  const [atla, setAtla] = useState(true)
  const uygula = useMutation({
    mutationFn: () => yaz<{ atanan: number }>("PUT", "/api/v1/takvim/toplu", { baslangic: bas, bitis: son, durum, hafta_sonu_atla: atla }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["takvim"] }),
  })
  return (
    <form
      className="grid gap-5"
      onSubmit={(e) => {
        e.preventDefault()
        uygula.mutate()
      }}
    >
      <p className="text-xs font-bold text-slate-500">{t.topluAciklama}</p>
      <div className="grid grid-cols-2 gap-3">
        <Alan etiket={t.baslangic}>
          <input type="date" required min={ILK_TARIH} className={`${GIRDI} !py-2.5`} value={bas} onChange={(e) => setBas(e.target.value)} />
        </Alan>
        <Alan etiket={t.bitis}>
          <input type="date" required min={bas} className={`${GIRDI} !py-2.5`} value={son} onChange={(e) => setSon(e.target.value)} />
        </Alan>
      </div>
      <DurumSecici deger={durum} onDegis={(d) => setDurum(d)} dil={dil} etiket={t.durum} />
      <label className="flex items-center gap-2 text-xs font-bold text-slate-700">
        <input type="checkbox" className="size-4 accent-[#002855]" checked={atla} onChange={(e) => setAtla(e.target.checked)} />
        {t.haftaSonuAtla}
      </label>
      {uygula.isError ? <Bildirim ton="kirmizi">{hataMesaji(uygula.error, t.kaydedilemedi)}</Bildirim> : null}
      {uygula.data ? <Bildirim ton="yesil">{t.atandi(uygula.data.atanan)}</Bildirim> : null}
      <div className="flex gap-2 border-t border-slate-100 pt-4">
        <button type="submit" className={`${DUGME_SARI} !min-w-0 flex-1`} disabled={uygula.isPending}>
          {uygula.isPending ? t.kaydediliyor : t.topluUygula}
        </button>
        <button type="button" className={DUGME} onClick={onBitti}>
          {t.kapat}
        </button>
      </div>
    </form>
  )
}

type Sayac = { kod: string; etiket: string; deger: string | number; renk?: string; ikon?: typeof Video; ikonSinif?: string }

/** Gosterim: takvime veri girilen her alanin bu aydaki toplam adedi, KPI karosu biciminde. Renk noktasi ya da simge gun kutusundakiyle aynidir,
 * boylece kutucuklar ayni zamanda takvimin gosterimidir. Gun durumu sayilari ekranda gorunen durumdur (kayitsiz is gunu Calisiyor, hafta sonu Hafta Sonu). */
function Gosterim({ t, sayaclar, baslik }: { t: ReturnType<typeof takvimMetin>; sayaclar: Sayac[]; baslik: string }) {
  return (
    <section aria-label={t.simgeler} title={baslik} className="grid shrink-0 grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
      {sayaclar.map(({ kod, etiket, deger, renk, ikon: Ikon, ikonSinif }) => (
        <div key={kod} role="group" aria-label={`${etiket}: ${deger}`} className="relative min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-gradient-to-br from-slate-50 to-white px-3 py-2 shadow-sm">
          <div className="flex min-w-0 items-center gap-1.5">
            {Ikon ? <Ikon aria-hidden className={`size-3.5 shrink-0 ${ikonSinif ?? ""}`} /> : <span aria-hidden className="size-2.5 shrink-0 rounded-full" style={{ background: renk }} />}
            <span className="truncate text-[0.625rem] font-black uppercase text-slate-500" title={etiket}>
              {etiket}
            </span>
          </div>
          <div className="mt-1 font-mono text-xl font-black leading-none text-tl-navy">{deger}</div>
        </div>
      ))}
    </section>
  )
}

/** Izin&Takvim Yonetimi: giris yapan kisinin kendi takvimi (gun durumu, izin, toplanti, toplanti ozeti, yapilan isler; tek gun ya da toplu aralik).
 * Baskasinin verisi burada gorunmez. Sayfa tek ekrandir: ay izgarasi kalan yuksekligi doldurur, kaydirma cubugu cikmaz. */
export function IzinTakvim({ dil }: { dil: Dil }) {
  const t = takvimMetin(dil)
  const simdi = new Date()
  const [yil, setYil] = useState(simdi.getFullYear())
  const [ay, setAy] = useState(simdi.getMonth() + 1)
  const [secili, setSecili] = useState<string | null>(null)
  const [toplu, setToplu] = useState(false)
  const bugun = bugunYerel()

  const q = useQuery({ queryKey: ["takvim", "ben", yil, ay], queryFn: () => oku<Ay>(`/api/v1/takvim/ben?yil=${yil}&ay=${ay}`) })
  const gunler = new Map((q.data?.gunler ?? []).map((g) => [g.tarih, g]))
  const ilkGun = (new Date(yil, ay - 1, 1).getDay() + 6) % 7
  const gunSayisi = new Date(yil, ay, 0).getDate()
  const hucreler: (number | null)[] = [...Array<null>(ilkGun).fill(null), ...Array.from({ length: gunSayisi }, (_, i) => i + 1)]
  const haftaSayisi = Math.ceil(hucreler.length / 7)

  const ilkAy = yil === ILK_YIL && ay === 1 // 2026 oncesine gidilmez
  function git(fark: number) {
    const d = new Date(yil, ay - 1 + fark, 1)
    if (d.getFullYear() < ILK_YIL) return
    setYil(d.getFullYear())
    setAy(d.getMonth() + 1)
  }
  // Gosterim sayilari kisinin YIL toplami (sunucu yil_ozet): gun durumu ekranda gorunen haliyle (kayitsiz gun is gunu ya da hafta sonu,
  // yarim gun 0,5), metin alanlari dolu gun sayisi
  const o = q.data?.yil_ozet
  const durumSayisi: Record<string, number> = { ...Object.fromEntries(DURUM_SIRASI.map((k) => [k, 0])), ...o?.gorunen }
  const ozetGunu = o?.ozet_gunu ?? 0
  const isGunu = o?.is_gunu ?? 0
  const hazir = q.data !== undefined
  const sayaclar: Sayac[] = [
    { kod: "izin", etiket: t.izinGunu, deger: hazir ? sayi(o?.izin_gun) : "—", ikon: Umbrella, ikonSinif: "text-amber-500" },
    { kod: "online", etiket: t.toplantiOnline, deger: hazir ? (o?.online ?? 0) : "—", ikon: Video, ikonSinif: "text-tl-blue" },
    { kod: "yuzyuze", etiket: t.kutuYuzYuze, deger: hazir ? (o?.yuzyuze ?? 0) : "—", ikon: Users, ikonSinif: "text-emerald-600" },
    { kod: "ozet", etiket: t.toplantiOzeti, deger: hazir ? ozetGunu : "—", ikon: FileText, ikonSinif: "text-slate-500" },
    { kod: "isler", etiket: t.yapilanIsler, deger: hazir ? isGunu : "—", ikon: ClipboardList, ikonSinif: "text-tl-navy" },
    ...DURUM_SIRASI.filter((k) => k !== "calisiyor").map((k) => ({ kod: k, etiket: t.durumlar[k], deger: hazir ? durumSayisi[k] : "—", renk: DURUM_RENK[k] })),
    { kod: "calisiyor", etiket: t.durumlar.calisiyor, deger: hazir ? durumSayisi.calisiyor : "—", renk: DURUM_RENK.calisiyor },
  ]

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <SayfaKabi ikon={CalendarDays} baslik={t.izinBaslik} aciklama={t.izinAciklama}>
        <button type="button" className={DUGME} onClick={() => setToplu(true)}>
          <CalendarRange aria-hidden className="size-4" />
          {t.topluAtama}
        </button>
      </SayfaKabi>

      <Gosterim t={t} sayaclar={sayaclar} baslik={t.yilToplami(yil)} />

      <section className="flex min-h-[24rem] flex-1 flex-col rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
        <div className="mb-2 flex shrink-0 flex-wrap items-center justify-between gap-2">
          <h3 className="text-base font-black text-tl-navy">
            {t.aylar[ay - 1]} {yil}
          </h3>
          <div className="flex items-center gap-2">
            <button type="button" className={`${DUGME} !px-2.5 !py-1.5`} onClick={() => git(-1)} disabled={ilkAy} aria-label={t.oncekiAy}>
              <ChevronLeft aria-hidden className="size-4" />
            </button>
            <button
              type="button"
              className={`${DUGME} !py-1.5`}
              onClick={() => {
                setYil(simdi.getFullYear())
                setAy(simdi.getMonth() + 1)
              }}
            >
              {t.bugun}
            </button>
            <button type="button" className={`${DUGME} !px-2.5 !py-1.5`} onClick={() => git(1)} aria-label={t.sonrakiAy}>
              <ChevronRight aria-hidden className="size-4" />
            </button>
          </div>
        </div>

        {q.isPending ? (
          <Yukleniyor metin="…" />
        ) : q.isError ? (
          <HataKutu metin={t.yuklenemedi} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
        ) : (
          <>
            <div className="grid shrink-0 grid-cols-7 gap-1 text-center text-[0.6875rem] font-black uppercase tracking-wide text-slate-500">
              {t.gunler.map((g) => (
                <span key={g}>{g}</span>
              ))}
            </div>
            <div className="mt-1 grid min-h-0 flex-1 grid-cols-7 gap-1" style={{ gridTemplateRows: `repeat(${haftaSayisi}, minmax(0, 1fr))` }}>
              {hucreler.map((g, i) => {
                if (g === null) return <span key={`b${i}`} aria-hidden />
                const tarih = iso(yil, ay, g)
                const kayit = gunler.get(tarih)
                const haftaSonu = (ilkGun + g - 1) % 7 >= 5
                const durum = kayit?.durum ?? (haftaSonu ? "hafta_sonu" : "calisiyor")
                const durum2 = kayit?.durum2
                const renkli = (kayit !== undefined && durum !== "calisiyor") || durum2 !== undefined // ust bardaki renkle dolu kutu
                const kurumAdi = kayit?.kurum && kayit.kurum.durum === durum && (kayit.kurum.durum2 ?? undefined) === durum2 ? kayit.kurum.aciklama : ""
                const durumAdi = durum2 ? `${t.durumlar[durum]} / ${t.durumlar[durum2]}` : t.durumlar[durum]
                const ipucu = [kurumAdi, kayit?.yapilan_isler, kayit?.toplanti_ozeti].filter(Boolean).join("\n\n")
                return (
                  <button
                    key={tarih}
                    type="button"
                    onClick={() => setSecili(tarih)}
                    aria-label={`${g} ${t.aylar[ay - 1]}: ${durumAdi}${kurumAdi ? ` (${kurumAdi})` : ""}${kayit && kayit.online + kayit.yuzyuze > 0 ? `, ${kayit.online}/${kayit.yuzyuze}` : ""}${kayit?.toplanti_ozeti ? `, ${t.toplantiOzeti}` : ""}${kayit?.yapilan_isler ? `, ${t.yapilanIsler}` : ""}`}
                    title={ipucu || undefined}
                    className={`flex min-h-0 flex-col items-stretch gap-0.5 overflow-hidden rounded-lg border px-1.5 py-1 text-left transition-shadow hover:shadow-md focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow ${
                      tarih === bugun ? "border-tl-navy ring-2 ring-tl-yellow/70" : "border-slate-200"
                    } ${renkli ? "text-white" : ""}`}
                    style={{ background: gunZemini(durum, durum2, renkli), borderColor: renkli ? DURUM_RENK[durum] : undefined }}
                  >
                    <span className="flex items-center justify-between gap-1">
                      <span className={`font-mono text-sm font-black leading-none ${renkli ? "text-white" : tarih === bugun ? "text-tl-navy" : haftaSonu ? "text-slate-500" : "text-slate-700"}`}>{g}</span>
                      <span className="flex items-center gap-0.5">
                        {kayit?.yapilan_isler ? <ClipboardList aria-hidden className={`size-3.5 ${renkli ? "text-white" : "text-tl-navy"}`} /> : null}
                        {kayit?.toplanti_ozeti ? <FileText aria-hidden className={`size-3.5 ${renkli ? "text-white" : "text-slate-500"}`} /> : null}
                      </span>
                    </span>
                    <span className={`flex min-w-0 items-center gap-1 text-[0.6875rem] font-bold leading-tight ${renkli ? "text-white" : "text-slate-600"}`}>
                      <span aria-hidden className={`size-2 shrink-0 rounded-full ${renkli ? "ring-1 ring-white" : ""}`} style={{ background: DURUM_RENK[durum] }} />
                      <span className="hidden truncate sm:inline">{kurumAdi || durumAdi}</span>
                    </span>
                    {kayit && kayit.online + kayit.yuzyuze > 0 ? (
                      <span className="flex flex-wrap gap-1 font-mono text-xs font-black">
                        {kayit.online > 0 ? (
                          <span className="inline-flex items-center gap-0.5 rounded-full bg-tl-blue px-1.5 py-0.5 leading-none text-white shadow-sm ring-1 ring-white">
                            <Video aria-hidden className="size-3.5" strokeWidth={2.75} />
                            {kayit.online}
                          </span>
                        ) : null}
                        {kayit.yuzyuze > 0 ? (
                          <span className="inline-flex items-center gap-0.5 rounded-full bg-emerald-600 px-1.5 py-0.5 leading-none text-white shadow-sm ring-1 ring-white">
                            <Users aria-hidden className="size-3.5" strokeWidth={2.75} />
                            {kayit.yuzyuze}
                          </span>
                        ) : null}
                      </span>
                    ) : null}
                  </button>
                )
              })}
            </div>
          </>
        )}
      </section>

      <Cekmece acik={secili !== null} onKapat={() => setSecili(null)} baslik={t.gunDuzenle} aciklama={secili ? `${secili.slice(8, 10)} ${t.aylar[Number(secili.slice(5, 7)) - 1]} ${secili.slice(0, 4)}` : undefined} kapatEtiketi={t.kapat}>
        {secili ? <GunFormu key={secili} tarih={secili} gun={gunler.get(secili)} dil={dil} onBitti={() => setSecili(null)} /> : null}
      </Cekmece>
      <Cekmece acik={toplu} onKapat={() => setToplu(false)} baslik={t.topluAtama} kapatEtiketi={t.kapat}>
        {toplu ? <TopluFormu dil={dil} baslangic={bugun} onBitti={() => setToplu(false)} /> : null}
      </Cekmece>
    </div>
  )
}
