import { useQuery } from "@tanstack/react-query"
import { CircleCheck, CircleX, RefreshCw, TriangleAlert } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Bolum, DUGME, HataKutu, Rozet, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import { oku } from "@/lib/sorgu"
import type { Durum3, Ozet } from "@/yonetim/api"
import { ym } from "@/yonetim/metin"
import { DurumRozeti, Gosterge } from "@/yonetim/ui"
import { zaman, bayt } from "@/lib/bicim"

const BANT = {
  ok: { sinif: "border-emerald-200 bg-emerald-50 text-emerald-800", ikon: CircleCheck },
  uyari: { sinif: "border-amber-200 bg-amber-50 text-amber-800", ikon: TriangleAlert },
  hata: { sinif: "border-rose-200 bg-rose-50 text-rose-800", ikon: CircleX },
} as const

/** Genel Durum: tek istekte saglik kontrolleri + gostergeler + baglanti yuvalari. Sekme gorunurken 30 sn'de bir tazelenir. */
export default function Durum({ dil }: { dil: Dil }) {
  const t = ym(dil)
  const q = useQuery({ queryKey: ANAHTAR.ozet, queryFn: () => oku<Ozet>("/api/v1/yonetim/ozet"), refetchInterval: 30_000 })

  if (q.isPending) return <Yukleniyor metin={t.yukleniyor} iskelet />
  if (q.isError) return <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void q.refetch()} />
  const { saglik, gostergeler: g, baglantilar } = q.data
  const bant = BANT[saglik.genel as Durum3]
  const Ikon = bant.ikon

  return (
    <div className="grid gap-4">
      <div role="status" className={`flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 ${bant.sinif}`}>
        <Ikon aria-hidden className="size-5 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-black">{t.genel[saglik.genel]}</p>
          <p className="text-[11px] font-bold opacity-80">
            {t.sonKontrol}: {zaman(saglik.zaman)}
          </p>
        </div>
        <button type="button" className={DUGME} onClick={() => void q.refetch()} disabled={q.isFetching}>
          <RefreshCw aria-hidden className={`size-3.5 ${q.isFetching ? "animate-spin" : ""}`} />
          {t.simdiKontrolEt}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Gosterge
          etiket={t.gosterge.veritabani}
          deger={g.veritabani.motor.toUpperCase()}
          alt={`${bayt(g.veritabani.boyut_bayt)} · ${g.veritabani.surum ?? t.semaYok}`}
          ton={g.veritabani.surum_uyumlu === false ? "uyari" : "ok"}
          href="#/yonetim/veritabani"
        />
        <Gosterge
          etiket={t.gosterge.ariza}
          deger={g.ariza.acik}
          alt={t.gostergeAlt.ariza(g.ariza.son_24s)}
          ton={g.ariza.acik === 0 ? "ok" : g.ariza.son_24s_hata > 0 ? "hata" : "uyari"}
          href="#/yonetim/arizalar"
        />
        <Gosterge
          etiket={t.gosterge.gunluk}
          deger={g.gunluk.son_24s}
          alt={t.gostergeAlt.gunluk(g.gunluk.red_24s)}
          ton={g.gunluk.red_24s > 0 ? "uyari" : "ok"}
          href="#/yonetim/gunlukler"
        />
        <Gosterge
          etiket={t.gosterge.tampon}
          deger={g.tampon.hazir_parti}
          alt={t.gostergeAlt.tampon(g.tampon.kural_etkin, g.tampon.kural)}
          href="#/yonetim/tampon"
        />
      </div>

      <Bolum anahtar="yonetim-durum-kontroller" baslik={t.saglikKontrolleri}>
        <ul className="grid gap-1.5">
          {saglik.kontroller.map((k) => (
            <li key={k.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-slate-100 py-1.5 text-xs last:border-0">
              <span className="w-24 shrink-0">
                <DurumRozeti durum={k.durum} t={t} />
              </span>
              <span className="w-44 shrink-0 font-black text-tl-navy">{t.kontrolAdi[k.id] ?? k.id}</span>
              <span className="min-w-0 flex-1 break-words font-bold text-slate-500">{k.ayrinti}</span>
            </li>
          ))}
        </ul>
      </Bolum>

      <Bolum anahtar="yonetim-durum-baglantilar" baslik={t.baglantilar}>
        <ul className="flex flex-wrap gap-2">
          {baglantilar.map((b) => (
            <li key={b.id}>
              <Rozet ton={b.configured ? "yesil" : "gri"}>
                {b.slot} · {b.configured ? t.ayarli : t.ayarsiz}
              </Rozet>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-[11px] font-bold text-slate-400">{t.baglantiNotu}</p>
      </Bolum>
    </div>
  )
}
