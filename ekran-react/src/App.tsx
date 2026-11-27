import { useEffect, useState } from "react"
import { istemci } from "@/app/providers"
import { bicimDili } from "@/lib/bicim"
import { useOturum } from "@/lib/oturum"
import { Giris } from "@/shell/giris"
import type { Dil } from "@/shell/metin"
import { Panel } from "@/shell/panel"

function dilOku(): Dil {
  try {
    return window.localStorage.getItem("tamlife.dil") === "en" ? "en" : "tr"
  } catch {
    return "tr"
  }
}

export default function App() {
  const { durum, kullanici, giris, cikis, yenile } = useOturum()
  const [dil, setDil] = useState<Dil>(dilOku)
  // Alt bilesenler cizilmeden once: sayi/tarih bicimi ve sayfa dili (CSS buyuk harf: ADMIN/ADMİN, ekran okuyucu) dile uyar.
  bicimDili(dil)
  document.documentElement.lang = dil

  // Oturum kapaninca onbellekteki yonetim verisi bellekte kalmasin (ayni sekmede baska kullanici girebilir).
  useEffect(() => {
    if (durum === "yok") istemci.clear()
  }, [durum])

  function dilSec(sonraki: Dil) {
    setDil(sonraki)
    try {
      window.localStorage.setItem("tamlife.dil", sonraki)
    } catch {
      /* tarayici kaydedemiyor */
    }
    // Sunucunun urettigi metinler (saglik, ekip ozeti, kaynak durumu) X-Dil ile gelir: onbellekteki eski dil yenilenir.
    void istemci.invalidateQueries()
  }

  if (durum === "yukleniyor") return null
  if (durum === "yok" || !kullanici) return <Giris dil={dil} giris={giris} />
  return <Panel kullanici={kullanici} dil={dil} onDil={dilSec} onCikis={() => void cikis()} onProfilDegisti={() => void yenile()} />
}
