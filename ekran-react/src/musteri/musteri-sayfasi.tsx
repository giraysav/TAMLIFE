import { MusteriKarti } from "@/musteri/musteri-karti"
import { MusteriListesi } from "@/musteri/musteri-listesi"
import { MusteriRapor } from "@/musteri/musteri-rapor"
import type { Dil } from "@/shell/metin"
import { useHashSorgu } from "@/shell/rota"
import { TopoMaker } from "@/topoloji/topo-maker"

/** Musteri Yonetimi: #/musteri liste, ?m=<id> musteri karti, ?m=<id>&sekme=rapor aylik rapor, ?m=<id>&sekme=topoloji TopoMaker
 *  (uretimde kartin arac bolumundeki modal; header geri oku bir onceki ekrana doner). */
export function MusteriSayfasi({ dil, yazabilir }: { dil: Dil; yazabilir: boolean }) {
  const sorgu = useHashSorgu()
  const kimlik = Number(sorgu.get("m"))
  if (Number.isInteger(kimlik) && kimlik > 0) {
    const sekme = sorgu.get("sekme")
    if (sekme === "topoloji") return <TopoMaker dil={dil} />
    return sekme === "rapor" ? <MusteriRapor key={`r${kimlik}`} id={kimlik} dil={dil} /> : <MusteriKarti key={kimlik} id={kimlik} dil={dil} />
  }
  return <MusteriListesi dil={dil} yazabilir={yazabilir} />
}
