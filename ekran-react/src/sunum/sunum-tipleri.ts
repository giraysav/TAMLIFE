import type { Ozet } from "@/takvim/takvim-grafigi"

/** Sunucunun /sunum/donem yuku (bkz. backend app/sunum/servis.py). Eski dondurulmus kayitlarda opsiyonel alanlar (alt_en, onceki, onizleme, stil) yoktur. */

export type Hucre = string | number | null
export type KpiVeri = { ad: string; ad_en: string; deger: number | null; birim: string; alt: string; alt_en?: string; onceki?: number | null; kod?: string }
/** Kisa kartin ilk satirlari: kac satir ve hangi sutunlardan (sutun numarasi) cizilecegi. */
export type Onizleme = { adet?: number; sira?: number; etiket?: number; deger?: number; tavan?: number }
export type TabloVeri = { sutunlar: { ad: string; ad_en: string; birim: string }[]; satirlar: Hucre[][]; onizleme?: Onizleme }
export type GenelVeri = { stil?: "sayilar"; kpi: KpiVeri[]; tablo?: TabloVeri }
export type TakvimVeri = { genel: Ozet; uyeler: ({ ad: string } & Ozet)[] }
export type KodDili = { dil: string; satir: number; dosya: number; pay: number; rol: string; rol_en: string }
export type TanitimVeri = {
  stil: "tanitim"
  kpi: KpiVeri[]
  olcum: string
  amac: { tr: string; en: string }
  kapsam: { ad: string; ad_en: string }[]
  fayda: { ad: string; ad_en: string; aciklama: string; aciklama_en: string }[]
  kod: { satir: number; dosya: number; test_satir: number; diller: KodDili[] } | null
  sayilar: { kod: string; ad: string; ad_en: string; deger: number }[]
  canli: { ad: string; ad_en: string; deger: number }[]
  yigin: string[]
}
export type SunumVeri = GenelVeri | TakvimVeri | TanitimVeri

export type Oge = {
  kaynak: string
  ad: string
  ad_en: string
  anlik: boolean
  durum: "canli" | "kayitli" | "yok" | "hata"
  gonderen: string
  zaman: string | null
  veri: SunumVeri | null
  kayit_no: string
}
export type Donem = { yil: number; ceyrek: number; donem: string; zaman: "guncel" | "gecmis" | "gelecek"; ogeler: Oge[]; yonetebilir: boolean; onay?: { onaylayan: string; zaman: string | null } | null }

export const tanitimMi = (v: SunumVeri): v is TanitimVeri => "stil" in v && v.stil === "tanitim"
export const takvimMi = (kaynak: string, v: SunumVeri): v is TakvimVeri => kaynak === "takvim" && "genel" in v
export const sayilarMi = (v: SunumVeri): v is GenelVeri & { stil: "sayilar" } => "stil" in v && v.stil === "sayilar"
