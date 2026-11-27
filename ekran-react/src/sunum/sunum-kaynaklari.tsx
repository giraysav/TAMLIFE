import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowDown, ArrowUp } from "lucide-react"
import { Bildirim, HataKutu, Rozet, Yukleniyor } from "@/components/sayfa-ui"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { yerel } from "@/shell/metin"
import type { Dil } from "@/shell/metin"
import { sunumMetin } from "@/sunum/sunum-metin"

export type SunumKaynagi = { id: string; ad: string; ad_en: string; aciklama: string; aciklama_en: string; modul: string; modul_en: string; anlik: boolean; acik: boolean; grup?: string }
export type Kaynaklar = { kaynaklar: SunumKaynagi[]; duzenleyebilir: boolean }
const KAYNAK_ANAHTARI = ["sunum", "kaynaklar"] as const

/** Sunum duzenini kaydeder: gorunur alanlar + tum alanlarin sirasi. Yanit gelmeden liste yeni sirayla gosterilir (surukle-birak akici kalsin). */
export function useDuzenKaydet() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (liste: SunumKaynagi[]) => yaz<{ kaynaklar: SunumKaynagi[] }>("PUT", "/api/v1/sunum/kaynaklar", { kaynaklar: liste.filter((k) => k.acik).map((k) => k.id), sira: liste.map((k) => k.id) }),
    onMutate: (liste) => qc.setQueryData<Kaynaklar>(KAYNAK_ANAHTARI, (eski) => eski && { ...eski, kaynaklar: liste }),
    onSettled: (yanit) => {
      if (yanit) qc.setQueryData<Kaynaklar>(KAYNAK_ANAHTARI, (eski) => eski && { ...eski, kaynaklar: yanit.kaynaklar })
      else void qc.invalidateQueries({ queryKey: KAYNAK_ANAHTARI }) // hata: sunucudaki duzene don
      void qc.invalidateQueries({ queryKey: ["sunum", "donem"] })
    },
  })
}

export function useKaynaklar() {
  return useQuery({ queryKey: KAYNAK_ANAHTARI, queryFn: () => oku<Kaynaklar>("/api/v1/sunum/kaynaklar") })
}

/** Sunum icerigi penceresi: her panel modulunun sunumdaki alani; isaret = sunumda, oklar = sira. Degisiklik aninda kaydedilir; yetkiyi sunucu zorlar. */
export function SunumKaynaklari({ dil, onayli = false }: { dil: Dil; onayli?: boolean }) {
  const t = sunumMetin(dil)
  const q = useKaynaklar()
  const kaydet = useDuzenKaydet()
  if (q.isPending) return <Yukleniyor metin={t.yukleniyor} />
  if (q.isError) return <HataKutu metin={t.yuklenemedi} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
  const { kaynaklar, duzenleyebilir } = q.data
  const kapali = !duzenleyebilir || kaydet.isPending
  const degistir = (id: string, acik: boolean) => kaydet.mutate(kaynaklar.map((k) => (k.id === id ? { ...k, acik } : k)))
  const tasi = (i: number, fark: number) => {
    const yeni = [...kaynaklar]
    const [oge] = yeni.splice(i, 1)
    yeni.splice(i + fark, 0, oge)
    kaydet.mutate(yeni)
  }
  const OK = "grid size-7 place-items-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-30"

  return (
    <div className="grid gap-3">
      <p className="text-xs font-bold text-slate-500">{t.icerikAciklama}</p>
      {onayli ? <Bildirim ton="amber">{t.onayliPencere}</Bildirim> : null}
      <p className="text-[0.625rem] font-black uppercase tracking-widest text-slate-400">{t.gorunurSayisi(kaynaklar.filter((k) => k.acik).length, kaynaklar.length)}</p>
      <ol className="grid gap-2">
        {kaynaklar.map((k, i) => {
          const ad = yerel(dil, k.ad, k.ad_en)
          return (
            <li key={k.id} className={`flex items-start gap-2 rounded-xl border p-2.5 text-sm ${k.acik ? "border-tl-blue/50 bg-tl-blue/5" : "border-slate-200 bg-white"}`}>
              <span className="mt-0.5 w-5 shrink-0 text-right font-mono text-xs font-black text-slate-400">{i + 1}</span>
              <label className="flex min-w-0 flex-1 items-start gap-2">
                <input type="checkbox" className="mt-1 size-4 accent-[#002855]" checked={k.acik} disabled={kapali} onChange={(e) => degistir(k.id, e.target.checked)} />
                <span className="grid min-w-0 gap-0.5">
                  <span className="flex flex-wrap items-center gap-1.5 font-bold text-tl-navy">
                    {ad}
                    {k.anlik ? (
                      <span title={t.anlikIpucu}>
                        <Rozet ton="amber">{t.anlik}</Rozet>
                      </span>
                    ) : null}
                  </span>
                  <span className="text-xs text-slate-500">{yerel(dil, k.aciklama, k.aciklama_en)}</span>
                  <span className="text-[0.6875rem] font-bold text-slate-400">
                    {t.kaynakSayfa}: {yerel(dil, k.modul, k.modul_en)}
                  </span>
                </span>
              </label>
              {duzenleyebilir ? (
                <span className="flex shrink-0 flex-col gap-1">
                  <button type="button" className={OK} aria-label={t.yukari(ad)} disabled={kapali || i === 0} onClick={() => tasi(i, -1)}>
                    <ArrowUp aria-hidden className="size-3.5" />
                  </button>
                  <button type="button" className={OK} aria-label={t.asagi(ad)} disabled={kapali || i === kaynaklar.length - 1} onClick={() => tasi(i, 1)}>
                    <ArrowDown aria-hidden className="size-3.5" />
                  </button>
                </span>
              ) : null}
            </li>
          )
        })}
      </ol>
      <p className="text-xs text-slate-500">{duzenleyebilir ? t.aninda : t.saltOkunur}</p>
      {kaydet.isError ? <Bildirim ton="kirmizi">{hataMesaji(kaydet.error, t.kaydedilemedi)}</Bildirim> : kaydet.isSuccess ? <Bildirim ton="yesil">{t.kaydedildi}</Bildirim> : null}
    </div>
  )
}
