import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { DatabaseBackup, ShieldCheck } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Bildirim, Bolum, DUGME, DUGME_ANA, GIRDI, HataKutu, Rozet, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import type { Veritabani as VeritabaniTipi, Yedek } from "@/yonetim/api"
import { ym } from "@/yonetim/metin"
import { Gosterge } from "@/yonetim/ui"
import { zaman, bayt, sayi } from "@/lib/bicim"

type Dogrulama = { tamam: boolean; butunluk: string }

/** Veritabani: motor, sema surumu, butunluk, tablolar, yedek (al / dogrula). Geri yukleme bu surumde yok. */
export default function Veritabani({ dil }: { dil: Dil }) {
  const t = ym(dil)
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ANAHTAR.veritabani, queryFn: () => oku<VeritabaniTipi>("/api/v1/yonetim/veritabani") })
  const [ara, setAra] = useState("")
  const [bilgi, setBilgi] = useState<{ ton: "yesil" | "amber"; metin: string } | null>(null)
  const [dogrulamalar, setDogrulamalar] = useState<Record<string, Dogrulama>>({})

  const yedekAl = useMutation({
    mutationFn: () => yaz<{ ad: string }>("POST", "/api/v1/yonetim/veritabani/yedek"),
    onSuccess: (s) => {
      setBilgi({ ton: "yesil", metin: t.yedekAlindi(s.ad) })
      void qc.invalidateQueries({ queryKey: ANAHTAR.veritabani })
      void qc.invalidateQueries({ queryKey: ANAHTAR.ozet })
    },
    onError: (e) => setBilgi({ ton: "amber", metin: hataMesaji(e, t.islemBasarisiz) }),
  })
  const dogrula = useMutation({
    mutationFn: (ad: string) => yaz<Dogrulama & { ad: string }>("POST", `/api/v1/yonetim/veritabani/yedek/${encodeURIComponent(ad)}/dogrula`),
    onSuccess: (s) => setDogrulamalar((o) => ({ ...o, [s.ad]: { tamam: s.tamam, butunluk: s.butunluk } })),
    onError: (e) => setBilgi({ ton: "amber", metin: hataMesaji(e, t.islemBasarisiz) }),
  })

  const tablolar = useMemo(() => {
    const aranan = ara.trim().toLowerCase()
    return (q.data?.tablolar ?? []).filter((x) => !aranan || x.ad.includes(aranan) || x.modul.includes(aranan))
  }, [q.data, ara])

  if (q.isPending) return <Yukleniyor metin={t.yukleniyor} iskelet />
  if (q.isError) return <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void q.refetch()} />
  const d = q.data
  const butunlukTamam = d.butunluk === null || d.butunluk === "ok"

  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Gosterge etiket={t.motor} deger={d.motor.toUpperCase()} alt={d.dosya ?? undefined} />
        <Gosterge
          etiket={t.sema}
          deger={d.surum ? d.surum.split("_")[0] : "—"}
          alt={d.surum_uyumlu === null ? t.semaYok : d.surum_uyumlu ? t.semaUyumlu : t.semaUyumsuz(d.hedef_surum ?? "?")}
          ton={d.surum_uyumlu === false ? "uyari" : d.surum_uyumlu ? "ok" : "notr"}
        />
        <Gosterge etiket={t.boyut} deger={bayt(d.boyut_bayt)} alt={`${t.diskSerbest}: ${bayt(d.disk_serbest_bayt)} · ${sayi(d.toplam_satir)} ${t.satirAdedi.toLowerCase()}`} />
        <Gosterge etiket={t.butunluk} deger={d.butunluk ?? "—"} ton={butunlukTamam ? "ok" : "hata"} />
      </div>

      {d.eksik_tablolar.length > 0 ? <Bildirim ton="amber">{t.eksikTablo(d.eksik_tablolar.length)}</Bildirim> : null}

      <Bolum anahtar="yonetim-db-yedek" baslik={t.yedek}>
        <div className="grid gap-3">
          {d.yedek.desteklenir ? (
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" className={DUGME_ANA} disabled={yedekAl.isPending} onClick={() => yedekAl.mutate()}>
                <DatabaseBackup aria-hidden className="size-4" />
                {yedekAl.isPending ? t.yedekAliniyor : t.yedekAl}
              </button>
              <span className="text-[11px] font-bold text-slate-500">{t.yedekSaklanan(d.yedek.saklanan)}</span>
            </div>
          ) : (
            <Bildirim>{t.yedekDesteklenmiyor}</Bildirim>
          )}
          {bilgi ? <Bildirim ton={bilgi.ton}>{bilgi.metin}</Bildirim> : null}
          <VeriTablosu<Yedek>
            baslik={t.yedek}
            satirlar={d.yedek.liste}
            anahtar={(y) => y.ad}
            bos={<p className="text-xs font-bold text-slate-400">{t.yedekYok}</p>}
            kolonlar={[
              { baslik: t.yedek, hucre: (y) => <code className="text-[11px]">{y.ad}</code> },
              { baslik: t.zaman, hucre: (y) => zaman(y.zaman) },
              { baslik: t.boyut, hucre: (y) => bayt(y.boyut_bayt), sinif: "text-right" },
              {
                baslik: t.durum,
                hucre: (y) => {
                  const s = dogrulamalar[y.ad]
                  return s ? (
                    <Rozet ton={s.tamam ? "yesil" : "kirmizi"}>{s.tamam ? t.dogrulamaTamam : t.dogrulamaHata}</Rozet>
                  ) : (
                    <button type="button" className={DUGME} disabled={dogrula.isPending} onClick={() => dogrula.mutate(y.ad)}>
                      <ShieldCheck aria-hidden className="size-3.5" />
                      {t.yedekDogrula}
                    </button>
                  )
                },
              },
            ]}
          />
          <dl className="grid gap-1 text-[11px] font-bold text-slate-500">
            <div className="flex flex-wrap gap-x-2">
              <dt>{t.yedekKlasoru}:</dt>
              <dd className="break-all">
                <code>{d.yedek.dizin}</code>
              </dd>
            </div>
          </dl>
          <p className="text-[11px] font-bold text-slate-400">{t.yedekAyriDisk}</p>
          <p className="text-[11px] font-bold text-slate-400">{t.geriYuklemeNotu}</p>
        </div>
      </Bolum>

      <Bolum anahtar="yonetim-db-tablolar" baslik={`${t.tablolar} (${d.tablolar.length})`}>
        <div className="grid gap-3">
          <input aria-label={t.tabloAra} placeholder={t.tabloAra} className={`${GIRDI} max-w-xs`} value={ara} onChange={(e) => setAra(e.target.value)} />
          <VeriTablosu
            baslik={t.tablolar}
            satirlar={tablolar}
            anahtar={(x) => x.ad}
            kolonlar={[
              { baslik: t.tablolar, hucre: (x) => <code className="text-[11px]">{x.ad}</code> },
              { baslik: t.modul, hucre: (x) => x.modul },
              { baslik: t.satirAdedi, hucre: (x) => sayi(x.satir), sinif: "text-right font-mono" },
              { baslik: t.durum, hucre: (x) => <Rozet ton={x.var ? "yesil" : "kirmizi"}>{x.var ? t.tabloVar : t.tabloYok}</Rozet> },
            ]}
          />
        </div>
      </Bolum>
    </div>
  )
}
