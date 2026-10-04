import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { AltOge } from "@/lib/oturum"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

type Props = {
  baslik: string
  aciklama: string
  hazir: boolean
  ust?: string // alt modulde ana modulun adi
  altlar?: AltOge[]
  dil: Dil
  onGit: (id: string) => void
}

/** Modul ve alt modul ekranlari veri gecisi sirasinda tek tek bu kabugun icine eklenir. */
export function ModulSayfasi({ baslik, aciklama, hazir, ust, altlar, dil, onGit }: Props) {
  const t = metin(dil)
  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader>
          {ust ? <p className="text-xs text-muted-foreground">{ust}</p> : null}
          <CardTitle className="flex items-center gap-2">
            {baslik}
            {!hazir ? <Badge variant="secondary">{t.hazirlaniyor}</Badge> : null}
          </CardTitle>
          <CardDescription>{aciklama}</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">{hazir ? t.tasinacak : t.hazirlaniyorAciklama}</p>
        </CardContent>
      </Card>
      {altlar ? (
        <section aria-label={t.altModuller} className="grid gap-2">
          <h2 className="text-sm font-medium text-muted-foreground">{t.altModuller}</h2>
          {altlar.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t.altModulYok}</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {altlar.map((a) => (
                <a
                  key={a.id}
                  href={`#/${a.id}`}
                  onClick={() => onGit(a.id)}
                  className="rounded-xl focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <Card className="h-full transition-colors hover:bg-accent">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-base">
                        {a.label}
                        {!a.ready ? <Badge variant="secondary">{t.hazirlaniyor}</Badge> : null}
                      </CardTitle>
                      {a.description ? <CardDescription>{a.description}</CardDescription> : null}
                    </CardHeader>
                  </Card>
                </a>
              ))}
            </div>
          )}
        </section>
      ) : null}
    </div>
  )
}
