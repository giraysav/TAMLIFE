import { useState } from "react"
import type { FormEvent } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { GirisSonucu } from "@/lib/oturum"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

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
    setHata(sonuc === "kilit" ? t.girisKilit : sonuc === "ag" ? t.girisAg : t.girisRed)
  }

  return (
    <main className="flex min-h-dvh w-full items-center justify-center bg-background p-4">
      <form
        onSubmit={gonder}
        aria-label={t.giris}
        className="flex w-full max-w-sm flex-col gap-4 rounded-xl border bg-card p-6 shadow-xs"
      >
        <div>
          <h1 className="text-xl font-semibold">TAM Life</h1>
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
      </form>
    </main>
  )
}
