import { useEffect, useState } from "react"
import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { Briefcase, Building2, ChevronLeft, ChevronRight, CircleAlert, MessageSquareWarning, Plus, Search, SearchX, Siren, Sparkles, X } from "lucide-react"
import { Cekmece } from "@/components/cekmece"
import { BosKutu, DUGME, DUGME_SARI, GIRDI, HataKutu, Kpi, SayfaKabi } from "@/components/sayfa-ui"
import { Skeleton } from "@/components/ui/skeleton"
import { adaGoreSirala, sayi } from "@/lib/bicim"
import { oku, sorguMetni } from "@/lib/sorgu"
import { MusteriEkleFormu } from "@/musteri/musteri-ekle-formu"
import { MusteriKarti } from "@/musteri/portfoy-kart"
import type { PortfoyKart, Secenekler } from "@/musteri/portfoy-kart"
import { portfoyMetin } from "@/musteri/portfoy-metin"
import { useGecikmeli } from "@/lib/kanca"
import type { Dil } from "@/shell/metin"
import { hashParcala } from "@/shell/rota"
import { useMusteriYolu } from "@/musteri/musteri-yolu"

type Portfoy = {
  items: PortfoyKart[]
  ozet: { cati: number; istirak: number; alarm: number; sikayet: number; talep: number; ortalama_skor: number | null; skorlu: number }
  total: number
  page: number
  pages: number
}

const SAYFA_ADEDI = 24

