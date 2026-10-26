import { useRef, useState } from "react"
import type { FormEvent, ReactNode } from "react"
import { Camera, Lock, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { baslangicHarfleri } from "@/lib/bicim"
import { fotoAdresi, kareJpeg } from "@/lib/foto"
import type { Kullanici, Profil } from "@/lib/oturum"
import { hataMesaji, yaz, yukle } from "@/lib/sorgu"
import { ImzaEditoru } from "@/shell/imza-editoru"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

type Alan = "first_name" | "last_name" | "phone" | "company" | "website"
type Taslak = Record<Alan, string>

const ALANLAR: Alan[] = ["first_name", "last_name", "phone", "company", "website"]

function taslaktan(p: Profil | undefined): Taslak {
  return { first_name: p?.first_name ?? "", last_name: p?.last_name ?? "", phone: p?.phone ?? "", company: p?.company ?? "", website: p?.website ?? "" }
}

function AlanKutusu({ etiket, kimlik, sinif = "", children }: { etiket: string; kimlik: string; sinif?: string; children: ReactNode }) {
  return (
    <div className={`grid gap-1.5 ${sinif}`}>
      <Label htmlFor={kimlik}>{etiket}</Label>
      {children}
    </div>
  )
}

/** Profil fotografi: hesap kartindaki donen halkali dairenin aynisi; kisi fotografini secer (kare kirpilir, 256 px JPEG) ya da kaldirir. */
function ProfilFotografi({ kullanici, dil, onDegisti }: { kullanici: Kullanici; dil: Dil; onDegisti?: () => void }) {
  const t = metin(dil)
  const secici = useRef<HTMLInputElement>(null)
  const [surum, setSurum] = useState<number | null>(kullanici.profile?.photo_version ?? null)
  const [durum, setDurum] = useState<{ tur: "bos" | "calisiyor" | "tamam" | "hata"; metin: string }>({ tur: "bos", metin: "" })

  async function isle(is: () => Promise<{ photo_version: number | null }>, basari: string) {
    setDurum({ tur: "calisiyor", metin: "" })
    try {
      setSurum((await is()).photo_version)
      setDurum({ tur: "tamam", metin: basari })
      onDegisti?.()
    } catch (hata) {
      setDurum({ tur: "hata", metin: hataMesaji(hata, t.profilFotoHata) })
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t.profilFoto}</CardTitle>
        <CardDescription>{t.profilFotoAciklama}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-5">
        <span className="relative flex size-24 shrink-0 items-center justify-center">
          <span
            aria-hidden
            className="tl-hareket absolute inset-0 rounded-full"
            style={{ background: "conic-gradient(from 0deg, #ffc72c, #00a3e0, #ffc72c 60%, transparent 85%)", animation: "tl-donus 5s linear infinite" }}
          />
          {surum ? (
            <img src={fotoAdresi(surum)} alt={t.profilFoto} className="relative size-[5.25rem] rounded-full border-4 border-tl-navy bg-tl-navy object-cover" />
          ) : (
            <span className="relative flex size-[5.25rem] items-center justify-center rounded-full bg-tl-navy text-2xl font-black text-tl-yellow">{baslangicHarfleri(kullanici.display_name || kullanici.username)}</span>
          )}
        </span>
        <div className="grid gap-2">
          <input
            ref={secici}
            type="file"
            accept="image/*"
            className="sr-only"
            aria-label={t.profilFotoSec}
            onChange={(e) => {
              const dosya = e.target.files?.[0]
              e.target.value = ""
              if (dosya) void isle(async () => yukle<{ photo_version: number }>("/api/v1/session/photo", await kareJpeg(dosya), "image/jpeg"), t.profilFotoKaydedildi)
            }}
          />
          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={() => secici.current?.click()} disabled={durum.tur === "calisiyor"}>
              <Camera aria-hidden className="size-4" />
              {t.profilFotoSec}
            </Button>
            {surum ? (
              <Button type="button" variant="outline" onClick={() => void isle(() => yaz("DELETE", "/api/v1/session/photo"), t.profilFotoKaldirildi)} disabled={durum.tur === "calisiyor"}>
                <Trash2 aria-hidden className="size-4" />
                {t.profilFotoKaldir}
              </Button>
            ) : null}
          </div>
          <span role="status" className={`text-sm ${durum.tur === "hata" ? "text-destructive" : "text-muted-foreground"}`}>
            {durum.metin}
          </span>
        </div>
      </CardContent>
    </Card>
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

  const etiketler: Record<Alan, string> = { first_name: t.profilAd, last_name: t.profilSoyad, phone: t.profilTelefon, company: t.profilSirket, website: t.profilWeb }
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
      <ProfilFotografi kullanici={kullanici} dil={dil} onDegisti={onKaydedildi} />
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
      <ImzaEditoru dil={dil} />
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
