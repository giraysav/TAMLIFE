// --- Tipler (sunucu yanitlari) ------------------------------------
export type Durum3 = "ok" | "uyari" | "hata"

export type Kontrol = { id: string; durum: Durum3; ayrinti: string; veri: Record<string, unknown> }
export type Baglanti = { id: string; slot: string; tur: "dizin" | "veritabani"; configured: boolean }
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

/** Kurum Baglantilari (/yonetim/kurum): yalniz gizli olmayan ayarlar; CA yolu / grup DN'leri yalniz var-yok. */
type KurumOrtak = { id: string; label: string; state: "ready" | "incomplete" | "disabled"; missing: string[] }
export type AdBaglantisi = KurumOrtak & {
  tur: "dizin"
  bilgiler: { sunucu: string; port: number | null; ldaps: boolean; ssl: boolean; alan: string; ca_dosyasi: boolean; grup_kisiti: boolean; otomatik_ac: boolean }
}
/** Oracle: adres / servis / kullanici / parola yalniz tanimli mi (deger gelmez). */
export type OracleBaglantisi = KurumOrtak & {
  tur: "oracle"
  acma_anahtari: string
  bilgiler: { sunucu: string; port: number; servis: string; kullanici: string; parola: boolean; zaman_asimi: number; oracle_istemci: boolean; sorgu_tamam: boolean; sorgu_hata: string | null }
  son_parti: { id: number; durum: string; satir: number; zaman: string | null; hata: string } | null
  reportdb?: { kartlara_yaz: boolean; kural: number; yas_dk: number | null; taze: boolean; tazelik_dk: number }
}
export type PgKatalogOzeti = { id: number; durum: string; baslangic: string | null; bitis: string | null; kim: string; ozet: { semalar?: string[]; nesne?: number; sutun?: number }; hata: string }
export type PostgresBaglantisi = KurumOrtak & {
  tur: "postgres"
  acma_anahtari: string
  bilgiler: { sunucu: string; port: number; veritabani: string; kullanici: string; parola: boolean; ssl: string; zaman_asimi: number }
  katalog: PgKatalogOzeti | null
}
export type KurumBaglantisi = AdBaglantisi | OracleBaglantisi | PostgresBaglantisi
export type PgKaynagi = { id: string; label: string; acma_anahtari: string; acik: boolean; eksik: string[]; hazir: boolean; state: "ready" | "incomplete" | "disabled"; katalog: PgKatalogOzeti | null; son: PgKatalogOzeti | null; calisiyor: boolean }
export type PgNesneOzeti = { id: number; ad: string; tur: string; satir: number | null; sutun: number; aciklama: string }
export type PgKatalogu = { kaynak: string; son: PgKatalogOzeti | null; katalog: PgKatalogOzeti | null; calisiyor: boolean; semalar: { ad: string; nesneler: PgNesneOzeti[] }[] }
export type PgNesne = {
  id: number; sema: string; ad: string; tur: string; satir: number | null; aciklama: string
  sutunlar: { ad: string; tip: string; bos: boolean; aciklama: string }[]
  ornek: { sutunlar: string[]; satirlar: unknown[][]; not: string }
}
export type AdAdimi = { adim: "ayar" | "dns" | "tcp" | "tls" | "oturum"; durum: "ok" | "hata"; baslik: string; ayrinti: string }
export type AdTesti = { tamam: boolean; adimlar: AdAdimi[] }

