import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import type { Dil } from "@/shell/metin"
import { Bolum } from "@/components/kart-ui"
import { sorguAyarla, useHashSorgu } from "@/shell/rota"
import { ANAHTAR, oku } from "@/yonetim/api"
import type { Kaynak, PartiAyrintisi } from "@/yonetim/api"
import { ym } from "@/yonetim/metin"
import { Analiz } from "@/yonetim/tampon/analiz"
import { Dagitim } from "@/yonetim/tampon/dagitim"
import type { KuralOnerisi } from "@/yonetim/tampon/dagitim"
import { Kaynaklar } from "@/yonetim/tampon/kaynaklar"
import { Partiler } from "@/yonetim/tampon/partiler"
import { Bilgi, HataKutusu } from "@/yonetim/ui"

/** Veri Girisi: kaynak -> 1 tampon -> 2 analiz -> 3 dagitim. Secili parti adreste (#/yonetim/tampon?parti=12): geri/ileri ve baglanti paylasimi calisir. */
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
      <ol className="grid gap-2 md:grid-cols-3" aria-label={t.bolumler.tampon}>
        {(["tampon", "analiz", "dagitim"] as const).map((a) => (
          <li key={a} className="rounded-xl border border-slate-200 bg-white px-3 py-2 shadow-sm">
            <p className="text-xs font-black text-tl-navy">{t.adim[a]}</p>
            <p className="text-[11px] font-bold text-slate-500">{t.adimAciklama[a]}</p>
          </li>
        ))}
      </ol>

      <Kaynaklar dil={dil} onYeniParti={(p) => sec(p.id)} />
      <Partiler dil={dil} seciliId={seciliId} onSec={sec} />

      {seciliId === null ? (
        <Bilgi>{t.partiSecin}</Bilgi>
      ) : detay.isPending ? (
        <Bolum anahtar="yonetim-tampon-analiz" baslik={t.adim.analiz}>
          <p className="text-xs font-bold text-slate-400">{t.yukleniyor}</p>
        </Bolum>
      ) : detay.isError ? (
        <HataKutusu t={t} onTekrar={() => void detay.refetch()} />
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
