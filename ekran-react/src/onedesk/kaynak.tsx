import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Database, PlugZap, Upload } from "lucide-react"
import { Bildirim, BosKutu, DUGME_ANA, GIRDI, HataKutu, Panel, Yukleniyor } from "@/components/sayfa-ui"
import { sayi, zaman } from "@/lib/bicim"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import type { OnedeskMetin } from "@/onedesk/onedesk-metin"
import type { AktarSonuc, Kaynak, Parti } from "@/onedesk/tipler"

function PartiSatiri({ parti, t }: { parti: Parti; t: OnedeskMetin }) {
  const qc = useQueryClient()
  const [tur, setTur] = useState("")
  const aktar = useMutation({
    mutationFn: () => yaz<AktarSonuc>("POST", `/api/v1/onedesk/ice-al/${parti.id}`, tur ? { tur } : {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["onedesk"] })
      void qc.invalidateQueries({ queryKey: ["musteri"] })
    },
  })
  const s = aktar.data
  return (
    <li className="grid gap-2 rounded-xl border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-black text-tl-navy">
            #{parti.id} · {parti.etiket || parti.kaynak}
          </p>
          <p className="text-[0.625rem] font-bold text-slate-400">
            <code>{parti.kaynak}</code> · {sayi(parti.satir)} {t.satir} · {zaman(parti.zaman)}
          </p>
        </div>
        <label className="flex items-center gap-1.5 text-[0.625rem] font-black uppercase text-slate-400">
          {t.turSec}
          <select className={`${GIRDI} !w-auto`} value={tur} onChange={(e) => setTur(e.target.value)}>
            <option value="">{t.turOtomatik}</option>
            <option value="alarm">{t.alarm}</option>
            <option value="talep">{t.talep}</option>
            <option value="sikayet">{t.sikayet}</option>
          </select>
        </label>
        <button type="button" className={DUGME_ANA} disabled={aktar.isPending} onClick={() => aktar.mutate()}>
          <Upload aria-hidden className="size-3.5" />
          {aktar.isPending ? t.aktariliyor : t.aktar}
        </button>
      </div>
      {s ? <Bildirim ton="yesil">{t.aktarSonuc(s.eklenen, s.guncellenen, s.atlanan, s.musteri_eslesmeyen)}</Bildirim> : null}
      {aktar.isError ? <Bildirim ton="kirmizi">{hataMesaji(aktar.error, t.aktarHata)}</Bildirim> : null}
    </li>
  )
}

/** Yalniz admin: Onedesk verisinin kaynagi (canli baglanti yuvasi, kayit durumu) ve Veri Girisi partisi aktarimi. */
export function KaynakPaneli({ t }: { t: OnedeskMetin }) {
  const q = useQuery({ queryKey: ["onedesk", "kaynak"], queryFn: () => oku<Kaynak>("/api/v1/onedesk/kaynak") })
  const v = q.data
  return (
    <Panel baslik={t.kaynak} aciklama={t.kaynakAlt}>
      {q.isPending ? (
        <Yukleniyor metin="…" />
      ) : q.isError || !v ? (
        <HataKutu metin={t.yuklenemedi} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
      ) : (
        <div className="grid gap-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3">
              <p className="flex items-center gap-1.5 text-[0.625rem] font-black uppercase tracking-wide text-slate-400">
                <PlugZap aria-hidden className="size-3.5" />
                {t.canli}
              </p>
              <p className="mt-1 text-xs font-black text-slate-600">{t.canliKapali}</p>
              <p className="mt-0.5 text-[0.625rem] font-bold text-slate-400">
                {t.yuva}: <code>{v.canli_baglanti.yuva}</code> · {v.canli_baglanti.yapilandirildi ? t.yuvaVar : t.yuvaYok}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3">
              <p className="flex items-center gap-1.5 text-[0.625rem] font-black uppercase tracking-wide text-slate-400">
                <Database aria-hidden className="size-3.5" />
                {t.kayitSayisi}
              </p>
              <p className="mt-1 font-mono text-xl font-black text-tl-navy">{sayi(v.kayit)}</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3">
              <p className="text-[0.625rem] font-black uppercase tracking-wide text-slate-400">{t.sonKayit}</p>
              <p className="mt-1 text-xs font-black text-slate-600">{zaman(v.son_kayit)}</p>
            </div>
          </div>
          <div>
            <p className="text-[0.6875rem] font-black text-tl-navy">{t.aktarilabilir}</p>
            <p className="mb-2 text-[0.625rem] font-bold text-slate-400">{t.aktarilabilirAlt}</p>
            {v.partiler.length === 0 ? (
              <BosKutu baslik={t.partiYok} />
            ) : (
              <ul className="grid gap-2">
                {v.partiler.map((p) => (
                  <PartiSatiri key={p.id} parti={p} t={t} />
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </Panel>
  )
}