export type Yedek ={ ad: string; boyut_bayt: number; zaman: string | null }
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
  yedek: {
    dizin: string
    desteklenir: boolean
    saklanan: number
    adet: number
    liste: Yedek[]
    /** Yedek klasoru verinin bulundugu diskte mi (tek disk ikisini birlikte kaybeder). */
    ayni_disk: boolean
    /** Sifreli geri donus: <yedek klasoru>\ROLLBACK (betik ve sifre ozeti yerinde mi). */
    geri_donus: { klasor: string; betik: boolean; sifre: boolean }
  }
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
  tur: "dosya" | "oracle" | "oracle_parti" | "postgres" | "pg_parti"
  hazir: boolean
  neden: string
  yapilandirma: "tamam" | "eksik" | "kapalı"
  eksik: string[]
  /** yalniz postgres: <ON EK>_IMPORT_QUERY gecerli mi ve anahtarin adi */
  sorgu_tamam?: boolean
  sorgu_anahtari?: string
  parti_sayisi: number
  son: { id: number; durum: string; satir: number; zaman: string | null; hata: string } | null
  reportdb?: { kartlara_yaz: boolean; kural: number; yas_dk: number | null; taze: boolean; tazelik_dk: number }
}
export type BaglantiTesti = { ok: boolean; mesaj: string; ipucu: string }
/** Veri akislari (GET /tampon/akislar): panele veri getiren tum yollar. bilgi = elle gelen dosya (tazelik beklentisi yok). */
export type AkisDurumu = "taze" | "bayat" | "hata" | "yok" | "bilgi"
export type VeriAkisi = {
  anahtar: string
  ad: string
  yontem: string
  yer: string
  son: string | null
  durum: AkisDurumu
  aciklama: string
  parti?: number | null
  acik?: number
  kapali?: number
  radar?: number
  sema?: boolean
}
export type VeriAkislari = { akislar: VeriAkisi[]; dagitim: { kural: number; etkin: number; son_uygulama: string | null }; uyarilar: string[]; zaman: string }
/** Musteri eslesmesi (GET /tampon/eslesme): kaynak bazinda kart / TAM eslesmesi ve en cok kayit tasiyan kartsiz numaralar. */
export type EslesmeKaynagi = { anahtar: string; ad: string; toplam: number; karta_eslesen: number; tam_atanmis: number; kartsiz: number; oran: number | null; yer: string; not: string }
export type MusteriEslesmesi = {
  kaynaklar: EslesmeKaynagi[]
  kartlar: { toplam: number; tam_atanmis: number; tam_siz: number }
  kartsiz_ilk: { musteri_no: string; ad: string; adet: number }[]
  zaman: string
}
/** Ham katalog (GET /tampon/katalog): sema -> ana nesne -> alt nesne; sutunlar nesne acilinca (GET /tampon/katalog/nesne/{id}). */
export type KatalogDugumu = {
  id: number
  ad: string
  tur: string
  satir: number | null
  analiz: string
  aciklama: string
  sutun_sayisi: number
  ornek_satir: number
  ornek_notu: string
  es_ad: string
  bolum_anahtari: string[]
  bolum_sayisi: number
  alt: KatalogDugumu[]
}
export type KaynakKatalogu = {
  kaynak: string
  katalog: { id: number; durum: string; baslangic: string | null; bitis: string | null; olusturan: string; ozet: { semalar?: string[]; nesne?: number; sutun?: number; ornek_adet?: number; sure_sn?: number }; hata: string } | null
  calisiyor: boolean
  /** calisan taramanin son adimi (ornek "TEMIP.VIEW_REPORT_ACTIVE · 2026-05") */
  ilerleme?: string
  ilerleme_sn?: number
  son_hata: string
  semalar: { ad: string; nesneler: KatalogDugumu[] }[]
  /** Arama parametreleri (ara: deger metni, alan: domain sutunu) ve Domain -> tablo -> isabetli sutun agaci */
  parametreler?: { ara: string; alan: string; degerler: string[]; saat: number; satir_siniri: number; baslangic?: string; eslesmeyen: string[] } | Record<string, never>
  parametre_agaci?: ParametreDali[]
}
export type ParametreTablosu = {
  id: number
  sahip: string
  ad: string
  ust: string
  pencere: string
  satir: number
  isabet: number
  oran: number
  sutunlar: { ad: string; isabet: number; oran: number }[]
}
export type ParametreDali = { domain: string; tablolar: ParametreTablosu[]; isabet: number; satir: number }
export type KatalogSutunu = { ad: string; tip: string; bos_olabilir: boolean; aciklama: string; doluluk?: number | null; farkli?: number; ornekler?: { deger: string; adet: number }[] }
export type KatalogNesnesi = {
  id: number
  sahip: string
  ad: string
  tur: string
  ust: string
  satir: number | null
  analiz: string
  aciklama: string
  sutunlar: KatalogSutunu[]
  ayrinti: {
    es_ad?: { sahip: string; hedef: string }
    bolum_anahtari?: string[]
    bolumler?: { adet: number; son: { ad: string; sira: number; satir: number | null; analiz: string }[] }
    indeksler?: Record<string, string[]>
    dayandigi?: string[]
    arama?: { ara?: string; pencere?: string; domain_sutunu?: string; hata?: string; ornek_degerler?: Record<string, { deger: string; adet: number }[]> }
  }
  ornek_satir: number
  ornek_notu: string
}
/** Ham veri okuyucu (GET /tampon/katalog/veri): secili domainlerde arama metnini iceren satirlar, Excel filtresiyle. */
export type KatalogVerisi = {
  id: number
  ad: string
  pencere: string
  ara: string
  domainler: string[]
  sutunlar: string[]
  isabetli: string[]
  gizlenen_bos: number
  toplam_ham: number
  toplam: number
  sayfa: number
  adet: number
  satirlar: unknown[][]
  filtreli: string[]
}
export type KatalogDegerleri = { sutun: string; farkli: number; degerler: { deger: string; adet: number }[]; kesildi: boolean }
export type KatalogOrnegi = { id: number; ad: string; basliklar: string[]; satirlar: unknown[][]; not: string; grup?: string }
/** TEMIP eslesmesi (GET /tampon/temip/eslesme): Musteri No -> kart -> sorumlu personel -> acik kayit. */
export type TemipDurumu = "kart" | "kart_personelsiz" | "radar" | "belirsiz"
export type TemipMusterisi = {
  musteri_no: string
  temip_unvan: string
  durum: TemipDurumu
  kart_id: number | ""
  panel_unvan: string
  cati: string
  personel: string
  personel_kullanici: string
  acik: number
  acik_ticketli: number
  kapali: number
  toplam: number
  aday_kartlar: string
}
export type TemipPersoneli = { personel: string; personel_kullanici: string; tam: boolean; kart: number; musteri_no: number; acik: number; acik_ticketli: number; kapali: number }
export type TemipEslesme =
  | { hazir: false; neden: string }
  | {
      hazir: true
      ozet: Record<TemipDurumu, { musteri: number; acik: number; kapali: number }>
      personel: TemipPersoneli[]
      uyari: { belirsiz_numara: string[]; personelsiz_kart: string[]; bicimsiz_kart_no: string[]; kayitsiz_numarali_kart: number }
      bagli_olmayan: number
      toplam: number
      sayfa: number
      adet: number
      musteriler: TemipMusterisi[]
    }
