import { useQuery } from "@tanstack/react-query"
import { CalendarCheck, Presentation } from "lucide-react"
import { BosKutu, HataKutu, Panel, SayfaKabi, Yukleniyor } from "@/components/sayfa-ui"
import { zaman } from "@/lib/bicim"
import { oku } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"
import { TakvimGrafigi } from "@/takvim/takvim-grafigi"
import type { GrafikUyesi, Ozet } from "@/takvim/takvim-grafigi"
import { takvimMetin } from "@/takvim/takvim-metin"

type Oge = {
  id: number
  kaynak: string
  donem: string
  baslik: string
  gonderen: string
  zaman: string | null
  veri: { yil: number; ceyrek: number; genel: Ozet; uyeler: GrafikUyesi[] }
}

/** Ceyrek Bazli Sunum: ceyrek sunumuna gonderilen ozetler (su an TAM Takvim'den gonderilenler), yeniden eskiye. */
export function SunumSayfasi({ dil }: { dil: Dil }) {
  const t = takvimMetin(dil)
  const q = useQuery({ queryKey: ["sunum", "ogeler"], queryFn: () => oku<Oge[]>("/api/v1/sunum/ogeler") })
  return (
    <div className="grid grid-cols-1 gap-4">
      <SayfaKabi ikon={Presentation} baslik={t.sunumBaslik} aciklama={t.sunumAciklama} />
      {q.isPending ? (
        <Yukleniyor metin="…" />
      ) : q.isError ? (
        <HataKutu metin={t.yuklenemedi} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
      ) : q.data.length === 0 ? (
        <BosKutu ikon={Presentation} baslik={t.sunumYok} aciklama={t.sunumYokAlt} />
      ) : (
        q.data.map((o) => (
          <Panel key={o.id} baslik={`${o.donem} · ${o.kaynak === "takvim" ? t.kaynakTakvim : o.kaynak}`} aciklama={`${t.gonderen}: ${o.gonderen} · ${zaman(o.zaman)}`} sag={<CalendarCheck aria-hidden className="size-5 text-emerald-500" />}>
            <TakvimGrafigi genel={o.veri.genel} uyeler={o.veri.uyeler} t={t} />
          </Panel>
        ))
      )}
    </div>
  )
}
