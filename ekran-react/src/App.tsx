import { useState } from "react"
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
  const { durum, kullanici, giris, cikis } = useOturum()
  const [dil, setDil] = useState<Dil>(dilOku)

  function dilSec(sonraki: Dil) {
    setDil(sonraki)
    try {
      window.localStorage.setItem("tamlife.dil", sonraki)
    } catch {
      /* tarayici kaydedemiyor */
    }
  }

  if (durum === "yukleniyor") return null
  if (durum === "yok" || !kullanici) return <Giris dil={dil} giris={giris} />
  return <Panel kullanici={kullanici} dil={dil} onDil={dilSec} onCikis={() => void cikis()} />
}
