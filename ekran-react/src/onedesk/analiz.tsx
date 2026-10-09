import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { Bot, Lightbulb, MapPin, ShieldCheck, Sparkles, TriangleAlert, Trophy } from "lucide-react"
import { Lejant, YatayCubuklar } from "@/components/grafik"
import { Bildirim, BosKutu, DUGME_SARI, HataKutu, Panel, Yukleniyor } from "@/components/sayfa-ui"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import type { OnedeskMetin } from "@/onedesk/onedesk-metin"
import { TUR_RENK, turSerileri } from "@/onedesk/tipler"
import type { Oneriler, Rca, Top10, Tur } from "@/onedesk/tipler"

const SIRA_RENK = ["bg-tl-yellow text-tl-navy", "bg-slate-300 text-slate-700", "bg-amber-600/80 text-white"]

/** Yil boyu en cok kayit olusan 10 musteri; her satirda musteri adi ve en cok kayit olusan lokasyon(lar). */
export function Top10Paneli({ yil, t }: { yil: number; t: OnedeskMetin }) {
  const q = useQuery({ queryKey: ["onedesk", "top10", yil], queryFn: () => oku<Top10>(`/api/v1/onedesk/top10?yil=${yil}`) })
  const seriler = turSerileri(t)
  return (
    <Panel baslik={t.top10} aciklama={t.top10Alt(yil)} sag={<Lejant seriler={seriler} />}>
      {q.isPending ? (
        <Yukleniyor metin="…" />
      ) : q.isError ? (
        <HataKutu metin={t.yuklenemedi} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
      ) : q.data.musteriler.length === 0 ? (
        <BosKutu ikon={Trophy} baslik={t.veriYok} aciklama={t.veriYokAlt} />
      ) : (
        <ol className="grid gap-3">
          {q.data.musteriler.map((m) => (
            <li key={m.ad} className="grid gap-1.5 rounded-xl border border-slate-100 bg-slate-50/50 p-3">
              <div className="flex items-start gap-3">
                <span className={`flex size-7 shrink-0 items-center justify-center rounded-lg font-mono text-xs font-black ${SIRA_RENK[m.sira - 1] ?? "bg-slate-100 text-slate-500"}`}>{m.sira}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-black text-tl-navy" title={m.ad}>
                    {m.ad}
                  </p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] font-bold text-slate-500">
                    {m.lokasyonlar.map((l, i) => (
                      <span key={l.ad} className={`inline-flex items-center gap-1 ${i === 0 ? "text-tl-blue" : ""}`}>
                        <MapPin aria-hidden className="size-3" />
                        {l.ad} <span className="font-mono text-slate-400">×{l.adet}</span>
                      </span>
                    ))}
                  </p>
                </div>
                <span className="shrink-0 font-mono text-lg font-black text-tl-navy">{m.toplam}</span>
              </div>
              <YatayCubuklar satirlar={[{ anahtar: m.ad, etiket: "", degerler: { alarm: m.alarm, talep: m.talep, sikayet: m.sikayet }, sag: "" }]} seriler={seriler} yukseklik={6} />
            </li>
          ))}
        </ol>
      )}
    </Panel>
  )
}

