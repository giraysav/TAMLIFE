import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus, RotateCcw, Save, Trash2 } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Bildirim, Bolum, DUGME, DUGME_ANA, GIRDI, HataKutu, Rozet, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import type { AtamaSonucu, Kriter, KriterTablosu, SkorMeta } from "@/yonetim/api"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { zaman } from "@/lib/bicim"
import { OtoMetin } from "@/yonetim/utilizasyon/ortak"
import { uym } from "@/yonetim/utilizasyon/metin"
import type { UYM } from "@/yonetim/utilizasyon/metin"

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

/** Kriter tablolari (cati / istirak): barem hucreleri = kural, X sabit puan, agirlik, Servis Cesitliligi servis puanlari.
 *  Veri kaynagi salt okunur etikettir (2026-11-21: kriter basina kaynak duzenleyicisi kalkti; kayitli kaynak_secimi korunur). */
export function Kriterler({ dil }: { dil: Dil }) {
  const t = uym(dil)
  const u = t.util
  const qc = useQueryClient()
  const [kapsam, setKapsam] = useState<Kapsam>("parent")
  const tablo = useQuery({ queryKey: [...ANAHTAR.skorKriter, kapsam], queryFn: () => oku<KriterTablosu>(`/api/v1/skor/kriterler/${kapsam}`) })
  const meta = useQuery({ queryKey: ANAHTAR.skorMeta, queryFn: () => oku<SkorMeta>("/api/v1/skor/meta") })
  const [taslak, setTaslak] = useState<Kriter[] | null>(null) // null = sunucudaki surum
  const [acik, setAcik] = useState<number | null>(null) // servis listesi acik satir
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
                        <button type="button" className="mt-1 text-[0.625rem] font-black text-tl-blue underline-offset-2 hover:underline" onClick={() => setAcik(acik === i ? null : i)}>
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
                      <span
                        title={u.kaynakSabit}
                        className={`inline-flex max-w-full items-center rounded-2xl border px-2.5 py-1 text-left text-[0.625rem] font-black leading-tight ${
                          secim
                            ? "border-tl-navy bg-tl-navy text-tl-yellow"
                            : tur === KAYNAKSIZ
                              ? "border-rose-300 bg-rose-500/10 text-rose-700"
                              : "border-emerald-300 bg-emerald-500/10 text-emerald-700"
                        }`}
                      >
                        {secim ? `${secim.kaynak} · ${m.islemler[secim.islem] ?? secim.islem}` : (m.kaynak_adlari[tur] ?? tur)}
                      </span>
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
                  acik === i ? (
                    <tr key={`a-${i}`}>
                      <td colSpan={9} className="bg-slate-50 px-3 py-3">
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
                          onPuan={(ad, puan) =>
                            degistir(i, (yeni) => {
                              yeni.servis_puanlari = { ...servisTablosu, [ad]: puan }
                              return yeni
                            })
                          }
                        />
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

/** Servis Cesitliligi: sayilacak servisler (isaretsiz = hepsi) ve servis puanlari (0-100, tum musterilere gecerli; kaydedince
 *  kriter tablosunun yeni surumuyle yazilir). */
function ServisSecimi({
  tablo,
  dahil,
  t,
  onDegis,
  onPuan,
}: {
  tablo: Record<string, number>
  dahil: string[] | undefined
  t: UYM
  onDegis: (dahil: string[] | undefined) => void
  onPuan: (ad: string, puan: number) => void
}) {
  const u = t.util
  const adlar = Object.keys(tablo)
  const secili = new Set((dahil ?? adlar).map(normal))
  return (
    <fieldset className="grid gap-2">
      <legend className="text-[0.625rem] font-black uppercase tracking-wide text-slate-500">{u.servisler}</legend>
      <p className="text-[0.6875rem] font-bold text-slate-500">{u.servisPuanNot}</p>
      <div className="flex flex-wrap gap-2">
        {adlar.map((ad) => (
          <div
            key={ad}
            className={`inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs font-bold text-slate-700 ${secili.has(normal(ad)) ? "" : "opacity-60"}`}
          >
            <label className="inline-flex cursor-pointer items-center gap-1.5">
              <input
                type="checkbox"
                checked={secili.has(normal(ad))}
                onChange={(e) => {
                  const yeni = adlar.filter((a) => (normal(a) === normal(ad) ? e.target.checked : secili.has(normal(a))))
                  onDegis(yeni.length === adlar.length ? undefined : yeni)
                }}
              />
              {ad}
            </label>
            <input
              type="number"
              min={0}
              max={100}
              step="any"
              className="w-12 rounded-md border border-slate-300 px-1 py-0.5 text-center font-mono text-tl-navy focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
              aria-label={`${ad} ${u.puan}`}
              value={tablo[ad]}
              onChange={(e) => onPuan(ad, e.target.value === "" ? 0 : Math.min(100, Math.max(0, Number(e.target.value))))}
            />
          </div>
        ))}
      </div>
    </fieldset>
  )
}
