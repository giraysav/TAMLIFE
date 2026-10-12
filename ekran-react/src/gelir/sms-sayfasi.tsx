import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MessageSquare, Wallet } from "lucide-react"
import { DuzenlenebilirTablo } from "@/components/duzenlenebilir-tablo"
import type { Kolon } from "@/components/duzenlenebilir-tablo"
import { BosKutu, GIRDI, HataKutu, Kpi, SayfaKabi, Yukleniyor } from "@/components/sayfa-ui"
import { gelirMetin } from "@/gelir/gelir-metin"
import { para } from "@/lib/bicim"
import { oku, sorguMetni, yaz } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"

type SmsKayit = { id: number; musteri: string; proje: string; tutar: number; para_birimi: string; tam: string; yil: number; ay: number }
type Liste = { items: SmsKayit[]; toplam: Record<string, number>; yillar: number[] }

/** ICT Sms & Gelir: yalniz uc sutun, musteri adi - proje bilgisi - gelir bilgisi. */
export function SmsSayfasi({ dil, yazabilir }: { dil: Dil; yazabilir: boolean }) {
  const t = gelirMetin(dil)
  const qc = useQueryClient()
  const [yil, setYil] = useState("")
  const sorgu = { yil }
  const liste = useQuery({ queryKey: ["gelir", "sms", yil], queryFn: () => oku<Liste>(`/api/v1/gelir/sms${sorguMetni(sorgu)}`) })
  const adlar = useQuery({ queryKey: ["gelir", "musteri-adlari"], queryFn: () => oku<string[]>("/api/v1/gelir/musteri-adlari"), staleTime: 60_000 })
  const yenile = () => qc.invalidateQueries({ queryKey: ["gelir", "sms"] })
  const kaydet = useMutation({
    mutationFn: ({ govde, id }: { govde: Record<string, unknown>; id: number | null }) =>
      yaz(id === null ? "POST" : "PUT", id === null ? "/api/v1/gelir/sms" : `/api/v1/gelir/sms/${id}`, govde),
    onSuccess: yenile,
  })
  const sil = useMutation({ mutationFn: (id: number) => yaz("DELETE", `/api/v1/gelir/sms/${id}`), onSuccess: yenile })

  const kolonlar: Kolon[] = [
    { anahtar: "musteri", baslik: t.musteri, tip: "musteri", zorunlu: true },
    { anahtar: "proje", baslik: t.proje, tip: "metin", zorunlu: true },
    { anahtar: "tutar", baslik: t.gelir, tip: "tutarPara", sag: true },
  ]
  const toplamlar = Object.entries(liste.data?.toplam ?? {})
  const adet = liste.data?.items.length ?? 0

  return (
    <div className="grid grid-cols-1 gap-4">
      <SayfaKabi ikon={MessageSquare} baslik={t.smsBaslik} aciklama={t.smsAciklama}>
        <label className="flex items-center gap-2 text-[0.625rem] font-black uppercase tracking-wide text-white/70">
          {t.yil}
          <select className={`${GIRDI} !w-auto !py-2`} value={yil} onChange={(e) => setYil(e.target.value)}>
            <option value="">{t.tumYillar}</option>
            {(liste.data?.yillar ?? []).map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
      </SayfaKabi>

      {toplamlar.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {toplamlar.map(([birim, tutar]) => (
            <Kpi key={birim} etiket={`${t.smsToplam} · ${birim}`} deger={para(tutar, birim)} alt={t.smsKayit(adet)} ikon={Wallet} ton="yesil" />
          ))}
        </div>
      ) : null}

      {liste.isPending ? (
        <Yukleniyor metin="…" />
      ) : liste.isError || !liste.data ? (
        <HataKutu metin={t.yuklenemedi} tekrar={() => void liste.refetch()} tekrarEtiket={t.tekrar} />
      ) : (
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <DuzenlenebilirTablo
            kolonlar={kolonlar}
            satirlar={liste.data.items}
            metin={t.tablo}
            musteriAdlari={adlar.data}
            saltOkunur={!yazabilir}
            bosKutu={<BosKutu ikon={MessageSquare} baslik={t.smsBos} aciklama={t.smsBosAlt} />}
            onKaydet={async (govde, id) => {
              await kaydet.mutateAsync({ govde, id })
            }}
            onSil={async (id) => {
              await sil.mutateAsync(id)
            }}
          />
        </div>
      )}
    </div>
  )
}
