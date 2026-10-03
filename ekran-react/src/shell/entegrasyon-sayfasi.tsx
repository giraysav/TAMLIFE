import { useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { apiGet } from "@/lib/oturum"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

type Satir = {
  id: string
  label: string
  state: "ready" | "disabled" | "incomplete"
  description: string
  missing: string[]
}
type Veri = { items: Satir[]; runtime: { network: string; assets: string } }

/** Yalniz durum ve eksik anahtar adlari. Deger sunucuda bile okunmaz. */
export function EntegrasyonSayfasi({ dil }: { dil: Dil }) {
  const t = metin(dil)
  const [veri, setVeri] = useState<Veri | null | undefined>(undefined)

  useEffect(() => {
    let iptal = false
    void apiGet<Veri>("/api/v1/integrations").then((govde) => {
      if (!iptal) setVeri(govde)
    })
    return () => {
      iptal = true
    }
  }, [])

  if (veri === undefined) return <p className="text-sm text-muted-foreground">{t.yukleniyor}</p>
  if (veri === null) return <p role="alert" className="text-sm text-destructive">{t.yuklenemedi}</p>

  const etiket = { ready: t.durumHazir, disabled: t.durumKapali, incomplete: t.durumEksik } as const
  const ton = { ready: "default", disabled: "secondary", incomplete: "destructive" } as const

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {veri.items.map((s) => (
        <Card key={s.id}>
          <CardHeader>
            <CardTitle className="flex items-center justify-between gap-2 text-base">
              {s.label}
              <Badge variant={ton[s.state]}>{etiket[s.state]}</Badge>
            </CardTitle>
            <CardDescription>{s.description}</CardDescription>
          </CardHeader>
          {s.missing.length > 0 ? (
            <CardContent>
              <p className="mb-2 text-xs text-muted-foreground">{t.eksikAnahtar}</p>
              <ul className="flex flex-wrap gap-1.5">
                {s.missing.map((ad) => (
                  <li key={ad}>
                    <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{ad}</code>
                  </li>
                ))}
              </ul>
            </CardContent>
          ) : null}
        </Card>
      ))}
      <p className="text-xs text-muted-foreground md:col-span-2">
        {t.aglar}: {veri.runtime.network}
      </p>
    </div>
  )
}
