import { MusteriKarti } from "@/musteri/musteri-karti"
import { MusteriListesi } from "@/musteri/musteri-listesi"
import { MusteriRapor } from "@/musteri/musteri-rapor"
import type { Dil } from "@/shell/metin"
import { useHashSorgu } from "@/shell/rota"

/** Musteri Yonetimi: #/musteri liste, ?m=<id> musteri karti, ?m=<id>&sekme=rapor aylik rapor (header geri oku bir onceki ekrana doner). */
export function MusteriSayfasi({ dil }: { dil: Dil }) {
  const sorgu = useHashSorgu()
  const kimlik = Number(sorgu.get("m"))
  if (Number.isInteger(kimlik) && kimlik > 0) {
    return sorgu.get("sekme") === "rapor" ? <MusteriRapor key={`r${kimlik}`} id={kimlik} dil={dil} /> : <MusteriKarti key={kimlik} id={kimlik} dil={dil} />
  }
  return <MusteriListesi dil={dil} />
}
