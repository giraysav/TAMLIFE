import { useQuery } from "@tanstack/react-query"
import type { Dil } from "@/shell/metin"
import { Bos, HataKutu, Panel, Rozet, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import type { EslesmeKaynagi, MusteriEslesmesi } from "@/yonetim/api"
import { oku } from "@/lib/sorgu"
import { sayi } from "@/lib/bicim"
import { tm } from "@/yonetim/tampon/metin"

const BAG = "font-black text-tl-blue underline-offset-2 hover:underline"

function oranTonu(oran: number | null): "yesil" | "amber" | "kirmizi" | "gri" {
  if (oran === null) return "gri"
  return oran >= 90 ? "yesil" : oran >= 50 ? "amber" : "kirmizi"
}

/** Veri Girisi > Musteri Eslesmesi (2026-10-24): panele gelen her veri TAM'a atanmis bir karta baglanmali; kaynak bazinda durum + kartsiz numaralar. */
export function MusteriEslesmesiPanosu({ dil }: { dil: Dil }) {
  const t = tm(dil)
  const e = t.eslesme
  const q = useQuery({ queryKey: ANAHTAR.eslesme, queryFn: () => oku<MusteriEslesmesi>("/api/v1/tampon/eslesme"), refetchInterval: 120_000 })
  if (q.isPending) return <Yukleniyor metin={t.yukleniyor} iskelet />
  if (q.isError) return <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void q.refetch()} />
  const d = q.data
  return (
    <div className="grid gap-4">
      <Panel baslik={e.baslik} aciklama={e.aciklama}>
        <div className="grid gap-3">
          <p className="text-xs font-black text-tl-navy">{e.kartlar(d.kartlar.toplam, d.kartlar.tam_atanmis, d.kartlar.tam_siz)}</p>
          <VeriTablosu<EslesmeKaynagi>
            baslik={e.baslik}
            satirlar={d.kaynaklar}
            anahtar={(x) => x.anahtar}
            kolonlar={[
              {
                baslik: e.kaynak,
                hucre: (x) => (
                  <span className="grid">
                    <span className="font-black text-tl-navy">{x.ad}</span>
                    {x.not ? <span className="max-w-96 text-[0.625rem] font-normal text-slate-500">{x.not}</span> : null}
                  </span>
                ),
              },
              { baslik: e.toplam, hucre: (x) => sayi(x.toplam), sinif: "text-right font-mono" },
              { baslik: e.kartaEslesen, hucre: (x) => sayi(x.karta_eslesen), sinif: "text-right font-mono" },
              { baslik: e.tamAtanmis, hucre: (x) => sayi(x.tam_atanmis), sinif: "text-right font-mono" },
              { baslik: e.kartsiz, hucre: (x) => <span className={x.kartsiz ? "text-rose-700" : ""}>{sayi(x.kartsiz)}</span>, sinif: "text-right font-mono" },
              { baslik: e.oran, hucre: (x) => <Rozet ton={oranTonu(x.oran)}>{x.oran === null ? "—" : `%${x.oran}`}</Rozet> },
              { baslik: "", hucre: (x) => (x.yer ? <a href={`#/${x.yer}`} className={BAG}>{e.git}</a> : null) },
            ]}
          />
        </div>
      </Panel>

      <Panel baslik={e.kartsizBaslik} aciklama={e.kartsizAciklama}>
        <VeriTablosu
          baslik={e.kartsizBaslik}
          satirlar={d.kartsiz_ilk}
          anahtar={(x) => x.musteri_no || x.ad}
          bos={<Bos>{e.hepsiEslesik}</Bos>}
          kolonlar={[
            { baslik: e.musteriNo, hucre: (x) => <span className="font-mono font-black">{x.musteri_no || "—"}</span> },
            { baslik: e.unvan, hucre: (x) => x.ad || "—" },
            { baslik: e.kayit, hucre: (x) => sayi(x.adet), sinif: "text-right font-mono" },
            {
              baslik: "",
              hucre: () => (
                <span className="flex gap-3 whitespace-nowrap">
                  <a href="#/yonetim/tampon?sekme=akis" className={BAG}>
                    {e.temipAta}
                  </a>
                  <a href="#/radar" className={BAG}>
                    {e.radar}
                  </a>
                </span>
              ),
            },
          ]}
        />
      </Panel>
    </div>
  )
}