/** Fark (GET /tampon/fark): canli DB kayitlarinin kartla / TAM ile eslesmeyen numaralari. */
export type FarkTuru = Exclude<TemipDurumu, "kart">
export type FarkSatiri = TemipMusterisi & { durum: FarkTuru; kaynak: string }
export type FarkListesi =
  | { hazir: false; neden: string }
  | {
      hazir: true
      ozet: Record<FarkTuru, { musteri: number; kayit: number; acik: number }>
      radarda?: number
      silinen?: number
      toplam_kayit: number
      toplam: number
      sayfa: number
      adet: number
      satirlar: FarkSatiri[]
    }
export type FarkSiralama = "toplam" | "acik" | "musteri_no" | "unvan" | "durum" | "kart"
export type FarkSilinen = { musteri_no: string; temip_unvan: string; durum: FarkTuru; toplam: number; kim: string; zaman: string }
export type RadarAtamaSonucu = { atanan: number; atlanan: { musteri_no: string; neden: string }[] }
export type TopluAtamaSonucu = { atanan: number; atlanan: { musteri_no: string; neden: string }[]; kartlar: string[]; yeniden_baglanan: number; etkilenen_kart: number }
/** Ham Musteri Verisi: dosyanin katalogla karsilastirmasi. bicim: sablon | liste (takma adlar) | genis (cati/istirak). */
export type HamUyum = {
  toplam: number
  eslesen: number
  alanlar: { sutun: string; alan: string }[]
  eksik: string[]
  fazla: string[]
  zorunlu_eksik: string[]
  uyumlu: boolean
  bicim: "sablon" | "liste" | "genis"
}
export type HamDegisiklik = { alan: string; baslik: string; eski: string | number; yeni: string | number }
export type HamSatir = { sira: number; unvan: string; durum: "guncelle" | "yeni" | "hata" | "degisiklik_yok"; degisiklikler: HamDegisiklik[]; hatalar: string[]; uyarilar: string[] }
export type HamOnizleme = {
  parti_id: number
  ozet: { toplam: number; guncelle: number; degisiklik_yok: number; yeni: number; hata: number; uyari: number; alan_degisikligi: number; yeni_olustur: boolean; genis_bicim: boolean; uygulanacak: number; tanimsiz_sutunlar: string[] }
  uyum: HamUyum
  satirlar: HamSatir[]
  kesildi: number
  plan_ozeti: string
}
export type HamAktarim = { id: number; parti_id: number; zaman: string | null; kullanici: string; guncellenen: number; olusturulan: number; geri_alinan: { zaman: string; kullanici: string } | null }
export type HamGeriAl = { geri_alinan_alan: number; korunan_alan: number; silinen_musteri: number; silinemeyen_musteri: string[] }
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

