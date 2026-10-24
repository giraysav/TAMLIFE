import { useQuery } from "@tanstack/react-query"
import type { Dil } from "@/shell/metin"
import { Bildirim, Bolum, HataKutu, Rozet, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import type { AkisDurumu, VeriAkisi, VeriAkislari } from "@/yonetim/api"
import { oku } from "@/lib/sorgu"
import { zaman } from "@/lib/bicim"
import { tm } from "@/yonetim/tampon/metin"

const TON: Record<AkisDurumu, "yesil" | "amber" | "kirmizi" | "gri"> = { taze: "yesil", bayat: "amber", hata: "kirmizi", yok: "gri", bilgi: "gri" }

/** Tek sorgu: Veri akislari paneli ve Dagitim baslik rozeti ayni onbellegi kullanir. Dakikada bir tazelenir (isci 6 dk'da bir yazar). */
export function useVeriAkislari() {
  return useQuery({ queryKey: ANAHTAR.akislar, queryFn: () => oku<VeriAkislari>("/api/v1/tampon/akislar"), refetchInterval: 60_000 })
}

/** Veri Girisi ust paneli: panele veri getiren tum yollar (bu ekran, Onedesk, Utilizasyon, Gelir Faydasi, isci/CLI) ve bayat uyarisi. */
export function VeriAkislariPaneli({ dil }: { dil: Dil }) {
  const t = tm(dil)
  const a = tm(dil).akislar
  const q = useVeriAkislari()
  return (
    <Bolum anahtar="yonetim-tampon-akislar" baslik={a.baslik}>
      <div className="grid gap-3">
        <p className="text-[0.6875rem] font-bold text-slate-400">{a.aciklama}</p>
        {q.isPending ? (
          <Yukleniyor metin={t.yukleniyor} iskelet />
        ) : q.isError ? (
          <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void q.refetch()} />
        ) : (
          <>
            {q.data.uyarilar.length ? (
              <Bildirim ton="amber">
                {a.uyari(q.data.uyarilar.length)} {q.data.uyarilar.join(" · ")}
              </Bildirim>
            ) : null}
            <VeriTablosu<VeriAkisi>
              baslik={a.baslik}
              satirlar={q.data.akislar}
              anahtar={(x) => x.anahtar}
              kolonlar={[
                { baslik: a.akis, hucre: (x) => <span className="font-black text-tl-navy">{x.ad}</span> },
                { baslik: a.yontem, hucre: (x) => <span className="whitespace-nowrap">{x.yontem}</span> },
                { baslik: a.son, hucre: (x) => <span className="whitespace-nowrap">{x.son ? zaman(x.son) : "—"}</span> },
                { baslik: a.durum, hucre: (x) => <Rozet ton={TON[x.durum]}>{a.durumAdi[x.durum]}</Rozet> },
                {
                  baslik: a.not,
                  hucre: (x) => (
                    <span className="block max-w-96 font-normal">
                      {x.anahtar === "temip" && x.son ? `${a.kayitlar(x.acik ?? 0, x.kapali ?? 0, x.radar ?? 0)}. ` : ""}
                      {x.aciklama || ""}
                    </span>
                  ),
                },
                {
                  baslik: "",
                  hucre: (x) =>
                    x.yer ? (
                      <a href={`#/${x.yer}`} className="font-black text-tl-blue underline-offset-2 hover:underline">
                        {a.git}
                      </a>
                    ) : null,
                },
              ]}
            />
          </>
        )}
      </div>
    </Bolum>
  )
}
