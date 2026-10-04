import { MusteriKarti } from "@/shell/musteri-karti"
import { MusteriListesi } from "@/shell/musteri-listesi"
import type { Dil } from "@/shell/metin"
import { useHashSorgu } from "@/shell/rota"

/** Musteri Yonetimi: #/musteri liste, #/musteri?m=<id> musteri karti (header'daki geri oku listeye doner). */
export function MusteriSayfasi({ dil }: { dil: Dil }) {
  const sorgu = useHashSorgu()
  const kimlik = Number(sorgu.get("m"))
  if (Number.isInteger(kimlik) && kimlik > 0) return <MusteriKarti key={kimlik} id={kimlik} dil={dil} />
  return <MusteriListesi dil={dil} />
}
