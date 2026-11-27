import { useEffect, useRef, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Bell, Inbox } from "lucide-react"
import { zaman } from "@/lib/bicim"
import { oku, yaz } from "@/lib/sorgu"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

type Bildirimler = { toplam: number; son: { kayit_no: string; kod: string; mesaj: string; zaman: string | null }[] }

export const bildirimAdresi = (kod = "TL-RAP-01") => `#/yonetim/arizalar?kod=${kod}`

/** Admin ust cubuk bildirimi: kapanmamis aylik rapor gonderim hatalari (TL-RAP-01, 2026-10-26) ve gece senkronu / yeniden baslatma
 *  sorunlari (TL-SNC-01, 2026-10-27). Zil en son kaydin koduna suzulmus Arizalar'a gider; kayit kapatilinca rozet duser. Hata yoksa
 *  sessiz zil; yalniz admin icin cizilir (ucu da yalniz admin acar). */
export function AdminBildirimi({ dil, dugmeSinifi }: { dil: Dil; dugmeSinifi: string }) {
  const t = metin(dil)
  const q = useQuery({ queryKey: ["yonetim", "bildirimler"], queryFn: () => oku<Bildirimler>("/api/v1/yonetim/bildirimler"), refetchInterval: 60_000 })
  const n = q.data?.toplam ?? 0
  const etiket = t.bildirim(n)
  const ayrinti = (q.data?.son ?? []).map((s) => `• ${s.mesaj}`).join("\n")
  return (
    <a
      href={bildirimAdresi(q.data?.son[0]?.kod)}
      aria-label={etiket}
      title={ayrinti ? `${etiket}\n${ayrinti}` : etiket}
      className={`relative inline-flex size-9 items-center justify-center rounded-md ${dugmeSinifi}`}
    >
      <Bell aria-hidden className="size-4" />
      {n > 0 ? (
        <span aria-hidden className="absolute -top-0.5 -right-0.5 min-w-4 rounded-full bg-rose-500 px-1 text-center text-[0.625rem] leading-4 font-black text-white">
          {n > 99 ? "99+" : n}
        </span>
      ) : null}
    </a>
  )
}

type KisiselBildirimler = { okunmamis: number; son: { id: number; tur: string; mesaj: string; adres: string; zaman: string | null; okundu: boolean }[] }
const KISISEL = ["bildirim"] as const

/** Kisiye ozel bildirimler (2026-10-31: gelistirme talebinin durumu degisince talep sahibine). Herkes icin cizilir; pencerede son
 *  bildirimler listelenir, tiklanan okundu olur ve ilgili sayfaya gider; "tumunu okundu" rozeti sifirlar. */
export function KisiselBildirim({ dil, dugmeSinifi }: { dil: Dil; dugmeSinifi: string }) {
  const t = metin(dil)
  const qc = useQueryClient()
  const q = useQuery({ queryKey: KISISEL, queryFn: () => oku<KisiselBildirimler>("/api/v1/bildirim"), refetchInterval: 60_000 })
  const [acik, setAcik] = useState(false)
  const kutu = useRef<HTMLDialogElement>(null)
  const n = q.data?.okunmamis ?? 0
  const son = q.data?.son ?? []

  useEffect(() => {
    const d = kutu.current
    if (!d) return
    if (acik && !d.open) d.showModal()
    else if (!acik && d.open) d.close()
  }, [acik])

  async function okundu(ids?: number[]) {
    await yaz("POST", "/api/v1/bildirim/okundu", ids ? { ids } : {})
    await qc.invalidateQueries({ queryKey: KISISEL })
  }

  return (
    <>
      <button
        type="button"
        aria-label={t.kisiselBildirim(n)}
        title={t.kisiselBildirim(n)}
        onClick={() => setAcik(true)}
        className={`relative inline-flex size-9 items-center justify-center rounded-md ${dugmeSinifi}`}
      >
        <Inbox aria-hidden className="size-4" />
        {n > 0 ? (
          <span aria-hidden className="absolute -top-0.5 -right-0.5 min-w-4 rounded-full bg-tl-yellow px-1 text-center text-[0.625rem] leading-4 font-black text-tl-navy">
            {n > 99 ? "99+" : n}
          </span>
        ) : null}
      </button>
      <dialog
        ref={kutu}
        onClose={() => setAcik(false)}
        onClick={(e) => {
          if (e.target === kutu.current) setAcik(false)
        }}
        aria-label={t.bildirimlerim}
        className="m-auto w-full max-w-md rounded-xl border bg-popover p-3 text-popover-foreground shadow-lg backdrop:bg-black/40"
      >
        <div className="flex items-center justify-between gap-2 px-1 pb-2">
          <h2 className="text-sm font-black">{t.bildirimlerim}</h2>
          {n > 0 ? (
            <button type="button" className="text-xs font-bold text-tl-blue hover:underline" onClick={() => void okundu()}>
              {t.tumunuOkundu}
            </button>
          ) : null}
        </div>
        <ul className="max-h-80 overflow-auto">
          {son.length === 0 ? <li className="px-2 py-3 text-sm text-muted-foreground">{t.bildirimYok}</li> : null}
          {son.map((b) => (
            <li key={b.id}>
              <a
                href={b.adres || undefined}
                className={`flex flex-col rounded-md px-2 py-2 hover:bg-accent focus-visible:bg-accent focus-visible:outline-hidden ${b.okundu ? "opacity-60" : ""}`}
                onClick={() => {
                  setAcik(false)
                  if (!b.okundu) void okundu([b.id])
                }}
              >
                <span className={`text-sm ${b.okundu ? "" : "font-bold"}`}>{b.mesaj}</span>
                <span className="font-mono text-[0.625rem] text-muted-foreground">{zaman(b.zaman)}</span>
              </a>
            </li>
          ))}
        </ul>
      </dialog>
    </>
  )
}
