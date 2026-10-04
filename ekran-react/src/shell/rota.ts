import { useEffect, useState } from "react"

/** Adres cubugu: #/yol?anahtar=deger. Yol menu kimligidir; sorgu sayfa icindeki secimi tasir (geri oku calisir). */
export function hashParcala(): { yol: string; sorgu: URLSearchParams } {
  const ham = window.location.hash.replace(/^#\/?/, "")
  const [yol, sorgu = ""] = ham.split("?")
  return { yol: decodeURIComponent(yol), sorgu: new URLSearchParams(sorgu) }
}

export function useHashSorgu(): URLSearchParams {
  const [sorgu, setSorgu] = useState(() => hashParcala().sorgu)
  useEffect(() => {
    const degisti = () => setSorgu(hashParcala().sorgu)
    window.addEventListener("hashchange", degisti)
    return () => window.removeEventListener("hashchange", degisti)
  }, [])
  return sorgu
}

/** Ayni sayfada sorguyu degistirir (yeni gecmis kaydi acar). */
export function sorguAyarla(yol: string, degerler: Record<string, string | null>) {
  const sorgu = new URLSearchParams()
  for (const [k, v] of Object.entries(degerler)) if (v) sorgu.set(k, v)
  const metin = sorgu.toString()
  window.location.hash = `#/${yol}${metin ? `?${metin}` : ""}`
}
