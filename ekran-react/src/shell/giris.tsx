import { useState } from "react"
import type { FormEvent } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { GirisSonucu } from "@/lib/oturum"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

// 2026-11-18 canli: giris ekrani yeniden tasarlandi (arka plan gorseli, logo, Keyflow yetki talebi, tanitim PDF'i).
// Bu metinler canlida her iki dilde de Turkce gorunur; oyle birakildi.
const YETKI_YOK = "Giriş Yetkiniz Bulunmamaktadır. Yetki Talep Ediniz."
const KEYFLOW_ADRESI =
  "https://keyflow.turkcell.com.tr/SmartScreen/Instance/KYF_TCELL_URT_GENERIC_ENT?UG=APPLICATION&APP=URT_GENERIC_AD&APPGR=&APPID=473321"
const KEYFLOW_ETIKETI = "Keyflow Yetki Talebi"
const TANITIM_ETIKETI = "Tamlife Tanıtım"
const GIRIS_NOTU =
  "Panele giriş yalnızca yetkili rol ile yapılır. Rolünüz yoksa Tamlife Tanıtım dosyasını indirip panelin modülleri hakkında bilgi alabilirsiniz."

type Props = {
  dil: Dil
  giris: (ad: string, parola: string) => Promise<GirisSonucu>
}

export function Giris({ dil, giris }: Props) {
  const t = metin(dil)
  const [ad, setAd] = useState("")
  const [parola, setParola] = useState("")
  const [hata, setHata] = useState<string | null>(null)
  const [bekliyor, setBekliyor] = useState(false)

  async function gonder(olay: FormEvent<HTMLFormElement>) {
    olay.preventDefault()
    setHata(null)
    setBekliyor(true)
    const sonuc = await giris(ad, parola)
    setBekliyor(false)
    setParola("")
    if (sonuc === "ok") return
    setHata(sonuc === "kilit" ? t.girisKilit : sonuc === "ag" ? t.girisAg : sonuc === "yetki" ? YETKI_YOK : t.girisRed)
  }

  return (
    <main className="giris-sahne">
      <div className="giris-cerceve">
        <img src="/assets/giris-arka.jpg" alt="" aria-hidden className="giris-gorsel" />
        <div className="giris-kutu">
          <form
            onSubmit={gonder}
            aria-label={t.giris}
            className="giris-form flex w-full max-w-sm flex-col gap-4 rounded-xl border bg-card p-6 shadow-xs"
          >
            <div>
              <h1 className="giris-baslik">
                <img src="/assets/tamlife-logo.png" alt="TAM.Life" className="giris-logo" />
              </h1>
              <p className="text-sm text-muted-foreground">{t.girisAciklama}</p>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="kullanici-adi">{t.kullaniciAdi}</Label>
              <Input
                id="kullanici-adi"
                name="username"
                autoComplete="username"
                autoFocus
                required
                maxLength={64}
                value={ad}
                onChange={(e) => setAd(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="parola">{t.parola}</Label>
              <Input
                id="parola"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                maxLength={256}
                value={parola}
                onChange={(e) => setParola(e.target.value)}
              />
            </div>
            {hata ? (
              <p role="alert" className="text-sm text-destructive">
                {hata}
              </p>
            ) : null}
            <Button type="submit" disabled={bekliyor} className="w-full">
              {t.giris}
            </Button>
            <a
              href={KEYFLOW_ADRESI}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex h-9 w-full items-center justify-center rounded-md border border-input bg-background px-4 text-sm font-medium shadow-xs transition-colors hover:bg-accent focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
            >
              {KEYFLOW_ETIKETI}
            </a>
            <a href="/assets/tamlife-tanitim.pdf" download="TAMLife-Tanitim.pdf" className="giris-misafir">
              {TANITIM_ETIKETI}
            </a>
            <p className="giris-not">{GIRIS_NOTU}</p>
          </form>
        </div>
      </div>
    </main>
  )
}
