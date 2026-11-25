import { Fragment, useLayoutEffect, useRef, useState } from "react"
import { ChevronDown, ChevronRight } from "lucide-react"
import type { ComponentProps } from "react"
import { Bildirim, GIRDI, Rozet } from "@/components/sayfa-ui"
import type { AgacMusterisi, AltKriter, KaynakDurumu, KriterSonucu, SkorAgaci } from "@/yonetim/api"
import { adaGoreSirala } from "@/lib/bicim"
import type { UYM } from "@/yonetim/utilizasyon/metin"

/** Utilizasyon alt bolumlerinin ortak parcalari. */

const DOGAL_BOY = typeof CSS !== "undefined" && typeof CSS.supports === "function" && CSS.supports("field-sizing", "content")

/** Yazdikca boyu uzayan tek paragraf metin alani: uzun metin kesilmez, alt satira kayar (Enter yeni satir acmaz).
 * Edge/Chrome'da CSS field-sizing, digerlerinde scrollHeight ile. */
export function OtoMetin({
  deger,
  onDeger,
  className = "",
  ...props
}: Omit<ComponentProps<"textarea">, "value" | "onChange" | "rows"> & { deger: string; onDeger: (deger: string) => void }) {
  const ref = useRef<HTMLTextAreaElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el || DOGAL_BOY) return
    el.style.height = "auto"
    if (el.scrollHeight) el.style.height = `${el.scrollHeight}px`
  }, [deger])
  return (
    <textarea
      ref={ref}
      rows={1}
      value={deger}
      onChange={(e) => onDeger(e.target.value.replace(/\s*\n\s*/g, " "))}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.preventDefault()
      }}
      className={`${GIRDI} block resize-none overflow-hidden !py-1.5 leading-snug field-sizing-content ${className}`}
      {...props}
    />
  )
}

export const AGAC_YOLU = "/api/v1/skor/agac"

/** Final skor gosterimi (musteri kartiyla ayni: %70.0). */
export function skorYaz(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : `%${n.toFixed(1)}`
}

/** Metrik degeri: liste virgulle, sayi yerel bicimde. */
export function degerYaz(d: unknown): string {
  if (d === null || d === undefined || d === "") return "—"
  if (Array.isArray(d)) return d.length ? d.join(", ") : "—"
  if (typeof d === "number") return d.toLocaleString()
  return String(d)
}

/** Agactaki tum cati musteriler (personel altindakiler + atanmamis), ada gore. */
export function tumCatilar(agac: SkorAgaci): AgacMusterisi[] {
  const liste = [...agac.personel.flatMap((p) => p.musteriler), ...agac.atanmamis]
  return adaGoreSirala(liste, (a) => a.ad)
}

/** Kaynak durumlari + hesap uyarilari (renk + metin). */
export function KaynakListesi({ kaynaklar, uyarilar, t }: { kaynaklar: KaynakDurumu[]; uyarilar: string[]; t: UYM }) {
  const u = t.util
  return (
    <div className="grid gap-2">
      <p className="text-[0.6875rem] font-bold text-slate-400">{u.kaynaklarAciklama}</p>
      <ul className="grid gap-1.5">
        {kaynaklar.map((k) => (
          <li key={k.ad} className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-slate-100 py-1.5 text-xs last:border-0">
            <span className="w-24 shrink-0">
              <Rozet ton={k.hazir ? "yesil" : "gri"}>{k.hazir ? u.hazir : u.hazirDegil}</Rozet>
            </span>
            <span className="w-44 shrink-0 font-black text-tl-navy">{k.ad}</span>
            <span className="min-w-0 flex-1 break-words font-bold text-slate-500">
              {k.metrikler.join(", ") || "—"}
              {k.neden ? <span className="block text-[0.6875rem] text-slate-400">{k.neden}</span> : null}
            </span>
          </li>
        ))}
      </ul>
      {uyarilar.length > 0 ? (
        <Bildirim ton="amber">
          <span className="font-black">{u.uyarilar}: </span>
          {uyarilar.join(" · ")}
        </Bildirim>
      ) : null}
    </div>
  )
}

/** Manuel puanlamada dokumun duzenlenebilir hali: baslik -> secilen puan (Servis Cesitliligi: alinan servis adlari; Sozlesme: elle
 *  saglanan alt kriter adlari). Servis puanlari dokumde degil, Kriterler tablosunda degisir. */
export type DokumSecimi = {
  secim: Record<string, number | string[]>
  onSecim: (baslik: string, deger: number | string[]) => void
  kilitli?: boolean
}

const yuvarla = (n: number) => Math.round(n * 100) / 100

