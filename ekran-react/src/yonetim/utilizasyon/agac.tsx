import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ChevronRight, Save } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Bildirim, Bos, DUGME_ANA, HataKutu, Panel, Rozet, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import type { AgacMusterisi, SkorAgaci } from "@/yonetim/api"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { AGAC_YOLU, KriterDokumu, TamamRozeti, skorYaz } from "@/yonetim/utilizasyon/ortak"
import { uym } from "@/yonetim/utilizasyon/metin"
import type { UYM } from "@/yonetim/utilizasyon/metin"

/** Skor agaci (uretim Skorlari Dagit): personel -> cati -> istirak; iştirak "finale dahil" secimi ve puanlamaya girecek personel. */
export function SkorAgaciBolumu({ dil }: { dil: Dil }) {
  const t = uym(dil)
  const u = t.util
  const qc = useQueryClient()
  const agac = useQuery({ queryKey: ANAHTAR.skorAgac, queryFn: () => oku<SkorAgaci>(AGAC_YOLU) })
  const [hata, setHata] = useState("")
  const yenile = () => {
    for (const anahtar of [ANAHTAR.skorAgac, ANAHTAR.skorSiralama, ["skor", "onizleme"]]) void qc.invalidateQueries({ queryKey: anahtar })
  }
  const dahil = useMutation({
    mutationFn: (v: { id: number; dahil: boolean }) => yaz<{ dahil: boolean }>("PUT", `/api/v1/skor/istirak/${v.id}/final-dahil`, { dahil: v.dahil }),
    onSuccess: () => {
      setHata("")
      yenile()
    },
    onError: (e) => setHata(hataMesaji(e, t.islemBasarisiz)),
  })

  if (agac.isPending) return <Yukleniyor metin={t.yukleniyor} iskelet />
  if (agac.isError) return <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void agac.refetch()} />
  const a = agac.data
  const musteriler = (liste: AgacMusterisi[]) =>
    liste.length === 0 ? (
      <Bos>{u.musteriYok}</Bos>
    ) : (
      <ul className="grid gap-1.5">
        {liste.map((m) => (
          <MusteriDugumu key={m.id} m={m} t={t} kilitli={dahil.isPending} onDahil={(id, evet) => dahil.mutate({ id, dahil: evet })} />
        ))}
      </ul>
    )

  return (
    <div className="grid gap-4">
      <p className="text-[0.6875rem] font-bold text-slate-400">{u.agacAciklama}</p>
      {hata ? <Bildirim ton="amber">{hata}</Bildirim> : null}
      {a.personel.map((p) => (
        <details key={p.id} className="group overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <summary className="flex cursor-pointer select-none list-none flex-wrap items-center gap-2 bg-slate-50/80 px-4 py-2.5 hover:bg-slate-100/80 [&::-webkit-details-marker]:hidden">
            <ChevronRight aria-hidden className="size-4 shrink-0 text-tl-navy/60 transition-transform group-open:rotate-90" />
            <span className="text-sm font-black text-tl-navy">{p.ad}</span>
            <Rozet ton={p.tam ? "sari" : "gri"}>{p.tam ? u.tamRozet : u.digerRozet}</Rozet>
            <span className="ml-auto flex flex-wrap gap-3 text-[0.6875rem] font-bold text-slate-500">
              <span>
                {u.musteri}: <b className="font-mono text-tl-navy">{p.musteri_sayisi}</b>
              </span>
              <span>
                {u.skorlu}: <b className="font-mono text-tl-navy">{p.skorlu_musteri}</b>
              </span>
              <span>
                {u.toplamPuan}: <b className="font-mono text-tl-navy">{p.toplam_puan}</b>
              </span>
              <span>
                {u.agirlik}: <b className="font-mono text-tl-navy">{p.agirlik_puani ?? "—"}</b>
              </span>
            </span>
          </summary>
          <div className="p-3">{musteriler(p.musteriler)}</div>
        </details>
      ))}
      <Panel baslik={u.atanmamis}>{musteriler(a.atanmamis)}</Panel>
      <PuanlamaPersoneli agac={a} t={t} onKaydedildi={yenile} />
    </div>
  )
}

