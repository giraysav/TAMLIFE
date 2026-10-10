import { sayi } from "@/lib/bicim"
import { Halka, Lejant, YatayCubuklar } from "@/components/grafik"
import type { Seri } from "@/components/grafik"
import { DURUM_RENK, DURUM_SIRASI } from "@/takvim/takvim-metin"
import type { TakvimMetin } from "@/takvim/takvim-metin"

export type Ozet = { durumlar: Record<string, number>; online: number; yuzyuze: number; kayitli_gun: number; izin_gun: number; toplanti: number }
export type GrafikUyesi = { ad: string } & Ozet

export function durumSerileri(t: TakvimMetin): Seri[] {
  // 'calisiyor' yalniz kayitli (varsayilan olmayan) gunleri sayar; grafikte de gorunur
  return DURUM_SIRASI.map((k) => ({ anahtar: k, ad: t.durumlar[k] ?? k, renk: DURUM_RENK[k] ?? "#64748b" }))
}

/** Donem grafigi: durum toplami (halka), kisi bazinda gun dagilimi ve toplantilar (yatay yigilmis cubuklar). Sunum modulu de ayni bilesenle cizer. */
export function TakvimGrafigi({ genel, uyeler, t }: { genel: Ozet; uyeler: GrafikUyesi[]; t: TakvimMetin }) {
  // Izin ve tatil gorunur olsun diye 'Calisiyor' (yalniz toplanti girilen gunler) grafikten cikarilir.
  const seriler = durumSerileri(t).filter((s) => s.anahtar !== "calisiyor")
  const izinToplam = seriler.reduce((a, s) => a + (genel.durumlar[s.anahtar] ?? 0), 0)
  const toplanti: Seri[] = [
    { anahtar: "online", ad: t.toplantiOnline, renk: "#0055a5" },
    { anahtar: "yuzyuze", ad: t.toplantiYuzYuze, renk: "#ffc72c" },
  ]
  return (
    <div className="grid gap-6 lg:grid-cols-[auto_1fr]">
      <div className="grid justify-items-center gap-3">
        <p className="text-[10px] font-black uppercase tracking-wide text-slate-400">{t.durumToplami}</p>
        <Halka
          dilimler={seriler.map((s) => ({ anahtar: s.anahtar, ad: s.ad, deger: genel.durumlar[s.anahtar] ?? 0, renk: s.renk }))}
          baslik={sayi(izinToplam)}
          alt={t.izinTatilGunu}
        />
        <Lejant seriler={seriler.filter((s) => (genel.durumlar[s.anahtar] ?? 0) > 0)} sayilar={genel.durumlar} />
      </div>
      <div className="grid gap-5">
        <div>
          <p className="mb-2 text-[10px] font-black uppercase tracking-wide text-slate-400">{t.kisiBazinda}</p>
          <YatayCubuklar satirlar={uyeler.map((u) => ({ anahtar: u.ad, etiket: u.ad, degerler: u.durumlar, sag: sayi(u.izin_gun) }))} seriler={seriler} yukseklik={12} />
        </div>
        <div>
          <p className="mb-2 text-[10px] font-black uppercase tracking-wide text-slate-400">{t.toplantilar}</p>
          <YatayCubuklar
            satirlar={uyeler.map((u) => ({ anahtar: u.ad, etiket: u.ad, degerler: { online: u.online, yuzyuze: u.yuzyuze }, sag: `${u.online} / ${u.yuzyuze}` }))}
            seriler={toplanti}
            yukseklik={12}
          />
          <div className="mt-2">
            <Lejant seriler={toplanti} />
          </div>
        </div>
      </div>
    </div>
  )
}
