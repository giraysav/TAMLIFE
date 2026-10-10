import { Fragment, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { BarChart3, CalendarCheck, CalendarOff, ChevronDown, Lock, Presentation, Users } from "lucide-react"
import { Bildirim, BosKutu, DUGME, DUGME_SARI, GIRDI, HataKutu, Kpi, Panel, SayfaKabi, Yukleniyor } from "@/components/sayfa-ui"
import { baslangicHarfleri, sayi, tarih, zaman } from "@/lib/bicim"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"
import { durumSerileri, TakvimGrafigi } from "@/takvim/takvim-grafigi"
import type { Ozet } from "@/takvim/takvim-grafigi"
import { DURUM_RENK, DURUM_SIRASI, takvimMetin } from "@/takvim/takvim-metin"
import type { TakvimMetin } from "@/takvim/takvim-metin"

type Uye = Ozet & { id: number; ad: string; kullanici: string; rol: string; son_giris: string | null }
type Ekip = {
  yil: number
  ceyrek: number
  donem: string
  uyeler: Uye[]
  genel: Ozet
  sunumda: { gonderen: string; zaman: string | null } | null
  sunuma_gonderebilir: boolean
}
type UyeGunleri = { uye: string; gunler: { tarih: string; durum: string; online: number; yuzyuze: number }[] }

function ayniCeyrek(): number {
  return Math.floor(new Date().getMonth() / 3) + 1
}

type Gun = UyeGunleri["gunler"][number]

/** Donemin aylari (ceyrek 0 = tum yil). */
function donemAylari(ceyrek: number): number[] {
  return ceyrek === 0 ? Array.from({ length: 12 }, (_, i) => i + 1) : [1, 2, 3].map((i) => 3 * (ceyrek - 1) + i)
}

/** Ay izgarasi: haftalar satir, Pazartesi ilk sutun; kayitli gun durum rengiyle boyanir, toplanti olan gunde nokta. */
function AyIzgarasi({ yil, ay, gunler, yerel, t }: { yil: number; ay: number; gunler: Map<string, Gun>; yerel: string; t: TakvimMetin }) {
  const bos = (new Date(yil, ay - 1, 1).getDay() + 6) % 7
  const gunSayisi = new Date(yil, ay, 0).getDate()
  const haftaGunleri = Array.from({ length: 7 }, (_, i) => new Intl.DateTimeFormat(yerel, { weekday: "short" }).format(new Date(2024, 0, 1 + i)))
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3">
      <p className="mb-2 text-[11px] font-black uppercase tracking-wide text-tl-navy">{new Intl.DateTimeFormat(yerel, { month: "long" }).format(new Date(yil, ay - 1, 1))}</p>
      <div className="grid grid-cols-7 gap-1 text-center">
        {haftaGunleri.map((g, i) => (
          <span key={g + i} className={`text-[9px] font-black ${i >= 5 ? "text-slate-300" : "text-slate-400"}`}>
            {g}
          </span>
        ))}
        {Array.from({ length: bos }, (_, i) => (
          <span key={`b${i}`} />
        ))}
        {Array.from({ length: gunSayisi }, (_, i) => {
          const anahtar = `${yil}-${String(ay).padStart(2, "0")}-${String(i + 1).padStart(2, "0")}`
          const g = gunler.get(anahtar)
          const haftaSonu = (bos + i) % 7 >= 5
          const durum = g ? (t.durumlar[g.durum] ?? g.durum) : ""
          return (
            <span
              key={anahtar}
              title={g ? `${tarih(anahtar)} · ${durum}${g.online + g.yuzyuze ? ` · ${t.toplantiAlt(g.online, g.yuzyuze)}` : ""}` : undefined}
              className={`relative flex h-7 items-center justify-center rounded-md font-mono text-[10px] font-bold ${g ? "text-white shadow-sm" : haftaSonu ? "text-slate-300" : "bg-slate-50 text-slate-500"}`}
              style={g ? { background: DURUM_RENK[g.durum] ?? "#64748b" } : undefined}
            >
              {i + 1}
              {g && g.online + g.yuzyuze > 0 ? <span aria-hidden className="absolute right-0.5 top-0.5 size-1.5 rounded-full bg-white ring-1 ring-black/10" /> : null}
            </span>
          )
        })}
      </div>
    </div>
  )
}

