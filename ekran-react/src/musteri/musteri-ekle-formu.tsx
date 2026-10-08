import { useState } from "react"
import type { FormEvent } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Building2, GitBranch } from "lucide-react"
import { DUGME, DUGME_SARI, GIRDI } from "@/components/kart-ui"
import { Alan, Bildirim } from "@/components/sayfa-ui"
import { hataMesaji, yaz } from "@/lib/sorgu"
import { MusteriKarti } from "@/musteri/portfoy-kart"
import type { Secenekler } from "@/musteri/portfoy-kart"
import { portfoyMetin } from "@/musteri/portfoy-metin"
import type { Dil } from "@/shell/metin"
import { sorguAyarla } from "@/shell/rota"

type Tur = "ana" | "istirak"

/** "Musteri ekle" formu (cekmece icinde): tur, cati (istirak), unvan, segment, sorumlu TAM; ustte canli kart onizlemesi. */
export function MusteriEkleFormu({ dil, secenek, onBitti }: { dil: Dil; secenek: Secenekler; onBitti: () => void }) {
  const t = portfoyMetin(dil)
  const qc = useQueryClient()
  const [tur, setTur] = useState<Tur>("ana")
  const [catiId, setCatiId] = useState("")
  const [unvan, setUnvan] = useState("")
  const [segment, setSegment] = useState("")
  const [tamId, setTamId] = useState("")
  const [hata, setHata] = useState("")

  const cati = secenek.catilar.find((c) => String(c.id) === catiId)
  const ekle = useMutation({
    mutationFn: () =>
      yaz<{ id: number }>("POST", "/api/v1/musteri", {
        name: unvan.trim(),
        ...(segment ? { segment } : {}),
        ...(tur === "istirak" && catiId ? { parent_id: Number(catiId) } : {}),
        ...(secenek.yonetici && tamId ? { owner_id: Number(tamId) } : {}),
      }),
    onSuccess: (sonuc) => {
      void qc.invalidateQueries({ queryKey: ["musteri"] })
      onBitti()
      sorguAyarla("musteri", { m: String(sonuc.id) })
    },
    onError: (e) => setHata(hataMesaji(e, t.eklenemedi)),
  })

  function gonder(olay: FormEvent) {
    olay.preventDefault()
    setHata("")
    if (!unvan.trim()) return setHata(t.unvanZorunlu)
    if (tur === "istirak" && !catiId) return setHata(t.catiZorunlu)
    ekle.mutate()
  }

  const tamAdi = secenek.tam.find((k) => String(k.id) === (tamId || String(secenek.kendi_id ?? "")))?.ad ?? null

  return (
    <form onSubmit={gonder} className="grid gap-5" aria-label={t.formBaslik}>
      <div className="grid gap-1.5">
        <p className="text-[10px] font-black uppercase tracking-wide text-slate-400">{t.onizleme}</p>
        <MusteriKarti
          onizleme
          dil={dil}
          m={{ id: 0, name: unvan.trim() || t.unvanBos, segment: segment || (tur === "istirak" ? "" : ""), owner: tamAdi, owner_id: null, score: null, alarm: 0, sikayet: 0, talep: 0, istirakler: [] }}
        />
      </div>

      <fieldset className="grid gap-1.5">
        <legend className="mb-1 text-[10px] font-black uppercase tracking-wide text-slate-500">{t.tur}</legend>
        <div className="grid grid-cols-2 gap-2">
          {(
            [
              ["ana", t.turAna, Building2],
              ["istirak", t.turIstirak, GitBranch],
            ] as const
          ).map(([k, etiket, Ikon]) => (
            <button
              key={k}
              type="button"
              aria-pressed={tur === k}
              onClick={() => setTur(k)}
              className={`flex items-center justify-center gap-2 rounded-xl border px-3 py-3 text-sm font-black transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow ${
                tur === k ? "border-tl-yellow bg-tl-yellow/20 text-tl-navy ring-1 ring-tl-yellow" : "border-slate-200 bg-white text-slate-500 hover:bg-slate-50"
              }`}
            >
              <Ikon aria-hidden className="size-4" />
              {etiket}
            </button>
          ))}
        </div>
      </fieldset>

      {tur === "istirak" ? (
        <Alan etiket={t.cati} ipucu={secenek.catilar.length === 0 ? t.catiYok : undefined}>
          <select className={`${GIRDI} !py-2.5`} value={catiId} onChange={(e) => setCatiId(e.target.value)} required>
            <option value="">{t.catiSec}</option>
            {secenek.catilar.map((c) => (
              <option key={c.id} value={c.id}>
                {c.ad}
              </option>
            ))}
          </select>
        </Alan>
      ) : null}

      <Alan etiket={t.unvan} ipucu={`${t.unvanIpucu} (${unvan.length}/150)`}>
        <input className={`${GIRDI} !py-2.5 !text-sm`} value={unvan} onChange={(e) => setUnvan(e.target.value)} maxLength={150} required autoFocus />
      </Alan>

      <fieldset className="grid gap-1.5">
        <legend className="mb-1 text-[10px] font-black uppercase tracking-wide text-slate-500">{t.segmentSec}</legend>
        <div className="flex flex-wrap gap-2">
          {["", ...secenek.segmentler].map((s) => (
            <button
              key={s || "yok"}
              type="button"
              aria-pressed={segment === s}
              onClick={() => setSegment(s)}
              className={`rounded-full border px-3.5 py-1.5 text-xs font-black transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow ${
                segment === s ? "border-tl-navy bg-tl-navy text-tl-yellow" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
              }`}
            >
              {s || t.segmentYok}
            </button>
          ))}
        </div>
        {tur === "istirak" ? <p className="text-[10px] font-bold text-slate-400">{t.segmentCati}</p> : null}
      </fieldset>

      <Alan etiket={t.tamSec}>
        <select className={`${GIRDI} !py-2.5`} value={tamId} onChange={(e) => setTamId(e.target.value)} disabled={!secenek.yonetici}>
          <option value="">{secenek.yonetici ? (cati ? `${t.cati}` : t.tamKendi) : t.tamKendi}</option>
          {secenek.tam.map((k) => (
            <option key={k.id} value={k.id}>
              {k.ad}
            </option>
          ))}
        </select>
      </Alan>

      {hata ? <Bildirim ton="kirmizi">{hata}</Bildirim> : null}

      <div className="flex gap-2 border-t border-slate-100 pt-4">
        <button type="submit" className={`${DUGME_SARI} !min-w-0 flex-1`} disabled={ekle.isPending}>
          {ekle.isPending ? t.kaydediliyor : t.kaydet}
        </button>
        <button type="button" className={DUGME} onClick={onBitti}>
          {t.vazgec}
        </button>
      </div>
    </form>
  )
}
