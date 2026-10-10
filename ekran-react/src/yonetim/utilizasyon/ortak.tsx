import { Bildirim, Rozet } from "@/components/sayfa-ui"
import type { AgacMusterisi, KaynakDurumu, KriterSonucu, SkorAgaci } from "@/yonetim/api"
import type { YM } from "@/yonetim/metin"

/** Utilizasyon alt bolumlerinin ortak parcalari. */

export const AGAC_YOLU = "/api/v1/skor/agac"

/** Final skor gosterimi (musteri kartiyla ayni: %70.0). */
export function skorYaz(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : `%${n.toFixed(1)}`
}

/** Metrik degeri: liste virgulle, sayi yerel bicimde. */
export function degerYaz(d: unknown): string {
  if (d === null || d === undefined || d === "") return "—"
  if (Array.isArray(d)) return d.length ? d.join(", ") : "—"
  if (typeof d === "number") return d.toLocaleString()
  return String(d)
}

/** Agactaki tum cati musteriler (personel altindakiler + atanmamis), ada gore. */
export function tumCatilar(agac: SkorAgaci): AgacMusterisi[] {
  const liste = [...agac.personel.flatMap((p) => p.musteriler), ...agac.atanmamis]
  return liste.sort((a, b) => a.ad.localeCompare(b.ad, "tr"))
}

/** Kaynak durumlari + hesap uyarilari (renk + metin). */
export function KaynakListesi({ kaynaklar, uyarilar, t }: { kaynaklar: KaynakDurumu[]; uyarilar: string[]; t: YM }) {
  const u = t.util
  return (
    <div className="grid gap-2">
      <p className="text-[11px] font-bold text-slate-400">{u.kaynaklarAciklama}</p>
      <ul className="grid gap-1.5">
        {kaynaklar.map((k) => (
          <li key={k.ad} className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-slate-100 py-1.5 text-xs last:border-0">
            <span className="w-24 shrink-0">
              <Rozet ton={k.hazir ? "yesil" : "gri"}>{k.hazir ? u.hazir : u.hazirDegil}</Rozet>
            </span>
            <span className="w-44 shrink-0 font-black text-tl-navy">{k.ad}</span>
            <span className="min-w-0 flex-1 break-words font-bold text-slate-500">
              {k.metrikler.join(", ") || "—"}
              {k.neden ? <span className="block text-[11px] text-slate-400">{k.neden}</span> : null}
            </span>
          </li>
        ))}
      </ul>
      {uyarilar.length > 0 ? (
        <Bildirim ton="amber">
          <span className="font-black">{u.uyarilar}: </span>
          {uyarilar.join(" · ")}
        </Bildirim>
      ) : null}
    </div>
  )
}

/** Tek musterinin kriter dokumu: puan, katki, deger, kaynak, durum. */
export function KriterDokumu({ kriterler, t }: { kriterler: KriterSonucu[]; t: YM }) {
  const u = t.util
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full text-left text-xs">
        <caption className="sr-only">{u.dokumAc}</caption>
        <thead className="bg-slate-50 text-[10px] uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="px-3 py-1.5 font-black">{u.kriter}</th>
            <th scope="col" className="px-3 py-1.5 text-right font-black">{u.agirlik}</th>
            <th scope="col" className="px-3 py-1.5 text-right font-black">{u.puan}</th>
            <th scope="col" className="px-3 py-1.5 text-right font-black">{u.katki}</th>
            <th scope="col" className="px-3 py-1.5 font-black">{u.deger}</th>
            <th scope="col" className="px-3 py-1.5 font-black">{u.kaynakKol}</th>
            <th scope="col" className="px-3 py-1.5 font-black">{u.durum}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {kriterler.map((k, i) => (
            <tr key={`${k.baslik}-${i}`}>
              <td className="px-3 py-1.5 font-black text-tl-navy">{k.baslik || k.tur}</td>
              <td className="px-3 py-1.5 text-right font-mono font-bold">{k.agirlik}</td>
              <td className="px-3 py-1.5 text-right font-mono font-black text-tl-navy">{k.puan}</td>
              <td className="px-3 py-1.5 text-right font-mono font-bold text-slate-500">{k.katki}</td>
              <td className="max-w-56 truncate px-3 py-1.5 font-bold text-slate-600" title={degerYaz(k.deger)}>
                {degerYaz(k.deger)}
              </td>
              <td className="px-3 py-1.5 font-bold text-slate-500">
                {k.kaynak ?? "—"}
                {k.varsayilan_kural ? <span className="ml-1 text-[10px] text-slate-400">({u.varsayilanKural})</span> : null}
              </td>
              <td className="px-3 py-1.5">
                <Rozet ton={k.durum === "eksik" ? "amber" : k.durum === "manuel" ? "gri" : "yesil"}>{u.durumEtiket[k.durum] ?? k.durum}</Rozet>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Tamam / Eksik rozeti. */
export function TamamRozeti({ tamam, eksik, t }: { tamam: boolean; eksik: string[]; t: YM }) {
  return tamam ? <Rozet ton="yesil">{t.util.tamam}</Rozet> : <Rozet ton="amber">{t.util.eksik(eksik.join(", ") || t.util.kriterYok)}</Rozet>
}