function GunListesi({ yil, ceyrek, uyeId, dil }: { yil: number; ceyrek: number; uyeId: number; dil: Dil }) {
  const t = takvimMetin(dil)
  const q = useQuery({ queryKey: ["takvim", "uye", uyeId, yil, ceyrek], queryFn: () => oku<UyeGunleri>(`/api/v1/takvim/ekip/${uyeId}?yil=${yil}&ceyrek=${ceyrek}`) })
  if (q.isPending) return <Yukleniyor metin="…" />
  if (q.isError) return <HataKutu metin={t.yuklenemedi} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
  if (q.data.gunler.length === 0) return <p className="text-xs font-bold text-slate-400">{t.gunKayitYok}</p>
  const gunler = new Map(q.data.gunler.map((g) => [g.tarih, g]))
  const sayilar = DURUM_SIRASI.map((d) => [d, q.data.gunler.filter((g) => g.durum === d).length] as const).filter(([, n]) => n > 0)
  const yerel = dil === "en" ? "en-GB" : "tr-TR"
  return (
    <div className="grid gap-3">
      <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] font-bold text-slate-600">
        {sayilar.map(([d, n]) => (
          <li key={d} className="flex items-center gap-1.5">
            <span aria-hidden className="size-3 rounded" style={{ background: DURUM_RENK[d] }} />
            {t.durumlar[d] ?? d} <span className="font-mono text-slate-400">{n}</span>
          </li>
        ))}
        <li className="flex items-center gap-1.5">
          <span aria-hidden className="relative size-3 rounded bg-slate-400">
            <span className="absolute right-px top-px size-1.5 rounded-full bg-white" />
          </span>
          {t.toplanti}
        </li>
      </ul>
      <div className={`grid gap-3 sm:grid-cols-2 ${ceyrek === 0 ? "lg:grid-cols-3 2xl:grid-cols-4" : "lg:grid-cols-3"}`}>
        {donemAylari(ceyrek).map((ay) => (
          <AyIzgarasi key={ay} yil={yil} ay={ay} gunler={gunler} yerel={yerel} t={t} />
        ))}
      </div>
    </div>
  )
}

/**
 * TAM Takvim: panele giris yapmis herkesin izin ve takvim ozeti (yalniz isimler ve Izin&Takvim Yonetimi'ne girilen veriler).
 * "Grafik olustur" istendiginde donem grafigi cizilir; yetkili rol grafigin yaninda "ceyrek bazli sunuma gonder" kutusunu gorur.
 */
