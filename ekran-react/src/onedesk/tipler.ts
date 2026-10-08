import type { Seri } from "@/components/grafik"
import type { OnedeskMetin } from "@/onedesk/onedesk-metin"

export type Tur = "alarm" | "talep" | "sikayet"

export type Durum = {
  kapsam: "acik" | "kapali"
  yil: number
  toplam: Record<Tur | "hepsi", number>
  musteriler: ({ id: number | null; ad: string; toplam: number } & Record<Tur, number>)[]
  musteri_sayisi: number
  grafik: ({ etiket?: string; ay?: number } & Record<Tur, number>)[]
  kaynak: { kayit: number; ornek: boolean; son_kayit: string | null }
}
export type Top10 = {
  yil: number
  musteriler: ({ sira: number; ad: string; toplam: number; lokasyon: string; lokasyonlar: { ad: string; adet: number }[] } & Record<Tur, number>)[]
}
export type OrtakNokta = { kok_sebep: string; adet: number; oran: number; musteri_sayisi: number; lokasyon_sayisi: number; turler: Partial<Record<Tur, number>>; kategori: string; oneriler: string[] }
export type Rca = {
  yil: number
  kapsanan: number
  ortak_noktalar: OrtakNokta[]
  anahtar_kelimeler: { kelime: string; adet: number }[]
  tekrar_lokasyonlar: { musteri: string; lokasyon: string; adet: number }[]
  kategoriler: { ad: string; adet: number }[]
}
export type YzDurum = { saglayici: string; hazir: boolean; model: string | null; eksik: string[] }
export type Oneriler = { yil: number; kapsanan: number; gruplar: { kok_sebep: string; adet: number; oran: number; oneriler: string[] }[]; yz: YzDurum }
export type Parti = { id: number; kaynak: string; etiket: string; satir: number; zaman: string | null; sutunlar: string[] }
export type Kaynak = {
  kayit: number
  ornek: boolean
  son_kayit: string | null
  canli_baglanti: { yuva: string; yapilandirildi: boolean; acik: boolean }
  partiler: Parti[]
}
export type AktarSonuc = { parti: number; eklenen: number; guncellenen: number; atlanan: number; musteri_eslesmeyen: number; etkilenen_musteri: number; sutunlar: Record<string, string | null> }

export const TUR_RENK: Record<Tur, string> = { alarm: "#e11d48", talep: "#0055a5", sikayet: "#f59e0b" }

export function turSerileri(t: OnedeskMetin): Seri[] {
  return [
    { anahtar: "alarm", ad: t.alarm, renk: TUR_RENK.alarm },
    { anahtar: "talep", ad: t.talep, renk: TUR_RENK.talep },
    { anahtar: "sikayet", ad: t.sikayet, renk: TUR_RENK.sikayet },
  ]
}
