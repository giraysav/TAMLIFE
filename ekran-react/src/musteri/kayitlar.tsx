import { useState } from "react"
import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { ChevronLeft, ChevronRight, ListFilter, X } from "lucide-react"
import { DUGME, HataKutu } from "@/components/sayfa-ui"
import { Skeleton } from "@/components/ui/skeleton"
import { sayi, zaman } from "@/lib/bicim"
import { oku, sorguMetni } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"

/** Musteri karti kayit listesi (GET /musteri/{id}/kayitlar?tur&durum): Operasyon kutusundaki "acik / kapanan" dugmeleri acar. */
export type KayitTuru = "alarm" | "talep" | "sikayet"
export type KayitDurumu = "acik" | "kapali"
type Kayit = { id: number; ticket: string; ci: string; baslik: string; durum: string; acilis: string | null; kapanis: string | null; sure_dk: number | null }
type Yanit = { tur: KayitTuru; durum: KayitDurumu; yil: number; toplam: number; sayfa: number; adet: number; kayitlar: Kayit[] }

const TR = {
  tur: { alarm: "Alarm", talep: "Talep", sikayet: "Şikayet" } as Record<KayitTuru, string>,
  baslik: (tur: string, durum: KayitDurumu, yil: number) => (durum === "acik" ? `Açık ${tur} kayıtları` : `${yil} yılında kapanan ${tur} kayıtları`),
  adet: (n: string) => `${n} kayıt`,
  yok: "Bu süzgeçte kayıt yok.",
  kapat: "Listeyi kapat",
  ticket: "Ticket",
  ci: "CI",
  baslikSutun: "Başlık",
  durum: "Durum",
  acilis: "Açılış",
  kapanis: "Kapanış",
  sure: "Süre",
  acikSure: "Açık süre",
  yuklenemedi: "Kayıtlar yüklenemedi.",
  tekrar: "Tekrar dene",
  onceki: "Önceki",
  sonraki: "Sonraki",
  dk: "dk",
  sa: "sa",
  gun: "gün",
}
const EN: typeof TR = {
  tur: { alarm: "Alarm", talep: "Request", sikayet: "Complaint" },
  baslik: (tur: string, durum: KayitDurumu, yil: number) => (durum === "acik" ? `Open ${tur} records` : `${tur} records closed in ${yil}`),
  adet: (n: string) => `${n} records`,
  yok: "No records for this filter.",
  kapat: "Close list",
  ticket: "Ticket",
  ci: "CI",
  baslikSutun: "Header",
  durum: "Status",
  acilis: "Opened",
  kapanis: "Closed",
  sure: "Duration",
  acikSure: "Open for",
  yuklenemedi: "Records could not be loaded.",
  tekrar: "Retry",
  onceki: "Previous",
  sonraki: "Next",
  dk: "min",
  sa: "h",
  gun: "d",
}
type Metin = typeof TR
const metin = (dil: Dil) => (dil === "en" ? EN : TR)

/** Dakika -> "45 dk" / "5 sa 20 dk" / "3 gün 4 sa". */
export function sureMetni(dk: number | null, t: Pick<Metin, "dk" | "sa" | "gun">): string {
  if (dk === null) return "—"
  if (dk < 60) return `${dk} ${t.dk}`
  if (dk < 1440) return `${Math.floor(dk / 60)} ${t.sa}${dk % 60 ? ` ${dk % 60} ${t.dk}` : ""}`
  const sa = Math.floor((dk % 1440) / 60)
  return `${Math.floor(dk / 1440)} ${t.gun}${sa ? ` ${sa} ${t.sa}` : ""}`
}