// --- TAM Utilizasyon (/api/v1/skor) -------------------------------------------------------------------------------------
export type KaynakSecimi = {
  kaynak: string
  eslesme: { sutun: string; alan: string }[]
  islem: string
  sutun: string
  filtreler: { sutun: string; islec: string; deger: string }[]
  esleme: [string, string][]
}
export type Kriter = {
  title: string
  type?: string
  metric?: string
  weight: number | string
  b30?: string
  b50?: string
  b70?: string
  b100?: string
  servis_puanlari?: Record<string, number>
  servis_dahil?: string[]
  kaynak_secimi?: KaynakSecimi
}
export type KriterTablosu = { scope: "parent" | "affiliate"; version: number; criteria: Kriter[]; varsayilan: boolean; updated_by: string | null; updated_at: string | null }
export type SkorMeta = {
  kaynak_adlari: Record<string, string>
  tur_ipuclari: [string, string][]
  varsayilan_kurallar: Record<string, Record<string, string>>
  servis_puanlari: Record<string, number>
  metrikler: Record<string, string>
  sabit_puan_turleri: string[]
  islemler: Record<string, string>
  islecler: Record<string, string>
  degersiz_islecler: string[]
  eslesme_alanlari: Record<string, string>
  tur_islemleri: Record<string, string[]>
  partiler: { kaynak: string; parti: number; etiket: string; satir: number; sutunlar: string[]; zaman: string | null }[]
}
export type KriterSonucu = {
  baslik: string
  tur: string
  agirlik: number
  puan: number
  katki: number
  durum: "otomatik" | "manuel" | "eksik"
  kaynak: string | null
  deger: unknown
  varsayilan_kural: boolean
  /** Manuel puanlamada (2026-10-20) dokumdeki secim listesi: barem puani + kural metni. X sabit puanli satirda yok. */
  secenekler?: { puan: number; etiket: string }[]
  /** Manuel Servis Cesitliligi: alt kriter servisleri ve puanlari (kriter puani = alinan / toplam). */
  servisler?: { ad: string; puan: number }[]
}
export type SonAtama = { kaynak: string; atayan: string; zaman: string | null } | null
export type SkorMusterisi = {
  id: number
  ad: string
  tam: string
  tam_id: number | null
  mevcut: number | null
  yeni: number
  fark: number | null
  tamam: boolean
  eksik: string[]
  kriterler: KriterSonucu[]
  son_atama: SonAtama
}
export type KaynakDurumu = { ad: string; metrikler: string[]; hazir: boolean; neden: string }
export type SkorOnizleme = {
  /** true: veri kaynakli otomatik puanlama kapali, kriterler dokumde elle secilir. */
  manuel?: boolean
  kaynaklar: KaynakDurumu[]
  uyarilar: string[]
  kriterler: { baslik: string; tur: string; agirlik: number }[]
  musteriler: SkorMusterisi[]
  ozet: { toplam: number; hazir: number }
}
export type AtamaSonucu = { uygulanan: { id: number; ad: string; eski: number | null; yeni: number }[]; atlanan: { id: number; ad: string; neden: string }[]; degismeyen: number }
export type IstirakDugumu = { id: number; ad: string; dahil: boolean; yeni: number | null; tamam: boolean | null; eksik: string[]; kriterler: KriterSonucu[] }
export type AgacMusterisi = SkorMusterisi & { istirakler: IstirakDugumu[] }
export type AgacPersoneli = { id: number; ad: string; tam: boolean; musteri_sayisi: number; skorlu_musteri: number; toplam_puan: number; agirlik_puani: number | null; musteriler: AgacMusterisi[] }
export type DagilimSatiri = {
  id: number
  ad: string
  sira: number
  musteri_sayisi: number
  istirakli_musteri: number
  skorlu_musteri: number
  toplam_puan: number
  agirlik_puani: number | null
  hedef_fark: number
  dengeleme_musteri: number
}
export type SkorAgaci = {
  kaynaklar: KaynakDurumu[]
  kriterler: { baslik: string; tur: string; agirlik: number }[]
  uyarilar: string[]
  personel: AgacPersoneli[]
  atanmamis: AgacMusterisi[]
  tum_personel: { id: number; ad: string; tam: boolean; dahil: boolean; musteri_sayisi: number }[]
  ozet: { toplam: number; cati: number; hazir: number; istirak: number; istirak_dahil: number }
  dagilim: {
    satirlar: DagilimSatiri[]
    ozet: { tam_sayisi: number; musteri_sayisi: number; toplam_puan: number; hedef_agirlik: number; ortalama_musteri_puani: number; skorlu_musteri: number }
  }
}
export type SiralamaSatiri = { id: number; full_name: string; customer_count: number; avg_score: number; rank: number; bar_pct: number }
export type SkorTalebi = {
  id: number
  customer_id: number
  customer_name: string
  tam_id: number | null
  tam_name: string
  score: number | null
  requested_by_name: string
  requested_at: string
}
export type UrunTutarOzeti = {
  satir: number
  aktif_satir: number
  lokasyon_sayisi: number
  devre_sayisi: number
  fatura_bedeli: number
  servisler: string[]
  baglanti: string[]
  eslesmeyen_gruplar: string[]
}
export type UrunTutarKaydi = UrunTutarOzeti & { id: number; ad: string; cati: boolean; dosya: string; yukleyen: string; zaman: string | null }
export type UrunTutarYukleme = {
  eslesen: number
  kart_musterisine: number
  dosyadaki: { ad: string; musteri_no: string; satir: number }[]
  dosyadaki_adet: number
  kart_musteri_no: string
  musteriler: (UrunTutarOzeti & { id: number; ad: string })[]
}
export type KaynakOnizleme = {
  parti: number
  toplam_satir: number
  filtrelenen: number
  musteri: number
  eslesmeyen: number
  eslesmeyen_ornek: [string, number][]
  ornek: { ad: string; cati: boolean; deger: unknown; satir: number }[]
}

