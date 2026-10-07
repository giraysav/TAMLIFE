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

// --- Tipler (sunucu yanitlari; api-types.ts yeniden uretilince bunlara baglanabilir) ------------------------------------
export type Durum3 = "ok" | "uyari" | "hata"

export type Kontrol = { id: string; durum: Durum3; ayrinti: string; veri: Record<string, unknown> }
export type Baglanti = { id: string; slot: string; configured: boolean }
export type Ozet = {
  saglik: { genel: Durum3; zaman: string; kontroller: Kontrol[] }
  gostergeler: {
    veritabani: { motor: string; boyut_bayt: number | null; surum: string | null; surum_uyumlu: boolean | null }
    ariza: { acik: number; son_24s: number; son_24s_hata: number; son_zaman: string | null }
    gunluk: { son_24s: number; red_24s: number; toplam: number }
    oturum: { aktif: number }
    tampon: {
      hazir_parti: number
      kural: number
      kural_etkin: number
      son: { id: number; kaynak: string; durum: string; satir: number; zaman: string | null } | null
    }
  }
  baglantilar: Baglanti[]
}

export type Yedek = { ad: string; boyut_bayt: number; zaman: string | null }
export type Veritabani = {
  motor: string
  dosya: string | null
  boyut_bayt: number | null
  disk_serbest_bayt: number | null
  surum: string | null
  hedef_surum: string | null
  surum_uyumlu: boolean | null
  eksik_tablolar: string[]
  tablolar: { ad: string; modul: string; var: boolean; satir: number | null }[]
  toplam_satir: number
  butunluk: string | null
  yedek: { dizin: string; desteklenir: boolean; saklanan: number; adet: number; liste: Yedek[] }
}

export type Ariza = {
  id: number
  kayit_no: string
  kod: string
  seviye: "error" | "warning"
  kaynak: string
  mesaj: string
  istisna: string
  kullanici: string
  zaman: string | null
  durum: "open" | "ack" | "closed"
  not: string
  kapatan: string
  kapanis: string | null
  cozum_adimi: string
}
export type Sayfali<T> = { toplam: number; sayfa: number; adet: number; satirlar: T[] }
export type ArizaKodu = { kod: string; aciklama: string; cozum: string }

export type Olay = { id: number; zaman: string | null; kullanici: string; olay: string; sonuc: "allow" | "deny" | string; modul: string; ayrinti: string }
export type Oturum = { username: string; role: string; is_admin: boolean; age_s: number; idle_s: number }
export type GunlukDosyasi = { dosya: string; var: boolean; satirlar: string[] }

export type Kaynak = {
  anahtar: string
  ad: string
  tur: "dosya" | "ornek" | "oracle"
  hazir: boolean
  neden: string
  yapilandirma: "tamam" | "eksik" | "kapalı"
  eksik: string[]
  parti_sayisi: number
  son: { id: number; durum: string; satir: number; zaman: string | null; hata: string } | null
}
export type Parti = {
  id: number
  kaynak: string
  etiket: string
  durum: "receiving" | "ready" | "failed" | "rejected"
  satir: number
  sutun_sayisi: number
  hata: string
  olusturan: string
  zaman: string | null
  bitis: string | null
}
export type SutunProfili = { sutun: string; dolu: number; farkli: number | string; tip: string; en_sik: [string, number][] }
export type Oneri = { kolon: string; alan: string; farkli: number; eslesen: number; oran: number }
export type Analiz = { ornek_satir: number; toplam_satir: number; musteri_sayisi: number; oneriler: Oneri[]; uyarilar: string[] }
export type PartiAyrintisi = Parti & { sutunlar: string[]; profil: SutunProfili[]; analiz: Analiz | null; kullanimda: boolean }
export type PartiSatirlari = { basliklar: string[]; satirlar: (string | null)[][]; toplam: number; sayfa: number; adet: number }

export type Katalog = {
  hedefler: { anahtar: string; ad: string; sutun: string; tip: "sayi" | "metin" }[]
  islemler: { anahtar: string; ad: string; tip: "sayi" | "metin" }[]
  islecler: string[]
  degersiz_islecler: string[]
  eslesme_alanlari: { anahtar: string; ad: string }[]
}
export type Kosul = { kolon: string; islec: string; deger: string }
export type Kural = {
  id: number
  ad: string
  kaynak: string
  eslesme_alani: string
  anahtar_sutunu: string
  hedef: string
  islem: string
  deger_sutunu: string
  kosullar: Kosul[]
  eslesmeyeni_sifirla: boolean
  en_buyuk_yas_dk: number | null
  etkin: boolean
  olusturan: string
  guncelleme: string | null
}
export type KuralGovdesi = {
  name: string
  source_key: string
  match_field: string
  key_column: string
  target: string
  operation: string
  value_column: string
  conditions: Kosul[]
  zero_unmatched: boolean
  max_age_minutes: number | null
}
export type Onizleme = {
  toplam_satir: number
  kosul_disi: number
  eslesen_musteri: number
  degisecek: number
  sifirlanacak: number
  degismeyen: number
  eslesmeyen_satir: number
  belirsiz_satir: number
  gecersiz: number
  uyarilar: string[]
  ornek: { musteri_id: number; ad: string; eski: string | number | null; yeni: string | number | null; sifirlama: boolean }[]
}
export type Uygulama = {
  run_id: string
  kural_id: number
  kural: string
  parti_id: number
  hedef: string
  hedef_adi: string
  kullanici: string
  zaman: string | null
  yazilan: number
  geri_alinan: number
}

// --- Sorgu anahtarlari --------------------------------------------------------------------------------------------------
export const ANAHTAR = {
  ozet: ["yonetim", "ozet"] as const,
  veritabani: ["yonetim", "veritabani"] as const,
  arizalar: ["yonetim", "arizalar"] as const,
  arizaKodlari: ["yonetim", "ariza-kodlari"] as const,
  gunlukler: ["yonetim", "gunlukler"] as const,
  oturumlar: ["yonetim", "oturumlar"] as const,
  uygulamaGunlugu: ["yonetim", "uygulama-gunlugu"] as const,
  kaynaklar: ["tampon", "kaynaklar"] as const,
  partiler: ["tampon", "partiler"] as const,
  parti: ["tampon", "parti"] as const,
  hedefler: ["tampon", "hedefler"] as const,
  kurallar: ["tampon", "kurallar"] as const,
  uygulamalar: ["tampon", "uygulamalar"] as const,
}

/** {a: "x", b: ""} -> "?a=x" (bos degerler atilir). */
export function sorguMetni(degerler: Record<string, string | number | null | undefined>): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(degerler)) if (v !== null && v !== undefined && v !== "") p.set(k, String(v))
  const metin = p.toString()
  return metin ? `?${metin}` : ""
}