function MusteriDugumu({ m, t, kilitli, onDahil }: { m: AgacMusterisi; t: UYM; kilitli: boolean; onDahil: (id: number, evet: boolean) => void }) {
  const u = t.util
  const [acik, setAcik] = useState(false)
  return (
    <li className="rounded-xl border border-slate-200 bg-white px-3 py-2">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <button type="button" className="font-black text-tl-navy underline-offset-2 hover:underline" aria-expanded={acik} onClick={() => setAcik(!acik)}>
          {m.ad}
        </button>
        <TamamRozeti tamam={m.tamam} eksik={m.eksik} t={t} />
        <span className="ml-auto flex gap-3 font-mono font-bold text-slate-500">
          <span>
            {u.mevcut} <b className="text-tl-navy">{skorYaz(m.mevcut)}</b>
          </span>
          <span>
            {u.hesap} <b className="text-tl-navy">{skorYaz(m.yeni)}</b>
          </span>
        </span>
      </div>
      {acik ? (
        <div className="mt-2">
          <KriterDokumu kriterler={m.kriterler} t={t} />
        </div>
      ) : null}
      {m.istirakler.length > 0 ? (
        <ul className="mt-2 grid gap-1 border-l-2 border-tl-yellow/60 pl-3">
          {m.istirakler.map((i) => (
            <li key={i.id} className="flex flex-wrap items-center gap-2 text-xs">
              <span className="font-bold text-slate-700">{i.ad}</span>
              <label className="inline-flex items-center gap-1 text-[0.6875rem] font-bold text-slate-500" title={u.finaleDahilIpucu}>
                <input type="checkbox" checked={i.dahil} disabled={kilitli} onChange={(e) => onDahil(i.id, e.target.checked)} />
                {u.finaleDahil}
              </label>
              {i.dahil ? (
                <>
                  <TamamRozeti tamam={Boolean(i.tamam)} eksik={i.eksik} t={t} />
                  <span className="ml-auto font-mono font-bold text-slate-500">
                    {u.hesap} <b className="text-tl-navy">{skorYaz(i.yeni)}</b>
                  </span>
                </>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  )
}

/** Puanlamaya girmeyen personel (uretim Final Skoru Atama > Personel filtresi). Liste tamamen degisir. */
function PuanlamaPersoneli({ agac, t, onKaydedildi }: { agac: SkorAgaci; t: UYM; onKaydedildi: () => void }) {
  const u = t.util
  const sunucu = new Set(agac.tum_personel.filter((p) => p.dahil).map((p) => p.id))
  const [dahil, setDahil] = useState<Set<number>>(sunucu)
  const [bilgi, setBilgi] = useState<{ ton: "yesil" | "amber"; metin: string } | null>(null)
  const anahtar = agac.tum_personel.map((p) => `${p.id}:${p.dahil}`).join(",")
  useEffect(() => {
    setDahil(new Set(agac.tum_personel.filter((p) => p.dahil).map((p) => p.id)))
  }, [anahtar]) // eslint-disable-line react-hooks/exhaustive-deps
  const kaydet = useMutation({
    mutationFn: () => yaz<{ disi: number[] }>("PUT", "/api/v1/skor/puanlama-disi", { disi: agac.tum_personel.filter((p) => !dahil.has(p.id)).map((p) => p.id) }),
    onSuccess: () => {
      setBilgi({ ton: "yesil", metin: u.puanlamaKaydedildi })
      onKaydedildi()
    },
    onError: (e) => setBilgi({ ton: "amber", metin: hataMesaji(e, t.islemBasarisiz) }),
  })
  const degisti = agac.tum_personel.some((p) => dahil.has(p.id) !== p.dahil)
  return (
    <Panel baslik={u.puanlamaDisi} aciklama={u.puanlamaDisiAciklama}>
      {agac.tum_personel.length === 0 ? (
        <Bos>{u.musteriYok}</Bos>
      ) : (
        <div className="grid gap-3">
          <div className="flex flex-wrap gap-2">
            {agac.tum_personel.map((p) => (
              <label key={p.id} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs font-bold text-slate-700">
                <input
                  type="checkbox"
                  checked={dahil.has(p.id)}
                  onChange={(e) =>
                    setDahil((once) => {
                      const yeni = new Set(once)
                      if (e.target.checked) yeni.add(p.id)
                      else yeni.delete(p.id)
                      return yeni
                    })
                  }
                />
                {p.ad}
                <span className="font-mono text-slate-400">{p.musteri_sayisi}</span>
                {!p.tam ? <Rozet>{u.digerRozet}</Rozet> : null}
              </label>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className={DUGME_ANA} disabled={!degisti || kaydet.isPending} onClick={() => kaydet.mutate()}>
              <Save aria-hidden className="size-4" />
              {t.kaydet}
            </button>
            {bilgi ? <Bildirim ton={bilgi.ton}>{bilgi.metin}</Bildirim> : null}
          </div>
        </div>
      )}
    </Panel>
  )
}
