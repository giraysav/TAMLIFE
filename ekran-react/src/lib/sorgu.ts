import { apiYolu, csrfBasliklari, oturumYok } from "@/lib/http"

/** Sunucu yaniti basarisizsa firlatilir; TanStack Query hata durumuna duser. durum 0 = ag. */
export class ApiHata extends Error {
  durum: number
  constructor(durum: number, mesaj: string) {
    super(mesaj)
    this.durum = durum
  }
}

/** Tek API cagrisi: 401 oturumu kapatir; basari govdesi {data}, hata govdesi {detail}. */
async function gonder<T>(yontem: string, yol: string, yedek: string, basliklar?: Record<string, string>, govde?: BodyInit): Promise<T> {
  let cevap: Response
  try {
    cevap = await fetch(apiYolu(yol), { method: yontem, credentials: "same-origin", headers: basliklar, body: govde })
  } catch {
    throw new ApiHata(0, "ağ")
  }
  if (oturumYok(cevap)) window.dispatchEvent(new Event("tamlife:oturum-bitti"))
  const json = (await cevap.json().catch(() => null)) as { data?: T; detail?: unknown } | null
  const veri = cevap.ok ? (json?.data ?? null) : null
  if (veri !== null) return veri
  const ayrinti = json?.detail
  throw new ApiHata(cevap.status, (!cevap.ok && (typeof ayrinti === "string" ? ayrinti : ayrinti ? "Geçersiz istek." : "")) || yedek)
}

export const oku = <T>(yol: string) => gonder<T>("GET", yol, "Yüklenemedi.")

export function yaz<T>(yontem: "POST" | "PUT" | "DELETE", yol: string, govde?: unknown): Promise<T> {
  const json = govde !== undefined
  return gonder<T>(yontem, yol, "İşlem tamamlanamadı.", csrfBasliklari(json ? { "Content-Type": "application/json" } : {}), json ? JSON.stringify(govde) : undefined)
}

/** Ham dosya govdesi (cok parcali form degil): sunucu tarafinda yeni bagimlilik gerektirmez. */
export const yukle = <T>(yol: string, dosya: Blob, tur = "text/csv") => gonder<T>("PUT", yol, "Yükleme tamamlanamadı.", csrfBasliklari({ "Content-Type": tur }), dosya)

export function hataMesaji(hata: unknown, yedek: string): string {
  if (hata instanceof ApiHata && hata.durum !== 0 && hata.message && hata.message !== "ağ") return hata.message
  return yedek
}

export function sorguMetni(degerler: Record<string, string | number | null | undefined>): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(degerler)) if (v !== null && v !== undefined && v !== "") p.set(k, String(v))
  const metin = p.toString()
  return metin ? `?${metin}` : ""
}
