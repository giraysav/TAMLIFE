import { useCallback, useEffect, useRef, useState } from "react"
import { apiYolu, csrfBasliklari, hareketKaydet, sonHareketSn } from "@/lib/http"

/** `*_en`: arayuz English iken gosterilen ad/aciklama (catalog.py); eski sunucuda yoksa TR kullanilir. */
export type AltOge = {
  id: string
  label: string
  label_en?: string
  description: string
  description_en?: string
  ready: boolean
}

export type MenuOgesi = AltOge & {
  group: "work" | "insights" | "admin"
  icon: string
  children: AltOge[]
}

/** Kisinin kendi profili (PUT /session/profile). `username` AD/LDAP kullanici adidir, degistirilemez. */
export type Profil = {
  username: string
  display_name: string
  ad_user: boolean
  first_name: string
  last_name: string
  phone: string
  company: string
  address: string
  website: string
  /** Profil fotografi surumu (ms); yoksa null. Adres: fotoAdresi(photo_version). */
  photo_version?: number | null
}

export type Kullanici = {
  username: string
  /** Personelin ad soyadi (kisa kullanici adi degil); ekranda bu gosterilir. */
  display_name: string
  profile: Profil
  role: string
  is_admin: boolean
  /** Sahibi oldugu yonetimli modul (tamsms | tamapn | toptan | baglantili; yoksa bos): o modulde yazma yetkisi (2026-10-20). */
  module_owner?: string
  idle_timeout_minutes: number
  landing: string
  navigation: MenuOgesi[]
}

export type OturumDurumu = "yukleniyor" | "yok" | "var"

const YENILE_ARALIK_MS = 2 * 60 * 1000
const TAZELE_ESIK_MS = 60 * 1000
const OLAYLAR = ["pointerdown", "keydown", "scroll"] as const

class OturumYok extends Error {}

export type GirisSonucu = "ok" | "red" | "kilit" | "ag"

export function useOturum() {
  const [durum, setDurum] = useState<OturumDurumu>("yukleniyor")
  const [kullanici, setKullanici] = useState<Kullanici | null>(null)
  const sonYenileme = useRef(Date.now())

  const yukle = useCallback(async (): Promise<boolean> => {
    try {
      const cevap = await fetch(apiYolu("/api/v1/session/me"), { credentials: "same-origin" })
      if (cevap.status === 401) throw new OturumYok()
      if (!cevap.ok) throw new Error(String(cevap.status))
      const govde = (await cevap.json()) as { data: Kullanici }
      setKullanici(govde.data)
      setDurum("var")
      sonYenileme.current = Date.now()
      return true
    } catch (hata) {
      // Yalniz sunucunun "oturum yok" demesi cikis sayilir. Ag kopmasi / panel yeniden baslatmasi (5xx) acik oturumu dusurmez.
      if (hata instanceof OturumYok) {
        setKullanici(null)
        setDurum("yok")
        return false
      }
      setDurum((onceki) => (onceki === "yukleniyor" ? "yok" : onceki))
      return false
    }
  }, [])

  useEffect(() => {
    void yukle()
  }, [yukle])

  useEffect(() => {
    const bitti = () => {
      setKullanici(null)
      setDurum("yok")
    }
    window.addEventListener("tamlife:oturum-bitti", bitti)
    return () => window.removeEventListener("tamlife:oturum-bitti", bitti)
  }, [])

  // Bosta sure: kullanici hareketsizse sunucudakiyle ayni sinirda istemci de kapanir;
  // hareket varsa sunucu oturumu periyodik olarak canli tutulur.
  useEffect(() => {
    if (durum !== "var" || !kullanici) return
    const sinirMs = kullanici.idle_timeout_minutes * 60 * 1000
    const hareket = () => {
      hareketKaydet()
      // Sessizlikten sonraki ilk harekette sunucu oturumunu hemen tazele: sunucu bosta sureyi son istekten sayar.
      if (Date.now() - sonYenileme.current > TAZELE_ESIK_MS) void yukle()
    }
    for (const olay of OLAYLAR) window.addEventListener(olay, hareket, { passive: true })
    const zamanlayici = window.setInterval(() => {
      const simdi = Date.now()
      if (sonHareketSn() * 1000 > sinirMs) {
        void fetch(apiYolu("/api/v1/session/logout"), {
          method: "POST",
          credentials: "same-origin",
          headers: csrfBasliklari(),
        }).finally(() => window.dispatchEvent(new Event("tamlife:oturum-bitti")))
        return
      }
      if (simdi - sonYenileme.current > YENILE_ARALIK_MS && sonHareketSn() * 1000 < YENILE_ARALIK_MS) {
        void yukle()
      }
    }, 15 * 1000)
    return () => {
      window.clearInterval(zamanlayici)
      for (const olay of OLAYLAR) window.removeEventListener(olay, hareket)
    }
  }, [durum, kullanici, yukle])

  const giris = useCallback(
    async (ad: string, parola: string): Promise<GirisSonucu> => {
      try {
        const cevap = await fetch(apiYolu("/api/v1/session/login"), {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: ad.trim(), password: parola }),
        })
        if (cevap.status === 429) return "kilit"
        if (!cevap.ok) return "red"
        hareketKaydet()
        return (await yukle()) ? "ok" : "red"
      } catch {
        return "ag"
      }
    },
    [yukle],
  )

  const cikis = useCallback(async () => {
    try {
      await fetch(apiYolu("/api/v1/session/logout"), {
        method: "POST",
        credentials: "same-origin",
        headers: csrfBasliklari(),
      })
    } finally {
      setKullanici(null)
      setDurum("yok")
    }
  }, [])

  return { durum, kullanici, giris, cikis, yenile: yukle }
}
