import { LayoutDashboard } from "lucide-react"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { MenuOgesi } from "@/lib/oturum"
import { IKON } from "@/shell/ikon"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

/** Yonetim alanlari icin ayri sayfa: yalniz admin'e sunucunun verdigi yonetim ogeleri. */
export function YonetimSayfasi({ ogeler, dil, onGit }: { ogeler: MenuOgesi[]; dil: Dil; onGit: (id: string) => void }) {
  const t = metin(dil)
  if (ogeler.length === 0) return <p className="text-sm text-muted-foreground">{t.yetkisiz}</p>
  return (
    <div className="grid gap-4">
      <p className="text-sm text-muted-foreground">{t.yonetimAciklama}</p>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {ogeler.map((o) => {
          const Ikon = IKON[o.icon] ?? LayoutDashboard
          return (
            <a
              key={o.id}
              href={`#/${o.id}`}
              onClick={() => onGit(o.id)}
              className="rounded-xl focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Card className="h-full transition-colors hover:bg-accent">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Ikon aria-hidden className="size-4 text-muted-foreground" />
                    {o.label}
                  </CardTitle>
                  <CardDescription>{o.description}</CardDescription>
                </CardHeader>
              </Card>
            </a>
          )
        })}
      </div>
    </div>
  )
}
