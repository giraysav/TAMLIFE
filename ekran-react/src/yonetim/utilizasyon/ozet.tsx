import { useQuery } from "@tanstack/react-query"
import type { Dil } from "@/shell/metin"
import { Bos, HataKutu, Panel, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { YatayCubuklar } from "@/components/grafik"
import { ANAHTAR } from "@/yonetim/api"
import type { DagilimSatiri, SiralamaSatiri, SkorAgaci } from "@/yonetim/api"
import { oku } from "@/lib/sorgu"
import { ym } from "@/yonetim/metin"
import { Gosterge } from "@/yonetim/ui"
import { AGAC_YOLU, KaynakListesi, skorYaz, tumCatilar } from "@/yonetim/utilizasyon/ortak"

/** Ozet: gostergeler, TAM Utilizasyon siralamasi, personel agirlik ve dagilim, veri kaynaklari. Hicbir sey yazmaz. */
export function UtilOzet({ dil }: { dil: Dil }) {
  const t = ym(dil)
  const u = t.util
  const agac = useQuery({ queryKey: ANAHTAR.skorAgac, queryFn: () => oku<SkorAgaci>(AGAC_YOLU) })
  const siralama = useQuery({ queryKey: ANAHTAR.skorSiralama, queryFn: () => oku<SiralamaSatiri[]>("/api/v1/skor/siralama") })

  if (agac.isPending) return <Yukleniyor metin={t.yukleniyor} iskelet />
  if (agac.isError) return <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void agac.refetch()} />
  const a = agac.data
  const catilar = tumCatilar(a)
  const skorlu = catilar.filter((c) => c.mevcut)
  const ortalama = skorlu.length ? skorlu.reduce((top, c) => top + (c.mevcut ?? 0), 0) / skorlu.length : null
  const d = a.dagilim

  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Gosterge etiket={u.cati} deger={a.ozet.cati} alt={u.catiAlt(a.ozet.istirak, a.ozet.istirak_dahil)} />
        <Gosterge
          etiket={u.kriterTam}
          deger={`${a.ozet.hazir}/${a.ozet.cati}`}
          alt={u.kriterTamAlt}
          ton={a.ozet.cati > 0 && a.ozet.hazir === a.ozet.cati ? "ok" : "uyari"}
          href="#/yonetim/utilizasyon?sekme=atama"
        />
        <Gosterge etiket={u.skorlu} deger={skorlu.length} alt={u.skorluAlt(skorYaz(ortalama))} ton={skorlu.length ? "ok" : "uyari"} />
        <Gosterge etiket={u.hedefAgirlik} deger={d.ozet.hedef_agirlik} alt={u.hedefAlt(d.ozet.tam_sayisi, d.ozet.ortalama_musteri_puani)} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel baslik={u.siralama} aciklama={u.siralamaAciklama}>
          {siralama.isPending ? (
            <Yukleniyor metin={t.yukleniyor} />
          ) : siralama.isError ? (
            <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void siralama.refetch()} />
          ) : siralama.data.length === 0 ? (
            <Bos>{u.siralamaBos}</Bos>
          ) : (
            <YatayCubuklar
              seriler={[{ anahtar: "skor", ad: u.puan, renk: "#10b981" }]}
              satirlar={siralama.data.map((r) => ({
                anahtar: r.id,
                etiket: (
                  <>
                    {r.rank}. {r.full_name} <span className="text-slate-400">({u.musteriAdet(r.customer_count)})</span>
                  </>
                ),
                degerler: { skor: r.avg_score },
                sag: skorYaz(r.avg_score),
              }))}
            />
          )}
        </Panel>

        <Panel baslik={u.kaynaklar}>
          <KaynakListesi kaynaklar={a.kaynaklar} uyarilar={a.uyarilar} t={t} />
        </Panel>
      </div>

      <Panel baslik={u.dagilim} aciklama={u.dagilimAciklama}>
        <VeriTablosu<DagilimSatiri>
          baslik={u.dagilim}
          satirlar={d.satirlar}
          anahtar={(s) => s.id}
          bos={<Bos>{u.musteriYok}</Bos>}
          kolonlar={[
            { baslik: u.sira, hucre: (s) => <span className="font-mono">{s.sira}</span> },
            { baslik: u.personel, hucre: (s) => <span className="font-black text-tl-navy">{s.ad}</span> },
            { baslik: u.musteri, hucre: (s) => s.musteri_sayisi, sinif: "text-right font-mono" },
            { baslik: u.istirakli, hucre: (s) => s.istirakli_musteri, sinif: "text-right font-mono" },
            { baslik: u.skorlu, hucre: (s) => s.skorlu_musteri, sinif: "text-right font-mono" },
            { baslik: u.toplamPuan, hucre: (s) => s.toplam_puan, sinif: "text-right font-mono" },
            { baslik: u.agirlik, hucre: (s) => <span className="font-black text-tl-navy">{s.agirlik_puani ?? "—"}</span>, sinif: "text-right font-mono" },
            {
              baslik: u.hedefFarki,
              hucre: (s) => <span className={s.hedef_fark > 0 ? "text-rose-600" : s.hedef_fark < 0 ? "text-emerald-600" : ""}>{s.hedef_fark > 0 ? `+${s.hedef_fark}` : s.hedef_fark}</span>,
              sinif: "text-right font-mono",
            },
            { baslik: u.dengeleme, hucre: (s) => (s.dengeleme_musteri > 0 ? `+${s.dengeleme_musteri}` : s.dengeleme_musteri), sinif: "text-right font-mono" },
          ]}
        />
        <p className="mt-2 text-[0.6875rem] font-bold text-slate-400">
          {u.toplamPuan}: {d.ozet.toplam_puan} · {u.musteri}: {d.ozet.musteri_sayisi} · {u.skorlu}: {d.ozet.skorlu_musteri}
        </p>
      </Panel>
    </div>
  )
}