/** Kartin secilen tur + durumdaki kayitlari (sayfa basina 10). */
export function KartKayitlari({ dil, id, tur, durum, onKapat }: { dil: Dil; id: number; tur: KayitTuru; durum: KayitDurumu; onKapat: () => void }) {
  const t = metin(dil)
  const [sayfa, setSayfa] = useState(1)
  const r = useQuery({
    queryKey: ["musteri", "kayitlar", id, tur, durum, sayfa],
    queryFn: () => oku<Yanit>(`/api/v1/musteri/${id}/kayitlar${sorguMetni({ tur, durum, page: sayfa, per_page: 10 })}`),
    placeholderData: keepPreviousData,
  })
  const kapali = durum === "kapali"
  const baslik = t.baslik(t.tur[tur].toLocaleLowerCase(dil === "en" ? "en" : "tr"), durum, r.data?.yil ?? new Date().getFullYear())
  const son = r.data ? Math.max(1, Math.ceil(r.data.toplam / r.data.adet)) : 1
  const kolonlar = [t.ticket, t.ci, t.baslikSutun, t.durum, t.acilis, ...(kapali ? [t.kapanis, t.sure] : [t.acikSure])]
  return (
    <section aria-label={baslik} className="grid gap-2 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <ListFilter aria-hidden className="size-4 text-tl-blue" />
        <h3 className="text-xs font-black uppercase tracking-widest text-tl-navy">{baslik}</h3>
        {r.data ? <span className="text-[0.6875rem] font-bold text-slate-500">{t.adet(sayi(r.data.toplam))}</span> : null}
        <span className="ml-auto flex items-center gap-2 text-xs font-bold text-slate-500">
          {r.data && son > 1 ? (
            <>
              <button type="button" className={`${DUGME} !px-2 !py-1`} aria-label={t.onceki} disabled={r.data.sayfa <= 1} onClick={() => setSayfa(r.data.sayfa - 1)}>
                <ChevronLeft aria-hidden className="size-3.5" />
              </button>
              <span>
                {r.data.sayfa} / {son}
              </span>
              <button type="button" className={`${DUGME} !px-2 !py-1`} aria-label={t.sonraki} disabled={r.data.sayfa >= son} onClick={() => setSayfa(r.data.sayfa + 1)}>
                <ChevronRight aria-hidden className="size-3.5" />
              </button>
            </>
          ) : null}
          <button type="button" className={`${DUGME} !px-2 !py-1`} aria-label={t.kapat} onClick={onKapat}>
            <X aria-hidden className="size-3.5" />
          </button>
        </span>
      </div>
      {r.isPending ? (
        <Skeleton className="h-32 rounded-xl" />
      ) : r.isError || !Array.isArray(r.data.kayitlar) ? (
        <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void r.refetch()} />
      ) : r.data.kayitlar.length === 0 ? (
        <p className="text-xs font-bold text-slate-400">{t.yok}</p>
      ) : (
        <div className={`overflow-x-auto rounded-xl border border-slate-200 ${r.isPlaceholderData ? "opacity-60" : ""}`}>
          <table className="w-full text-left text-[0.6875rem]">
            <caption className="sr-only">{baslik}</caption>
            <thead className="bg-tl-navy text-white">
              <tr>
                {kolonlar.map((k) => (
                  <th key={k} scope="col" className="whitespace-nowrap px-2 py-1.5 font-black">
                    {k}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {r.data.kayitlar.map((k) => (
                <tr key={k.id} className="border-t border-slate-100 odd:bg-slate-50/60">
                  <td className="whitespace-nowrap px-2 py-1 font-mono">{k.ticket || "—"}</td>
                  <td className="max-w-72 truncate px-2 py-1 font-mono" title={k.ci}>
                    {k.ci || "—"}
                  </td>
                  <td className="max-w-48 truncate px-2 py-1" title={k.baslik}>
                    {k.baslik || "—"}
                  </td>
                  <td className="whitespace-nowrap px-2 py-1 text-slate-500">{k.durum}</td>
                  <td className="whitespace-nowrap px-2 py-1">{zaman(k.acilis)}</td>
                  {kapali ? <td className="whitespace-nowrap px-2 py-1">{zaman(k.kapanis)}</td> : null}
                  <td className="whitespace-nowrap px-2 py-1 text-right font-mono">{sureMetni(k.sure_dk, t)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
