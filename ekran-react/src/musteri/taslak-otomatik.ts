import { useCallback, useEffect, useRef, useState } from "react"
import type { MutableRefObject } from "react"
import { ApiHata, yaz } from "@/lib/sorgu"

/** Yazim durduktan sonra sunucuya yazmadan once beklenen sure. */
export const OTOMATIK_GECIKME = 1500
const YENIDEN_DENE = 20_000

export type KayitDurumu =
  | { tur: "" }
  | { tur: "kaydediliyor" }
  | { tur: "kaydedildi"; saat: string }
  | { tur: "bekliyor" }
  | { tur: "kilitli" }
  | { tur: "hata"; mesaj: string }

/** Tarayicidaki yedek: sunucuya ulasamadan kalan son hal. `taban`: yedegin ustune yazildigi sunucu taslaginin zamani. */
export type TaslakYedegi = { alanlar: Record<string, string>; taban: string; zaman: string }

export const yedekAnahtari = (musteriId: number, yil: number, ay: number) => `tamlife-rapor-taslak:${musteriId}:${yil}-${String(ay).padStart(2, "0")}`

export function yedekOku(anahtar: string): TaslakYedegi | null {
  try {
    const ham = localStorage.getItem(anahtar)
    const y = ham ? (JSON.parse(ham) as TaslakYedegi) : null
    return y && typeof y.alanlar === "object" && y.alanlar ? y : null
  } catch {
    return null
  }
}

function yedekYaz(anahtar: string, yedek: TaslakYedegi) {
  try {
    localStorage.setItem(anahtar, JSON.stringify(yedek))
  } catch {
    // dolu / kapali depolama: sunucu kaydi yine denenir
  }
}

export function yedekSil(anahtar: string) {
  try {
    localStorage.removeItem(anahtar)
  } catch {
    // yok sayilir
  }
}

/**
 * Sunucu taslagi yuklenince yedekle karsilastirir: yedek ayni sunucu surumunun ustune yazilmis ve farkliysa geri yuklenecek
 * alanlari dondurur. Sunucu daha yeniyse (baskasi / elle kaydedildi) ya da donem gonderildiyse yedek silinir.
 * Sunucu yedekten eskiyse (onbellekteki eski yanit) yedege dokunulmaz: tazelenen yanit gelince yeniden bakilir.
 */
export function yedektenGeriYukle(anahtar: string, sunucu: { alanlar: Record<string, string>; zaman: string | null; gonderildi: boolean }): Record<string, string> | null {
  const y = yedekOku(anahtar)
  if (!y) return null
  const zaman = sunucu.zaman ?? ""
  if (sunucu.gonderildi || zaman > y.taban || JSON.stringify(y.alanlar) === JSON.stringify(sunucu.alanlar)) {
    yedekSil(anahtar)
    return null
  }
  return zaman === y.taban ? y.alanlar : null
}

const saatYaz = (t: Date) => `${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}`

/** Bir kayit icin gereken her sey, istek baslarken donduruldugu haliyle (donem degisse de eski doneme yazilir). */
type Baglam = {
  anahtar: string | null
  adres: string
  alanlar: Record<string, string>
  etkin: boolean
  onKaydedildi: (alanlar: Record<string, string>, zaman: string) => void
}

/**
 * Aylik rapor taslaginin otomatik kaydi (2026-11-03 kullanici: "taslakta yapilan her degisiklik otomatik kaydedilsin; erisim
 * gittiginde ya da sayfa degisirse direkt kaydetsin"):
 * - her degisiklik aninda tarayiciya yedeklenir, yazim OTOMATIK_GECIKME durunca sunucuya yazilir;
 * - sekme gizlenince, sayfa kapanirken (keepalive), donem degisince ve rapor ekrani kapaninca beklemeden yazilir;
 * - sunucuya ulasilamazsa (ag, oturum bitti) yedek kalir; baglanti gelince / araliklarla yeniden denenir, ekran yeniden
 *   acilinca `yedektenGeriYukle` ile forma geri gelir.
 * `anahtar` null: form bu donemin taslagiyla henuz doldurulmadi (kayit yapilmaz). `kaydedilen`: sunucudaki halin JSON'u.
 */