/** Servis Cesitliligi kriter puani (sunucuyla ayni): alinan servislerin puan toplami, kriterin baremine (alt..ust -> puan) gore. */
function servisPuani(servisler: { ad: string; puan: number }[], kurallar: KriterSonucu["kurallar"], secilen: string[]) {
  const alinan = servisler.filter((s) => secilen.includes(s.ad)).reduce((t, s) => t + s.puan, 0)
  const kural = [...(kurallar ?? [])].sort((a, b) => b.puan - a.puan).find((r) => alinan >= r.alt && (r.ust === null || alinan <= r.ust))
  return { alinan, puan: kural ? kural.puan : 0 }
}

/** Sozlesme kriter puani: saglanan alt kriterlerin puan toplami (en fazla 100). Otomatik alt kriter veriden, digerleri secimden. */
function altKriterPuani(alt: AltKriter[], secilen: string[]) {
  const saglanan = alt.filter((a) => (a.oto ? a.saglandi : secilen.includes(a.ad)))
  return { puan: Math.min(100, saglanan.reduce((t, a) => t + a.puan, 0)), adlar: saglanan.map((a) => a.ad) }
}

/** Tek musterinin kriter dokumu: puan, katki, deger, kaynak, durum. `duzenle` verilirse (manuel puanlama) secenekli satirda puan secilir. */
export function KriterDokumu({ kriterler, t, duzenle }: { kriterler: KriterSonucu[]; t: UYM; duzenle?: DokumSecimi }) {
  const u = t.util
  const [acikServis, setAcikServis] = useState<string | null>(null)
  /** Duzenlemede canli puan / katki / deger (kaydedilmeden once); duzenleme yoksa sunucunun hesabi. */
  const canli = (k: KriterSonucu) => {
    const s = duzenle?.secim[k.baslik]
    if (!duzenle || s === undefined) return { puan: k.puan, katki: k.katki, deger: k.deger, oran: null }
    if (k.alt_kriterler && Array.isArray(s)) {
      const alt = altKriterPuani(k.alt_kriterler, s)
      return { puan: alt.puan, katki: yuvarla((k.agirlik * alt.puan) / 100), deger: alt.adlar, oran: null }
    }
    if (k.servisler && Array.isArray(s)) {
      const oran = servisPuani(k.servisler, k.kurallar, s)
      return { puan: oran.puan, katki: yuvarla((k.agirlik * oran.puan) / 100), deger: u.servisDeger(s.length), oran }
    }
    return typeof s === "number" ? { puan: s, katki: yuvarla((k.agirlik * s) / 100), deger: k.deger, oran: null } : { puan: k.puan, katki: k.katki, deger: k.deger, oran: null }
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full text-left text-xs">
        <caption className="sr-only">{u.dokumAc}</caption>
        <thead className="bg-slate-50 text-[0.625rem] uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="px-3 py-1.5 font-black">{u.kriter}</th>
            <th scope="col" className="px-3 py-1.5 text-right font-black">{u.agirlik}</th>
            <th scope="col" className="px-3 py-1.5 text-right font-black">{u.puan}</th>
            <th scope="col" className="px-3 py-1.5 text-right font-black">{u.katki}</th>
            <th scope="col" className="px-3 py-1.5 font-black">{u.deger}</th>
            <th scope="col" className="px-3 py-1.5 font-black">{u.kaynakKol}</th>
            <th scope="col" className="px-3 py-1.5 font-black">{u.durum}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {kriterler.map((k, i) => {
            const c = canli(k)
            const servisli = Boolean(duzenle && (k.servisler || k.alt_kriterler))
            const acik = servisli && acikServis === k.baslik
            const secilen = duzenle && Array.isArray(duzenle.secim[k.baslik]) ? (duzenle.secim[k.baslik] as string[]) : []
            return (
              <Fragment key={`${k.baslik}-${i}`}>
                <tr>
                  <td className="px-3 py-1.5 font-black text-tl-navy">
                    {servisli && duzenle ? (
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 text-left font-black text-tl-navy underline-offset-2 hover:underline"
                        aria-expanded={acik}
                        onClick={() => {
                          setAcikServis(acik ? null : k.baslik)
                          if (duzenle.secim[k.baslik] === undefined) duzenle.onSecim(k.baslik, k.secim ?? [])
                        }}
                      >
                        {acik ? <ChevronDown aria-hidden className="size-3.5" /> : <ChevronRight aria-hidden className="size-3.5" />}
                        {k.baslik || k.tur}
                      </button>
                    ) : (
                      k.baslik || k.tur
                    )}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono font-bold">{k.agirlik}</td>
                  <td className={`px-3 py-1.5 font-mono font-black text-tl-navy ${duzenle && k.secenekler ? "text-left" : "text-right"}`}>
                    {duzenle && k.secenekler ? (
                      <select
                        className={`${GIRDI} !w-auto !py-1 text-left`}
                        aria-label={u.puanSecEtiket(k.baslik || k.tur)}
                        disabled={duzenle.kilitli}
                        value={duzenle.secim[k.baslik] ?? ""}
                        onChange={(e) => duzenle.onSecim(k.baslik, Number(e.target.value))}
                      >
                        <option value="" disabled>
                          {u.puanSec}
                        </option>
                        {k.secenekler.map((s) => (
                          <option key={s.puan} value={s.puan}>
                            {s.etiket ? `${s.puan} · ${s.etiket}` : s.puan}
                          </option>
                        ))}
                      </select>
                    ) : (
                      c.puan
                    )}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono font-bold text-slate-500">{c.katki}</td>
                  <td className="max-w-56 truncate px-3 py-1.5 font-bold text-slate-600" title={degerYaz(c.deger)}>
                    {degerYaz(c.deger)}
                  </td>
                  <td className="px-3 py-1.5 font-bold text-slate-500">
                    {k.kaynak ?? "—"}
                    {k.varsayilan_kural ? <span className="ml-1 text-[0.625rem] text-slate-400">({u.varsayilanKural})</span> : null}
                  </td>
                  <td className="px-3 py-1.5">
                    <Rozet ton={k.durum === "eksik" ? "amber" : k.durum === "manuel" ? "gri" : "yesil"}>{u.durumEtiket[k.durum] ?? k.durum}</Rozet>
                  </td>
                </tr>
                {acik && duzenle && k.servisler ? (
                  <tr className="bg-slate-50/60">
                    <td colSpan={7} className="px-3 py-2">
                      <ul className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                        {k.servisler.map((s) => {
                          const var_ = secilen.includes(s.ad)
                          return (
                            <li key={s.ad} className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2 py-1">
                              <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 font-bold text-slate-700">
                                <input
                                  type="checkbox"
                                  className="size-4 cursor-pointer accent-tl-navy"
                                  aria-label={u.servisAlinir(s.ad)}
                                  disabled={duzenle.kilitli}
                                  checked={var_}
                                  onChange={(e) => duzenle.onSecim(k.baslik, e.target.checked ? [...secilen, s.ad] : secilen.filter((x) => x !== s.ad))}
                                />
                                <span className="truncate">{s.ad}</span>
                              </label>
                              <span className="shrink-0 font-mono text-slate-400">{s.puan}</span>
                            </li>
                          )
                        })}
                      </ul>
                      {c.oran ? <p className="mt-2 text-xs font-black text-tl-navy">{u.servisOzet(String(yuvarla(c.oran.alinan)), String(c.oran.puan))}</p> : null}
                      <p className="mt-1 text-[0.6875rem] font-bold text-slate-400">{u.servisNot}</p>
                    </td>
                  </tr>
                ) : acik && duzenle && k.alt_kriterler ? (
                  <tr className="bg-slate-50/60">
                    <td colSpan={7} className="px-3 py-2">
                      <ul className="grid gap-1.5 sm:grid-cols-3">
                        {k.alt_kriterler.map((a, j) => {
                          const saglanir = a.oto ? a.saglandi : secilen.includes(a.ad)
                          return (
                            <li key={a.ad} className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2 py-1">
                              <label className={`flex min-w-0 flex-1 items-center gap-2 font-bold text-slate-700 ${a.oto ? "" : "cursor-pointer"}`}>
                                <input
                                  type="checkbox"
                                  className={`size-4 accent-tl-navy ${a.oto ? "" : "cursor-pointer"}`}
                                  aria-label={u.altKriterSaglanir(a.ad)}
                                  disabled={duzenle.kilitli || a.oto}
                                  checked={saglanir}
                                  onChange={(e) => duzenle.onSecim(k.baslik, e.target.checked ? [...secilen, a.ad] : secilen.filter((x) => x !== a.ad))}
                                />
                                <span className="min-w-0">
                                  <span className="block truncate">{a.ad}</span>
                                  {"fatura_bedeli" in a ? (
                                    <span className="block text-[0.625rem] font-bold text-slate-400">
                                      {a.oto ? u.faturaOto(Number(a.fatura_bedeli).toLocaleString("tr-TR", { maximumFractionDigits: 0 })) : u.faturaYok}
                                    </span>
                                  ) : null}
                                </span>
                              </label>
                              {/* Ilk alt kriter taban puan, digerleri ekler (Fatura 70, +15, +15). */}
                              <span className="shrink-0 font-mono text-slate-400">{j === 0 ? a.puan : `+${a.puan}`}</span>
                            </li>
                          )
                        })}
                      </ul>
                      <p className="mt-1 text-[0.6875rem] font-bold text-slate-400">{u.sozlesmeNot}</p>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/** Tamam / Eksik rozeti. */
export function TamamRozeti({ tamam, eksik, t }: { tamam: boolean; eksik: string[]; t: UYM }) {
  return tamam ? <Rozet ton="yesil">{t.util.tamam}</Rozet> : <Rozet ton="amber">{t.util.eksik(eksik.join(", ") || t.util.kriterYok)}</Rozet>
}
