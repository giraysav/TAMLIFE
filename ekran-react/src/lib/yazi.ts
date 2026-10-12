import { useSyncExternalStore } from "react"

/**
 * Panel yazi/gorunum olcegi: tum arayuz rem tabanlidir, <html data-yazi> kok yazi boyutunu degistirince harf, dugme, bosluk ve
 * simgeler birlikte orantili buyur. Tek ayar noktasi YAZI_OLCEKLERI; kullanici hesap menusunden secer, secim tarayicida hatirlanir.
 * Varsayilan "buyuk" (1.125x): onceki boyuttan bir basamak buyuk.
 */

export type YaziBoyutu = "normal" | "buyuk" | "cok"

export const YAZI_OLCEKLERI: Record<YaziBoyutu, number> = { normal: 1, buyuk: 1.125, cok: 1.25 }
export const YAZI_VARSAYILAN: YaziBoyutu = "buyuk"

const ANAHTAR = "tamlife.yazi"
const OLAY = "tamlife:yazi"

export function yaziOku(): YaziBoyutu {
  try {
    const ham = window.localStorage.getItem(ANAHTAR)
    return ham === "normal" || ham === "buyuk" || ham === "cok" ? ham : YAZI_VARSAYILAN
  } catch {
    return YAZI_VARSAYILAN
  }
}


/** `<html data-yazi>` ozelligini gecerli tercihle esler (CSS kok yazi boyutu buna bakar). */
export function yaziUygula(): void {
  document.documentElement.dataset.yazi = yaziOku()
}

export function yaziDegistir(yeni: YaziBoyutu): void {
  try {
    window.localStorage.setItem(ANAHTAR, yeni)
  } catch {
    /* depolama kapali: secim yalniz bu sayfa omru boyunca gecerli olmaz; ozellik yine de guncellenir */
  }
  document.documentElement.dataset.yazi = yeni
  window.dispatchEvent(new Event(OLAY))
}

function abone(bildir: () => void): () => void {
  const yenile = () => {
    yaziUygula()
    bildir()
  }
  window.addEventListener(OLAY, yenile)
  window.addEventListener("storage", yenile)
  yaziUygula()
  return () => {
    window.removeEventListener(OLAY, yenile)
    window.removeEventListener("storage", yenile)
  }
}

/** Gecerli yazi boyutu; degisince tum kullananlar yenilenir. */
export function useYazi(): YaziBoyutu {
  return useSyncExternalStore(abone, yaziOku, () => YAZI_VARSAYILAN)
}
