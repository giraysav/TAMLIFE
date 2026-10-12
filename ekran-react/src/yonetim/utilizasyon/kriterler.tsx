import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Eye, Plus, RotateCcw, Save, Trash2, X } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Alan, Bildirim, Bolum, DUGME, DUGME_ANA, GIRDI, HataKutu, Rozet, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import type { AtamaSonucu, KaynakOnizleme, KaynakSecimi, Kriter, KriterTablosu, SkorMeta } from "@/yonetim/api"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { zaman } from "@/lib/bicim"
import { ym } from "@/yonetim/metin"
import type { YM } from "@/yonetim/metin"
import { OtoMetin, degerYaz } from "@/yonetim/utilizasyon/ortak"

type Kapsam = "parent" | "affiliate"
const BAREM = ["b30", "b50", "b70", "b100"] as const
const PUAN: Record<(typeof BAREM)[number], number> = { b30: 30, b50: 50, b70: 70, b100: 100 }
const KAYNAKSIZ = "auto_kaynaksiz"
const ASCII: Record<string, string> = { ç: "c", ğ: "g", ı: "i", ö: "o", ş: "s", ü: "u", Ç: "C", Ğ: "G", İ: "I", Ö: "O", Ş: "S", Ü: "U" }

/** Sunucudaki ortak.normal ile ayni: Turkce harf -> ASCII, kucuk harf, tek bosluk. */
export function normal(metin: unknown): string {
  return String(metin ?? "")
    .replace(/[çğıöşüÇĞİÖŞÜ]/g, (h) => ASCII[h] ?? h)
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim()
}

/** motor.tur_coz: kayitli tur otomatikse o, degilse basliktan (ilk eslesen ipucu). Sunucu kayitta ayni kurali uygular. */
export function turCoz(k: Kriter, meta: Pick<SkorMeta, "metrikler" | "tur_ipuclari">): string {
  if (k.type && k.type in meta.metrikler) return k.type
  const baslik = normal(k.title)
  return meta.tur_ipuclari.find(([ipucu]) => baslik.includes(ipucu))?.[1] ?? KAYNAKSIZ
}

/** motor.sabit_puan: Sozlesme / Raporlama satirinda TEK X'li hucre (yoksa ya da birden coksa null). */
export function xHucresi(k: Kriter, tur: string, meta: Pick<SkorMeta, "sabit_puan_turleri">): (typeof BAREM)[number] | null {
  if (!meta.sabit_puan_turleri.includes(tur)) return null
  const isaretli = BAREM.filter((b) => normal(k[b]) === "x")
  return isaretli.length === 1 ? isaretli[0] : null
}

function kopya(k: Kriter): Kriter {
  return JSON.parse(JSON.stringify(k)) as Kriter
}

