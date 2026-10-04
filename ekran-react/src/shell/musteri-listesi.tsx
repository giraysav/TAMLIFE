import { useCallback, useEffect, useState } from "react"
import type { FormEvent } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiOku, apiYaz } from "@/lib/api-yaz"
import { musteriMetin } from "@/shell/musteri-metin"
import type { Dil } from "@/shell/metin"
import { sorguAyarla } from "@/shell/rota"

type Satir = { id: number; name: string; segment: string; owner: string | null; score: number | null; parent_id: number | null }
type Sayfa = { items: Satir[]; total: number; page: number; per_page: number; pages: number }

const SEGMENTLER = ["SMB", "SA", "MA", "PA", "WHOLESALE"]

/** Musteri listesi: kapsama gore sunucu filtreler (Member yalniz kendi musterileri). */
export function MusteriListesi({ dil }: { dil: Dil }) {
  const t = musteriMetin(dil)
  const [arama, setArama] = useState("")
  const [sorgu, setSorgu] = useState("")
  const [sayfa, setSayfa] = useState(1)
  const [veri, setVeri] = useState<Sayfa | null | undefined>(undefined)
  const [yeniAcik, setYeniAcik] = useState(false)
  const [yeniAd, setYeniAd] = useState("")
  const [yeniSegment, setYeniSegment] = useState("")
  const [hata, setHata] = useState("")

  const yukle = useCallback(async () => {
    const q = new URLSearchParams({ page: String(sayfa), per_page: "20" })
    if (sorgu) q.set("q", sorgu)
    const sonuc = await apiOku<Sayfa>(`/api/v1/musteri?${q.toString()}`)
    setVeri(sonuc.ok ? sonuc.veri : null)
  }, [sayfa, sorgu])

  useEffect(() => {
    void yukle()
  }, [yukle])

  function ara(olay: FormEvent) {
    olay.preventDefault()
    setSayfa(1)
    setSorgu(arama.trim())
  }

  async function ekle(olay: FormEvent) {
    olay.preventDefault()
    setHata("")
    const sonuc = await apiYaz<{ id: number }>("POST", "/api/v1/musteri", { name: yeniAd, ...(yeniSegment ? { segment: yeniSegment } : {}) })
    if (!sonuc.ok || !sonuc.veri) {
      setHata(sonuc.hata || t.kaydedilemedi)
      return
    }
    setYeniAcik(false)
    setYeniAd("")
    setYeniSegment("")
    sorguAyarla("musteri", { m: String(sonuc.veri.id) })
  }

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <form onSubmit={ara} className="flex flex-1 items-center gap-2" role="search">
          <Input value={arama} onChange={(e) => setArama(e.target.value)} placeholder={t.ara} aria-label={t.ara} maxLength={100} className="max-w-sm" />
          <Button type="submit" variant="outline">
            {t.aramaDugmesi}
          </Button>
        </form>
        <Button type="button" onClick={() => setYeniAcik((a) => !a)} aria-expanded={yeniAcik}>
          {t.ekle}
        </Button>
      </div>

      {yeniAcik ? (
        <Card>
          <CardContent className="pt-6">
            <form onSubmit={ekle} className="grid gap-3 sm:grid-cols-[1fr_12rem_auto] sm:items-end" aria-label={t.yeniMusteri}>
              <div className="grid gap-1.5">
                <Label htmlFor="yeni-unvan">{t.unvan}</Label>
                <Input id="yeni-unvan" value={yeniAd} onChange={(e) => setYeniAd(e.target.value)} required maxLength={150} />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="yeni-segment">{t.segment}</Label>
                <select id="yeni-segment" value={yeniSegment} onChange={(e) => setYeniSegment(e.target.value)} className="h-9 rounded-md border bg-background px-2 text-sm">
                  <option value="">{t.seciniz}</option>
                  {SEGMENTLER.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
              <Button type="submit">{t.kaydet}</Button>
            </form>
            {hata ? (
              <p role="alert" className="mt-2 text-sm text-destructive">
                {hata}
              </p>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {veri === undefined ? <p className="text-sm text-muted-foreground">…</p> : null}
      {veri === null ? (
        <p role="alert" className="text-sm text-destructive">
          {t.yuklenemedi}
        </p>
      ) : null}
      {veri ? (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">{t.liste}</caption>
                <thead>
                  <tr className="bg-tl-navy text-left text-xs text-white">
                    <th scope="col" className="px-4 py-3 font-black">
                      {t.unvan}
                    </th>
                    <th scope="col" className="px-4 py-3 font-black">
                      {t.segment}
                    </th>
                    <th scope="col" className="px-4 py-3 font-black">
                      {t.sorumlu}
                    </th>
                    <th scope="col" className="px-4 py-3 text-right font-black">
                      {t.skor}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {veri.items.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="px-4 py-6 text-center text-muted-foreground">
                        {t.sonucYok}
                      </td>
                    </tr>
                  ) : (
                    veri.items.map((m) => (
                      <tr key={m.id} className="border-b border-slate-100 last:border-0 hover:bg-tl-yellow/10">
                        <td className="px-4 py-3">
                          <a
                            href={`#/musteri?m=${m.id}`}
                            className="font-bold text-tl-navy underline-offset-4 hover:underline focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
                          >
                            {m.parent_id ? "↳ " : ""}
                            {m.name}
                          </a>
                        </td>
                        <td className="px-4 py-3">{m.segment || "—"}</td>
                        <td className="px-4 py-3">{m.owner ?? "—"}</td>
                        <td className="px-4 py-3 text-right tabular-nums">{m.score ?? "—"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {veri && veri.pages > 0 ? (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {veri.total} {t.toplam} · {t.sayfa} {veri.page}/{veri.pages}
          </span>
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" disabled={veri.page <= 1} onClick={() => setSayfa((s) => s - 1)}>
              {t.onceki}
            </Button>
            <Button type="button" variant="outline" size="sm" disabled={veri.page >= veri.pages} onClick={() => setSayfa((s) => s + 1)}>
              {t.sonraki}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