/** Musteri Yonetimi portfoyu: cati musteri kartlari, KPI seridi, segment/TAM/arama filtreleri, sagdan acilan "Musteri ekle" formu. */
export function MusteriListesi({ dil, yazabilir }: { dil: Dil; yazabilir: boolean }) {
  const t = portfoyMetin(dil)
  const yol = useMusteriYolu()
  const ilkSorgu = hashParcala().sorgu
  const [arama, setArama] = useState(() => ilkSorgu.get("q") ?? "")
  const [segment, setSegment] = useState(() => ilkSorgu.get("segment") ?? "")
  const [tam, setTam] = useState(() => ilkSorgu.get("tam") ?? "")
  const [sayfa, setSayfa] = useState(1)
  const [formAcik, setFormAcik] = useState(false)
  const q = useGecikmeli(arama.trim())

  useEffect(() => setSayfa(1), [q, segment, tam])
  useEffect(() => {
    const params = new URLSearchParams()
    if (arama.trim()) params.set("q", arama.trim())
    if (segment) params.set("segment", segment)
    if (tam) params.set("tam", tam)
    const sorguMetni = params.toString()
    const hedef = `#/${yol}${sorguMetni ? `?${sorguMetni}` : ""}`
    if (window.location.hash !== hedef) window.history.replaceState(window.history.state, "", hedef)
  }, [arama, segment, tam, yol])

  const sorgu = { q, segment, tam, page: sayfa, per_page: SAYFA_ADEDI }
  const portfoy = useQuery({
    queryKey: ["musteri", "portfoy", sorgu],
    queryFn: () => oku<Portfoy>(`/api/v1/musteri/portfoy${sorguMetni(sorgu)}`),
    placeholderData: keepPreviousData,
  })
  const secenek = useQuery({ queryKey: ["musteri", "secenekler"], queryFn: () => oku<Secenekler>("/api/v1/musteri/secenekler") })

  const veri = portfoy.data
  const tamSecenekleri = adaGoreSirala(secenek.data?.tam ?? [], (k) => k.ad)
  const filtreVar = Boolean(q || segment || tam)
  const ozet = veri?.ozet

  return (
    <div className="grid grid-cols-1 gap-4">
      <SayfaKabi ikon={Briefcase} baslik={t.baslik} aciklama={t.aciklama}>
        {yazabilir ? (
          <button type="button" className={DUGME_SARI} onClick={() => setFormAcik(true)} disabled={!secenek.data}>
            <Plus aria-hidden className="size-4" />
            {t.musteriEkle}
          </button>
        ) : null}
      </SayfaKabi>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi etiket={t.kpiCati} deger={sayi(ozet?.cati)} ikon={Building2} ton="mavi" />
        <Kpi etiket={t.kpiIstirak} deger={sayi(ozet?.istirak)} ikon={Sparkles} ton="sari" />
        <Kpi etiket={t.kpiAlarm} deger={sayi(ozet?.alarm)} ikon={Siren} ton="kirmizi" />
        <Kpi etiket={t.kpiSikayet} deger={sayi(ozet?.sikayet)} ikon={MessageSquareWarning} ton="amber" />
        <Kpi etiket={t.kpiTalep} deger={sayi(ozet?.talep)} ikon={CircleAlert} ton="mavi" />
        <Kpi etiket={t.kpiSkor} deger={ozet?.ortalama_skor != null ? `%${ozet.ortalama_skor}` : "—"} alt={ozet ? t.kpiSkorAlt(ozet.skorlu) : undefined} ton="yesil" />
      </div>

      <div className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
        <div className="flex flex-wrap items-center gap-3">
          <label className="relative min-w-56 flex-1">
            <span className="sr-only">{t.ara}</span>
            <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
            <input type="search" value={arama} onChange={(e) => setArama(e.target.value)} placeholder={t.ara} maxLength={100} className={`${GIRDI} !py-2.5 pl-9`} />
          </label>
          {secenek.data?.yonetici && tamSecenekleri.length > 1 ? (
            <label className="grid gap-0.5">
              <span className="sr-only">{t.tam}</span>
              <select value={tam} onChange={(e) => setTam(e.target.value)} className={`${GIRDI} !w-auto min-w-44 !py-2.5`}>
                <option value="">{t.tumTam}</option>
                {tamSecenekleri.map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.ad}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {filtreVar ? (
            <button
              type="button"
              className={DUGME}
              onClick={() => {
                setArama("")
                setSegment("")
                setTam("")
              }}
            >
              <X aria-hidden className="size-3.5" />
              {t.temizle}
            </button>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t.segment}>
          {["", ...(secenek.data?.segmentler ?? ["SMB", "SA", "MA", "PA", "WHOLESALE"])].map((s) => (
            <button
              key={s || "tumu"}
              type="button"
              aria-pressed={segment === s}
              onClick={() => setSegment(s)}
              className={`rounded-full border px-3.5 py-1.5 text-xs font-black transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow ${
                segment === s ? "border-tl-navy bg-tl-navy text-tl-yellow" : "border-slate-200 bg-white text-slate-600 hover:border-tl-blue/40 hover:bg-slate-50"
              }`}
            >
              {s || t.tumu}
            </button>
          ))}
          {veri ? <span className="ml-auto text-xs font-bold text-slate-400">{t.toplam(veri.total)}</span> : null}
        </div>
      </div>

      {portfoy.isPending ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4" aria-hidden>
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton key={i} className="h-52 rounded-2xl" />
          ))}
        </div>
      ) : portfoy.isError ? (
        <HataKutu metin={t.yuklenemedi} tekrar={() => void portfoy.refetch()} tekrarEtiket={t.tekrar} />
      ) : veri && veri.items.length === 0 ? (
        <BosKutu ikon={filtreVar ? SearchX : Briefcase} baslik={filtreVar ? t.sonucYok : t.hicMusteri} aciklama={filtreVar ? t.sonucYokAlt : t.hicMusteriAlt} />
      ) : veri ? (
        <div className={`grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 ${portfoy.isPlaceholderData ? "opacity-60" : ""}`}>
          {veri.items.map((m) => (
            <MusteriKarti key={m.id} m={m} dil={dil} />
          ))}
        </div>
      ) : null}

      {veri && veri.pages > 1 ? (
        <nav aria-label={t.sayfalama} className="flex items-center justify-center gap-3">
          <button type="button" className={DUGME} disabled={veri.page <= 1} onClick={() => setSayfa((s) => s - 1)}>
            <ChevronLeft aria-hidden className="size-4" />
            {t.onceki}
          </button>
          <span className="text-xs font-bold text-slate-500">{t.sayfa(veri.page, veri.pages)}</span>
          <button type="button" className={DUGME} disabled={veri.page >= veri.pages} onClick={() => setSayfa((s) => s + 1)}>
            {t.sonraki}
            <ChevronRight aria-hidden className="size-4" />
          </button>
        </nav>
      ) : null}

      {yazabilir ? (
        <Cekmece acik={formAcik} onKapat={() => setFormAcik(false)} baslik={t.formBaslik} aciklama={t.formAciklama} kapatEtiketi={t.kapat}>
          {secenek.data ? <MusteriEkleFormu dil={dil} secenek={secenek.data} onBitti={() => setFormAcik(false)} /> : null}
        </Cekmece>
      ) : null}
    </div>
  )
}
