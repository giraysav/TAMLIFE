import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { RefreshCw } from "lucide-react"
import { Bildirim, DUGME, DUGME_ANA, HataKutu, Rozet, Yukleniyor } from "@/components/sayfa-ui"
import { sayi, zaman } from "@/lib/bicim"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { yerel } from "@/shell/metin"
import type { Dil } from "@/shell/metin"
import { sunumMetin } from "@/sunum/sunum-metin"

export type SenkronDurumu = "guncel" | "farkli" | "eksik" | "canli" | "kapsam_disi" | "hata"
type Fark = { ad: string; eski: number | null; yeni: number | null }
type Satir = { kaynak: string; ad: string; ad_en: string; durum: SenkronDurumu; gonderen: string; zaman: string | null; farklar: Fark[]; kayit_no: string }
export type Karsilastirma = {
  donem: string
  zaman: "guncel" | "gecmis" | "gelecek"
  onayli: boolean
  kontrol: string
  kaynaklar: Satir[]
  sayilar: Record<SenkronDurumu, number>
  senkron_gerekli: boolean
  yonetebilir: boolean
}

const TON: Record<SenkronDurumu, "yesil" | "amber" | "kirmizi" | "gri" | "sari"> = { guncel: "yesil", canli: "yesil", farkli: "amber", eksik: "amber", hata: "kirmizi", kapsam_disi: "gri" }
const deger = (n: number | null) => (n === null || n === undefined ? "—" : sayi(n))

/**
 * Sunum senkronu: once karsilastirir (kayitli ceyrek goruntusu ile canli veri; hicbir sey yazmaz), guncel olmayan alanlari listeler;
 * yetkili "Senkronla" ile hepsini canli veriyle yeniler. Onayli ceyrek senkronlanmaz (once onay kaldirilir).
 */
export function SunumSenkron({ dil, yil, ceyrek }: { dil: Dil; yil: number; ceyrek: number }) {
  const t = sunumMetin(dil)
  const qc = useQueryClient()
  const anahtar = ["sunum", "karsilastir", yil, ceyrek]
  const q = useQuery({ queryKey: anahtar, queryFn: () => oku<Karsilastirma>(`/api/v1/sunum/karsilastir?yil=${yil}&ceyrek=${ceyrek}`), staleTime: 0 })
  const senkron = useMutation({
    mutationFn: () => yaz<{ yenilenen: string[]; sonra: Karsilastirma }>("POST", "/api/v1/sunum/senkron", { yil, ceyrek }),
    onSuccess: (s) => {
      qc.setQueryData(anahtar, (eski: Karsilastirma | undefined) => (eski ? { ...s.sonra, yonetebilir: eski.yonetebilir } : eski))
      void qc.invalidateQueries({ queryKey: ["sunum", "donem"] })
    },
  })
  const v = q.data
  if (q.isPending) return <Yukleniyor metin={t.senkronKontrol} />
  if (q.isError || !v) return <HataKutu metin={t.senkronHata} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
  const bekleyen = v.sayilar.farkli + v.sayilar.eksik

  return (
    <div className="grid gap-4">
      <div className="grid gap-2">
        <Bildirim ton={v.senkron_gerekli ? "amber" : "yesil"}>{v.senkron_gerekli ? t.senkronGerekli(bekleyen) : t.senkronTamam}</Bildirim>
        <p className="text-[0.625rem] font-bold text-slate-400">{t.senkronKontrolZamani(zaman(v.kontrol))}</p>
        {senkron.isSuccess ? <Bildirim ton="yesil">{t.senkronYapildi(senkron.data.yenilenen.length)}</Bildirim> : null}
        {senkron.isError ? <Bildirim ton="kirmizi">{hataMesaji(senkron.error, t.islemHata)}</Bildirim> : null}
        {v.onayli && v.senkron_gerekli ? <Bildirim ton="gri">{t.senkronOnayli}</Bildirim> : null}
      </div>

      <ul className="grid gap-2" aria-label={t.senkronListe}>
        {v.kaynaklar.map((s) => (
          <li key={s.kaynak} className="grid gap-1.5 rounded-xl border border-slate-200 px-3 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="min-w-0 break-words text-xs font-black text-tl-navy">{yerel(dil, s.ad, s.ad_en)}</span>
              <Rozet ton={TON[s.durum]}>{t.senkronDurum[s.durum]}</Rozet>
            </div>
            {s.zaman ? <span className="text-[0.625rem] font-bold text-slate-400">{t.senkronKayit(s.gonderen, zaman(s.zaman))}</span> : null}
            {s.durum === "hata" ? <span className="text-[0.625rem] font-bold text-rose-600">{t.kaynakHata(s.kayit_no)}</span> : null}
            {s.farklar.length > 0 ? (
              <table className="w-full text-[0.6875rem]">
                <thead>
                  <tr className="text-left text-slate-400">
                    <th className="py-0.5 font-bold">{t.senkronKpi}</th>
                    <th className="py-0.5 text-right font-bold">{t.senkronEski}</th>
                    <th className="py-0.5 text-right font-bold">{t.senkronYeni}</th>
                  </tr>
                </thead>
                <tbody>
                  {s.farklar.map((f) => (
                    <tr key={f.ad} className="border-t border-slate-100 font-bold text-slate-700">
                      <td className="py-0.5">{f.ad}</td>
                      <td className="py-0.5 text-right tabular-nums">{deger(f.eski)}</td>
                      <td className="py-0.5 text-right tabular-nums text-tl-blue">{deger(f.yeni)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap items-center justify-end gap-2">
        <button type="button" className={DUGME} disabled={q.isFetching} onClick={() => void q.refetch()}>
          <RefreshCw aria-hidden className={`size-4 ${q.isFetching ? "animate-spin" : ""}`} />
          {t.senkronYenidenKarsilastir}
        </button>
        {v.yonetebilir ? (
          <button type="button" className={DUGME_ANA} disabled={!v.senkron_gerekli || v.onayli || senkron.isPending} onClick={() => senkron.mutate()}>
            <RefreshCw aria-hidden className={`size-4 ${senkron.isPending ? "animate-spin" : ""}`} />
            {t.senkronla(bekleyen)}
          </button>
        ) : null}
      </div>
    </div>
  )
}
