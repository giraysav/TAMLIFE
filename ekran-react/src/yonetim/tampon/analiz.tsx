import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ScanSearch, Trash2 } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Bildirim, Bolum, DUGME, DUGME_ANA, Rozet, VeriTablosu } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import { hataMesaji, oku, sorguMetni, yaz } from "@/lib/sorgu"
import type { Analiz as AnalizTipi, Oneri, PartiAyrintisi, PartiSatirlari, SutunProfili } from "@/yonetim/api"
import { ym } from "@/yonetim/metin"
import { sayi, zaman } from "@/lib/bicim"
import { PARTI_TON } from "@/yonetim/tampon/partiler"

export type OneriSecimi = { kolon: string; alan: string }

/** Secili parti: ust serit (durum + islemler), sutun profili, anahtar onerileri, ilk satirlar. */
export function Analiz({ dil, parti, onKuralOner, onSilindi }: { dil: Dil; parti: PartiAyrintisi; onKuralOner: (oneri: OneriSecimi) => void; onSilindi: () => void }) {
  const t = ym(dil)
  const qc = useQueryClient()
  const [bilgi, setBilgi] = useState<{ ton: "yesil" | "amber"; metin: string } | null>(null)
  const yenile = () => {
    void qc.invalidateQueries({ queryKey: ANAHTAR.parti })
    void qc.invalidateQueries({ queryKey: ANAHTAR.partiler })
    void qc.invalidateQueries({ queryKey: ANAHTAR.kaynaklar })
    void qc.invalidateQueries({ queryKey: ANAHTAR.ozet })
  }
  const hata = (e: unknown) => setBilgi({ ton: "amber", metin: hataMesaji(e, t.islemBasarisiz) })

  const analizEt = useMutation({
    mutationFn: () => yaz<AnalizTipi>("POST", `/api/v1/tampon/partiler/${parti.id}/analiz`),
    onSuccess: () => {
      setBilgi(null)
      yenile()
    },
    onError: hata,
  })
  const kabul = useMutation({
    mutationFn: () => yaz<unknown>("POST", `/api/v1/tampon/partiler/${parti.id}/kabul`),
    onSuccess: () => {
      setBilgi(null)
      yenile()
    },
    onError: hata,
  })
  const sil = useMutation({
    mutationFn: () => yaz<unknown>("DELETE", `/api/v1/tampon/partiler/${parti.id}`),
    onSuccess: () => {
      yenile()
      onSilindi()
    },
    onError: hata,
  })

  const satirlar = useQuery({
    queryKey: [...ANAHTAR.parti, parti.id, "satirlar"],
    queryFn: () => oku<PartiSatirlari>(`/api/v1/tampon/partiler/${parti.id}/satirlar${sorguMetni({ adet: 8 })}`),
    enabled: parti.durum === "ready" || parti.durum === "rejected",
  })
  const hazir = parti.durum === "ready" || parti.durum === "rejected"
  const analiz = parti.analiz

  // Hazir partide analiz yoksa bir kez otomatik calisir: oneriler ilk bakista gelir (yonetici yine "Analiz et" ile tazeleyebilir).
  const otomatikDenenen = useRef<number | null>(null)
  useEffect(() => {
    if (hazir && analiz === null && otomatikDenenen.current !== parti.id) {
      otomatikDenenen.current = parti.id
      analizEt.mutate()
    }
  }, [hazir, analiz, parti.id, analizEt])

  return (
    <Bolum anahtar="yonetim-tampon-analiz" baslik={`${t.adim.analiz} · #${parti.id}`}>
      <div className="grid gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <Rozet ton={PARTI_TON[parti.durum]}>{t.partiDurum[parti.durum]}</Rozet>
          <span className="text-xs font-black text-tl-navy">{parti.etiket || `#${parti.id}`}</span>
          <span className="text-[11px] font-bold text-slate-500">
            {sayi(parti.satir)} {t.satir.toLowerCase()} · {parti.sutun_sayisi} {t.sutun.toLowerCase()} · {zaman(parti.zaman)}
          </span>
          <span className="ml-auto flex flex-wrap gap-2">
            {parti.durum === "rejected" ? (
              <button type="button" className={DUGME_ANA} disabled={kabul.isPending} onClick={() => kabul.mutate()}>
                {t.yineDeKabul}
              </button>
            ) : null}
            <button type="button" className={DUGME_ANA} disabled={!hazir || analizEt.isPending} onClick={() => analizEt.mutate()}>
              <ScanSearch aria-hidden className="size-4" />
              {analizEt.isPending ? t.analizEdiliyor : t.analizEt}
            </button>
            <button
              type="button"
              className={DUGME}
              disabled={sil.isPending || parti.kullanimda}
              title={parti.kullanimda ? t.kullanimda : undefined}
              onClick={() => {
                if (window.confirm(t.partiSilOnay(parti.id))) sil.mutate()
              }}
            >
              <Trash2 aria-hidden className="size-3.5" />
              {t.partiSil}
            </button>
          </span>
        </div>
        {parti.hata ? <Bildirim ton="amber">{parti.hata}</Bildirim> : null}
        {parti.kullanimda ? <Bildirim>{t.kullanimda}</Bildirim> : null}
        {bilgi ? <Bildirim ton={bilgi.ton}>{bilgi.metin}</Bildirim> : null}
        <p className="text-[11px] font-bold text-slate-400">{t.adimAciklama.analiz}</p>

        <div className="grid gap-2">
          <h4 className="text-[11px] font-black uppercase tracking-widest text-tl-navy">{t.oneriler}</h4>
          {analiz === null || analiz.oneriler.length === 0 ? (
            <>
              <Bildirim>{t.oneriYok}</Bildirim>
              {analiz?.uyarilar.map((u) => (
                <Bildirim key={u} ton="amber">
                  {u}
                </Bildirim>
              ))}
            </>
          ) : (
            <>
              <p className="text-[11px] font-bold text-slate-400">{t.oneriAciklama(analiz.musteri_sayisi)}</p>
              <ul className="grid gap-2 md:grid-cols-2">
                {analiz.oneriler.map((o: Oneri) => (
                  <li key={`${o.kolon}-${o.alan}`} className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-3 text-xs shadow-sm">
                    <div className="min-w-0 flex-1">
                      <p className="font-black text-tl-navy">
                        {o.kolon} <span className="text-slate-400">→</span> {t.alanAdi[o.alan] ?? o.alan}
                      </p>
                      <p className="font-bold text-slate-500">{t.eslesenOran(o.eslesen, o.farkli, o.oran)}</p>
                    </div>
                    <button type="button" className={DUGME} onClick={() => onKuralOner({ kolon: o.kolon, alan: o.alan })}>
                      {t.kuralOlustur}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        <details className="group rounded-xl border border-slate-200">
          <summary className="cursor-pointer select-none px-3 py-2 text-[11px] font-black uppercase tracking-widest text-tl-navy">{t.sutunProfili}</summary>
          <div className="p-3">
            <VeriTablosu<SutunProfili>
              baslik={t.sutunProfili}
              satirlar={parti.profil}
              anahtar={(s) => s.sutun}
              kolonlar={[
                { baslik: t.sutun, hucre: (s) => <span className="font-black text-tl-navy">{s.sutun}</span> },
                { baslik: t.doluluk, hucre: (s) => `${sayi(s.dolu)} (%${parti.satir ? Math.round((s.dolu * 100) / parti.satir) : 0})`, sinif: "text-right" },
                { baslik: t.farkli, hucre: (s) => String(s.farkli), sinif: "text-right" },
                { baslik: t.tip, hucre: (s) => s.tip },
                { baslik: t.enSik, hucre: (s) => <span className="line-clamp-2 max-w-80 break-words font-normal">{s.en_sik.map(([d, n]) => `${d} (${n})`).join(" · ")}</span> },
              ]}
            />
          </div>
        </details>

        {satirlar.data ? (
          <details className="group rounded-xl border border-slate-200">
            <summary className="cursor-pointer select-none px-3 py-2 text-[11px] font-black uppercase tracking-widest text-tl-navy">{t.ilkSatirlar}</summary>
            <div className="p-3">
              <VeriTablosu<(string | null)[]>
                baslik={t.ilkSatirlar}
                satirlar={satirlar.data.satirlar}
                anahtar={(s) => s.join("|")}
                kolonlar={satirlar.data.basliklar.map((b, i) => ({ baslik: b, hucre: (s: (string | null)[]) => <span className="whitespace-nowrap font-normal">{s[i] ?? "—"}</span> }))}
              />
            </div>
          </details>
        ) : null}
      </div>
    </Bolum>
  )
}
