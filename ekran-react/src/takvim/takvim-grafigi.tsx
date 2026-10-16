import { sayi } from "@/lib/bicim"
import { Lejant, Sutunlar } from "@/components/grafik"
import type { Seri } from "@/components/grafik"
import { DURUM_RENK, DURUM_SIRASI } from "@/takvim/takvim-metin"
import type { TakvimMetin } from "@/takvim/takvim-metin"

/** kayitli_gun sunucuda kalir (sunum bos/dolu denetimi), ekranda gosterilmez. is_gunu: yapilan is girilen gun sayisi. */
export type Ozet = { durumlar: Record<string, number>; online: number; yuzyuze: number; kayitli_gun: number; izin_gun: number; toplanti: number; is_gunu?: number }

export function durumSerileri(t: TakvimMetin): Seri[] {
  // 'calisiyor' yalniz kayitli (varsayilan olmayan) gunleri sayar; grafikte de gorunur
  return DURUM_SIRASI.map((k) => ({ anahtar: k, ad: t.durumlar[k] ?? k, renk: DURUM_RENK[k] ?? "#64748b" }))
}

/** TAM Takvim tablo sutunlari ve grafik kalemleri, kullanicinin sirasiyla (2026-10-15: is girilen gun, calisiyor, toplanti ve
 * raporlu kalkti; online / yuz yuze toplanti zaten calisma gunu sayilir). Yarim gun = arife. */
export function takvimKalemleri(t: TakvimMetin, o: Ozet): (Seri & { deger: number })[] {
  const durum = (k: string, ad: string) => ({ anahtar: k, ad, renk: DURUM_RENK[k] ?? "#64748b", deger: o.durumlar[k] ?? 0 })
  return [
    { anahtar: "online", ad: t.sutunOnline, renk: "#0055a5", deger: o.online },
    { anahtar: "yuzyuze", ad: t.sutunYuzyuze, renk: "#059669", deger: o.yuzyuze },
    durum("yillik_izin", t.sutunYillik),
    durum("sirket_izni", t.sutunSirket),
    durum("arife_tatili", t.sutunYarim),
    durum("resmi_tatil", t.sutunResmi),
  ]
}

/** Donem grafigi: tum personelin toplami, veri turu basina bir sutun ve sayili lejant (kisi listesi yok). Sunum modulu de ayni bilesenle cizer. */
export function TakvimGrafigi({ genel, t }: { genel: Ozet; t: TakvimMetin }) {
  const kalemler = takvimKalemleri(t, genel)
  return (
    <div className="grid max-w-3xl gap-3">
      <p className="text-xs font-bold text-slate-500">
        {t.toplamToplanti}: <span className="font-mono font-black text-tl-navy">{sayi(genel.toplanti)}</span> · {t.izinGunu}: <span className="font-mono font-black text-tl-navy">{sayi(genel.izin_gun)}</span>
      </p>
      <Sutunlar sutunlar={kalemler.map((k) => ({ etiket: k.ad, degerler: { [k.anahtar]: k.deger } }))} seriler={kalemler} yukseklik={128} />
      <Lejant seriler={kalemler} sayilar={Object.fromEntries(kalemler.map((k) => [k.anahtar, k.deger]))} />
    </div>
  )
}
