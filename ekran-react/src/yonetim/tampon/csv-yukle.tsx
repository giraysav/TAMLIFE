import { useRef, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Upload } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Alan, Bildirim, DUGME_ANA, GIRDI } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import { hataMesaji, sorguMetni, yukle } from "@/lib/sorgu"
import { tm } from "@/yonetim/tampon/metin"

type Yuklenen = { id: number; kaynak: string; satir: number; durum: string }

/** Genel CSV -> tampon partisi (PUT /tampon/yukle; kaynak csv_<ad>). Kartlara yazmaz: Dagitim kurali uygulanana kadar yalniz tampondadir. */
export function GenelCsvYukle({ dil, onYeniParti }: { dil: Dil; onYeniParti: (id: number) => void }) {
  const t = tm(dil)
  const c = tm(dil).csv
  const qc = useQueryClient()
  const girdi = useRef<HTMLInputElement>(null)
  const [ad, setAd] = useState("")
  const [dosya, setDosya] = useState<File | null>(null)
  const [bilgi, setBilgi] = useState<{ ton: "yesil" | "amber"; metin: string } | null>(null)
  const mut = useMutation({
    mutationFn: (v: { ad: string; dosya: File }) => yukle<Yuklenen>(`/api/v1/tampon/yukle${sorguMetni({ kaynak: v.ad, dosya: v.dosya.name })}`, v.dosya, "text/csv"),
    onSuccess: (p) => {
      setBilgi(p.durum === "rejected" ? { ton: "amber", metin: c.reddedildi(p.id) } : { ton: "yesil", metin: c.yuklendi(p.id, p.satir) })
      setDosya(null)
      if (girdi.current) girdi.current.value = ""
      for (const k of [ANAHTAR.kaynaklar, ANAHTAR.partiler, ANAHTAR.akislar, ANAHTAR.ozet]) void qc.invalidateQueries({ queryKey: k })
      onYeniParti(p.id)
    },
    onError: (e) => setBilgi({ ton: "amber", metin: hataMesaji(e, t.islemBasarisiz) }),
  })
  return (
    <form
      className="grid gap-3 rounded-xl border border-slate-200 p-3"
      onSubmit={(e) => {
        e.preventDefault()
        if (!ad.trim() || !dosya) return setBilgi({ ton: "amber", metin: c.eksik })
        mut.mutate({ ad: ad.trim(), dosya })
      }}
    >
      <div>
        <h4 className="text-[0.6875rem] font-black uppercase tracking-widest text-tl-navy">{c.baslik}</h4>
        <p className="text-[0.6875rem] font-bold text-slate-400">{c.aciklama}</p>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <Alan etiket={c.kaynakAdi} ipucu={c.kaynakIpucu} sinif="max-w-64 flex-1">
          <input className={GIRDI} value={ad} maxLength={60} onChange={(e) => setAd(e.target.value)} />
        </Alan>
        <Alan etiket={c.dosya} sinif="max-w-72 flex-1">
          <input ref={girdi} type="file" accept=".csv,text/csv" className={GIRDI} onChange={(e) => setDosya(e.target.files?.[0] ?? null)} />
        </Alan>
        <button type="submit" className={DUGME_ANA} disabled={mut.isPending}>
          <Upload aria-hidden className="size-4" />
          {mut.isPending ? c.yukleniyor : c.yukle}
        </button>
      </div>
      {bilgi ? <Bildirim ton={bilgi.ton}>{bilgi.metin}</Bildirim> : null}
    </form>
  )
}
