import { useEffect, useState } from "react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { API_KOK } from "@/lib/api"

type Kaynak = {
  id: string
  ad: string
  durum: string
}

type Dugum = {
  id: string
  ad: string
  cocuklar: Kaynak[]
}

export function VeriAgaci({
  baslik,
  yukleniyor,
  hataMetni,
  tanimli,
  degil,
  ikinciKaynak,
}: {
  baslik: string
  yukleniyor: string
  hataMetni: string
  tanimli: string
  degil: string
  ikinciKaynak: string
}) {
  const [agacBaslik, setAgacBaslik] = useState(baslik)
  const [dugumler, setDugumler] = useState<Dugum[] | null>(null)
  const [hata, setHata] = useState<string | null>(null)

  useEffect(() => {
    setAgacBaslik(baslik)
  }, [baslik])

  useEffect(() => {
    let iptal = false
    fetch(`${API_KOK}/api/admin/veri-agaci`)
      .then((response) => {
        if (!response.ok) throw new Error(String(response.status))
        return response.json()
      })
      .then((govde) => {
        if (iptal) return
        const agac = govde.agac || {}
        const gelen = String(agac.baslik || "")
        const bilinen = gelen === "Veri ağacı" || gelen === "Veri agaci" || gelen === ""
        setAgacBaslik(bilinen ? baslik : gelen)
        setDugumler(agac.dugumler || [])
      })
      .catch(() => {
        if (!iptal) setHata(hataMetni)
      })
    return () => {
      iptal = true
    }
  }, [baslik, hataMetni])

  function kaynakAdi(ad: string) {
    if (ad === "İkinci kaynak tanımlı değil" || ad === "Ikinci kaynak tanimli degil") return ikinciKaynak
    return ad
  }

  function durumYazi(durum: string) {
    const kucuk = durum.toLocaleLowerCase("tr")
    if (kucuk === "tanımlı" || kucuk === "tanimli") return tanimli
    if (kucuk === "değil" || kucuk === "degil") return degil
    return durum
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{agacBaslik}</CardTitle>
      </CardHeader>
      <CardContent>
        {hata ? <p className="text-sm text-muted-foreground">{hata}</p> : null}
        {!dugumler && !hata ? <p className="text-sm text-muted-foreground">{yukleniyor}</p> : null}
        {dugumler?.map((dugum) => (
          <div key={dugum.id}>
            <p className="text-sm font-medium">{dugum.ad}</p>
            <ul className="mt-2 flex list-disc flex-col gap-1 pl-5">
              {dugum.cocuklar.map((kaynak) => (
                <li key={kaynak.id} className="text-sm">
                  {kaynakAdi(kaynak.ad)}
                  <span className="text-muted-foreground"> - {durumYazi(kaynak.durum)}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