/** Kapanan kayitlarin kok neden (RCA) ortak noktalari: gruplar, sik sozcukler, tekrar eden lokasyonlar. */
export function RcaPaneli({ yil, t }: { yil: number; t: OnedeskMetin }) {
  const q = useQuery({ queryKey: ["onedesk", "rca", yil], queryFn: () => oku<Rca>(`/api/v1/onedesk/rca?yil=${yil}`) })
  const veri = q.data
  return (
    <Panel baslik={t.rca} aciklama={veri ? t.rcaAlt(veri.kapsanan, yil) : undefined}>
      {q.isPending ? (
        <Yukleniyor metin="…" />
      ) : q.isError ? (
        <HataKutu metin={t.yuklenemedi} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
      ) : !veri || veri.ortak_noktalar.length === 0 ? (
        <BosKutu ikon={ShieldCheck} baslik={t.rcaYok} />
      ) : (
        <div className="grid gap-4">
          <ol className="grid gap-3">
            {veri.ortak_noktalar.map((g, i) => (
              <li key={g.kok_sebep} className="grid gap-1.5">
                <div className="flex items-start justify-between gap-3">
                  <p className="min-w-0 text-xs font-bold leading-snug text-slate-700">
                    <span className="mr-1.5 font-mono text-slate-400">{i + 1}.</span>
                    {g.kok_sebep}
                  </p>
                  <span className="shrink-0 text-right font-mono text-xs font-black text-tl-navy">
                    {g.adet} <span className="text-slate-400">· %{g.oran}</span>
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-gradient-to-r from-tl-blue to-tl-accent" style={{ width: `${Math.min(100, g.oran)}%` }} />
                </div>
                <p className="flex flex-wrap gap-x-3 text-[10px] font-bold text-slate-400">
                  <span>{t.musteriSayisi(g.musteri_sayisi)}</span>
                  <span>{t.lokasyonSayisi(g.lokasyon_sayisi)}</span>
                  {(Object.entries(g.turler) as [Tur, number][]).map(([tur, n]) => (
                    <span key={tur} className="inline-flex items-center gap-1">
                      <span aria-hidden className="size-1.5 rounded-full" style={{ background: TUR_RENK[tur] }} />
                      {t[tur]} {n}
                    </span>
                  ))}
                </p>
              </li>
            ))}
          </ol>
          {veri.anahtar_kelimeler.length > 0 ? (
            <div>
              <p className="mb-1.5 text-[10px] font-black uppercase tracking-wide text-slate-400">{t.anahtarKelimeler}</p>
              <ul className="flex flex-wrap gap-1.5">
                {veri.anahtar_kelimeler.map((k) => (
                  <li key={k.kelime} className="rounded-full bg-tl-blue/10 px-2.5 py-1 text-[11px] font-black text-tl-blue">
                    {k.kelime} <span className="font-mono text-tl-blue/60">{k.adet}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {veri.tekrar_lokasyonlar.length > 0 ? (
            <div>
              <p className="text-[10px] font-black uppercase tracking-wide text-slate-400">{t.tekrarLokasyon}</p>
              <p className="mb-1.5 text-[10px] font-bold text-slate-400">{t.tekrarLokasyonAlt}</p>
              <ul className="grid gap-1">
                {veri.tekrar_lokasyonlar.map((l) => (
                  <li key={`${l.musteri}|${l.lokasyon}`} className="flex items-center justify-between gap-3 rounded-lg bg-amber-50 px-2.5 py-1.5 text-xs font-bold text-amber-900">
                    <span className="inline-flex min-w-0 items-center gap-1.5 truncate">
                      <TriangleAlert aria-hidden className="size-3.5 shrink-0" />
                      <span className="truncate">
                        {l.musteri} · {l.lokasyon}
                      </span>
                    </span>
                    <span className="font-mono">×{l.adet}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      )}
    </Panel>
  )
}

/** Cozum tavsiyeleri: yerlesik kural tabanli oneriler her zaman; LLM yorumu yalniz yonetici ayarlariyla aciksa istenebilir. */
export function OneriPaneli({ yil, t }: { yil: number; t: OnedeskMetin }) {
  const q = useQuery({ queryKey: ["onedesk", "oneriler", yil], queryFn: () => oku<Oneriler>(`/api/v1/onedesk/oneriler?yil=${yil}`) })
  const [yorum, setYorum] = useState<string | null>(null)
  const yz = useMutation({
    mutationFn: () => yaz<{ yorum: string }>("POST", `/api/v1/onedesk/yz-yorum?yil=${yil}`),
    onSuccess: (s) => setYorum(s.yorum),
  })
  const veri = q.data
  const hazir = veri?.yz.hazir ?? false
  return (
    <Panel baslik={t.oneriler} aciklama={t.onerilerAlt} sinif="lg:col-span-2">
      {q.isPending ? (
        <Yukleniyor metin="…" />
      ) : q.isError || !veri ? (
        <HataKutu metin={t.yuklenemedi} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
          <div className="grid gap-3">
            <p className="flex items-center gap-2 text-[11px] font-black text-tl-navy">
              <Lightbulb aria-hidden className="size-4 text-tl-yellow" />
              {t.yerlesik}
              <span className="font-bold text-slate-400">· {t.yerlesikAlt}</span>
            </p>
            {veri.gruplar.length === 0 ? (
              <BosKutu ikon={Lightbulb} baslik={t.rcaYok} />
            ) : (
              veri.gruplar.slice(0, 5).map((g, i) => (
                <article key={g.kok_sebep} className="rounded-xl border border-slate-200 border-l-4 border-l-tl-yellow bg-white p-3">
                  <p className="text-xs font-black text-tl-navy">
                    {i + 1}. {g.kok_sebep} <span className="font-mono text-slate-400">· {g.adet} {t.kayit} · %{g.oran}</span>
                  </p>
                  <ul className="mt-1.5 grid gap-1">
                    {g.oneriler.map((o) => (
                      <li key={o} className="flex gap-2 text-xs font-bold leading-snug text-slate-600">
                        <ShieldCheck aria-hidden className="mt-0.5 size-3.5 shrink-0 text-emerald-500" />
                        {o}
                      </li>
                    ))}
                  </ul>
                </article>
              ))
            )}
          </div>
          <div className="grid content-start gap-3 rounded-2xl border border-slate-200 bg-gradient-to-br from-slate-50 to-white p-4">
            <p className="flex items-center gap-2 text-[11px] font-black text-tl-navy">
              <Bot aria-hidden className="size-4 text-tl-blue" />
              {t.yz}
              <span className={`ml-auto rounded-md px-2 py-0.5 text-[10px] font-black ${hazir ? "bg-emerald-100 text-emerald-700" : "bg-slate-200 text-slate-500"}`}>
                {hazir ? t.yzHazir(veri.yz.model) : t.yzKapali}
              </span>
            </p>
            {hazir ? null : (
              <>
                <p className="text-xs font-bold leading-snug text-slate-500">{t.yzKapaliAciklama}</p>
                {veri.yz.eksik.length > 0 ? (
                  <p className="text-[10px] font-bold text-slate-400">
                    {t.yzEksik}: <code className="font-mono">{veri.yz.eksik.join(", ")}</code>
                  </p>
                ) : null}
              </>
            )}
            <button type="button" className={`${DUGME_SARI} !min-w-0`} disabled={!hazir || yz.isPending || veri.gruplar.length === 0} onClick={() => yz.mutate()} title={veri.gruplar.length === 0 ? t.yzIpucu : undefined}>
              <Sparkles aria-hidden className="size-4" />
              {yz.isPending ? t.yzBekle : t.yzIste}
            </button>
            {yz.isError ? <Bildirim ton="kirmizi">{hataMesaji(yz.error, t.yzHata)}</Bildirim> : null}
            {yorum ? (
              <div className="rounded-xl border border-tl-blue/20 bg-white p-3">
                <p className="mb-1 text-[10px] font-black uppercase tracking-wide text-tl-blue">{t.yzYorum}</p>
                <p className="whitespace-pre-wrap text-xs font-bold leading-relaxed text-slate-700">{yorum}</p>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </Panel>
  )
}