/** Kriter tablolari (cati / istirak): barem hucreleri = kural, X sabit puan, agirlik, kriter basina veri kaynagi secimi. */
export function Kriterler({ dil }: { dil: Dil }) {
  const t = ym(dil)
  const u = t.util
  const qc = useQueryClient()
  const [kapsam, setKapsam] = useState<Kapsam>("parent")
  const tablo = useQuery({ queryKey: [...ANAHTAR.skorKriter, kapsam], queryFn: () => oku<KriterTablosu>(`/api/v1/skor/kriterler/${kapsam}`) })
  const meta = useQuery({ queryKey: ANAHTAR.skorMeta, queryFn: () => oku<SkorMeta>("/api/v1/skor/meta") })
  const [taslak, setTaslak] = useState<Kriter[] | null>(null) // null = sunucudaki surum
  const [acik, setAcik] = useState<{ i: number; ne: "kaynak" | "servis" } | null>(null)
  const [bilgi, setBilgi] = useState<{ ton: "yesil" | "amber"; metin: string } | null>(null)

  useEffect(() => {
    setTaslak(null)
    setAcik(null)
  }, [kapsam])

  const liste = taslak ?? tablo.data?.criteria ?? []
  const kirli = taslak !== null
  const degistir = (i: number, yama: Partial<Kriter> | ((k: Kriter) => Kriter)) =>
    setTaslak(liste.map((k, j) => (j === i ? (typeof yama === "function" ? yama(kopya(k)) : { ...k, ...yama }) : k)))

  const kaydet = useMutation({
    mutationFn: () =>
      yaz<{ version: number; uygulama: AtamaSonucu | null }>("PUT", `/api/v1/skor/kriterler/${kapsam}`, {
        criteria: liste.map((k) => ({ ...k, weight: Number(k.weight) || 0 })),
      }),
    onSuccess: (s) => {
      setTaslak(null)
      setAcik(null)
      const ek = s.uygulama ? ` ${u.otomatikAtama(s.uygulama.uygulanan.length, s.uygulama.atlanan.length, s.uygulama.degismeyen)}` : ""
      setBilgi({ ton: "yesil", metin: u.kaydedildi(s.version) + ek })
      for (const anahtar of [ANAHTAR.skorKriter, ANAHTAR.skorAgac, ANAHTAR.skorSiralama, ["skor", "onizleme"]]) void qc.invalidateQueries({ queryKey: anahtar })
    },
    onError: (e) => setBilgi({ ton: "amber", metin: hataMesaji(e, t.islemBasarisiz) }),
  })

  if (tablo.isPending || meta.isPending) return <Yukleniyor metin={t.yukleniyor} iskelet />
  if (tablo.isError || meta.isError) return <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void tablo.refetch()} />
  const m = meta.data
  const toplam = liste.reduce((top, k) => top + (Number(k.weight) || 0), 0)

  return (
    <Bolum anahtar="yonetim-util-kriterler" baslik={kapsam === "parent" ? u.catiTablo : u.istirakTablo}>
      <div className="grid gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {(["parent", "affiliate"] as const).map((k) => (
            <button
              key={k}
              type="button"
              aria-pressed={kapsam === k}
              className={kapsam === k ? `${DUGME} !border-tl-navy !bg-tl-navy !text-white` : DUGME}
              onClick={() => {
                if (kirli && !window.confirm(u.kaydedilmedi)) return
                setKapsam(k)
                setBilgi(null)
              }}
            >
              {k === "parent" ? u.catiTablo : u.istirakTablo}
            </button>
          ))}
          <span className="text-[0.6875rem] font-bold text-slate-400">
            {tablo.data.varsayilan ? <Rozet ton="amber">{u.varsayilan}</Rozet> : u.surum(tablo.data.version, tablo.data.updated_by, tablo.data.updated_at ? zaman(tablo.data.updated_at) : "")}
          </span>
          {kirli ? <Rozet ton="sari">{u.kaydedilmedi}</Rozet> : null}
        </div>
        <p className="text-[0.6875rem] font-bold text-slate-400">
          {u.kuralIpucu} {u.xIpucu}
          {kapsam === "affiliate" ? ` ${u.istirakNotu}` : ""}
        </p>

        <div className="overflow-x-auto rounded-xl border border-slate-200">
          {/* Sabit kolon oranlari (table-fixed): hucre metni kesilmez, alan yazdikca asagi uzar (OtoMetin). */}
          <table className="w-full min-w-[64rem] table-fixed text-left text-xs">
            <caption className="sr-only">{kapsam === "parent" ? u.catiTablo : u.istirakTablo}</caption>
            <colgroup>
              <col className="w-[15%]" />
              <col className="w-[21%]" />
              {BAREM.map((b) => (
                <col key={b} className="w-[10%]" />
              ))}
              <col className="w-[6%]" />
              <col className="w-[14%]" />
              <col className="w-[4%]" />
            </colgroup>
            <thead className="bg-tl-navy text-white">
              <tr>
                <th scope="col" className="px-2 py-2 font-black">{u.kriter}</th>
                <th scope="col" className="px-2 py-2 font-black">{u.metrik}</th>
                {BAREM.map((b) => (
                  <th key={b} scope="col" className="px-2 py-2 text-center font-black">
                    {PUAN[b]}
                  </th>
                ))}
                <th scope="col" className="bg-tl-yellow/20 px-1 py-2 text-center font-black">{u.agirlik}</th>
                <th scope="col" className="px-2 py-2 text-center font-black">{u.veriKaynagi}</th>
                <th scope="col" className="px-1 py-2">
                  <span className="sr-only">{u.sil}</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {liste.map((k, i) => {
                const tur = turCoz(k, m)
                const x = xHucresi(k, tur, m)
                const secim = k.kaynak_secimi
                const servisli = tur === "servis_cesitliligi"
                const servisTablosu = k.servis_puanlari ?? m.servis_puanlari
                return [
                  <tr key={`k-${i}`} className="align-top even:bg-slate-50/70">
                    <td className="px-1.5 py-1.5">
                      <OtoMetin
                        className="font-black text-tl-navy"
                        aria-label={u.kriter}
                        placeholder={u.baslikYer}
                        maxLength={200}
                        deger={k.title}
                        onDeger={(v) => degistir(i, { title: v, type: "" })}
                      />
                      {servisli ? (
                        <button type="button" className="mt-1 text-[0.625rem] font-black text-tl-blue underline-offset-2 hover:underline" onClick={() => setAcik(acik?.i === i && acik.ne === "servis" ? null : { i, ne: "servis" })}>
                          {u.servisler}: {k.servis_dahil ? u.servisSecili(k.servis_dahil.length, Object.keys(servisTablosu).length) : u.servisTumu}
                        </button>
                      ) : null}
                    </td>
                    <td className="px-1.5 py-1.5">
                      <OtoMetin className="font-normal" aria-label={u.metrik} maxLength={200} deger={k.metric ?? ""} onDeger={(v) => degistir(i, { metric: v })} />
                    </td>
                    {BAREM.map((b) => {
                      const kilitli = x !== null && x !== b
                      return (
                        <td key={b} className="bg-slate-50/70 px-1 py-1.5">
                          <OtoMetin
                            className={`text-center ${kilitli ? "cursor-not-allowed opacity-40" : ""} ${x === b ? "!border-tl-navy !bg-tl-yellow/30" : ""}`}
                            aria-label={`${k.title || u.kriter} ${PUAN[b]}`}
                            title={kilitli ? u.xKilit : undefined}
                            disabled={kilitli}
                            maxLength={120}
                            placeholder={m.varsayilan_kurallar[tur]?.[b] ?? ""}
                            deger={k[b] ?? ""}
                            onDeger={(v) => {
                              const deger = m.sabit_puan_turleri.includes(tur) && normal(v) === "x" ? "X" : v
                              degistir(i, (yeni) => {
                                yeni[b] = deger
                                return yeni
                              })
                            }}
                          />
                        </td>
                      )
                    })}
                    <td className="bg-tl-yellow/10 px-1 py-1.5">
                      <input
                        type="number"
                        min={0}
                        max={100}
                        className={`${GIRDI} !px-1 !py-1.5 text-center font-black text-tl-navy`}
                        aria-label={`${k.title || u.kriter} ${u.agirlik}`}
                        value={k.weight}
                        onChange={(e) => degistir(i, { weight: e.target.value })}
                      />
                    </td>
                    <td className="px-1.5 py-1.5 text-center">
                      <button
                        type="button"
                        aria-expanded={acik?.i === i && acik.ne === "kaynak"}
                        onClick={() => setAcik(acik?.i === i && acik.ne === "kaynak" ? null : { i, ne: "kaynak" })}
                        className={`inline-flex max-w-full items-center rounded-2xl border px-2.5 py-1 text-left text-[0.625rem] font-black leading-tight focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow ${
                          secim
                            ? "border-tl-navy bg-tl-navy text-tl-yellow"
                            : tur === KAYNAKSIZ
                              ? "border-rose-300 bg-rose-500/10 text-rose-700"
                              : "border-emerald-300 bg-emerald-500/10 text-emerald-700"
                        }`}
                      >
                        {secim ? `${secim.kaynak} · ${m.islemler[secim.islem] ?? secim.islem}` : (m.kaynak_adlari[tur] ?? tur)} ▾
                      </button>
                    </td>
                    <td className="px-1 py-1.5 text-center">
                      <button
                        type="button"
                        className="inline-flex size-7 items-center justify-center rounded-full bg-rose-500/10 text-rose-600 hover:bg-rose-600 hover:text-white focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
                        aria-label={`${u.sil}: ${k.title}`}
                        title={u.sil}
                        onClick={() => {
                          setTaslak(liste.filter((_, j) => j !== i))
                          setAcik(null)
                        }}
                      >
                        <Trash2 aria-hidden className="size-3.5" />
                      </button>
                    </td>
                  </tr>,
                  acik?.i === i ? (
                    <tr key={`a-${i}`}>
                      <td colSpan={9} className="bg-slate-50 px-3 py-3">
                        {acik.ne === "servis" ? (
                          <ServisSecimi
                            tablo={servisTablosu}
                            dahil={k.servis_dahil}
                            t={t}
                            onDegis={(dahil) =>
                              degistir(i, (yeni) => {
                                if (dahil === undefined) delete yeni.servis_dahil
                                else yeni.servis_dahil = dahil
                                return yeni
                              })
                            }
                          />
                        ) : (
                          <KaynakFormu
                            key={`${kapsam}-${i}`}
                            kriter={k}
                            tur={tur}
                            meta={m}
                            t={t}
                            onKapat={() => setAcik(null)}
                            onUygula={(s) => {
                              degistir(i, (yeni) => {
                                if (s === undefined) delete yeni.kaynak_secimi
                                else yeni.kaynak_secimi = s
                                return yeni
                              })
                              setAcik(null)
                            }}
                          />
                        )}
                      </td>
                    </tr>
                  ) : null,
                ]
              })}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Rozet ton={toplam === 100 ? "yesil" : "amber"}>{u.toplamAgirlik(toplam)}</Rozet>
          <button type="button" className={DUGME} onClick={() => setTaslak([...liste, { title: "", type: "", metric: "", b30: "", b50: "", b70: "", b100: "", weight: 0 }])}>
            <Plus aria-hidden className="size-3.5" />
            {u.kriterEkle}
          </button>
          {kirli ? (
            <button
              type="button"
              className={DUGME}
              onClick={() => {
                setTaslak(null)
                setAcik(null)
              }}
            >
              <RotateCcw aria-hidden className="size-3.5" />
              {u.degisiklikleriAt}
            </button>
          ) : null}
          <button type="button" className={`${DUGME_ANA} ml-auto`} disabled={(!kirli && !tablo.data.varsayilan) || kaydet.isPending} onClick={() => kaydet.mutate()}>
            <Save aria-hidden className="size-4" />
            {t.kaydet}
          </button>
        </div>
        {bilgi ? <Bildirim ton={bilgi.ton}>{bilgi.metin}</Bildirim> : null}
      </div>
    </Bolum>
  )
}

