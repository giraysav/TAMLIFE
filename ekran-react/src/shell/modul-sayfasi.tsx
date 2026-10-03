import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { MenuOgesi } from "@/lib/oturum"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

/** Modul ekranlari veri gecisi sirasinda tek tek bu kabugun icine eklenir. */
export function ModulSayfasi({ oge, dil }: { oge: MenuOgesi; dil: Dil }) {
  const t = metin(dil)
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {oge.label}
          {!oge.ready ? <Badge variant="secondary">{t.hazirlaniyor}</Badge> : null}
        </CardTitle>
        <CardDescription>{oge.description}</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">{oge.ready ? t.tasinacak : t.hazirlaniyorAciklama}</p>
      </CardContent>
    </Card>
  )
}
