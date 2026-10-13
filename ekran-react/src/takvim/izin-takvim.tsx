import { useLayoutEffect, useRef, useState } from "react"
import type { FormEvent } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CalendarDays, CalendarRange, ChevronLeft, ChevronRight, FileText, Presentation, Umbrella, Users, Video } from "lucide-react"
import { Cekmece } from "@/components/cekmece"
import { Alan, Bildirim, DUGME, DUGME_SARI, GIRDI, HataKutu, Kpi, SayfaKabi, Yukleniyor } from "@/components/sayfa-ui"
import { bugunYerel, sayi } from "@/lib/bicim"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"
import type { Ozet } from "@/takvim/takvim-grafigi"
import { DURUM_RENK, DURUM_SIRASI, takvimMetin } from "@/takvim/takvim-metin"
import { ILK_TARIH, ILK_YIL } from "@/lib/yillar"

type Gun = { tarih: string; durum: string; online: number; yuzyuze: number; toplanti_ozeti?: string }

const EN_COK_OZET = 4000 // sunucudaki sinirla ayni (takvim/servis.py EN_COK_OZET)
type Ay = { yil: number; ay: number; gunler: Gun[]; ozet: Ozet }

function iso(y: number, a: number, g: number): string {
  return `${y}-${String(a).padStart(2, "0")}-${String(g).padStart(2, "0")}`
}

