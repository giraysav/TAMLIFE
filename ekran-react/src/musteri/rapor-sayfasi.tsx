import { useQuery } from "@tanstack/react-query"
import { Halka, Lejant } from "@/components/grafik"
import { Rozet } from "@/components/sayfa-ui"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { oku } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"
import { musteriMetin } from "@/musteri/musteri-metin"

type Gonderim = { id: number; customer_id: number; musteri: string; yil: number; ay: number; gonderen: string; zaman: string; konu: string; durum: string }
type Durum = {
  yil: number
  ay: number
  satirlar: { id: number | null; ad: string; musteri: number; atilan: number; bekleyen: number; muaf: number }[]
  toplam: { musteri: number; atilan: number; bekleyen: number; muaf: number }
}

/** Gonderilen Aylik Rapor: bu ayin TAM basina atilan/bekleyen ozeti ve gorebildigi gonderimler. */
export function RaporSayfasi({ dil }: { dil: Dil }) {
  const t = musteriMetin(dil)
  const durumQ = useQuery({ queryKey: ["rapor", "durum"], queryFn: () => oku<Durum>("/api/v1/rapor/durum") })
  const listeQ = useQuery({ queryKey: ["rapor", "gonderilenler"], queryFn: () => oku<Gonderim[]>("/api/v1/rapor/gonderilenler") })
  const durum = durumQ.data
  const liste = listeQ.data ?? []
  const seriler = [
    { anahtar: "atilan", ad: t.atilan, renk: "#16a34a" },
    { anahtar: "bekleyen", ad: t.bekleyen, renk: "#f5c400" },
  ]

  if (durumQ.isPending) return <p className="text-sm text-muted-foreground">…</p>
  if (!durum) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t.yuklenemedi}
      </p>
    )
  }

  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {t.donem}: {t.aylar[durum.ay - 1]} / {durum.yil}
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4">
          {/* 2026-10-31 kullanici: gonderilen rapor sayisinin rapor birimi toplamina orani (muaflar toplama girmez) */}
          <div className="flex flex-wrap items-center gap-4">
            <Halka
              dilimler={seriler.map((s) => ({ ...s, deger: durum.toplam[s.anahtar as "atilan" | "bekleyen"] }))}
              baslik={`%${durum.toplam.musteri ? Math.round((durum.toplam.atilan / durum.toplam.musteri) * 100) : 0}`}
              alt={t.gonderimOrani}
              boyut={136}
              kalinlik={18}
            />
            <Lejant seriler={seriler} sayilar={durum.toplam} />
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th scope="col" className="py-2 font-medium">{t.sorumlu}</th>
                <th scope="col" className="py-2 text-right font-medium">{t.toplamBirim}</th>
                <th scope="col" className="py-2 text-right font-medium">{t.atilan}</th>
                <th scope="col" className="py-2 text-right font-medium">{t.bekleyen}</th>
                <th scope="col" className="py-2 text-right font-medium">{t.muaf}</th>
              </tr>
            </thead>
            <tbody>
              {durum.satirlar.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-4 text-center text-muted-foreground">
                    {t.sonucYok}
                  </td>
                </tr>
              ) : (
                durum.satirlar.map((s) => (
                  <tr key={s.id ?? s.ad} className="border-b last:border-0">
                    <td className="py-2">{s.ad}</td>
                    <td className="py-2 text-right tabular-nums">{s.musteri}</td>
                    <td className="py-2 text-right tabular-nums">{s.atilan}</td>
                    <td className="py-2 text-right tabular-nums">{s.bekleyen}</td>
                    <td className="py-2 text-right tabular-nums text-muted-foreground">{s.muaf}</td>
                  </tr>
                ))
              )}
            </tbody>
            <tfoot>
              <tr className="font-medium">
                <td className="py-2">{t.genelToplam}</td>
                <td className="py-2 text-right tabular-nums">{durum.toplam.musteri}</td>
                <td className="py-2 text-right tabular-nums">{durum.toplam.atilan}</td>
                <td className="py-2 text-right tabular-nums">{durum.toplam.bekleyen}</td>
                <td className="py-2 text-right tabular-nums text-muted-foreground">{durum.toplam.muaf}</td>
              </tr>
            </tfoot>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.gecmis}</CardTitle>
        </CardHeader>
        <CardContent>
          {liste.length === 0 ? <p className="text-sm text-muted-foreground">{t.gecmisYok}</p> : null}
          <ul className="grid gap-2 text-sm">
            {liste.map((g) => (
              <li key={g.id} className="flex flex-wrap items-center gap-2 border-b pb-2 last:border-0">
                <span className="tabular-nums">
                  {t.aylar[g.ay - 1]} / {g.yil}
                </span>
                <a className="font-medium underline-offset-4 hover:underline" href={`#/musteri?m=${g.customer_id}`}>
                  {g.musteri}
                </a>
                <span className="flex-1 text-muted-foreground">{g.konu}</span>
                <span className="text-muted-foreground">{g.gonderen}</span>
                {g.durum === "reverted" ? <Rozet>{t.geriAlindi}</Rozet> : null}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
