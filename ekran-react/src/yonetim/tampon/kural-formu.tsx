import { useState } from "react"
import type { ReactNode } from "react"
import { Plus, X } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Alan, Bildirim, DUGME, DUGME_ANA, GIRDI } from "@/components/sayfa-ui"
import type { Katalog, Kosul, KuralGovdesi } from "@/yonetim/api"
import { tm } from "@/yonetim/tampon/metin"

export const BOS_KURAL: KuralGovdesi = {
  name: "",
  source_key: "",
  match_field: "customer_no",
  key_column: "",
  target: "",
  operation: "",
  value_column: "",
  conditions: [],
  zero_unmatched: false,
  max_age_minutes: null,
}

const AZAMI_KOSUL = 5

/** Etiketli alan + altinda kisa ipucu (ipucu etiketin disinda: alanin erisilebilir adi kisa kalir). */
function Ipuclu({ etiket, ipucu, children }: { etiket: string; ipucu: string; children: ReactNode }) {
  return (
    <div className="grid content-start gap-1">
      <Alan etiket={etiket}>{children}</Alan>
      <span className="text-[0.625rem] font-bold leading-snug text-slate-400">{ipucu}</span>
    </div>
  )
}

type Props = {
  dil: Dil
  katalog: Katalog
  baslangic: KuralGovdesi
  duzenleme: boolean
  kaynakAnahtarlari: string[]
  /** Secili partinin sutun adlari (bos ise sutun alanlari serbest metin). */
  sutunlar: string[]
  hata: string
  kaydediliyor: boolean
  onKaydet: (govde: KuralGovdesi) => void
  onVazgec: () => void
}

