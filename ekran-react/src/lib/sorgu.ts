import { apiOku, apiYaz, apiYukle } from "@/lib/api-yaz"

/** Sunucu yaniti basarisizsa firlatilir; TanStack Query hata durumuna duser. durum 0 = ag. */
export class ApiHata extends Error {
  durum: number
  constructor(durum: number, mesaj: string) {
    super(mesaj)
    this.durum = durum
  }
}

export async function oku<T>(yol: string): Promise<T> {
  const s = await apiOku<T>(yol)
  if (!s.ok || s.veri === null) throw new ApiHata(s.durum, s.hata || "Yüklenemedi.")
  return s.veri
}

export async function yaz<T>(yontem: "POST" | "PUT" | "DELETE", yol: string, govde?: unknown): Promise<T> {
  const s = await apiYaz<T>(yontem, yol, govde)
  if (!s.ok || s.veri === null) throw new ApiHata(s.durum, s.hata || "İşlem tamamlanamadı.")
  return s.veri
}

export async function yukle<T>(yol: string, dosya: Blob): Promise<T> {
  const s = await apiYukle<T>(yol, dosya)
  if (!s.ok || s.veri === null) throw new ApiHata(s.durum, s.hata || "Yükleme tamamlanamadı.")
  return s.veri
}

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
