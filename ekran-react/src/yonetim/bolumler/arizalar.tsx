import { useEffect, useState } from "react"
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import type { Dil } from "@/shell/metin"
import { Alan, Bildirim, Bolum, DUGME, DUGME_ANA, GIRDI, HataKutu, Rozet, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import { hataMesaji, oku, sorguMetni, yaz } from "@/lib/sorgu"
import type { Ariza, ArizaKodu, Sayfali } from "@/yonetim/api"
import { ym } from "@/yonetim/metin"
import { Sayfalama } from "@/yonetim/ui"
import { zaman } from "@/lib/bicim"

const ADET = 15
const DURUM_TON = { open: "kirmizi", ack: "amber", closed: "yesil" } as const

function Ayrinti({ dil, ariza, onGuncel }: { dil: Dil; ariza: Ariza; onGuncel: (a: Ariza) => void }) {
  const t = ym(dil)
  const qc = useQueryClient()
  const [durum, setDurum] = useState<string>(ariza.durum)
  const [notu, setNotu] = useState(ariza.not)
  const [bilgi, setBilgi] = useState<{ ton: "yesil" | "amber"; metin: string } | null>(null)

  const guncelle = useMutation({
    mutationFn: () => yaz<Ariza>("POST", `/api/v1/yonetim/arizalar/${ariza.id}/durum`, { durum, notu }),
    onSuccess: (a) => {
      onGuncel(a)
      setBilgi({ ton: "yesil", metin: t.arizaGuncellendi })
      void qc.invalidateQueries({ queryKey: ANAHTAR.arizalar })
      void qc.invalidateQueries({ queryKey: ANAHTAR.ozet })
    },
    onError: (e) => setBilgi({ ton: "amber", metin: hataMesaji(e, t.islemBasarisiz) }),
  })

  return (
    <div className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <code className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-black text-tl-navy">{ariza.kod}</code>
        <Rozet ton={ariza.seviye === "error" ? "kirmizi" : "amber"}>{t.seviyeler[ariza.seviye]}</Rozet>
        <Rozet ton={DURUM_TON[ariza.durum]}>{t.durumlar[ariza.durum]}</Rozet>
      </div>
      <dl className="grid gap-1.5 text-xs">
        {[
          [t.kayitNo, <code key="k">{ariza.kayit_no}</code>],
          [t.zaman, zaman(ariza.zaman)],
          [t.kaynakSutunu, ariza.kaynak || "—"],
          [t.kullanici, ariza.kullanici || "—"],
          [t.istisna, ariza.istisna || "—"],
          ...(ariza.kapanis ? [[t.kapatan, `${ariza.kapatan} · ${zaman(ariza.kapanis)}`]] : []),
        ].map(([e, d]) => (
          <div key={String(e)} className="flex justify-between gap-3 border-b border-slate-100 pb-1 last:border-0">
            <dt className="shrink-0 font-bold text-slate-400">{e}</dt>
            <dd className="min-w-0 break-all text-right font-bold text-slate-700">{d}</dd>
          </div>
        ))}
      </dl>
      <div>
        <p className="text-[10px] font-black uppercase tracking-wide text-slate-400">{t.mesaj}</p>
        <p className="mt-0.5 break-words text-xs font-bold text-slate-700">{ariza.mesaj || "—"}</p>
      </div>
      <div className="rounded-lg border border-tl-yellow/60 bg-tl-yellow/10 p-2">
        <p className="text-[10px] font-black uppercase tracking-wide text-tl-navy/70">{t.cozumAdimi}</p>
        <p className="mt-0.5 text-xs font-bold text-tl-navy">{ariza.cozum_adimi}</p>
      </div>
      <a className={`${DUGME} justify-self-start`} href={`#/yonetim/gunlukler${sorguMetni({ kayit: ariza.kayit_no.slice(0, 8) })}`}>
        {t.gunluktAra}
      </a>
      <form
        className="grid gap-2 border-t border-slate-100 pt-3"
        onSubmit={(e) => {
          e.preventDefault()
          setBilgi(null)
          guncelle.mutate()
        }}
      >
        <Alan etiket={t.durum}>
          <select className={GIRDI} value={durum} onChange={(e) => setDurum(e.target.value)}>
            {(["open", "ack", "closed"] as const).map((d) => (
              <option key={d} value={d}>
                {t.durumlar[d]}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t.notu}>
          <textarea className={`${GIRDI} min-h-16 font-normal`} maxLength={500} value={notu} onChange={(e) => setNotu(e.target.value)} />
        </Alan>
        <button type="submit" className={`${DUGME_ANA} justify-self-start`} disabled={guncelle.isPending}>
          {t.durumuGuncelle}
        </button>
        {bilgi ? <Bildirim ton={bilgi.ton}>{bilgi.metin}</Bildirim> : null}
      </form>
    </div>
  )
}

/** Arizalar: kod + kayit numarali hata kayitlari; liste solda, secilen kaydin ayrintisi ve durum islemleri sagda. */
export default function Arizalar({ dil }: { dil: Dil }) {
  const t = ym(dil)
  const [durum, setDurum] = useState("")
  const [seviye, setSeviye] = useState("")
  const [giris, setGiris] = useState("")
  const [q, setQ] = useState("")
  const [sayfa, setSayfa] = useState(1)
  const [secili, setSecili] = useState<Ariza | null>(null)

  useEffect(() => {
    const zamanlayici = window.setTimeout(() => {
      setQ(giris.trim())
      setSayfa(1)
    }, 300)
    return () => window.clearTimeout(zamanlayici)
  }, [giris])

  const filtre = { durum, seviye, q, sayfa, adet: ADET }
  const liste = useQuery({
    queryKey: [...ANAHTAR.arizalar, filtre],
    queryFn: () => oku<Sayfali<Ariza>>(`/api/v1/yonetim/arizalar${sorguMetni(filtre)}`),
    placeholderData: keepPreviousData,
  })
  const kodlar = useQuery({ queryKey: ANAHTAR.arizaKodlari, queryFn: () => oku<ArizaKodu[]>("/api/v1/yonetim/ariza-kodlari"), staleTime: Infinity })

  if (liste.isPending) return <Yukleniyor metin={t.yukleniyor} iskelet />
  if (liste.isError) return <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void liste.refetch()} />
  const d = liste.data

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <Alan etiket={t.durum}>
          <select
            className={GIRDI}
            value={durum}
            onChange={(e) => {
              setDurum(e.target.value)
              setSayfa(1)
            }}
          >
            <option value="">{t.hepsi}</option>
            {(["open", "ack", "closed"] as const).map((x) => (
              <option key={x} value={x}>
                {t.durumlar[x]}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t.seviye}>
          <select
            className={GIRDI}
            value={seviye}
            onChange={(e) => {
              setSeviye(e.target.value)
              setSayfa(1)
            }}
          >
            <option value="">{t.hepsi}</option>
            {(["error", "warning"] as const).map((x) => (
              <option key={x} value={x}>
                {t.seviyeler[x]}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t.ara} sinif="min-w-56 flex-1">
          <input className={GIRDI} placeholder={t.arizaAra} value={giris} onChange={(e) => setGiris(e.target.value)} />
        </Alan>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className={`grid content-start gap-3 lg:col-span-2 ${liste.isPlaceholderData ? "opacity-70" : ""}`}>
          <VeriTablosu<Ariza>
            baslik={t.bolumler.arizalar}
            satirlar={d.satirlar}
            anahtar={(a) => a.id}
            vurgulu={(a) => a.id === secili?.id}
            bos={<p className="text-xs font-bold text-slate-400">{t.arizaYok}</p>}
            kolonlar={[
              {
                baslik: t.kayitNo,
                hucre: (a) => (
                  <button type="button" aria-pressed={a.id === secili?.id} onClick={() => setSecili(a)} className="font-mono text-[11px] font-black text-tl-blue underline-offset-2 hover:underline focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow">
                    {a.kayit_no.slice(0, 8)}
                  </button>
                ),
              },
              { baslik: t.kod, hucre: (a) => <code className="text-[11px]">{a.kod}</code> },
              { baslik: t.durum, hucre: (a) => <Rozet ton={DURUM_TON[a.durum]}>{t.durumlar[a.durum]}</Rozet> },
              { baslik: t.zaman, hucre: (a) => zaman(a.zaman) },
              { baslik: t.kaynakSutunu, hucre: (a) => <span className="line-clamp-1 max-w-56 break-all">{a.kaynak || "—"}</span> },
            ]}
          />
          <Sayfalama t={t} sayfa={d.sayfa} adet={d.adet} toplam={d.toplam} onSayfa={setSayfa} />
        </div>
        <div className="lg:sticky lg:top-20 lg:self-start">
          {secili ? <Ayrinti key={secili.id} dil={dil} ariza={secili} onGuncel={setSecili} /> : <Bildirim>{t.arizaSec}</Bildirim>}
        </div>
      </div>

      <Bolum anahtar="yonetim-ariza-kodlari" baslik={t.hataKodlari} varsayilanAcik={false}>
        <ul className="grid gap-2">
          {(kodlar.data ?? []).map((k) => (
            <li key={k.kod} className="grid gap-0.5 border-b border-slate-100 pb-2 text-xs last:border-0">
              <span>
                <code className="mr-2 rounded bg-slate-100 px-1.5 py-0.5 font-black text-tl-navy">{k.kod}</code>
                <span className="font-black text-slate-700">{k.aciklama}</span>
              </span>
              <span className="font-bold text-slate-500">{k.cozum}</span>
            </li>
          ))}
        </ul>
      </Bolum>
    </div>
  )
}
