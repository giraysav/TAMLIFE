import { Fragment, useState } from "react"
import type { FormEvent } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { History, Lightbulb, Send, StickyNote, Trash2 } from "lucide-react"
import { Alan, Bildirim, BosKutu, DUGME, DUGME_SARI, GIRDI, HataKutu, Panel, Rozet, SayfaKabi, Yukleniyor } from "@/components/sayfa-ui"
import { tarih, zaman } from "@/lib/bicim"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"
import { DURUMLAR, EKRANLAR, KANALLAR, ONCELIKLER, TURLER, talepMetin } from "@/talep/talep-metin"
import type { Durum, Oncelik, Tur } from "@/talep/talep-metin"

type Gecmis = { zaman: string | null; yapan: string; alan: string; eski: string; yeni: string }
type Talep = {
  id: number
  baslik: string
  tur: Tur
  oncelik: Oncelik
  modul: string
  mevcut_durum: string
  beklenen_durum: string
  kabul_olcutu: string
  durum: Durum
  acik: boolean
  talep_eden_id: number
  talep_eden: string
  talep_eden_kullanici: string
  /** Talebi baskasi adina giren (bos = talep edenin kendisi). */
  giren: string
  kanal: Kanal
  olusturuldu: string | null
  guncellendi: string | null
  hedef_surum: string
  admin_notu: string
  atanan_id: number | null
  atanan: string
  gecmis?: Gecmis[]
}
type Kisi = { id: number; ad: string; kullanici?: string }
type Liste = { yonetebilir: boolean; silebilir: boolean; talepler: Talep[]; acik_sayisi?: number; kisiler?: Kisi[] }
type Degisiklik = Partial<{ durum: Durum; oncelik: Oncelik; atanan_id: number | null; hedef_surum: string; admin_notu: string; talep_eden_id: number }>
type Kanal = (typeof KANALLAR)[number]
const kisiEtiketi = (k: Kisi) => (k.kullanici && k.kullanici !== k.ad ? `${k.ad} (${k.kullanici})` : k.ad)

/** Uretimdeki renkler: durum ve onem rozetleri (Tailwind siniflari sabit yazilir, derleyici ayiklamasin). */
const DURUM_RENK: Record<Durum, string> = {
  yeni: "border-slate-300 bg-slate-500/10 text-slate-600",
  incelemede: "border-blue-300 bg-blue-500/10 text-blue-700",
  planlandi: "border-violet-300 bg-violet-500/10 text-violet-700",
  yapiliyor: "border-amber-300 bg-amber-500/10 text-amber-700",
  tamamlandi: "border-emerald-300 bg-emerald-500/10 text-emerald-700",
  reddedildi: "border-rose-300 bg-rose-500/10 text-rose-700",
}
const ONCELIK_RENK: Record<Oncelik, string> = {
  dusuk: "bg-slate-500/10 text-slate-600",
  orta: "bg-blue-500/10 text-blue-700",
  yuksek: "bg-amber-500/10 text-amber-700",
  kritik: "bg-rose-500/10 text-rose-700",
}
const BOS_FORM = { baslik: "", tur: "ozellik" as Tur, oncelik: "orta" as Oncelik, modul: "", mevcut_durum: "", beklenen_durum: "", kabul_olcutu: "", talep_eden_id: "", kanal: "panel" as Kanal }
const ANAHTAR = ["talep"] as const

/** Talep formu: mevcut ve beklenen durum ayri ayri zorunlu (tek kutuda "sunu duzeltin" yazan talepler yorum farkina donusuyordu).
 *  `kisiler` yalniz yonetene gelir: e-postayla gelen talebi baskasi adina girebilir (2026-10-31). */