export function TamTakvim({ dil }: { dil: Dil }) {
  const t = takvimMetin(dil)
  const qc = useQueryClient()
  const buYil = new Date().getFullYear()
  const [yil, setYil] = useState(buYil)
  const [ceyrek, setCeyrek] = useState(ayniCeyrek())
  const [acik, setAcik] = useState<number | null>(null)
  const [grafik, setGrafik] = useState(false)
  const [bilgi, setBilgi] = useState<{ ton: "yesil" | "kirmizi"; metin: string } | null>(null)

  const q = useQuery({ queryKey: ["takvim", "ekip", yil, ceyrek], queryFn: () => oku<Ekip>(`/api/v1/takvim/ekip?yil=${yil}&ceyrek=${ceyrek}`) })
  const sunum = useMutation({
    mutationFn: (gonder: boolean) => yaz("POST", "/api/v1/takvim/sunuma-gonder", { yil, ceyrek, gonder }),
    onSuccess: (_, gonder) => {
      setBilgi({ ton: "yesil", metin: gonder ? t.sunumGonderildi : t.sunumKaldirildi })
      void qc.invalidateQueries({ queryKey: ["takvim", "ekip"] })
      void qc.invalidateQueries({ queryKey: ["sunum"] })
    },
    onError: (e) => setBilgi({ ton: "kirmizi", metin: hataMesaji(e, t.sunumHata) }),
  })
  const v = q.data
  const seriler = durumSerileri(t)
  const donemAdi = ceyrek === 0 ? `${yil}` : `${yil} · ${t.ceyrek(ceyrek)}`

  return (
    <div className="grid grid-cols-1 gap-4">
      <SayfaKabi ikon={CalendarCheck} baslik={t.tamBaslik} aciklama={t.tamAciklama}>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-[10px] font-black uppercase tracking-wide text-white/70">
            {t.yil}
            <select className={`${GIRDI} !w-auto !py-2`} value={yil} onChange={(e) => setYil(Number(e.target.value))}>
              {[buYil, buYil - 1, buYil - 2].map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </label>
          <div role="group" aria-label={t.donem} className="flex overflow-hidden rounded-xl border border-white/30">
            {[0, 1, 2, 3, 4].map((c) => (
              <button
                key={c}
                type="button"
                aria-pressed={ceyrek === c}
                onClick={() => setCeyrek(c)}
                className={`px-3 py-2 text-xs font-black transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow ${ceyrek === c ? "bg-tl-yellow text-tl-navy" : "text-white/80 hover:bg-white/10"}`}
              >
                {c === 0 ? t.tumYil : `${dil === "en" ? "Q" : "Ç"}${c}`}
              </button>
            ))}
          </div>
        </div>
      </SayfaKabi>

      {q.isPending ? (
        <Yukleniyor metin="…" />
      ) : q.isError || !v ? (
        <HataKutu metin={t.yuklenemedi} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi etiket={t.kpiKisi} deger={v.uyeler.length} ikon={Users} ton="mavi" />
            <Kpi etiket={t.kpiIzin} deger={sayi(v.uyeler.reduce((a, u) => a + u.izin_gun, 0))} ikon={CalendarOff} ton="sari" />
            <Kpi etiket={t.kpiToplanti} deger={v.genel.toplanti} alt={t.toplantiAlt(v.genel.online, v.genel.yuzyuze)} ikon={Presentation} ton="yesil" />
            <Kpi etiket={t.kpiKayit} deger={v.genel.kayitli_gun} ikon={CalendarCheck} ton="gri" />
          </div>

          <Panel
            baslik={t.kisi}
            aciklama={donemAdi}
            sag={
              <button type="button" className={grafik ? DUGME : DUGME_SARI} onClick={() => setGrafik((g) => !g)} aria-expanded={grafik} disabled={v.uyeler.length === 0}>
                <BarChart3 aria-hidden className="size-4" />
                {grafik ? t.grafigiGizle : t.grafikOlustur}
              </button>
            }
          >
            {v.uyeler.length === 0 ? (
              <BosKutu ikon={Users} baslik={t.uyeYok} aciklama={t.uyeYokAlt} />
            ) : (
              <div className="overflow-x-auto rounded-xl border border-slate-200">
                <table className="w-full text-left text-xs">
                  <thead className="bg-tl-navy text-white">
                    <tr>
                      <th scope="col" className="px-3 py-2.5 font-black">
                        {t.kisi}
                      </th>
                      <th scope="col" className="min-w-48 px-3 py-2.5 font-black">
                        {t.durumDagilimi}
                      </th>
                      <th scope="col" className="px-3 py-2.5 text-right font-black">
                        {t.izinGunu}
                      </th>
                      <th scope="col" className="px-3 py-2.5 text-right font-black">
                        {t.toplanti}
                      </th>
                      <th scope="col" className="px-3 py-2.5 text-right font-black">
                        {t.kayitliGun}
                      </th>
                      <th scope="col" className="px-3 py-2.5 font-black">
                        {t.sonGiris}
                      </th>
                      <th scope="col" className="w-10 px-2 py-2.5">
                        <span className="sr-only">{t.gunAc}</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {v.uyeler.map((u) => {
                      const acikMi = acik === u.id
                      const toplamGun = Object.values(u.durumlar).reduce((a, b) => a + b, 0)
                      return (
                        <Fragment key={u.id}>
                          <tr className="hover:bg-slate-50">
                            <td className="px-3 py-2.5">
                              <span className="flex items-center gap-2.5">
                                <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-tl-navy text-[11px] font-black text-tl-yellow">{baslangicHarfleri(u.ad)}</span>
                                <span className="grid min-w-0">
                                  <span className="truncate font-black text-tl-navy">{u.ad}</span>
                                  <span className="text-[10px] font-bold text-slate-400">{u.rol}</span>
                                </span>
                              </span>
                            </td>
                            <td className="px-3 py-2.5">
                              {toplamGun === 0 ? (
                                <span className="text-slate-300">—</span>
                              ) : (
                                <div className="flex h-2.5 overflow-hidden rounded-full bg-slate-100" role="img" aria-label={seriler.map((s) => `${s.ad}: ${u.durumlar[s.anahtar] ?? 0}`).join(", ")}>
                                  {seriler.map((s) =>
                                    (u.durumlar[s.anahtar] ?? 0) > 0 ? <span key={s.anahtar} title={`${s.ad}: ${u.durumlar[s.anahtar]}`} style={{ background: s.renk, width: `${((u.durumlar[s.anahtar] ?? 0) / toplamGun) * 100}%` }} /> : null,
                                  )}
                                </div>
                              )}
                            </td>
                            <td className="px-3 py-2.5 text-right font-mono font-black text-tl-navy">{sayi(u.izin_gun)}</td>
                            <td className="whitespace-nowrap px-3 py-2.5 text-right font-mono font-bold text-slate-600">
                              {u.online} / {u.yuzyuze}
                            </td>
                            <td className="px-3 py-2.5 text-right font-mono font-bold text-slate-600">{u.kayitli_gun}</td>
                            <td className="whitespace-nowrap px-3 py-2.5 text-[11px] font-bold text-slate-400">{zaman(u.son_giris)}</td>
                            <td className="px-2 py-2.5 text-right">
                              <button
                                type="button"
                                aria-expanded={acikMi}
                                aria-label={`${acikMi ? t.gunKapat : t.gunAc}: ${u.ad}`}
                                title={acikMi ? t.gunKapat : t.gunAc}
                                onClick={() => setAcik(acikMi ? null : u.id)}
                                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-tl-navy focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
                              >
                                <ChevronDown aria-hidden className={`size-4 transition-transform ${acikMi ? "rotate-180" : ""}`} />
                              </button>
                            </td>
                          </tr>
                          {acikMi ? (
                            <tr className="bg-slate-50/70">
                              <td colSpan={7} className="px-4 py-3">
                                <GunListesi yil={yil} ceyrek={ceyrek} uyeId={u.id} dil={dil} />
                              </td>
                            </tr>
                          ) : null}
                        </Fragment>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          {grafik && v.uyeler.length > 0 ? (
            <Panel baslik={t.grafikBaslik} aciklama={t.grafikAlt(donemAdi)}>
              <TakvimGrafigi genel={v.genel} uyeler={v.uyeler} t={t} />
              <div className="mt-5 rounded-2xl border border-tl-yellow/50 bg-tl-yellow/10 p-4">
                <label className={`flex items-start gap-3 ${v.sunuma_gonderebilir && ceyrek !== 0 ? "cursor-pointer" : "cursor-not-allowed opacity-80"}`}>
                  <input
                    type="checkbox"
                    className="mt-1 size-4 accent-[#002855]"
                    checked={v.sunumda !== null}
                    disabled={!v.sunuma_gonderebilir || ceyrek === 0 || sunum.isPending}
                    onChange={(e) => sunum.mutate(e.target.checked)}
                  />
                  <span className="grid gap-0.5">
                    <span className="flex items-center gap-2 text-sm font-black text-tl-navy">
                      <Presentation aria-hidden className="size-4" />
                      {t.sunumaGonder}
                      {!v.sunuma_gonderebilir ? <Lock aria-hidden className="size-3.5 text-slate-400" /> : null}
                    </span>
                    <span className="text-xs font-bold text-slate-500">{t.sunumaGonderAlt}</span>
                    {!v.sunuma_gonderebilir ? <span className="text-xs font-bold text-amber-700">{t.sunumYetkisiYok}</span> : ceyrek === 0 ? <span className="text-xs font-bold text-amber-700">{t.sunumCeyrekGerekli}</span> : null}
                    {v.sunumda ? <span className="text-xs font-black text-emerald-700">{t.sunumda(v.sunumda.gonderen, zaman(v.sunumda.zaman))}</span> : null}
                  </span>
                </label>
                {bilgi ? (
                  <div className="mt-3">
                    <Bildirim ton={bilgi.ton}>{bilgi.metin}</Bildirim>
                  </div>
                ) : null}
              </div>
            </Panel>
          ) : null}
        </>
      )}
    </div>
  )
}
