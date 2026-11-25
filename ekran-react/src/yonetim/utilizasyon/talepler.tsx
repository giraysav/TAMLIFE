import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CircleCheck, CircleX } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Bildirim, Bos, DUGME, HataKutu, Panel, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import type { SkorTalebi } from "@/yonetim/api"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { zaman } from "@/lib/bicim"
import { skorYaz } from "@/yonetim/utilizasyon/ortak"
import { uym } from "@/yonetim/utilizasyon/metin"

/** Bekleyen final skor talepleri: onayla / reddet (skor atanirsa talep zaten kendiliginden onaylanir). */
export function Talepler({ dil }: { dil: Dil }) {
  const t = uym(dil)
  const u = t.util
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ANAHTAR.skorTalepler, queryFn: () => oku<{ count: number; requests: SkorTalebi[] }>("/api/v1/skor/talepler") })
  const [bilgi, setBilgi] = useState<{ ton: "yesil" | "amber"; metin: string } | null>(null)
  const karar = useMutation({
    mutationFn: (v: { id: number; action: "approve" | "reject" }) => yaz<{ id: number }>("POST", `/api/v1/skor/talepler/${v.id}/karar`, { action: v.action }),
    onSuccess: () => {
      setBilgi({ ton: "yesil", metin: u.kararVerildi })
      void qc.invalidateQueries({ queryKey: ANAHTAR.skorTalepler })
    },
    onError: (e) => setBilgi({ ton: "amber", metin: hataMesaji(e, t.islemBasarisiz) }),
  })

  return (
    <Panel baslik={u.sekme.talepler} aciklama={u.talepAciklama}>
      {q.isPending ? (
        <Yukleniyor metin={t.yukleniyor} />
      ) : q.isError ? (
        <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void q.refetch()} />
      ) : (
        <div className="grid gap-3">
          {bilgi ? <Bildirim ton={bilgi.ton}>{bilgi.metin}</Bildirim> : null}
          <VeriTablosu<SkorTalebi>
            baslik={u.sekme.talepler}
            satirlar={q.data.requests}
            anahtar={(r) => r.id}
            bos={<Bos>{u.talepYok}</Bos>}
            kolonlar={[
              { baslik: u.musteri, hucre: (r) => <span className="font-black text-tl-navy">{r.customer_name}</span> },
              { baslik: u.personel, hucre: (r) => r.tam_name || "—" },
              { baslik: u.talepEden, hucre: (r) => r.requested_by_name },
              { baslik: t.zaman, hucre: (r) => zaman(r.requested_at) },
              { baslik: u.mevcut, hucre: (r) => skorYaz(r.score), sinif: "text-right font-mono" },
              {
                baslik: u.durum,
                hucre: (r) => (
                  <span className="flex flex-wrap gap-1.5">
                    <button type="button" className={`${DUGME} !text-emerald-700`} disabled={karar.isPending} onClick={() => karar.mutate({ id: r.id, action: "approve" })}>
                      <CircleCheck aria-hidden className="size-3.5" />
                      {u.onayla}
                    </button>
                    <button
                      type="button"
                      className={`${DUGME} !text-rose-600`}
                      disabled={karar.isPending}
                      onClick={() => {
                        if (window.confirm(u.reddetOnay(r.customer_name))) karar.mutate({ id: r.id, action: "reject" })
                      }}
                    >
                      <CircleX aria-hidden className="size-3.5" />
                      {u.reddet}
                    </button>
                  </span>
                ),
              },
            ]}
          />
        </div>
      )}
    </Panel>
  )
}