function TalepFormu({ dil, kisiler }: { dil: Dil; kisiler?: Kisi[] }) {
  const t = talepMetin(dil)
  const qc = useQueryClient()
  const [form, setForm] = useState(BOS_FORM)
  const [uyari, setUyari] = useState("")
  const gonder = useMutation({
    mutationFn: () => {
      const { talep_eden_id, kanal, ...temel } = form
      return yaz<{ id: number }>("POST", "/api/v1/talep", kisiler ? { ...temel, kanal, talep_eden_id: talep_eden_id ? Number(talep_eden_id) : null } : temel)
    },
    onSuccess: () => {
      setForm(BOS_FORM)
      void qc.invalidateQueries({ queryKey: ANAHTAR })
    },
  })
  const alan = <K extends keyof typeof BOS_FORM>(k: K, v: (typeof BOS_FORM)[K]) => setForm((f) => ({ ...f, [k]: v }))

  function gonderTikla(e: FormEvent) {
    e.preventDefault()
    if (!form.baslik.trim() || !form.mevcut_durum.trim() || !form.beklenen_durum.trim()) {
      setUyari(t.eksik)
      return
    }
    setUyari("")
    gonder.mutate()
  }

  return (
    <Panel baslik={t.formBaslik} aciklama={t.formAciklama}>
      <form className="grid gap-3" onSubmit={gonderTikla} noValidate>
        <div className="grid gap-3 md:grid-cols-4">
          <Alan etiket={t.talepBaslik} sinif="md:col-span-2">
            <input className={GIRDI} maxLength={160} placeholder={t.baslikIpucu} value={form.baslik} onChange={(e) => alan("baslik", e.target.value)} />
          </Alan>
          <Alan etiket={t.tur}>
            <select className={GIRDI} value={form.tur} onChange={(e) => alan("tur", e.target.value as Tur)}>
              {TURLER.map((k) => (
                <option key={k} value={k}>
                  {t.tur_[k]}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t.onem}>
            <select className={GIRDI} value={form.oncelik} onChange={(e) => alan("oncelik", e.target.value as Oncelik)}>
              {ONCELIKLER.map((k) => (
                <option key={k} value={k}>
                  {t.oncelik_[k]}
                </option>
              ))}
            </select>
          </Alan>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <Alan etiket={t.mevcut}>
            <textarea className={`${GIRDI} resize-y font-normal`} rows={4} maxLength={4000} placeholder={t.mevcutIpucu} value={form.mevcut_durum} onChange={(e) => alan("mevcut_durum", e.target.value)} />
          </Alan>
          <Alan etiket={t.beklenen}>
            <textarea className={`${GIRDI} resize-y font-normal`} rows={4} maxLength={4000} placeholder={t.beklenenIpucu} value={form.beklenen_durum} onChange={(e) => alan("beklenen_durum", e.target.value)} />
          </Alan>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <Alan etiket={t.kabul} sinif="md:col-span-2">
            <input className={`${GIRDI} font-normal`} maxLength={2000} placeholder={t.kabulIpucu} value={form.kabul_olcutu} onChange={(e) => alan("kabul_olcutu", e.target.value)} />
          </Alan>
          <Alan etiket={t.ekran}>
            <select className={GIRDI} value={form.modul} onChange={(e) => alan("modul", e.target.value)}>
              <option value="">{t.seciniz}</option>
              {EKRANLAR.map((k) => (
                <option key={k} value={k}>
                  {t.ekran_[k]}
                </option>
              ))}
            </select>
          </Alan>
        </div>
        {kisiler ? (
          <div className="grid gap-3 md:grid-cols-3">
            <Alan etiket={t.talepEden}>
              <select className={GIRDI} value={form.talep_eden_id} onChange={(e) => alan("talep_eden_id", e.target.value)}>
                <option value="">{t.kendim}</option>
                {kisiler.map((k) => (
                  <option key={k.id} value={k.id}>
                    {kisiEtiketi(k)}
                  </option>
                ))}
              </select>
            </Alan>
            <Alan etiket={t.gelisYolu}>
              <select className={GIRDI} value={form.kanal} onChange={(e) => alan("kanal", e.target.value as Kanal)}>
                {KANALLAR.map((k) => (
                  <option key={k} value={k}>
                    {t.kanal_[k]}
                  </option>
                ))}
              </select>
            </Alan>
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" className={DUGME_SARI} disabled={gonder.isPending}>
            <Send aria-hidden className="size-4" />
            {gonder.isPending ? t.gonderiliyor : t.gonder}
          </button>
          {uyari ? <Bildirim ton="amber">{uyari}</Bildirim> : null}
          {gonder.isError ? <Bildirim ton="kirmizi">{hataMesaji(gonder.error, t.gonderilemedi)}</Bildirim> : null}
          {gonder.isSuccess && !uyari ? <Bildirim ton="yesil">{t.alindi}</Bildirim> : null}
        </div>
      </form>
    </Panel>
  )
}

function Etiketli({ etiket, metin }: { etiket: string; metin: string }) {
  return (
    <div>
      <span className="block text-[0.625rem] font-black uppercase text-slate-500">{etiket}</span>
      <span className="whitespace-pre-wrap font-normal text-slate-600">{metin}</span>
    </div>
  )
}

/** Is listesi satiri. Yoneten durum/atanan/hedef/not degistirir (degisiklik aninda kaydedilir); admin siler. */
function TalepSatiri({ talep, v, dil }: { talep: Talep; v: Liste; dil: Dil }) {
  const t = talepMetin(dil)
  const qc = useQueryClient()
  const [gecmisAcik, setGecmisAcik] = useState(false)
  const [notAcik, setNotAcik] = useState(false)
  const [not, setNot] = useState(talep.admin_notu)
  const [hedef, setHedef] = useState(talep.hedef_surum)
  const kaydet = useMutation({
    mutationFn: (d: Degisiklik) => yaz<{ degisen: string[] }>("PATCH", `/api/v1/talep/${talep.id}`, d),
    onSuccess: () => {
      setNotAcik(false)
      void qc.invalidateQueries({ queryKey: ANAHTAR })
    },
  })
  const sil = useMutation({
    mutationFn: () => yaz("DELETE", `/api/v1/talep/${talep.id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ANAHTAR }),
  })
  const sutun = v.yonetebilir ? 7 : 4
  const durumRozeti = <span className={`inline-block rounded-lg border px-2.5 py-1 text-[0.6875rem] font-black ${DURUM_RENK[talep.durum]}`}>{t.durum_[talep.durum] ?? talep.durum}</span>

  return (
    <Fragment>
      <tr className="align-top hover:bg-slate-50">
        <td className="max-w-md px-3 py-2">
          <div className="font-black text-tl-navy">{talep.baslik}</div>
          {talep.modul ? <div className="mt-0.5 text-[0.625rem] font-black uppercase text-slate-400">{t.ekran_[talep.modul] ?? talep.modul}</div> : null}
          <details className="mt-1.5">
            <summary className="cursor-pointer text-[0.6875rem] font-bold text-tl-blue">{t.ayrinti}</summary>
            <div className="mt-2 grid gap-2">
              <Etiketli etiket={t.suAn} metin={talep.mevcut_durum} />
              <Etiketli etiket={t.beklenenKisa} metin={talep.beklenen_durum} />
              {talep.kabul_olcutu ? <Etiketli etiket={t.tamamlanmaOlcutu} metin={talep.kabul_olcutu} /> : null}
              {talep.admin_notu ? (
                <div className="rounded-lg bg-slate-100 p-2">
                  <Etiketli etiket={t.yoneticiNotu} metin={talep.admin_notu} />
                </div>
              ) : null}
            </div>
          </details>
        </td>
        <td className="whitespace-nowrap px-3 py-2">
          <div className="text-slate-600">{t.tur_[talep.tur] ?? talep.tur}</div>
          <span className={`mt-1 inline-block rounded-md px-2 py-0.5 text-[0.625rem] font-black ${ONCELIK_RENK[talep.oncelik]}`}>{t.oncelik_[talep.oncelik] ?? talep.oncelik}</span>
        </td>
        <td className="whitespace-nowrap px-3 py-2">
          {v.yonetebilir ? (
            <select
              aria-label={`${t.kolTalepEden}: ${talep.baslik}`}
              className={`${GIRDI} max-w-[180px] cursor-pointer !py-1.5`}
              value={talep.talep_eden_id}
              disabled={kaydet.isPending}
              onChange={(e) => kaydet.mutate({ talep_eden_id: Number(e.target.value) })}
            >
              {(v.kisiler ?? []).some((k) => k.id === talep.talep_eden_id) ? null : <option value={talep.talep_eden_id}>{talep.talep_eden || "—"}</option>}
              {(v.kisiler ?? []).map((k) => (
                <option key={k.id} value={k.id}>
                  {kisiEtiketi(k)}
                </option>
              ))}
            </select>
          ) : (
            <div className="text-slate-700">{talep.talep_eden || "—"}</div>
          )}
          {talep.talep_eden_kullanici ? <div className="font-mono text-[0.625rem] text-slate-500">{talep.talep_eden_kullanici}</div> : null}
          <div className="flex flex-wrap items-center gap-1 font-mono text-[0.625rem] text-slate-400">
            {tarih(talep.olusturuldu)}
            {talep.kanal === "eposta" ? <span className="rounded bg-sky-500/10 px-1.5 font-sans font-black text-sky-700">{t.kanal_.eposta}</span> : null}
          </div>
          {talep.giren ? <div className="text-[0.625rem] text-slate-400">{t.giren(talep.giren)}</div> : null}
        </td>
        <td className="whitespace-nowrap px-3 py-2">
          {v.yonetebilir ? (
            <select
              aria-label={`${t.kolDurum}: ${talep.baslik}`}
              className={`cursor-pointer rounded-lg border px-2 py-1.5 text-xs font-black outline-none focus-visible:ring-2 focus-visible:ring-tl-yellow ${DURUM_RENK[talep.durum]}`}
              value={talep.durum}
              disabled={kaydet.isPending}
              onChange={(e) => kaydet.mutate({ durum: e.target.value as Durum })}
            >
              {DURUMLAR.map((d) => (
                <option key={d} value={d}>
                  {t.durum_[d]}
                </option>
              ))}
            </select>
          ) : (
            durumRozeti
          )}
          {kaydet.isSuccess ? <div className="mt-1 text-[0.625rem] font-black text-emerald-600">{t.kaydedildi}</div> : null}
          {kaydet.isError ? <div className="mt-1 max-w-[12rem] whitespace-normal text-[0.625rem] font-black text-rose-600">{hataMesaji(kaydet.error, t.kaydedilemedi)}</div> : null}
        </td>
        {v.yonetebilir ? (
          <>
            <td className="whitespace-nowrap px-3 py-2">
              <select
                aria-label={`${t.kolAtanan}: ${talep.baslik}`}
                className={`${GIRDI} max-w-[150px] cursor-pointer !py-1.5`}
                value={talep.atanan_id ?? ""}
                disabled={kaydet.isPending}
                onChange={(e) => kaydet.mutate({ atanan_id: e.target.value ? Number(e.target.value) : null })}
              >
                <option value="">{t.atanmadi}</option>
                {(v.kisiler ?? []).map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.ad}
                  </option>
                ))}
              </select>
            </td>
            <td className="whitespace-nowrap px-3 py-2">
              <input
                aria-label={`${t.kolHedef}: ${talep.baslik}`}
                className={`${GIRDI} !w-20 !py-1.5 font-mono`}
                maxLength={40}
                placeholder={t.hedefIpucu}
                value={hedef}
                onChange={(e) => setHedef(e.target.value)}
                onBlur={() => {
                  if (hedef.trim() !== talep.hedef_surum) kaydet.mutate({ hedef_surum: hedef })
                }}
              />
            </td>
            <td className="whitespace-nowrap px-3 py-2 text-center">
              <div className="inline-flex gap-1">
                <button type="button" className={`${DUGME} !px-2 !py-1.5`} title={t.yoneticiNotu} aria-expanded={notAcik} onClick={() => setNotAcik((a) => !a)}>
                  <StickyNote aria-hidden className="size-3.5" />
                  {t.not}
                </button>
                <button type="button" className={`${DUGME} !px-2 !py-1.5`} title={t.gecmis} aria-label={t.gecmisAc(talep.baslik)} aria-expanded={gecmisAcik} onClick={() => setGecmisAcik((a) => !a)}>
                  <History aria-hidden className="size-3.5" />
                </button>
                {v.silebilir ? (
                  <button
                    type="button"
                    className="inline-flex items-center rounded-xl bg-rose-500/10 px-2 py-1.5 text-rose-600 transition-colors hover:bg-rose-600 hover:text-white focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow disabled:opacity-60"
                    title={t.silIpucu}
                    aria-label={`${t.sil}: ${talep.baslik}`}
                    disabled={sil.isPending}
                    onClick={() => {
                      if (window.confirm(t.silOnay(talep.baslik))) sil.mutate()
                    }}
                  >
                    <Trash2 aria-hidden className="size-3.5" />
                  </button>
                ) : null}
              </div>
            </td>
          </>
        ) : null}
      </tr>
      {notAcik ? (
        <tr className="bg-slate-50">
          <td colSpan={sutun} className="px-6 py-3">
            <Alan etiket={t.yoneticiNotu}>
              <textarea className={`${GIRDI} resize-y font-normal`} rows={3} maxLength={4000} value={not} onChange={(e) => setNot(e.target.value)} />
            </Alan>
            <div className="mt-2 flex gap-2">
              <button type="button" className={DUGME} disabled={kaydet.isPending} onClick={() => kaydet.mutate({ admin_notu: not })}>
                {t.kaydet}
              </button>
              <button
                type="button"
                className={DUGME}
                onClick={() => {
                  setNot(talep.admin_notu)
                  setNotAcik(false)
                }}
              >
                {t.vazgec}
              </button>
            </div>
          </td>
        </tr>
      ) : null}
      {gecmisAcik ? (
        <tr className="bg-slate-50">
          <td colSpan={sutun} className="px-6 py-3">
            <div className="mb-1.5 text-[0.625rem] font-black uppercase tracking-wider text-slate-500">{t.gecmis}</div>
            {(talep.gecmis ?? []).length === 0 ? <div className="text-[0.6875rem] font-bold text-slate-400">—</div> : null}
            <ul className="grid gap-0.5">
              {(talep.gecmis ?? []).map((g, i) => (
                <li key={i} className="text-[0.6875rem] font-bold text-slate-600">
                  <span className="font-mono text-slate-400">{zaman(g.zaman)}</span> · {g.yapan || "—"} · {t.gecmisAlan[g.alan] ?? g.alan}
                  {g.alan !== "olusturma" ? (
                    <>
                      : {gecmisDegeri(g.alan, g.eski, dil) || "—"} → <strong>{gecmisDegeri(g.alan, g.yeni, dil) || "—"}</strong>
                    </>
                  ) : null}
                </li>
              ))}
            </ul>
          </td>
        </tr>
      ) : null}
    </Fragment>
  )
}

function gecmisDegeri(alan: string, deger: string, dil: Dil): string {
  const t = talepMetin(dil)
  if (alan === "durum") return t.durum_[deger as Durum] ?? deger
  if (alan === "oncelik") return t.oncelik_[deger as Oncelik] ?? deger
  if (alan === "kanal") return t.kanal_[deger as Kanal] ?? deger
  return deger
}

/**
 * Gelistirme Talepleri (uretim Yonetim › Talep sekmesi): ustte talep formu, altta liste. Yoneten (admin, TeamMngr ya da
 * "Geliştirme taleplerini yönet" ek yetkisi) herkesin taleplerini "Is Listesi" olarak gorur; digerleri kendi taleplerini.
 */
export function TalepSayfasi({ dil }: { dil: Dil }) {
  const t = talepMetin(dil)
  const [suzgec, setSuzgec] = useState("acik")
  const q = useQuery({ queryKey: [...ANAHTAR, suzgec], queryFn: () => oku<Liste>(`/api/v1/talep?durum=${encodeURIComponent(suzgec)}`) })
  const v = q.data

  const sag = (
    <select aria-label={t.suzgec} className={`${GIRDI} !w-auto`} value={suzgec} onChange={(e) => setSuzgec(e.target.value)}>
      <option value="acik">{t.acikOlanlar}</option>
      <option value="">{t.tumu}</option>
      {DURUMLAR.map((d) => (
        <option key={d} value={d}>
          {t.durum_[d]}
        </option>
      ))}
    </select>
  )
  const baslik = v?.yonetebilir ? t.isListesi : t.taleplerim

  return (
    <div className="grid grid-cols-1 gap-4">
      <SayfaKabi ikon={Lightbulb} baslik={t.baslik} aciklama={t.aciklama} />
      <TalepFormu dil={dil} kisiler={v?.yonetebilir ? v.kisiler : undefined} />
      <Panel baslik={baslik} sag={sag}>
        {v?.yonetebilir && v.acik_sayisi ? (
          <div className="-mt-1 mb-2">
            <Rozet ton="amber">{t.acikSayisi(v.acik_sayisi)}</Rozet>
          </div>
        ) : null}
        {q.isPending ? (
          <Yukleniyor metin={t.yukleniyor} />
        ) : q.isError ? (
          <HataKutu metin={hataMesaji(q.error, t.yuklenemedi)} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
        ) : v && v.talepler.length === 0 ? (
          suzgec === "acik" || suzgec === "" ? <BosKutu ikon={Lightbulb} baslik={t.bos} aciklama={t.bosAlt} /> : <p className="p-4 text-xs font-bold text-slate-400">{t.bosSuzgec}</p>
        ) : v ? (
          <div className="overflow-x-auto rounded-xl border border-slate-200">
            <table className="w-full text-left text-xs">
              <caption className="sr-only">{baslik}</caption>
              <thead className="bg-tl-navy text-white">
                <tr>
                  {[t.kolTalep, t.kolTurOnem, t.kolTalepEden, t.kolDurum, ...(v.yonetebilir ? [t.kolAtanan, t.kolHedef, t.kolIslem] : [])].map((b) => (
                    <th key={b} scope="col" className="whitespace-nowrap px-3 py-2 font-black">
                      {b}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-bold">
                {v.talepler.map((talep) => (
                  <TalepSatiri key={talep.id} talep={talep} v={v} dil={dil} />
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Panel>
    </div>
  )
}
