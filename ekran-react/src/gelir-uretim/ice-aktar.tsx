import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Upload } from "lucide-react"
import { Cekmece } from "@/components/cekmece"
import { Bildirim, DUGME, DUGME_SARI, Rozet, Yukleniyor } from "@/components/sayfa-ui"
import { para } from "@/lib/bicim"
import { hataMesaji, sorguMetni, yukle } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"
import { SATIR_DURUMLARI, gelirUretimMetin } from "@/gelir-uretim/gelir-uretim-metin"
import type { Onizleme, OnizlemeSatiri, SatirDurumu, UygulaSonucu } from "@/gelir-uretim/gelir-uretim-metin"
import { ANAHTAR, DURUM_TON, FaydaRozeti, SATIR_TON, TABAN, XLSX, kisilerMetni, saatMetni, tarihAraligi, tutarMetni } from "@/gelir-uretim/ortak"
import type { Metin } from "@/gelir-uretim/ortak"

/** Sunucu sinirinin aynisi: daha buyuk dosya hic gonderilmez. */
const AZAMI_BAYT = 5 * 1024 * 1024

/** Onizleme satirinin ikinci satiri: kisiler, tutar, yil ici gelir, saat ve tarih (bos olanlar atlanir). */
function ozetSatiri(s: OnizlemeSatiri, t: Metin): string {
  return [
    kisilerMetni(s.people, s.other_people),
    tutarMetni(s, t),
    s.year_revenue === null ? "" : `${t.yilIciKisa}: ${para(s.year_revenue)}`,
    saatMetni(s.hours_per_month, t),
    s.start_date || s.end_date ? tarihAraligi({ start_date: s.start_date, end_date: s.end_date, status: s.status || "baslamadi" }, t) : "",
  ]
    .filter(Boolean)
    .join(" · ")
}

function SatirKarti({ s, dil }: { s: OnizlemeSatiri; dil: Dil }) {
  const t = gelirUretimMetin(dil)
  const ozet = ozetSatiri(s, t)
  return (
    <li className="grid min-w-0 gap-1 rounded-xl border border-slate-200 bg-white p-3 text-xs">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="font-mono text-[0.6875rem] font-bold text-slate-400">#{s.satir}</span>
        <Rozet ton={SATIR_TON[s.durum]}>{t.satirDurum_[s.durum]}</Rozet>
        <Rozet ton={s.kind === "inisiyatif" ? "sari" : "gri"}>{t.tur_[s.kind]}</Rozet>
        {s.status ? <Rozet ton={DURUM_TON[s.status]}>{t.durum_[s.status]}</Rozet> : null}
        {s.benefit_type ? <FaydaRozeti fayda={s.benefit_type} dil={dil} /> : null}
      </div>
      <p className="break-words font-black text-tl-navy">{s.title || t.yok}</p>
      {ozet ? <p className="break-words font-bold text-slate-500">{ozet}</p> : null}
      {s.uyarilar.map((u, i) => (
        <p key={i} className="break-words font-bold text-amber-700">
          ⚠ {u}
        </p>
      ))}
    </li>
  )
}

