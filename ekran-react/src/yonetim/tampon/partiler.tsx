import { useState } from "react"
import { keepPreviousData, useQuery } from "@tanstack/react-query"
import type { Dil } from "@/shell/metin"
import { Alan, Bolum, GIRDI, HataKutu, Rozet, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import { oku, sorguMetni } from "@/lib/sorgu"
import type { Parti, Sayfali } from "@/yonetim/api"
import { Sayfalama } from "@/yonetim/ui"
import { zaman, sayi } from "@/lib/bicim"
import { tm } from "@/yonetim/tampon/metin"

const ADET = 10
export const PARTI_TON = { receiving: "amber", ready: "yesil", failed: "kirmizi", rejected: "amber" } as const

export function Partiler({ dil, seciliId, onSec }: { dil: Dil; seciliId: number | null; onSec: (id: number) => void }) {
  const t = tm(dil)
  const [durum, setDurum] = useState("")
  const [sayfa, setSayfa] = useState(1)
  const sorgu = { durum, sayfa, adet: ADET }
  const q = useQuery({
    queryKey: [...ANAHTAR.partiler, sorgu],
    queryFn: () => oku<Sayfali<Parti>>(`/api/v1/tampon/partiler${sorguMetni(sorgu)}`),
    placeholderData: keepPreviousData,
  })

  return (
    <Bolum anahtar="yonetim-tampon-partiler" baslik={`${t.adim.tampon} · ${t.partiler}`}>
      <div className="grid gap-3">
        <p className="text-[0.6875rem] font-bold text-slate-400">{t.adimAciklama.tampon}</p>
        <Alan etiket={t.durum} sinif="max-w-48">
          <select
            className={GIRDI}
            value={durum}
            onChange={(e) => {
              setDurum(e.target.value)
              setSayfa(1)
            }}
          >
            <option value="">{t.hepsi}</option>
            {(["ready", "rejected", "failed"] as const).map((d) => (
              <option key={d} value={d}>
                {t.partiDurum[d]}
              </option>
            ))}
          </select>
        </Alan>
        {q.isPending ? (
          <Yukleniyor metin={t.yukleniyor} iskelet />
        ) : q.isError ? (
          <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void q.refetch()} />
        ) : (
          <div className={`grid gap-3 ${q.isPlaceholderData ? "opacity-70" : ""}`}>
            <VeriTablosu<Parti>
              baslik={t.partiler}
              satirlar={q.data.satirlar}
              anahtar={(p) => p.id}
              vurgulu={(p) => p.id === seciliId}
              bos={<p className="text-xs font-bold text-slate-400">{t.partiYok}</p>}
              kolonlar={[
                {
                  baslik: "#",
                  hucre: (p) => (
                    <button
                      type="button"
                      aria-pressed={p.id === seciliId}
                      aria-label={`${t.sec}: #${p.id}`}
                      onClick={() => onSec(p.id)}
                      className="font-mono text-[0.6875rem] font-black text-tl-blue underline-offset-2 hover:underline focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
                    >
                      #{p.id}
                    </button>
                  ),
                },
                { baslik: t.kaynaklar, hucre: (p) => <code className="text-[0.6875rem]">{p.kaynak}</code> },
                { baslik: t.etiket, hucre: (p) => <span className="line-clamp-1 max-w-56 break-all font-normal">{p.etiket || "—"}</span> },
                { baslik: t.durum, hucre: (p) => <Rozet ton={PARTI_TON[p.durum]}>{t.partiDurum[p.durum]}</Rozet> },
                { baslik: t.satir, hucre: (p) => sayi(p.satir), sinif: "text-right font-mono" },
                { baslik: t.zaman, hucre: (p) => <span className="whitespace-nowrap">{zaman(p.zaman)}</span> },
                { baslik: t.olusturan, hucre: (p) => p.olusturan },
              ]}
            />
            <Sayfalama t={t} sayfa={q.data.sayfa} adet={q.data.adet} toplam={q.data.toplam} onSayfa={setSayfa} />
          </div>
        )}
      </div>
    </Bolum>
  )
}