export function useTaslakOtomatikKayit(p: Baglam & { kaydedilen: MutableRefObject<string>; taban: MutableRefObject<string> }) {
  const { kaydedilen, taban } = p
  const [durum, setDurum] = useState<KayitDurumu>({ tur: "" })
  const son = useRef<Baglam>(p)
  // Isleyici (passive) etkide guncellenir: donem degisirken / kapanirken temizlik once calisir ve eski donemin halini gorur.
  useEffect(() => {
    son.current = { anahtar: p.anahtar, adres: p.adres, alanlar: p.alanlar, etkin: p.etkin, onKaydedildi: p.onKaydedildi }
  })
  const ucusta = useRef(false)
  const bekleyen = useRef(false)

  const kaydet = useCallback(
    async (b: Baglam, zorla = false): Promise<boolean> => {
      if (!b.etkin || !b.anahtar) return false
      const json = JSON.stringify(b.alanlar)
      if (json === kaydedilen.current && !zorla) return true
      if (ucusta.current) {
        bekleyen.current = true
        return false
      }
      ucusta.current = true
      setDurum({ tur: "kaydediliyor" })
      try {
        const sonuc = await yaz<{ zaman: string }>("PUT", b.adres, { alanlar: b.alanlar }, true)
        const ayniDonem = son.current.anahtar === b.anahtar
        if (ayniDonem) {
          kaydedilen.current = json
          taban.current = sonuc.zaman
        }
        // Istek surerken yazilmaya devam edildiyse yedek kalir, yeni sunucu surumunun ustune.
        if (!ayniDonem || JSON.stringify(son.current.alanlar) === json) yedekSil(b.anahtar)
        else yedekYaz(b.anahtar, { alanlar: son.current.alanlar, taban: sonuc.zaman, zaman: new Date().toISOString() })
        b.onKaydedildi(b.alanlar, sonuc.zaman)
        setDurum({ tur: "kaydedildi", saat: saatYaz(new Date()) })
        return true
      } catch (h) {
        const kod = h instanceof ApiHata ? h.durum : 0
        if (kod === 409) setDurum({ tur: "kilitli" })
        else if (kod === 0 || kod === 401) setDurum({ tur: "bekliyor" })
        else setDurum({ tur: "hata", mesaj: h instanceof Error ? h.message : "" })
        return false
      } finally {
        ucusta.current = false
        if (bekleyen.current) {
          bekleyen.current = false
          if (JSON.stringify(son.current.alanlar) !== kaydedilen.current) void kaydet(son.current)
        }
      }
    },
    [kaydedilen, taban],
  )

  // Her degisiklik: once tarayiciya yedek, yazim durunca sunucuya.
  useEffect(() => {
    if (!p.etkin || !p.anahtar) return
    if (JSON.stringify(p.alanlar) === kaydedilen.current) return
    yedekYaz(p.anahtar, { alanlar: p.alanlar, taban: taban.current, zaman: new Date().toISOString() })
    const zamanlayici = window.setTimeout(() => void kaydet(son.current), OTOMATIK_GECIKME)
    return () => window.clearTimeout(zamanlayici)
  }, [p.alanlar, p.etkin, p.anahtar, kaydedilen, taban, kaydet])

  // Donem degisince ya da rapor ekrani kapaninca (musteri kartinda baska sekme, baska sayfa) beklemeden yaz.
  useEffect(() => {
    if (!p.anahtar) return
    return () => void kaydet(son.current)
  }, [p.anahtar, kaydet])

  // Sekme gizlenince / sayfa kapanirken / baglanti geri gelince.
  useEffect(() => {
    const hemen = () => void kaydet(son.current)
    const gorunurluk = () => {
      if (document.visibilityState === "hidden") hemen()
    }
    document.addEventListener("visibilitychange", gorunurluk)
    window.addEventListener("pagehide", hemen)
    window.addEventListener("online", hemen)
    return () => {
      document.removeEventListener("visibilitychange", gorunurluk)
      window.removeEventListener("pagehide", hemen)
      window.removeEventListener("online", hemen)
    }
  }, [kaydet])

  // Sunucuya ulasilamiyorken araliklarla yeniden dene (oturum yenilenince de kendiliginden yazar).
  useEffect(() => {
    if (durum.tur !== "bekliyor") return
    const aralik = window.setInterval(() => void kaydet(son.current), YENIDEN_DENE)
    return () => window.clearInterval(aralik)
  }, [durum.tur, kaydet])

  return {
    durum,
    /** "Taslagi kaydet" dugmesi: beklemeden yazar (degisiklik yoksa da). */
    simdi: () => kaydet({ anahtar: p.anahtar, adres: p.adres, alanlar: p.alanlar, etkin: p.etkin, onKaydedildi: p.onKaydedildi }, true),
    sifirla: () => setDurum({ tur: "" }),
  }
}
