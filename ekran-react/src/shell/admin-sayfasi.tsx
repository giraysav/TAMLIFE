import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { apiGet } from "@/lib/oturum"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

type Yonetim = {
  connections: { id: string; slot: string; configured: boolean }[]
  data_management: { tables: string[]; note: string }
}

/** Yalniz yapilandirma durumu ve tablo adlari; gizli deger hic gelmez. */
export function AdminSayfasi({ dil }: { dil: Dil }) {
  const t = metin(dil)
  const [veri, setVeri] = useState<Yonetim | null | undefined>(undefined)

  useEffect(() => {
    let iptal = false
    void apiGet<Yonetim>("/api/v1/admin").then((govde) => {
      if (!iptal) setVeri(govde)
    })
    return () => {
      iptal = true
    }
  }, [])

  if (veri === undefined) return <p className="text-sm text-muted-foreground">{t.yukleniyor}</p>
  if (veri === null) return <p role="alert" className="text-sm text-destructive">{t.yuklenemedi}</p>

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>{t.baglantilar}</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="grid gap-2 text-sm">
            {veri.connections.map((b) => (
              <li key={b.id} className="flex items-center justify-between gap-2">
                <span className="font-medium">{b.slot}</span>
                <span className={b.configured ? "text-foreground" : "text-muted-foreground"}>
                  {b.configured ? t.ayarli : t.ayarsiz}
                </span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t.veriYonetimi}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          <ul className="flex flex-wrap gap-2">
            {veri.data_management.tables.map((ad) => (
              <li key={ad}>
                <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{ad}</code>
              </li>
            ))}
          </ul>
          <p className="text-sm text-muted-foreground">{veri.data_management.note}</p>
        </CardContent>
      </Card>
    </div>
  )
}
