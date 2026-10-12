import { useState } from "react"
import type { FormEvent, ReactNode } from "react"
import { Lock } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { Kullanici, Profil } from "@/lib/oturum"
import { hataMesaji, yaz } from "@/lib/sorgu"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

type Alan = "first_name" | "last_name" | "phone" | "company" | "address" | "website"
type Taslak = Record<Alan, string>

const ALANLAR: Alan[] = ["first_name", "last_name", "phone", "company", "address", "website"]

function taslaktan(p: Profil | undefined): Taslak {
  return { first_name: p?.first_name ?? "", last_name: p?.last_name ?? "", phone: p?.phone ?? "", company: p?.company ?? "", address: p?.address ?? "", website: p?.website ?? "" }
}

function AlanKutusu({ etiket, kimlik, sinif = "", children }: { etiket: string; kimlik: string; sinif?: string; children: ReactNode }) {
  return (
    <div className={`grid gap-1.5 ${sinif}`}>
      <Label htmlFor={kimlik}>{etiket}</Label>
      {children}
    </div>
  )
}

/**
 * Profil: personel kendi ad, soyad, telefon, sirket, adres ve web adresini duzenler. Yalniz AD/LDAP kullanici adi degistirilemez
 * (salt okunur, kilitli). Kaydedilince oturum yenilenir: sol alttaki hesap karti ve karsilama metni yeni adi gosterir.
 */
export function ProfilSayfasi({ kullanici, dil, onKaydedildi }: { kullanici: Kullanici; dil: Dil; onKaydedildi?: () => void }) {
  const t = metin(dil)
  const [taslak, setTaslak] = useState<Taslak>(() => taslaktan(kullanici.profile))
  const [kayitli, setKayitli] = useState<Taslak>(() => taslaktan(kullanici.profile))
  const [durum, setDurum] = useState<{ tur: "bos" | "kaydediliyor" | "tamam" | "hata"; metin: string }>({ tur: "bos", metin: "" })
  const degisti = ALANLAR.some((a) => taslak[a] !== kayitli[a])

  const etiketler: Record<Alan, string> = { first_name: t.profilAd, last_name: t.profilSoyad, phone: t.profilTelefon, company: t.profilSirket, address: t.profilAdres, website: t.profilWeb }
  const guncelle = (alan: Alan, deger: string) => {
    setTaslak((o) => ({ ...o, [alan]: deger }))
    setDurum({ tur: "bos", metin: "" })
  }

  async function kaydet(olay: FormEvent) {
    olay.preventDefault()
    setDurum({ tur: "kaydediliyor", metin: t.profilKaydediliyor })
    try {
      const sonuc = await yaz<Profil>("PUT", "/api/v1/session/profile", taslak)
      const yeni = taslaktan(sonuc)
      setTaslak(yeni)
      setKayitli(yeni)
      setDurum({ tur: "tamam", metin: t.profilKaydedildi })
      onKaydedildi?.()
    } catch (hata) {
      setDurum({ tur: "hata", metin: hataMesaji(hata, t.profilKaydedilemedi) })
    }
  }

  const hesap: [string, string][] = [
    [t.rol, t.rolEtiket[kullanici.role] ?? kullanici.role],
    [t.yetkiDuzeyi, kullanici.is_admin ? t.yonetici : t.standart],
    [t.erisilebilirModul, String(kullanici.navigation.length)],
    [t.bostaSure, `${kullanici.idle_timeout_minutes} ${t.dakika}`],
  ]

  return (
    <div className="grid max-w-3xl gap-4">
      <Card>
        <CardHeader>
          <CardTitle>{t.profil}</CardTitle>
          <CardDescription>{t.profilAciklama}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={(e) => void kaydet(e)} className="grid gap-4" aria-label={t.profil}>
            <AlanKutusu etiket={t.kullaniciAdi} kimlik="profil-kullanici-adi">
              <div className="relative">
                <Input id="profil-kullanici-adi" value={kullanici.username} readOnly disabled aria-describedby="profil-kullanici-adi-not" className="bg-muted/50 pr-9 font-mono" />
                <Lock aria-hidden className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              </div>
              <p id="profil-kullanici-adi-not" className="text-xs text-muted-foreground">
                {t.profilKullaniciAdiNot}
              </p>
            </AlanKutusu>
            <div className="grid gap-4 sm:grid-cols-2">
              {(["first_name", "last_name", "phone", "company"] as const).map((alan) => (
                <AlanKutusu key={alan} etiket={etiketler[alan]} kimlik={`profil-${alan}`}>
                  <Input
                    id={`profil-${alan}`}
                    value={taslak[alan]}
                    onChange={(e) => guncelle(alan, e.target.value)}
                    maxLength={alan === "company" ? 200 : alan === "phone" ? 40 : 100}
                    type={alan === "phone" ? "tel" : "text"}
                    autoComplete={alan === "first_name" ? "given-name" : alan === "last_name" ? "family-name" : alan === "phone" ? "tel" : "organization"}
                  />
                </AlanKutusu>
              ))}
              <AlanKutusu etiket={etiketler.website} kimlik="profil-website" sinif="sm:col-span-2">
                <Input id="profil-website" value={taslak.website} onChange={(e) => guncelle("website", e.target.value)} maxLength={200} inputMode="url" placeholder="https://" autoComplete="url" />
              </AlanKutusu>
              <AlanKutusu etiket={etiketler.address} kimlik="profil-address" sinif="sm:col-span-2">
                <textarea
                  id="profil-address"
                  value={taslak.address}
                  onChange={(e) => guncelle("address", e.target.value)}
                  maxLength={500}
                  rows={3}
                  autoComplete="street-address"
                  className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
                />
              </AlanKutusu>
            </div>
            <p className="text-xs text-muted-foreground">{t.profilNot}</p>
            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" disabled={!degisti || durum.tur === "kaydediliyor"}>
                {durum.tur === "kaydediliyor" ? t.profilKaydediliyor : t.profilKaydet}
              </Button>
              <span role="status" className={`text-sm ${durum.tur === "hata" ? "text-destructive" : "text-muted-foreground"}`}>
                {durum.tur === "kaydediliyor" ? "" : durum.metin}
              </span>
            </div>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.hesapBilgileri}</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-3 text-sm sm:grid-cols-[12rem_1fr]">
            {hesap.map(([ad, deger]) => (
              <div key={ad} className="contents">
                <dt className="text-muted-foreground">{ad}</dt>
                <dd className="font-medium">{deger}</dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>
    </div>
  )
}
