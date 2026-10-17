import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { oku, yaz, hataMesaji } from "@/lib/sorgu"
import { DUGME, GIRDI } from "@/components/sayfa-ui"
import { KucukKart } from "@/musteri/sla-paneli"
import type { RaporGrafigi } from "@/musteri/rapor-onizleme"

type Ayar = { baglantilar: string[]; hazir: boolean; duzenleyebilir: boolean; kilitli: boolean; yil: number; ay: number }
type Grafikler = { yil: number; ay: number; grafikler: RaporGrafigi[] }

export function useCacti(taban: string) {
  const ayar = useQuery({ queryKey: ["cacti", taban], queryFn: () => oku<Ayar>(`${taban}/cacti`), retry: false })
  const baglantilar = ayar.data?.baglantilar ?? []
  const grafik = useQuery({
    queryKey: ["cacti-grafikler", taban, ayar.data?.yil, ayar.data?.ay, baglantilar],
    queryFn: () => oku<Grafikler>(`${taban}/cacti/grafikler`),
    enabled: ayar.isSuccess && baglantilar.length > 0,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
  const engel = ayar.isPending || ayar.isError || (baglantilar.length > 0 && !grafik.isSuccess)
  return { taban, ayar, grafik, engel, grafikler: grafik.isSuccess ? grafik.data.grafikler : [] }
}

export function CactiKarti({ cacti, ingilizce }: { cacti: ReturnType<typeof useCacti>; ingilizce: boolean }) {
  const istemci = useQueryClient()
  const [duzenleme, setDuzenleme] = useState<string | null>(null)
  const [mesaj, setMesaj] = useState("")
  const [mesgul, setMesgul] = useState(false)
  const a = cacti.ayar.data
  const text = (tr: string, en: string) => ingilizce ? en : tr
  async function kaydet() {
    setMesgul(true)
    try {
      const baglantilar = (duzenleme ?? "").split(/\r?\n/).map(s => s.trim()).filter(Boolean)
      const yeni = await yaz<Ayar>("PUT", `${cacti.taban}/cacti`, { baglantilar })
      istemci.setQueryData(["cacti", cacti.taban], yeni)
      setDuzenleme(null)
      setMesaj(text("Kaydedildi.", "Saved."))
    } catch (h) {
      setMesaj(hataMesaji(h, text("Kaydedilemedi.", "Could not save.")))
    } finally { setMesgul(false) }
  }
  const hata = cacti.ayar.error ?? cacti.grafik.error
  return (
    <KucukKart baslik="CACTI" aciklama={text("Tanımlı grafikler rapor dönemine göre otomatik alınır ve PDF'e eklenir.", "Configured graphs are fetched for the report month and included in the PDF.")} mesaj={mesaj}>
      {a ? <p className="text-xs">{text("LDAP hesabı", "LDAP account")}: {a.hazir ? text("Tanımlı ••••", "Configured ••••") : text("Tanımlanmamış", "Not configured")}</p> : null}
      {a?.duzenleyebilir && !a.kilitli ? (
        <div className="space-y-2">
          <label className="block text-xs" htmlFor="cacti-baglantilar">{text("Lookouteyes grafik bağlantısı (Graph.aspx) ya da Cacti grafik ID — her satıra bir grafik (en fazla 6)", "Lookouteyes graph URL (Graph.aspx) or Cacti graph ID — one per line (up to 6)")}</label>
          <textarea id="cacti-baglantilar" className={GIRDI} rows={4} maxLength={12000} value={duzenleme ?? a.baglantilar.join("\n")} onChange={e => setDuzenleme(e.target.value)} disabled={mesgul} />
          <button type="button" className={DUGME} disabled={mesgul || duzenleme === null} onClick={() => void kaydet()}>{text("Kaydet", "Save")}</button>
        </div>
      ) : a ? <p className="text-xs">{a.baglantilar.join(", ") || text("Grafik tanımlanmamış.", "No graphs configured.")}</p> : null}
      {cacti.grafik.isFetching ? <p role="status" className="text-xs">{text("Aylık grafikler alınıyor…", "Fetching monthly graphs…")}</p> : null}
      {hata ? <div role="alert" className="space-y-2 text-xs text-destructive">
        <p>{hataMesaji(hata, text("Cacti grafikleri alınamadı. PDF ve rapor hazırlama işlemi bekletiliyor.", "Cacti graphs are unavailable. PDF and report preparation are paused."))}</p>
        <button type="button" className={DUGME} onClick={() => void (cacti.ayar.isError ? cacti.ayar.refetch() : cacti.grafik.refetch())}>{text("Tekrar dene", "Retry")}</button>
      </div> : null}
      {cacti.grafik.isSuccess ? <p className="text-xs">{text("Rapora eklenen grafik", "Graphs in report")}: {cacti.grafikler.length}</p> : null}
    </KucukKart>
  )
}
