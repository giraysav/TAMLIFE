import { useEffect, useState } from "react"
import { LayoutDashboard } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { apiGet } from "@/lib/oturum"
import type { MenuOgesi } from "@/lib/oturum"
import { IKON } from "@/shell/ikon"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

type Kart = { key: string; title: string }

/** Ana sayfa kartlari: sunucudaki ANA_SAYFA sirasi (/home). Aciklama ve ikon menu verisinden gelir. */
export function AnaKartlar({ ogeler, dil, onGit }: { ogeler: MenuOgesi[]; dil: Dil; onGit: (id: string) => void }) {
  const t = metin(dil)
  const [kartlar, setKartlar] = useState<Kart[] | null>(null)

  useEffect(() => {
    let iptal = false
    void apiGet<Kart[]>("/api/v1/home").then((govde) => {
      if (!iptal) setKartlar(govde ?? [])
    })
    return () => {
      iptal = true
    }
  }, [])

  if (kartlar === null) return null
  const bul = (key: string) => ogeler.find((o) => o.id === key)

  return (
    <section aria-label={t.moduller}>
      <h2 className="mb-3 text-sm font-medium text-muted-foreground">{t.moduller}</h2>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {kartlar.map((kart) => {
          const oge = bul(kart.key)
          const Ikon = (oge && IKON[oge.icon]) || LayoutDashboard
          return (
            <a
              key={kart.key}
              href={`#/${kart.key}`}
              onClick={() => onGit(kart.key)}
              className="rounded-xl focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Card className="h-full transition-colors hover:bg-accent">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Ikon aria-hidden className="size-4 text-muted-foreground" />
                    {kart.title}
                    {oge && !oge.ready ? <Badge variant="secondary">{t.hazirlaniyor}</Badge> : null}
                  </CardTitle>
                  {oge ? <CardDescription>{oge.description}</CardDescription> : null}
                </CardHeader>
              </Card>
            </a>
          )
        })}
      </div>
    </section>
  )
}
