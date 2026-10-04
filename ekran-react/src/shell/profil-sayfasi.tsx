import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { Kullanici } from "@/lib/oturum"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

/** Oturumdaki personelin bilgileri. Yalniz sunucunun verdigi alanlar; olmayan alan uydurulmaz. */
export function ProfilSayfasi({ kullanici, dil }: { kullanici: Kullanici; dil: Dil }) {
  const t = metin(dil)
  const satirlar: [string, string][] = [
    [t.kullaniciAdi, kullanici.username],
    [t.rol, kullanici.role],
    [t.yetkiDuzeyi, kullanici.is_admin ? t.yonetici : t.standart],
    [t.erisilebilirModul, String(kullanici.navigation.length)],
    [t.bostaSure, `${kullanici.idle_timeout_minutes} ${t.dakika}`],
  ]
  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>{t.profil}</CardTitle>
        <CardDescription>{t.profilAciklama}</CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-3 text-sm sm:grid-cols-[12rem_1fr]">
          {satirlar.map(([ad, deger]) => (
            <div key={ad} className="contents">
              <dt className="text-muted-foreground">{ad}</dt>
              <dd className="font-medium">{deger}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 text-xs text-muted-foreground">{t.profilNot}</p>
      </CardContent>
    </Card>
  )
}
