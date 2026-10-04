import { apiYolu, csrfBasliklari, oturumYok } from "@/lib/http"

export type Sonuc<T> = {
  ok: boolean
  durum: number
  veri: T | null
  hata: string
  ek: Record<string, unknown>
}

function hataMetni(govde: unknown): string {
  const ayrinti = (govde as { detail?: unknown } | null)?.detail
  if (typeof ayrinti === "string") return ayrinti
  return ayrinti ? "Geçersiz istek." : ""
}

async function iste<T>(yontem: string, yol: string, govde?: unknown): Promise<Sonuc<T>> {
  try {
    const cevap = await fetch(apiYolu(yol), {
      method: yontem,
      credentials: "same-origin",
      headers: yontem === "GET" ? undefined : csrfBasliklari(govde !== undefined ? { "Content-Type": "application/json" } : {}),
      body: govde !== undefined ? JSON.stringify(govde) : undefined,
    })
    if (oturumYok(cevap)) window.dispatchEvent(new Event("tamlife:oturum-bitti"))
    const json = (await cevap.json().catch(() => null)) as Record<string, unknown> | null
    return {
      ok: cevap.ok,
      durum: cevap.status,
      veri: cevap.ok ? ((json?.data as T) ?? null) : null,
      hata: cevap.ok ? "" : hataMetni(json),
      ek: json ?? {},
    }
  } catch {
    return { ok: false, durum: 0, veri: null, hata: "ağ", ek: {} }
  }
}

export const apiOku = <T>(yol: string) => iste<T>("GET", yol)
export const apiYaz = <T>(yontem: "POST" | "PUT" | "DELETE", yol: string, govde?: unknown) => iste<T>(yontem, yol, govde)
