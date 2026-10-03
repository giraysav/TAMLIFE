import { useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { apiGet } from "@/lib/oturum"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

type Durum = {
  engine: string
  postgres: boolean
  postgres_ready: boolean
  note: string
  tables: { name: string; exists: boolean | null; rows: number | null }[]
  rows_note: string
}

/** Veri yonetimi kabugu: gercek veritabani durumu ve tablo varligi. Satir uretilmez. */
export function VeriSayfasi({ dil }: { dil: Dil }) {
  const t = metin(dil)
  const [veri, setVeri] = useState<Durum | null | undefined>(undefined)

  useEffect(() => {
    let iptal = false
    void apiGet<Durum>("/api/v1/veri").then((govde) => {
      if (!iptal) setVeri(govde)
    })
    return () => {
      iptal = true
    }
  }, [])

  if (veri === undefined) return <p className="text-sm text-muted-foreground">{t.yukleniyor}</p>
  if (veri === null) return <p role="alert" className="text-sm text-destructive">{t.yuklenemedi}</p>

  return (
    <div className="grid gap-4">
      {!veri.postgres_ready ? (
        <div role="status" className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm">
          <p className="font-medium">{t.postgresYok}</p>
          <p className="text-muted-foreground">{veri.note}</p>
        </div>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {t.veriYonetimi}
            <Badge variant={veri.postgres_ready ? "default" : "secondary"}>{veri.engine}</Badge>
          </CardTitle>
          <CardDescription>{veri.rows_note}</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="grid gap-2 text-sm">
            {veri.tables.map((tablo) => (
              <li key={tablo.name} className="flex items-center justify-between gap-2">
                <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{tablo.name}</code>
                <span className="text-muted-foreground">
                  {tablo.exists === null
                    ? t.dogrulanamadi
                    : tablo.exists
                      ? `${t.tabloVar} · ${tablo.rows ?? "—"} ${t.satir}`
                      : t.tabloYok}
                </span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
