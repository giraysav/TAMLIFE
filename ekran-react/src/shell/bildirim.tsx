import { useQuery } from "@tanstack/react-query"
import { Bell } from "lucide-react"
import { oku } from "@/lib/sorgu"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

type Bildirimler = { toplam: number; son: { kayit_no: string; mesaj: string; zaman: string | null }[] }

export const BILDIRIM_ADRESI = "#/yonetim/arizalar?kod=TL-RAP-01"

/** Admin ust cubuk bildirimi (2026-10-26): kapanmamis aylik rapor gonderim hatalari (TL-RAP-01). Kayit Arizalar'da kapatilinca
 *  rozet duser. Hata yoksa sessiz zil; yalniz admin icin cizilir (ucu da yalniz admin acar). */
export function AdminBildirimi({ dil, dugmeSinifi }: { dil: Dil; dugmeSinifi: string }) {
  const t = metin(dil)
  const q = useQuery({ queryKey: ["yonetim", "bildirimler"], queryFn: () => oku<Bildirimler>("/api/v1/yonetim/bildirimler"), refetchInterval: 60_000 })
  const n = q.data?.toplam ?? 0
  const etiket = t.bildirim(n)
  const ayrinti = (q.data?.son ?? []).map((s) => `• ${s.mesaj}`).join("\n")
  return (
    <a
      href={BILDIRIM_ADRESI}
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
