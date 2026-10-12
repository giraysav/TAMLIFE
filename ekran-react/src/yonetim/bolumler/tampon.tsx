import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import type { Dil } from "@/shell/metin"
import { Bildirim, Bolum, HataKutu } from "@/components/sayfa-ui"
import { sorguAyarla, useHashSorgu } from "@/shell/rota"
import { ANAHTAR } from "@/yonetim/api"
import { oku } from "@/lib/sorgu"
import type { Kaynak, PartiAyrintisi } from "@/yonetim/api"
import { ym } from "@/yonetim/metin"
import { Analiz } from "@/yonetim/tampon/analiz"
import { Dagitim } from "@/yonetim/tampon/dagitim"
import type { KuralOnerisi } from "@/yonetim/tampon/dagitim"
import { Kaynaklar } from "@/yonetim/tampon/kaynaklar"
import { Partiler } from "@/yonetim/tampon/partiler"
import { Rehber } from "@/yonetim/tampon/rehber"

/** Veri Girisi: rehber ("Nasil calisir?") + kaynak -> 1 tampon -> 2 analiz -> 3 dagitim. Secili parti adreste (#/yonetim/tampon?parti=12): geri/ileri ve baglanti paylasimi calisir. */
export default function Tampon({ dil }: { dil: Dil }) {
  const t = ym(dil)
  const sorgu = useHashSorgu()
  const seciliId = Number(sorgu.get("parti")) || null
  const [oneri, setOneri] = useState<KuralOnerisi | null>(null)

  const sec = (id: number | null) => sorguAyarla("yonetim/tampon", { parti: id ? String(id) : null })
  const detay = useQuery({
    queryKey: [...ANAHTAR.parti, seciliId],
    queryFn: () => oku<PartiAyrintisi>(`/api/v1/tampon/partiler/${seciliId}`),
    enabled: seciliId !== null,
    retry: false,
  })
  const kaynaklar = useQuery({ queryKey: ANAHTAR.kaynaklar, queryFn: () => oku<Kaynak[]>("/api/v1/tampon/kaynaklar") })
  const kaynakAnahtarlari = (kaynaklar.data ?? []).filter((k) => k.tur !== "oracle").map((k) => k.anahtar)

  const parti = detay.data ?? null
  return (
    <div className="grid gap-4">
      <Rehber dil={dil} />

      <Kaynaklar dil={dil} onYeniParti={(p) => sec(p.id)} />
      <Partiler dil={dil} seciliId={seciliId} onSec={sec} />

      {seciliId === null ? (
        <Bildirim>{t.partiSecin}</Bildirim>
      ) : detay.isPending ? (
        <Bolum anahtar="yonetim-tampon-analiz" baslik={t.adim.analiz}>
          <p className="text-xs font-bold text-slate-400">{t.yukleniyor}</p>
        </Bolum>
      ) : detay.isError ? (
        <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void detay.refetch()} />
      ) : (
        <Analiz
          dil={dil}
          parti={detay.data}
          onKuralOner={(o) => setOneri({ ...o, sayac: (oneri?.sayac ?? 0) + 1 })}
          onSilindi={() => sec(null)}
        />
      )}

      <Dagitim dil={dil} parti={parti} oneri={oneri} kaynakAnahtarlari={kaynakAnahtarlari} />
    </div>
  )
}
