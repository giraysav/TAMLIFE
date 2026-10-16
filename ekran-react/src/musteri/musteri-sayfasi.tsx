import { MusteriKarti } from "@/musteri/musteri-karti"
import { MusteriListesi } from "@/musteri/musteri-listesi"
import { MusteriRapor } from "@/musteri/musteri-rapor"
import { MusteriYolu } from "@/musteri/musteri-yolu"
import type { Dil } from "@/shell/metin"
import { useHashSorgu } from "@/shell/rota"
import { TopoMaker } from "@/topoloji/topo-maker"

/** Musteri Yonetimi: #/musteri liste, ?m=<id> musteri karti, ?m=<id>&sekme=rapor aylik rapor, ?m=<id>&sekme=topoloji TopoMaker
 *  Baglantili Araclar (#/baglantili) ve Toptan (#/toptan) simdilik ayni ekrani kendi yollariyla acar
 *  (uretimde kartin arac bolumundeki modal; header geri oku bir onceki ekrana doner). */
export function MusteriSayfasi({ dil, yazabilir, yol = "musteri" }: { dil: Dil; yazabilir: boolean; yol?: string }) {
  return (
    <MusteriYolu.Provider value={yol}>
      <Icerik dil={dil} yazabilir={yazabilir} />
    </MusteriYolu.Provider>
  )
}

function Icerik({ dil, yazabilir }: { dil: Dil; yazabilir: boolean }) {
  const sorgu = useHashSorgu()
  const kimlik = Number(sorgu.get("m"))
  if (Number.isInteger(kimlik) && kimlik > 0) {
    const sekme = sorgu.get("sekme")
    if (sekme === "topoloji") return <TopoMaker key={`t${kimlik}`} musteriId={kimlik} dil={dil} />
    return sekme === "rapor" ? <MusteriRapor key={`r${kimlik}`} id={kimlik} dil={dil} /> : <MusteriKarti key={kimlik} id={kimlik} dil={dil} />
  }
  return <MusteriListesi dil={dil} yazabilir={yazabilir} />
}