function DurumSecici({ deger, onDegis, dil, etiket }: { deger: string; onDegis: (d: string) => void; dil: Dil; etiket: string }) {
  const t = takvimMetin(dil)
  return (
    <fieldset className="grid gap-1.5">
      <legend className="mb-1 text-[0.625rem] font-black uppercase tracking-wide text-slate-500">{etiket}</legend>
      <div className="grid grid-cols-2 gap-2">
        {DURUM_SIRASI.map((k) => (
          <button
            key={k}
            type="button"
            aria-pressed={deger === k}
            onClick={() => onDegis(k)}
            className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-left text-xs font-black transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow ${
              deger === k ? "border-tl-navy bg-tl-navy/5 text-tl-navy ring-1 ring-tl-navy" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
            }`}
          >
            <span aria-hidden className="size-3 shrink-0 rounded-full" style={{ background: DURUM_RENK[k] }} />
            {t.durumlar[k]}
          </button>
        ))}
      </div>
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
  const [online, setOnline] = useState(String(gun?.online ?? 0))
  const [yuzyuze, setYuzyuze] = useState(String(gun?.yuzyuze ?? 0))
  const [ozet, setOzet] = useState(gun?.toplanti_ozeti ?? "")
  const kaydet = useMutation({
    mutationFn: (govde: { durum: string; online: number; yuzyuze: number; toplanti_ozeti: string }) => yaz("PUT", "/api/v1/takvim/gun", { tarih, ...govde }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["takvim"] })
      onBitti()
    },
  })
  function gonder(olay: FormEvent) {
    olay.preventDefault()
    kaydet.mutate({ durum, online: Number(online) || 0, yuzyuze: Number(yuzyuze) || 0, toplanti_ozeti: ozet })
  }
  return (
    <form onSubmit={gonder} className="grid gap-5">
      <DurumSecici deger={durum} onDegis={setDurum} dil={dil} etiket={t.durum} />
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
        <button type="button" className={DUGME} disabled={kaydet.isPending} onClick={() => kaydet.mutate({ durum: "calisiyor", online: 0, yuzyuze: 0, toplanti_ozeti: "" })}>
          {t.varsayilanaDon}
        </button>
      </div>
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
      <DurumSecici deger={durum} onDegis={setDurum} dil={dil} etiket={t.durum} />
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

/** Izin&Takvim Yonetimi: kisi kendi gun durumunu, izinlerini ve toplantilarini aylik takvimde girer (tek gun ya da toplu aralik). */
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

  const ilkAy = yil === ILK_YIL && ay === 1 // 2026 oncesine gidilmez
  function git(fark: number) {
    const d = new Date(yil, ay - 1 + fark, 1)
    if (d.getFullYear() < ILK_YIL) return
    setYil(d.getFullYear())
    setAy(d.getMonth() + 1)
  }
  const o = q.data?.ozet

  return (
    <div className="grid grid-cols-1 gap-4">
      <SayfaKabi ikon={CalendarDays} baslik={t.izinBaslik} aciklama={t.izinAciklama}>
        <button type="button" className={DUGME} onClick={() => setToplu(true)}>
          <CalendarRange aria-hidden className="size-4" />
          {t.topluAtama}
        </button>
      </SayfaKabi>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi etiket={t.izinGunu} deger={sayi(o?.izin_gun)} ikon={Umbrella} ton="sari" />
        <Kpi etiket={t.toplantiOnline} deger={o?.online ?? "—"} ikon={Video} ton="mavi" />
        <Kpi etiket={t.toplantiYuzYuze} deger={o?.yuzyuze ?? "—"} ikon={Users} ton="yesil" />
        <Kpi etiket={t.kayitliGun} deger={o?.kayitli_gun ?? "—"} ikon={Presentation} ton="gri" />
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-base font-black text-tl-navy">
            {t.aylar[ay - 1]} {yil}
          </h3>
          <div className="flex items-center gap-2">
            <button type="button" className={`${DUGME} !px-2.5`} onClick={() => git(-1)} disabled={ilkAy} aria-label={t.oncekiAy}>
              <ChevronLeft aria-hidden className="size-4" />
            </button>
            <button
              type="button"
              className={DUGME}
              onClick={() => {
                setYil(simdi.getFullYear())
                setAy(simdi.getMonth() + 1)
              }}
            >
              {t.bugun}
            </button>
            <button type="button" className={`${DUGME} !px-2.5`} onClick={() => git(1)} aria-label={t.sonrakiAy}>
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
            <div className="grid grid-cols-7 gap-1.5 text-center text-[0.625rem] font-black uppercase tracking-wide text-slate-400">
              {t.gunler.map((g) => (
                <span key={g}>{g}</span>
              ))}
            </div>
            <div className="mt-1.5 grid grid-cols-7 gap-1.5">
              {hucreler.map((g, i) => {
                if (g === null) return <span key={`b${i}`} aria-hidden />
                const tarih = iso(yil, ay, g)
                const kayit = gunler.get(tarih)
                const haftaSonu = (ilkGun + g - 1) % 7 >= 5
                const durum = kayit?.durum ?? (haftaSonu ? "hafta_sonu" : "calisiyor")
                const renkli = kayit !== undefined && kayit.durum !== "calisiyor"
                return (
                  <button
                    key={tarih}
                    type="button"
                    onClick={() => setSecili(tarih)}
                    aria-label={`${g} ${t.aylar[ay - 1]}: ${t.durumlar[durum]}${kayit && kayit.online + kayit.yuzyuze > 0 ? `, ${kayit.online}/${kayit.yuzyuze}` : ""}${kayit?.toplanti_ozeti ? `, ${t.toplantiOzeti}` : ""}`}
                    title={kayit?.toplanti_ozeti || undefined}
                    className={`group relative flex min-h-[4.5rem] flex-col items-start gap-1 rounded-xl border p-1.5 text-left transition-all hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow ${
                      tarih === bugun ? "border-tl-navy ring-2 ring-tl-yellow/70" : "border-slate-200"
                    } ${haftaSonu && !renkli ? "bg-slate-50" : "bg-white"}`}
                    style={renkli ? { background: `${DURUM_RENK[durum]}1a`, borderColor: `${DURUM_RENK[durum]}66` } : undefined}
                  >
                    <span className={`font-mono text-xs font-black ${tarih === bugun ? "text-tl-navy" : haftaSonu ? "text-slate-400" : "text-slate-600"}`}>{g}</span>
                    {renkli ? (
                      <span className="line-clamp-1 rounded px-1 text-[0.5625rem] font-black leading-tight text-white" style={{ background: DURUM_RENK[durum] }}>
                        {t.durumlar[durum]}
                      </span>
                    ) : null}
                    {kayit && (kayit.online + kayit.yuzyuze > 0 || kayit.toplanti_ozeti) ? (
                      <span className="mt-auto flex w-full items-center gap-1 font-mono text-[0.625rem] font-black text-tl-blue">
                        {kayit.online + kayit.yuzyuze > 0 ? (
                          <>
                            <Video aria-hidden className="size-3" />
                            {kayit.online}/{kayit.yuzyuze}
                          </>
                        ) : null}
                        {kayit.toplanti_ozeti ? <FileText aria-hidden className="ml-auto size-3 text-slate-400" /> : null}
                      </span>
                    ) : null}
                  </button>
                )
              })}
            </div>
            <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-1">
              {DURUM_SIRASI.map((k) => (
                <li key={k} className="flex items-center gap-1.5 text-[0.6875rem] font-bold text-slate-500">
                  <span aria-hidden className="size-2.5 rounded-sm" style={{ background: DURUM_RENK[k] }} />
                  {t.durumlar[k]}
                </li>
              ))}
            </ul>
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