// --- Sorgu anahtarlari --------------------------------------------------------------------------------------------------
/** TAM Utilizasyon > Musteri Listesi (GET /yonetim/musteriler): agac sirasiyla cati, altinda istirakleri. */
export type MusteriSatiri = {
  id: number
  name: string
  segment: string
  parent_id: number | null
  parent_name: string | null
  owner_id: number | null
  owner: string | null
  affiliates: number
  score: number | null
}
export type MusteriListesi = { total: number; items: MusteriSatiri[] }
export type MusteriSilSonucu = { silinen: number; istenen: number; hepsi: boolean }
export type MusteriEkleSonucu = { eklenen: number; idler: number[]; atlanan: { ad: string; sebep: string }[] }

export const ANAHTAR = {
  musteriListesi: ["yonetim", "musteriler"] as const,
  skorKriter: ["skor", "kriterler"] as const,
  skorMeta: ["skor", "meta"] as const,
  skorAgac: ["skor", "agac"] as const,
  skorSiralama: ["skor", "siralama"] as const,
  skorTalepler: ["skor", "talepler"] as const,
  skorUrunTutar: ["skor", "urun-tutar"] as const,
  ozet: ["yonetim", "ozet"] as const,
  kurum: ["yonetim", "kurum"] as const,
  pg: ["tampon", "pg"] as const,
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
  hamAktarimlar: ["tampon", "musteri-ham", "aktarimlar"] as const,
  akislar: ["tampon", "akislar"] as const,
  eslesme: ["tampon", "eslesme"] as const,
  fark: ["tampon", "fark"] as const,
  temipEslesme: ["tampon", "temip", "eslesme"] as const,
  temipAtamalar: ["tampon", "temip", "atamalar"] as const,
  katalog: ["tampon", "katalog"] as const,
}

/** {a: "x", b: ""} -> "?a=x" (bos degerler atilir). */
