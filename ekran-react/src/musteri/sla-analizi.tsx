import { useState } from "react"
import { hataMesaji, yaz } from "@/lib/sorgu"
import { DUGME, DUGME_ANA } from "@/components/sayfa-ui"
import { KucukKart } from "@/musteri/sla-paneli"
import type { musteriMetin } from "@/musteri/musteri-metin"

type AnalizSonucu = {
  analiz: { toplam: number; ci_sayisi: number; dil: string; acik_toplam?: Record<string, number> }
  ozet: { bilgi: string; devam: string }
  yz: { hazir: boolean; yorum: string | null; neden: string }
}

export type AnalizMetni = { bilgi: string; devam: string }

const BASLIKLAR = {
  bilgi: /^\s*(bilgilendirme(ler)?|information)\s*:?\s*$/i,
  devam: /^\s*(devam eden çalışmalar|ongoing work)\s*:?\s*$/i,
}

/** YZ yaniti iki basliga gore ayrilir ("Bilgilendirme:" / "Devam eden calismalar:"); baslik yoksa tamami bilgilendirmedir. */
export function yzBol(metin: string): AnalizMetni {
  const sonuc: Record<keyof AnalizMetni, string[]> = { bilgi: [], devam: [] }
  let alan: keyof AnalizMetni = "bilgi"
  for (const satir of metin.replace(/\r\n/g, "\n").split("\n")) {
    const temiz = satir.replace(/^[#*\s]+|[*\s]+$/g, "")
    if (BASLIKLAR.bilgi.test(temiz)) alan = "bilgi"
    else if (BASLIKLAR.devam.test(temiz)) alan = "devam"
    else sonuc[alan].push(satir)
  }
  const birlestir = (s: string[]) => s.join("\n").replace(/\n{3,}/g, "\n\n").trim()
  return { bilgi: birlestir(sonuc.bilgi), devam: birlestir(sonuc.devam) }
}

/** Uretim ats_analizi: SLA Excel'i ozetlenir ve metin dogrudan Bilgilendirmeler / Devam Eden Calismalar alanlarina yazilir. */
export function SlaAnalizi({
  taban,
  t,
  dil,
  slaVar,
  yzHazir,
  kilitli,
  onYaz,
}: {
  taban: string
  t: ReturnType<typeof musteriMetin>
  dil: "tr" | "en"
  slaVar: boolean
  yzHazir: boolean
  kilitli: boolean
  onYaz: (metin: AnalizMetni) => void
}) {
  const [mesgul, setMesgul] = useState<"" | "ozet" | "yz">("")
  const [mesaj, setMesaj] = useState("")

  async function analizEt(yz: boolean) {
    setMesgul(yz ? "yz" : "ozet")
    setMesaj("")
    try {
      const s = await yaz<AnalizSonucu>("POST", `${taban}/sla/analiz`, { dil, yz })
      const yzMetni = yz && s.yz.yorum ? yzBol(s.yz.yorum) : null
      onYaz({ bilgi: yzMetni?.bilgi || s.ozet.bilgi, devam: yzMetni?.devam || s.ozet.devam })
      const acik = Object.values(s.analiz.acik_toplam ?? {}).reduce((a, b) => a + b, 0)
      setMesaj([yz && !s.yz.yorum ? s.yz.neden || t.analizYzBos : "", t.analizYazildi(s.analiz.toplam, acik)].filter(Boolean).join(" "))
    } catch (h) {
      setMesaj(hataMesaji(h, t.yuklenemedi))
    } finally {
      setMesgul("")
    }
  }

  return (
    <KucukKart baslik={t.analiz} aciklama={slaVar ? t.analizAlt : t.analizYok} mesaj={mesaj}>
      {slaVar && !kilitli ? (
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className={DUGME_ANA} disabled={!!mesgul} onClick={() => void analizEt(false)}>
            {mesgul === "ozet" ? t.analizSuruyor : t.analizYap}
          </button>
          <button type="button" className={DUGME} disabled={!!mesgul || !yzHazir} title={yzHazir ? undefined : t.analizYzKapali} onClick={() => void analizEt(true)}>
            {mesgul === "yz" ? t.analizSuruyor : t.analizYz}
          </button>
        </div>
      ) : null}
    </KucukKart>
  )
}
