import { useEffect, useState } from "react"
import { ArrowLeft } from "lucide-react"
import { apiOku } from "@/lib/api-yaz"
import { AylikRapor } from "@/musteri/aylik-rapor"
import { Rozet } from "@/components/kart-ui"
import type { Kart } from "@/musteri/musteri-karti"
import type { Dil } from "@/shell/metin"
import { musteriMetin } from "@/musteri/musteri-metin"

/** Aylik rapor sayfasi (#/musteri?m=<id>&sekme=rapor): ustte musteri kimligi ve karta donus baglantisi. */
export function MusteriRapor({ id, dil }: { id: number; dil: Dil }) {
  const t = musteriMetin(dil)
  const [kart, setKart] = useState<Kart | null | undefined>(undefined)
  useEffect(() => {
    let iptal = false
    void apiOku<Kart>(`/api/v1/musteri/${id}`).then((s) => {
      if (!iptal) setKart(s.ok ? s.veri : null)
    })
    return () => {
      iptal = true
    }
  }, [id])

  if (kart === undefined) return <p className="text-sm text-muted-foreground">…</p>
  if (kart === null) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t.bulunamadi}
      </p>
    )
  }
  return (
    <div className="space-y-4">
      <div className="relative flex flex-wrap items-center gap-3 overflow-hidden rounded-2xl border border-slate-200 bg-gradient-to-br from-tl-navy to-[#003b80] px-5 py-3 text-white shadow-sm">
        <span aria-hidden className="absolute inset-y-0 left-0 w-1.5 bg-tl-yellow" />
        <div className="min-w-0 flex-1 pl-2">
          <p className="text-[10px] font-bold uppercase tracking-wide text-white/70">{t.aylikRapor}</p>
          <h2 className="break-words text-lg font-black leading-tight">{kart.kimlik.unvan}</h2>
        </div>
        {kart.kimlik.segment ? <Rozet ton="sari">{kart.kimlik.segment}</Rozet> : null}
        <a
          href={`#/musteri?m=${id}`}
          className="inline-flex items-center gap-1.5 rounded-xl border border-white/30 bg-white/10 px-3 py-2 text-xs font-bold hover:bg-white/20 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
        >
          <ArrowLeft aria-hidden className="size-3.5" />
          {t.musteriKartinaDon}
        </a>
      </div>
      <AylikRapor musteriId={id} dil={dil} geriAlabilir={kart.erisim.rapor_geri_al} />
    </div>
  )
}
