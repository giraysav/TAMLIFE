import { useCallback, useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { apiOku } from "@/lib/api-yaz"
import type { Dil } from "@/shell/metin"
import { musteriMetin } from "@/shell/musteri-metin"

type Gonderim = { id: number; customer_id: number; musteri: string; yil: number; ay: number; gonderen: string; zaman: string; konu: string; durum: string }
type Durum = {
  yil: number
  ay: number
  satirlar: { id: number | null; ad: string; musteri: number; atilan: number; bekleyen: number }[]
  toplam: { musteri: number; atilan: number; bekleyen: number }
}

/** Gonderilen Aylik Rapor: bu ayin TAM basina atilan/bekleyen ozeti ve gorebildigi gonderimler. */
export function RaporSayfasi({ dil }: { dil: Dil }) {
  const t = musteriMetin(dil)
  const [durum, setDurum] = useState<Durum | null | undefined>(undefined)
  const [liste, setListe] = useState<Gonderim[]>([])

  const yukle = useCallback(async () => {
    const [d, g] = await Promise.all([apiOku<Durum>("/api/v1/rapor/durum"), apiOku<Gonderim[]>("/api/v1/rapor/gonderilenler")])
    setDurum(d.ok ? d.veri : null)
    setListe(g.ok && g.veri ? g.veri : [])
  }, [])

  useEffect(() => {
    void yukle()
  }, [yukle])

  if (durum === undefined) return <p className="text-sm text-muted-foreground">…</p>
  if (durum === null) {
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
            {t.donem}: {String(durum.ay).padStart(2, "0")}.{durum.yil}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th scope="col" className="py-2 font-medium">{t.sorumlu}</th>
                <th scope="col" className="py-2 text-right font-medium">{t.toplamBirim}</th>
                <th scope="col" className="py-2 text-right font-medium">{t.atilan}</th>
                <th scope="col" className="py-2 text-right font-medium">{t.bekleyen}</th>
              </tr>
            </thead>
            <tbody>
              {durum.satirlar.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-4 text-center text-muted-foreground">
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
                  {String(g.ay).padStart(2, "0")}.{g.yil}
                </span>
                <a className="font-medium underline-offset-4 hover:underline" href={`#/musteri?m=${g.customer_id}`}>
                  {g.musteri}
                </a>
                <span className="flex-1 text-muted-foreground">{g.konu}</span>
                <span className="text-muted-foreground">{g.gonderen}</span>
                {g.durum === "reverted" ? <Badge variant="secondary">{t.geriAlindi}</Badge> : null}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