/** Servis Cesitliligi: sayilacak servisler (isaretsiz = hepsi). */
function ServisSecimi({ tablo, dahil, t, onDegis }: { tablo: Record<string, number>; dahil: string[] | undefined; t: YM; onDegis: (dahil: string[] | undefined) => void }) {
  const adlar = Object.keys(tablo)
  const secili = new Set((dahil ?? adlar).map(normal))
  return (
    <fieldset className="grid gap-2">
      <legend className="text-[0.625rem] font-black uppercase tracking-wide text-slate-500">{t.util.servisler}</legend>
      <div className="flex flex-wrap gap-2">
        {adlar.map((ad) => (
          <label key={ad} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs font-bold text-slate-700">
            <input
              type="checkbox"
              checked={secili.has(normal(ad))}
              onChange={(e) => {
                const yeni = adlar.filter((a) => (normal(a) === normal(ad) ? e.target.checked : secili.has(normal(a))))
                onDegis(yeni.length === adlar.length ? undefined : yeni)
              }}
            />
            {ad} <span className="font-mono text-slate-400">{tablo[ad]}</span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}

function bosSecim(tur: string, meta: SkorMeta): KaynakSecimi {
  return { kaynak: meta.partiler[0]?.kaynak ?? "", eslesme: [{ sutun: "", alan: "customer_no" }], islem: meta.tur_islemleri[tur]?.[0] ?? "say", sutun: "", filtreler: [], esleme: [] }
}

/** Kriter veri kaynagi secimi (uretim Veri Yonlendirici > kriter > Veri kaynagi): tampon partisinden esle -> kosul -> islem. */
function KaynakFormu({
  kriter,
  tur,
  meta,
  t,
  onUygula,
  onKapat,
}: {
  kriter: Kriter
  tur: string
  meta: SkorMeta
  t: YM
  onUygula: (s: KaynakSecimi | undefined) => void
  onKapat: () => void
}) {
  const u = t.util
  const [s, setS] = useState<KaynakSecimi>(() => (kriter.kaynak_secimi ? (JSON.parse(JSON.stringify(kriter.kaynak_secimi)) as KaynakSecimi) : bosSecim(tur, meta)))
  const [eslemeMetni, setEslemeMetni] = useState(() => (kriter.kaynak_secimi?.esleme ?? []).map(([a, b]) => `${a} => ${b}`).join("\n"))
  const [hata, setHata] = useState("")
  const [sonuc, setSonuc] = useState<KaynakOnizleme | null>(null)
  const islemler = meta.tur_islemleri[tur] ?? []
  const parti = meta.partiler.find((p) => p.kaynak === s.kaynak)
  const kullanilan = [...s.eslesme.map((e) => e.sutun), ...s.filtreler.map((f) => f.sutun), s.sutun].filter(Boolean)
  const sutunlar = [...new Set([...(parti?.sutunlar ?? []), ...kullanilan])]

  function temiz(): KaynakSecimi | null {
    const secim: KaynakSecimi = {
      ...s,
      eslesme: s.eslesme.filter((e) => e.sutun),
      filtreler: s.filtreler.filter((f) => f.sutun),
      sutun: s.islem === "say" ? "" : s.sutun,
      esleme:
        s.islem === "esle_liste"
          ? eslemeMetni
              .split("\n")
              .map((satir) => satir.split("=>").map((p) => p.trim()))
              .filter((p): p is [string, string] => p.length === 2 && Boolean(p[0]) && Boolean(p[1]))
          : [],
    }
    if (!secim.eslesme.length) {
      setHata(u.hataEslesme)
      return null
    }
    if (secim.islem !== "say" && !secim.sutun) {
      setHata(u.hataSutun)
      return null
    }
    setHata("")
    return secim
  }

  const onizle = useMutation({
    mutationFn: (secim: KaynakSecimi) => yaz<KaynakOnizleme>("POST", "/api/v1/skor/kaynak-onizle", { satir: { title: kriter.title, type: tur, kaynak_secimi: secim } }),
    onSuccess: setSonuc,
    onError: (e) => {
      setSonuc(null)
      setHata(hataMesaji(e, t.islemBasarisiz))
    },
  })

  const sutunSecimi = (deger: string, onDegis: (v: string) => void, etiket: string) => (
    <select className={`${GIRDI} !py-1.5`} aria-label={etiket} value={deger} onChange={(e) => onDegis(e.target.value)}>
      <option value="">{t.secin}</option>
      {sutunlar.map((c) => (
        <option key={c} value={c}>
          {c}
        </option>
      ))}
    </select>
  )

  return (
    <div className="grid gap-3">
      <div>
        <p className="text-xs font-black text-tl-navy">{u.kaynakSecimi}</p>
        <p className="text-[0.6875rem] font-bold text-slate-400">{u.kaynakSecimiAciklama}</p>
      </div>
      {tur === KAYNAKSIZ || islemler.length === 0 ? (
        <Bildirim ton="amber">{meta.kaynak_adlari[KAYNAKSIZ]}</Bildirim>
      ) : meta.partiler.length === 0 ? (
        <Bildirim ton="amber">{u.partiYok}</Bildirim>
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-3">
            <Alan etiket={u.kaynak} ipucu={parti ? u.parti(parti.parti, parti.satir) : undefined}>
              <select className={`${GIRDI} !py-1.5`} value={s.kaynak} onChange={(e) => setS({ ...s, kaynak: e.target.value })}>
                {meta.partiler.map((p) => (
                  <option key={p.kaynak} value={p.kaynak}>
                    {p.kaynak}
                  </option>
                ))}
                {!parti && s.kaynak ? <option value={s.kaynak}>{s.kaynak}</option> : null}
              </select>
            </Alan>
            <Alan etiket={u.islem}>
              <select className={`${GIRDI} !py-1.5`} value={s.islem} onChange={(e) => setS({ ...s, islem: e.target.value })}>
                {islemler.map((i) => (
                  <option key={i} value={i}>
                    {meta.islemler[i] ?? i}
                  </option>
                ))}
              </select>
            </Alan>
            {s.islem !== "say" ? <Alan etiket={u.sutun}>{sutunSecimi(s.sutun, (v) => setS({ ...s, sutun: v }), u.sutun)}</Alan> : null}
          </div>

          <fieldset className="grid gap-1.5">
            <legend className="text-[0.625rem] font-black uppercase tracking-wide text-slate-500">{u.eslesme}</legend>
            {s.eslesme.map((e, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2">
                <span className="w-56">{sutunSecimi(e.sutun, (v) => setS({ ...s, eslesme: s.eslesme.map((x, j) => (j === i ? { ...x, sutun: v } : x)) }), u.sutun)}</span>
                <span className="text-xs font-black text-slate-400">→</span>
                <select
                  className={`${GIRDI} !w-48 !py-1.5`}
                  aria-label={u.eslesme}
                  value={e.alan}
                  onChange={(ev) => setS({ ...s, eslesme: s.eslesme.map((x, j) => (j === i ? { ...x, alan: ev.target.value } : x)) })}
                >
                  {Object.entries(meta.eslesme_alanlari).map(([k, ad]) => (
                    <option key={k} value={k}>
                      {ad}
                    </option>
                  ))}
                </select>
                {s.eslesme.length > 1 ? (
                  <button type="button" className={DUGME} aria-label={t.sil} onClick={() => setS({ ...s, eslesme: s.eslesme.filter((_, j) => j !== i) })}>
                    <X aria-hidden className="size-3.5" />
                  </button>
                ) : null}
              </div>
            ))}
            {s.eslesme.length < 3 ? (
              <button type="button" className={`${DUGME} justify-self-start`} onClick={() => setS({ ...s, eslesme: [...s.eslesme, { sutun: "", alan: "customer_no" }] })}>
                <Plus aria-hidden className="size-3.5" />
                {u.eslesmeEkle}
              </button>
            ) : null}
          </fieldset>

          <fieldset className="grid gap-1.5">
            <legend className="text-[0.625rem] font-black uppercase tracking-wide text-slate-500">{u.kosullar}</legend>
            {s.filtreler.map((f, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2">
                <span className="w-56">{sutunSecimi(f.sutun, (v) => setS({ ...s, filtreler: s.filtreler.map((x, j) => (j === i ? { ...x, sutun: v } : x)) }), u.sutun)}</span>
                <select
                  className={`${GIRDI} !w-40 !py-1.5`}
                  aria-label={u.islem}
                  value={f.islec}
                  onChange={(e) => setS({ ...s, filtreler: s.filtreler.map((x, j) => (j === i ? { ...x, islec: e.target.value } : x)) })}
                >
                  {Object.entries(meta.islecler).map(([k, ad]) => (
                    <option key={k} value={k}>
                      {ad}
                    </option>
                  ))}
                </select>
                {meta.degersiz_islecler.includes(f.islec) ? null : (
                  <input
                    className={`${GIRDI} !w-48 !py-1.5`}
                    aria-label={u.deger}
                    placeholder={u.deger}
                    maxLength={200}
                    value={f.deger}
                    onChange={(e) => setS({ ...s, filtreler: s.filtreler.map((x, j) => (j === i ? { ...x, deger: e.target.value } : x)) })}
                  />
                )}
                <button type="button" className={DUGME} aria-label={t.sil} onClick={() => setS({ ...s, filtreler: s.filtreler.filter((_, j) => j !== i) })}>
                  <X aria-hidden className="size-3.5" />
                </button>
              </div>
            ))}
            {s.filtreler.length < 5 ? (
              <button type="button" className={`${DUGME} justify-self-start`} onClick={() => setS({ ...s, filtreler: [...s.filtreler, { sutun: "", islec: "esit", deger: "" }] })}>
                <Plus aria-hidden className="size-3.5" />
                {u.kosulEkle}
              </button>
            ) : null}
          </fieldset>

          {s.islem === "esle_liste" ? (
            <Alan etiket={u.esleme}>
              <textarea className={`${GIRDI} min-h-24 font-mono`} value={eslemeMetni} onChange={(e) => setEslemeMetni(e.target.value)} placeholder={"mpls => Data\nvoip => Ses"} />
            </Alan>
          ) : null}

          {sonuc ? (
            <div className="grid gap-1 rounded-lg bg-white p-2 text-[0.6875rem] font-bold text-slate-600 ring-1 ring-slate-200">
              <p className="text-tl-navy">{u.onizlemeOzet(sonuc.musteri, sonuc.eslesmeyen, sonuc.filtrelenen, sonuc.toplam_satir)}</p>
              {sonuc.eslesmeyen_ornek.length ? (
                <p className="text-amber-700">
                  {u.eslesmeyenOrnek} {sonuc.eslesmeyen_ornek.map(([v, n]) => `${v} (${n})`).join(" · ")}
                </p>
              ) : null}
              {sonuc.ornek.slice(0, 5).map((o) => (
                <p key={o.ad} className="truncate font-mono">
                  {o.ad}: {degerYaz(o.deger)}
                </p>
              ))}
            </div>
          ) : null}
        </>
      )}
      {hata ? <p className="text-xs font-bold text-rose-600">{hata}</p> : null}
      <div className="flex flex-wrap items-center gap-2">
        {meta.partiler.length > 0 && islemler.length > 0 ? (
          <>
            <button
              type="button"
              className={DUGME}
              disabled={onizle.isPending}
              onClick={() => {
                const secim = temiz()
                if (secim) onizle.mutate(secim)
              }}
            >
              <Eye aria-hidden className="size-3.5" />
              {u.onizle}
            </button>
            <button
              type="button"
              className={DUGME_ANA}
              onClick={() => {
                const secim = temiz()
                if (secim) onUygula(secim)
              }}
            >
              {u.uygula}
            </button>
          </>
        ) : null}
        {kriter.kaynak_secimi ? (
          <button type="button" className={`${DUGME} !text-rose-600`} onClick={() => onUygula(undefined)}>
            {u.otomatigeDon}
          </button>
        ) : null}
        <button type="button" className={DUGME} onClick={onKapat}>
          {t.vazgec}
        </button>
      </div>
    </div>
  )
}