/** Dagitim kurali formu. Hedef katalogu SABITTIR (serbest hedef yok); islem hedef tipine gore suzulur; kural kapali baslar. */
export function KuralFormu({ dil, katalog, baslangic, duzenleme, kaynakAnahtarlari, sutunlar, hata, kaydediliyor, onKaydet, onVazgec }: Props) {
  const t = tm(dil)
  const ip = t.kuralIpuclari
  const [f, setF] = useState<KuralGovdesi>(baslangic)
  const set = <K extends keyof KuralGovdesi>(alan: K, deger: KuralGovdesi[K]) => setF((o) => ({ ...o, [alan]: deger }))

  const hedef = katalog.hedefler.find((h) => h.anahtar === f.target)
  const islemler = katalog.islemler.filter((i) => !hedef || i.tip === hedef.tip)
  const sayisal = hedef?.tip !== "metin"
  const degerGerekli = f.operation !== "" && f.operation !== "say"
  const kaynaklar = f.source_key && !kaynakAnahtarlari.includes(f.source_key) ? [f.source_key, ...kaynakAnahtarlari] : kaynakAnahtarlari

  function hedefSec(anahtar: string) {
    const yeni = katalog.hedefler.find((h) => h.anahtar === anahtar)
    const gecerli = katalog.islemler.some((i) => i.anahtar === f.operation && i.tip === yeni?.tip)
    setF((o) => ({ ...o, target: anahtar, operation: gecerli ? o.operation : "", zero_unmatched: yeni?.tip === "sayi" ? o.zero_unmatched : false }))
  }
  function kosulDegistir(i: number, yama: Partial<Kosul>) {
    setF((o) => ({ ...o, conditions: o.conditions.map((k, j) => (j === i ? { ...k, ...yama } : k)) }))
  }
  const sutunKontrolu = (deger: string, degistir: (v: string) => void, etiket: string) =>
    sutunlar.length > 0 ? (
      <select className={GIRDI} required aria-label={etiket} value={deger} onChange={(e) => degistir(e.target.value)}>
        <option value="">{t.secin}</option>
        {(deger && !sutunlar.includes(deger) ? [deger, ...sutunlar] : sutunlar).map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
    ) : (
      <input className={GIRDI} required aria-label={etiket} value={deger} onChange={(e) => degistir(e.target.value)} />
    )

  return (
    <form
      className="grid gap-4 rounded-xl border border-tl-yellow/70 bg-tl-yellow/5 p-4"
      onSubmit={(e) => {
        e.preventDefault()
        onKaydet({ ...f, value_column: degerGerekli ? f.value_column : "" })
      }}
    >
      <h4 className="text-[0.6875rem] font-black uppercase tracking-widest text-tl-navy">{duzenleme ? t.kuralDuzenle : t.yeniKural}</h4>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Alan etiket={t.kuralAdi}>
          <input className={GIRDI} required maxLength={120} value={f.name} onChange={(e) => set("name", e.target.value)} />
        </Alan>
        <Ipuclu etiket={t.kuralKaynak} ipucu={ip.kuralKaynak}>
          <select className={GIRDI} required value={f.source_key} onChange={(e) => set("source_key", e.target.value)}>
            <option value="">{t.secin}</option>
            {kaynaklar.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </Ipuclu>
        <Ipuclu etiket={t.anahtarSutunu} ipucu={ip.anahtarSutunu}>
          {sutunKontrolu(f.key_column, (v) => set("key_column", v), t.anahtarSutunu)}
        </Ipuclu>
        <Ipuclu etiket={t.eslesmeAlani} ipucu={ip.eslesmeAlani}>
          <select className={GIRDI} value={f.match_field} onChange={(e) => set("match_field", e.target.value)}>
            {katalog.eslesme_alanlari.map((a) => (
              <option key={a.anahtar} value={a.anahtar}>
                {t.alanAdi[a.anahtar] ?? a.ad}
              </option>
            ))}
          </select>
        </Ipuclu>
        <Ipuclu etiket={t.hedef} ipucu={ip.hedef}>
          <select className={GIRDI} required value={f.target} onChange={(e) => hedefSec(e.target.value)}>
            <option value="">{t.secin}</option>
            {katalog.hedefler.map((h) => (
              <option key={h.anahtar} value={h.anahtar}>
                {h.ad}
              </option>
            ))}
          </select>
        </Ipuclu>
        <Ipuclu etiket={t.islem} ipucu={ip.islem}>
          <select className={GIRDI} required value={f.operation} onChange={(e) => set("operation", e.target.value)}>
            <option value="">{t.secin}</option>
            {islemler.map((i) => (
              <option key={i.anahtar} value={i.anahtar}>
                {i.ad}
              </option>
            ))}
          </select>
        </Ipuclu>
        {degerGerekli ? (
          <Ipuclu etiket={t.degerSutunu} ipucu={ip.degerSutunu}>
            {sutunKontrolu(f.value_column, (v) => set("value_column", v), t.degerSutunu)}
          </Ipuclu>
        ) : null}
      </div>

      <fieldset className="grid gap-2">
        <legend className="mb-1 text-[0.625rem] font-black uppercase tracking-wide text-slate-400">{t.kosullar}</legend>
        <p className="-mt-1 text-[0.625rem] font-bold text-slate-400">{ip.kosullar}</p>
        {f.conditions.map((k, i) => {
          const degersiz = katalog.degersiz_islecler.includes(k.islec)
          return (
            <div key={i} className="flex flex-wrap items-center gap-2">
              <span className="min-w-44 flex-1">{sutunKontrolu(k.kolon, (v) => kosulDegistir(i, { kolon: v }), t.sutun)}</span>
              <select className={`${GIRDI} w-auto`} aria-label={t.islec} value={k.islec} onChange={(e) => kosulDegistir(i, { islec: e.target.value })}>
                {katalog.islecler.map((x) => (
                  <option key={x} value={x}>
                    {t.islecEtiket[x] ?? x}
                  </option>
                ))}
              </select>
              {degersiz ? null : (
                <input className={`${GIRDI} min-w-32 flex-1`} aria-label={t.deger} required value={k.deger} onChange={(e) => kosulDegistir(i, { deger: e.target.value })} />
              )}
              <button type="button" className={DUGME} aria-label={t.kosulSil} onClick={() => setF((o) => ({ ...o, conditions: o.conditions.filter((_, j) => j !== i) }))}>
                <X aria-hidden className="size-3.5" />
              </button>
            </div>
          )
        })}
        {f.conditions.length < AZAMI_KOSUL ? (
          <button type="button" className={`${DUGME} justify-self-start`} onClick={() => setF((o) => ({ ...o, conditions: [...o.conditions, { kolon: "", islec: "esit", deger: "" }] }))}>
            <Plus aria-hidden className="size-3.5" />
            {t.kosulEkle}
          </button>
        ) : null}
      </fieldset>

      <div className="grid gap-3 md:grid-cols-2">
        {sayisal ? (
          <label className="flex items-start gap-2 text-xs font-bold text-slate-700">
            <input type="checkbox" className="mt-0.5" checked={f.zero_unmatched} onChange={(e) => set("zero_unmatched", e.target.checked)} />
            <span>
              {t.eslesmeyeniSifirla}
              <span className="block text-[0.6875rem] font-bold text-slate-400">{t.eslesmeyeniAciklama}</span>
            </span>
          </label>
        ) : null}
        <Ipuclu etiket={t.enBuyukYas} ipucu={ip.enBuyukYas}>
          <input
            type="number"
            min={1}
            max={525600}
            className={`${GIRDI} max-w-40`}
            value={f.max_age_minutes ?? ""}
            onChange={(e) => set("max_age_minutes", e.target.value === "" ? null : Number(e.target.value))}
          />
        </Ipuclu>
      </div>

      {hata ? <Bildirim ton="amber">{hata}</Bildirim> : null}
      <div className="flex gap-2">
        <button type="submit" className={DUGME_ANA} disabled={kaydediliyor}>
          {t.kaydet}
        </button>
        <button type="button" className={DUGME} onClick={onVazgec}>
          {t.vazgec}
        </button>
      </div>
    </form>
  )
}
