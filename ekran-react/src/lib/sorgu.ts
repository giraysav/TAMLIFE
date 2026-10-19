import { apiYolu, csrfBasliklari, dilBasligi, musteriAlaniBasligi, oturumYok } from "@/lib/http"

/** Sunucu yaniti basarisizsa firlatilir; TanStack Query hata durumuna duser. durum 0 = ag. Mesaj yalniz sunucunun metnidir (yoksa bos; ekran kendi dilindeki yedegi yazar). */
export class ApiHata extends Error {
  durum: number
  constructor(durum: number, mesaj: string) {
    super(mesaj)
    this.durum = durum
  }
}

/** Tek API cagrisi: 401 oturumu kapatir; basari govdesi {data}, hata govdesi {detail}. */
async function gonder<T>(yontem: string, yol: string, basliklar?: Record<string, string>, govde?: BodyInit): Promise<T> {
  let cevap: Response
  try {
    cevap = await fetch(apiYolu(yol), { method: yontem, credentials: "same-origin", headers: { ...dilBasligi(), ...musteriAlaniBasligi(yol), ...basliklar }, body: govde })
  } catch {
    throw new ApiHata(0, "")
  }
  if (oturumYok(cevap)) window.dispatchEvent(new Event("tamlife:oturum-bitti"))
  const json = (await cevap.json().catch(() => null)) as { data?: T; detail?: unknown } | null
  const veri = cevap.ok ? (json?.data ?? null) : null
  if (veri !== null) return veri
  const ayrinti = json?.detail
  throw new ApiHata(cevap.status, !cevap.ok && typeof ayrinti === "string" ? ayrinti : "")
}

export const oku = <T>(yol: string) => gonder<T>("GET", yol)

export function yaz<T>(yontem: "POST" | "PUT" | "PATCH" | "DELETE", yol: string, govde?: unknown): Promise<T> {
  const json = govde !== undefined
  return gonder<T>(yontem, yol, csrfBasliklari(json ? { "Content-Type": "application/json" } : {}), json ? JSON.stringify(govde) : undefined)
}

/** Ham dosya govdesi (cok parcali form degil): sunucu tarafinda yeni bagimlilik gerektirmez. */
export const yukle = <T>(yol: string, dosya: Blob, tur = "text/csv", yontem: "PUT" | "POST" = "PUT") =>
  gonder<T>(yontem, yol, csrfBasliklari({ "Content-Type": tur }), dosya)

export function hataMesaji(hata: unknown, yedek: string): string {
  return hata instanceof ApiHata && hata.message ? hata.message : yedek
}

export function sorguMetni(degerler: Record<string, string | number | null | undefined>): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(degerler)) if (v !== null && v !== undefined && v !== "") p.set(k, String(v))
  const metin = p.toString()
  return metin ? `?${metin}` : ""
}