/** Excel'den ice aktarma cekmecesi (yalniz admin): dosya sec -> onizleme (hicbir sey yazilmaz) -> yalniz yeni satirlari ekle. */
export function IceAktar({ dil, onKapat }: { dil: Dil; onKapat: () => void }) {
  const t = gelirUretimMetin(dil)
  const qc = useQueryClient()
  const [dosya, setDosya] = useState<File | null>(null)
  const [suz, setSuz] = useState<SatirDurumu | "">("")
  const [uyari, setUyari] = useState("")
  const yol = (son: "onizleme" | "uygula", d: File) => `${TABAN}/ice-al/${son}${sorguMetni({ dosya: d.name.slice(0, 150) })}`
  const onizle = useMutation({ mutationFn: (d: File) => yukle<Onizleme>(yol("onizleme", d), d, XLSX, "POST") })
  const uygula = useMutation({
    mutationFn: (d: File) => yukle<UygulaSonucu>(yol("uygula", d), d, XLSX, "POST"),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ANAHTAR }),
  })

  function sec(d: File | undefined) {
    onizle.reset()
    uygula.reset()
    setSuz("")
    setUyari("")
    setDosya(null)
    if (!d) return
    if (d.size > AZAMI_BAYT) return setUyari(t.dosyaBuyuk)
    setDosya(d)
    onizle.mutate(d)
  }

  const o = onizle.data
  const sonuc = uygula.data
  const gorunen = o ? o.satirlar.filter((s) => !suz || s.durum === suz) : []
  const kutular: { id: SatirDurumu | ""; ad: string; n: number }[] = o
    ? [
        { id: "", ad: t.planToplam, n: o.plan.toplam },
        ...SATIR_DURUMLARI.map((id) => ({ id, ad: t.satirDurum_[id], n: o.plan[id] })),
      ]
    : []

  return (
    <Cekmece
      acik
      genis
      onKapat={onKapat}
      baslik={t.iceBaslik}
      aciklama={t.iceAciklama}
      kapatEtiketi={t.kapat}
      alt={
        <div className="grid gap-2">
          {uygula.isError ? <Bildirim ton="kirmizi">{hataMesaji(uygula.error, t.eklenemedi)}</Bildirim> : null}
          <div className="flex flex-wrap items-center justify-end gap-2">
            <button type="button" className={DUGME} onClick={onKapat}>
              {t.kapat}
            </button>
            {o && !sonuc ? (
              <button type="button" className={DUGME_SARI} disabled={o.plan.yeni === 0 || uygula.isPending || !dosya} onClick={() => dosya && uygula.mutate(dosya)}>
                {uygula.isPending ? t.uygulaniyor : t.uygula(o.plan.yeni)}
              </button>
            ) : null}
          </div>
        </div>
      }
    >
      <div className="grid gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex cursor-pointer items-center justify-center gap-1.5 rounded-xl border border-tl-blue bg-white px-4 py-2 text-xs font-bold text-tl-blue shadow-sm transition-colors hover:bg-tl-blue/5 focus-within:ring-2 focus-within:ring-tl-yellow">
            <Upload aria-hidden className="size-4" />
            {dosya ? t.baskaDosya : t.dosyaSec}
            <input
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              className="sr-only"
              onChange={(e) => {
                sec(e.target.files?.[0])
                e.target.value = ""
              }}
            />
          </label>
          {dosya ? <span className="min-w-0 break-words text-xs font-bold text-slate-500">{dosya.name}</span> : null}
        </div>

        {uyari ? <Bildirim ton="amber">{uyari}</Bildirim> : null}
        {onizle.isPending ? <Yukleniyor metin={t.okunuyor} /> : null}
        {onizle.isError ? <Bildirim ton="kirmizi">{hataMesaji(onizle.error, t.okunamadi)}</Bildirim> : null}
        {!o && !onizle.isPending && !uyari ? <p className="text-xs font-bold text-slate-500">{t.dosyaKural}</p> : null}

        {sonuc ? (
          <div className="grid gap-3">
            <Bildirim ton="yesil">{[t.eklendi(sonuc.eklendi), t.eklendiAlt(sonuc.var + sonuc.tekrar + sonuc.hatali)].filter(Boolean).join(" ")}</Bildirim>
            {sonuc.uyarilar.map((u, i) => (
              <Bildirim key={i} ton="amber">
                {u}
              </Bildirim>
            ))}
          </div>
        ) : o ? (
          <div className="grid gap-3">
            <p className="break-words text-xs font-bold text-slate-500">{t.onizlemeDosya(o.dosya || dosya?.name || "", o.sayfa)}</p>
            <div role="group" aria-label={t.planSuz} className="flex flex-wrap gap-2">
              {kutular.map((c) => (
                <button
                  key={c.id || "toplam"}
                  type="button"
                  aria-pressed={suz === c.id}
                  disabled={c.n === 0 && c.id !== ""}
                  onClick={() => setSuz(c.id === "" || suz === c.id ? "" : c.id)}
                  className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-black transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow disabled:opacity-50 ${
                    suz === c.id ? "border-tl-navy bg-tl-navy text-tl-yellow" : "border-slate-200 bg-white text-slate-600 hover:border-tl-blue/40 hover:bg-slate-50"
                  }`}
                >
                  {c.ad}
                  <span className="font-mono">{c.n}</span>
                </button>
              ))}
            </div>
            {o.plan.yeni === 0 ? <Bildirim ton="gri">{t.hicYeni}</Bildirim> : null}
            {o.uyarilar.length > 0 ? (
              <div className="grid gap-1.5">
                <h4 className="text-[0.625rem] font-black uppercase tracking-wide text-slate-500">{t.genelUyarilar}</h4>
                {o.uyarilar.map((u, i) => (
                  <Bildirim key={i} ton="amber">
                    {u}
                  </Bildirim>
                ))}
              </div>
            ) : null}
            <ol aria-label={t.satirlar} className="grid gap-2">
              {gorunen.map((s) => (
                <SatirKarti key={s.satir} s={s} dil={dil} />
              ))}
            </ol>
          </div>
        ) : null}
      </div>
    </Cekmece>
  )
}
