import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Upload } from "lucide-react"
import { Cekmece } from "@/components/cekmece"
import { Alan, Bildirim, DUGME, DUGME_SARI, GIRDI, Yukleniyor } from "@/components/sayfa-ui"
import { hataMesaji, oku, sorguMetni, yukle } from "@/lib/sorgu"
import { yilSecenekleri } from "@/lib/yillar"
import type { Dil } from "@/shell/metin"
import { musteriMetin } from "@/musteri/musteri-metin"

/** Sunucu sinirinin aynisi (rs.AZAMI_ICE_AKTARMA): daha buyuk dosya hic gonderilmez. */
const AZAMI_BAYT = 25 * 1024 * 1024
type Secenek = { id: number; ad: string; gonderildi: boolean }

/** Gecmis rapor ice aktarma (2026-10-31): ay + yil secilir, yalniz kullanicinin rapor yazabildigi musteriler listelenir (personel:
 *  kendi musterileri; o donem raporu olan secilemez), Outlook iletisi (.msg / .eml) ya da PDF o donemin gonderimi olarak kaydedilir. */
export function RaporIceAktar({ dil, yil: ilkYil, ay: ilkAy, onKapat }: { dil: Dil; yil: number; ay: number; onKapat: () => void }) {
  const t = musteriMetin(dil)
  const qc = useQueryClient()
  const [yil, setYil] = useState(ilkYil)
  const [ay, setAy] = useState(ilkAy)
  const [musteri, setMusteri] = useState("")
  const [dosya, setDosya] = useState<File | null>(null)
  const [uyari, setUyari] = useState("")
  const [son, setSon] = useState("")
  const musteriler = useQuery({
    queryKey: ["rapor", "ice-al", yil, ay],
    queryFn: () => oku<Secenek[]>(`/api/v1/rapor/ice-al/musteriler${sorguMetni({ yil, ay })}`),
  })
  const aktar = useMutation({
    mutationFn: ({ d, id }: { d: File; id: string }) =>
      yukle(`/api/v1/rapor/ice-al${sorguMetni({ musteri_id: id, yil, ay, dosya: d.name.slice(0, 150) })}`, d, d.type || "application/octet-stream", "POST"),
    onSuccess: () => {
      const ad = musteriler.data?.find((m) => String(m.id) === musteri)?.ad ?? ""
      setSon(t.iceAktarildi(ad, `${t.aylar[ay - 1]} ${yil}`))
      setMusteri("")
      setDosya(null)
      void qc.invalidateQueries({ queryKey: ["rapor"] })
    },
  })

  function sec(d: File | undefined) {
    setUyari("")
    setSon("")
    aktar.reset()
    if (!d) return setDosya(null)
    if (d.size > AZAMI_BAYT) return setUyari(t.iceDosyaBuyuk)
    if (!/\.(msg|eml|pdf)$/i.test(d.name)) return setUyari(t.iceDosyaTuru)
    setDosya(d)
  }

  const donemDegis = (y: number, a: number) => {
    setYil(y)
    setAy(a)
    setMusteri("")
    setSon("")
    aktar.reset()
  }
  const liste = musteriler.data ?? []

  return (
    <Cekmece
      acik
      onKapat={onKapat}
      baslik={t.iceBaslik}
      aciklama={t.iceAciklama}
      kapatEtiketi={t.kapat}
      alt={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <button type="button" className={DUGME} onClick={onKapat}>
            {t.kapat}
          </button>
          <button type="button" className={DUGME_SARI} disabled={!musteri || !dosya || aktar.isPending} onClick={() => dosya && aktar.mutate({ d: dosya, id: musteri })}>
            <Upload aria-hidden className="size-4" />
            {aktar.isPending ? t.iceAktariliyor : t.iceAktar}
          </button>
        </div>
      }
    >
      <div className="grid gap-4">
        <div className="grid grid-cols-2 gap-3">
          <Alan etiket={t.ay}>
            <select className={GIRDI} value={ay} onChange={(e) => donemDegis(yil, Number(e.target.value))}>
              {t.aylar.map((ad, i) => (
                <option key={ad} value={i + 1}>
                  {ad}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t.yil}>
            <select className={GIRDI} value={yil} onChange={(e) => donemDegis(Number(e.target.value), ay)}>
              {yilSecenekleri().map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </Alan>
        </div>
        <Alan etiket={t.musteriKolon} ipucu={t.iceMusteriIpucu}>
          {musteriler.isPending ? (
            <Yukleniyor metin="…" />
          ) : (
            <select className={GIRDI} value={musteri} onChange={(e) => setMusteri(e.target.value)}>
              <option value="">{liste.length ? t.musteriSec : t.iceMusteriYok}</option>
              {liste.map((m) => (
                <option key={m.id} value={m.id} disabled={m.gonderildi}>
                  {m.gonderildi ? `${m.ad} · ${t.raporuVar}` : m.ad}
                </option>
              ))}
            </select>
          )}
        </Alan>
        <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex cursor-pointer items-center justify-center gap-1.5 rounded-xl border border-tl-blue bg-white px-4 py-2 text-xs font-bold text-tl-blue shadow-sm transition-colors hover:bg-tl-blue/5 focus-within:ring-2 focus-within:ring-tl-yellow">
            <Upload aria-hidden className="size-4" />
            {t.iceDosyaSec}
            <input
              type="file"
              accept=".msg,.eml,.pdf"
              className="sr-only"
              onChange={(e) => {
                sec(e.target.files?.[0])
                e.target.value = ""
              }}
            />
          </label>
          {dosya ? <span className="min-w-0 break-words text-xs font-bold text-slate-500">{dosya.name}</span> : null}
        </div>
        <p className="text-xs font-bold text-slate-500">{t.iceKural}</p>
        {uyari ? <Bildirim ton="amber">{uyari}</Bildirim> : null}
        {aktar.isError ? <Bildirim ton="kirmizi">{hataMesaji(aktar.error, t.iceHata)}</Bildirim> : null}
        {son ? <Bildirim ton="yesil">{son}</Bildirim> : null}
      </div>
    </Cekmece>
  )
}
