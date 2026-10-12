import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Bildirim, HataKutu, Rozet, Yukleniyor } from "@/components/sayfa-ui"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { yerel } from "@/shell/metin"
import type { Dil } from "@/shell/metin"
import { sunumMetin } from "@/sunum/sunum-metin"

type SunumKaynagi = { id: string; ad: string; ad_en: string; aciklama: string; aciklama_en: string; modul: string; modul_en: string; anlik: boolean; acik: boolean; grup?: string }
const GRUP_SIRASI = ["work", "insights", "admin"]
type Kaynaklar = { kaynaklar: SunumKaynagi[]; duzenleyebilir: boolean }

/** Sunuma kendiliginden akan kaynaklarin isaretlenmesi (panel geneli ayar). Isaret aninda kaydedilir; yetkiyi sunucu zorlar. */
export function SunumKaynaklari({ dil }: { dil: Dil }) {
  const t = sunumMetin(dil)
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ["sunum", "kaynaklar"], queryFn: () => oku<Kaynaklar>("/api/v1/sunum/kaynaklar") })
  const kaydet = useMutation({
    mutationFn: (kaynaklar: string[]) => yaz<{ kaynaklar: SunumKaynagi[] }>("PUT", "/api/v1/sunum/kaynaklar", { kaynaklar }),
    onSuccess: (yanit) => {
      qc.setQueryData<Kaynaklar>(["sunum", "kaynaklar"], (eski) => eski && { ...eski, kaynaklar: yanit.kaynaklar })
      void qc.invalidateQueries({ queryKey: ["sunum", "donem"] })
    },
  })
  if (q.isPending) return <Yukleniyor metin={t.yukleniyor} />
  if (q.isError) return <HataKutu metin={t.yuklenemedi} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
  const { kaynaklar, duzenleyebilir } = q.data
  const degistir = (id: string, acik: boolean) => kaydet.mutate(kaynaklar.filter((k) => (k.id === id ? acik : k.acik)).map((k) => k.id))
  /** Benim Yerim / Raporlar bolumunun tum modullerini birlikte sunuma acar ya da kapatir. */
  const grubuDegistir = (grup: string, acik: boolean) => kaydet.mutate(kaynaklar.filter((k) => ((k.grup ?? "insights") === grup ? acik : k.acik)).map((k) => k.id))
  const gruplar = GRUP_SIRASI.map((g) => ({ g, liste: kaynaklar.filter((k) => (k.grup ?? "insights") === g) })).filter((x) => x.liste.length > 0)

  return (
    <div className="grid gap-2">
      <p className="text-xs text-muted-foreground">{t.akisKurali}</p>
      {gruplar.map(({ g, liste }) => {
        const hepsi = liste.every((k) => k.acik)
        return (
          <section key={g} className="grid gap-2" aria-label={t.gruplar[g] ?? g}>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-1">
              <span className="grid">
                <span className="text-sm font-semibold text-tl-navy">{t.gruplar[g] ?? g}</span>
                <span className="text-[0.6875rem] text-muted-foreground">{t.grupAciklama}</span>
              </span>
              {duzenleyebilir ? (
                <button type="button" className="rounded-md border px-2 py-1 text-xs font-semibold hover:bg-muted" disabled={kaydet.isPending} onClick={() => grubuDegistir(g, !hepsi)}>
                  {hepsi ? t.grubuKaldir : t.grubuGonder}
                </button>
              ) : null}
            </div>
            <ul className="grid gap-2 sm:grid-cols-2">
              {liste.map((k) => (
                <li key={k.id}>
                  <label className={`flex h-full items-start gap-2 rounded-lg border p-2.5 text-sm ${k.acik ? "border-tl-blue/50 bg-tl-blue/5" : "bg-background"}`}>
                    <input type="checkbox" className="mt-1" checked={k.acik} disabled={!duzenleyebilir || kaydet.isPending} onChange={(e) => degistir(k.id, e.target.checked)} />
                    <span className="grid gap-0.5">
                      <span className="flex flex-wrap items-center gap-1.5 font-medium">
                        {yerel(dil, k.ad, k.ad_en)}
                        {k.anlik ? (
                          <span title={t.anlikIpucu}>
                            <Rozet ton="amber">{t.anlik}</Rozet>
                          </span>
                        ) : null}
                      </span>
                      <span className="text-xs text-muted-foreground">{yerel(dil, k.aciklama, k.aciklama_en)}</span>
                      <span className="text-[0.6875rem] text-muted-foreground">
                        {t.kaynakSayfa}: {yerel(dil, k.modul, k.modul_en)}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
      <p className="text-xs text-muted-foreground">{duzenleyebilir ? t.aninda : t.saltOkunur}</p>
      {kaydet.isError ? <Bildirim ton="kirmizi">{hataMesaji(kaydet.error, t.kaydedilemedi)}</Bildirim> : kaydet.isSuccess ? <Bildirim ton="yesil">{t.kaydedildi}</Bildirim> : null}
    </div>
  )
}
