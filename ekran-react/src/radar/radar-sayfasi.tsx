import { useQuery } from "@tanstack/react-query"
import { Radar } from "lucide-react"
import { Bildirim, BosKutu, HataKutu, Panel, SayfaKabi, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { sayi } from "@/lib/bicim"
import { hataMesaji, oku } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"
import { radarMetin } from "@/radar/radar-metin"

type Aday = { sira: number; musteri_no: string; unvan: string; aktif: number; kapanan: number; toplam: number }
type RadarVeri = { var: boolean; taze: boolean; veri_zamani: string | null; satirlar: Aday[] }

/** Musteri Radar (uretim radarModal): elle giris yok; liste ReportDB tamponundan sunucuda uretilir. Sikayet/talep sutunu bilet semasi gelene kadar bos. */
export function RadarSayfasi({ dil }: { dil: Dil }) {
  const t = radarMetin(dil)
  const q = useQuery({ queryKey: ["radar"], queryFn: () => oku<RadarVeri>("/api/v1/radar") })
  const v = q.data
  const bilet = (
    <span className="text-slate-400" title={t.biletYok}>
      —
    </span>
  )

  return (
    <div className="grid grid-cols-1 gap-4">
      <SayfaKabi ikon={Radar} baslik={t.baslik} aciklama={t.aciklama} />
      <Bildirim>{t.kural}</Bildirim>
      <Panel>
        {q.isPending ? (
          <Yukleniyor metin={t.yukleniyor} />
        ) : q.isError ? (
          <HataKutu metin={hataMesaji(q.error, t.yuklenemedi)} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
        ) : v && !v.var ? (
          <BosKutu ikon={Radar} baslik={t.veriYok} />
        ) : v ? (
          <div className="grid gap-3">
            {!v.taze ? <Bildirim ton="amber">{t.bayat}</Bildirim> : null}
            <VeriTablosu
              baslik={t.baslik}
              satirlar={v.satirlar}
              anahtar={(a) => a.musteri_no}
              bos={<BosKutu ikon={Radar} baslik={t.bos} />}
              kolonlar={[
                { baslik: "#", hucre: (a) => a.sira, sinif: "w-10 text-center text-slate-400" },
                { baslik: t.kolUnvan, hucre: (a) => <span className="font-black text-tl-navy">{a.unvan}</span> },
                { baslik: t.kolNo, hucre: (a) => <span className="font-mono">{a.musteri_no}</span> },
                { baslik: t.kolAlarm, hucre: (a) => `${sayi(a.aktif)} / ${sayi(a.kapanan)}`, sinif: "text-center" },
                { baslik: t.kolToplam, hucre: (a) => <span className="font-black text-rose-600">{sayi(a.toplam)}</span>, sinif: "text-center" },
                { baslik: t.kolSikayet, hucre: () => bilet, sinif: "text-center" },
                { baslik: t.kolTalep, hucre: () => bilet, sinif: "text-center" },
              ]}
            />
            <p className="text-[0.6875rem] font-bold text-slate-400">
              {t.dipnot}
              {v.veri_zamani ? ` · ${t.veriZamani}: ${v.veri_zamani}` : ""}
            </p>
          </div>
        ) : null}
      </Panel>
    </div>
  )
}
