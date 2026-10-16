import { useSyncExternalStore } from "react"

/**
 * Animasyon tercihi: "sistem" (isletim sistemi `prefers-reduced-motion` ayarini izler), "ac" ya da "kapat".
 * Kullanici hesap menusunden degistirir; secim tarayicida hatirlanir. Bazi sunucu/RDP oturumlari hareketi sistem duzeyinde
 * kapali bildirir; "ac" secimi yalniz bu panel icin gecerlidir ve isletim sistemi ayarina dokunmaz.
 * <html data-hareket="ac|kapat"> CSS animasyonlarini (`.tl-hareket`) yonetir.
 */

export type HareketTercihi = "sistem" | "ac" | "kapat"

const ANAHTAR = "tamlife.hareket"
const OLAY = "tamlife:hareket"

function sistemAzHareket(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
}

function tercihOku(): HareketTercihi {
  try {
    const ham = window.localStorage.getItem(ANAHTAR)
    return ham === "ac" || ham === "kapat" ? ham : "sistem"
  } catch {
    return "sistem"
  }
}

export function hareketVarMi(tercih: HareketTercihi = tercihOku()): boolean {
  return tercih === "ac" || (tercih === "sistem" && !sistemAzHareket())
}

/** `<html data-hareket>` ozelligini gecerli tercihle esler (CSS animasyonlari buna bakar). */
export function hareketUygula(): void {
  document.documentElement.dataset.hareket = hareketVarMi() ? "ac" : "kapat"
}

export function hareketDegistir(): void {
  const yeni: HareketTercihi = hareketVarMi() ? "kapat" : "ac"
  try {
    window.localStorage.setItem(ANAHTAR, yeni)
  } catch {
    /* depolama kapali: yalniz bu oturumda gecerli olmaz; ozellik yine de guncellenir */
  }
  hareketUygula()
  window.dispatchEvent(new Event(OLAY))
}

function abone(bildir: () => void): () => void {
  const yenile = () => {
    hareketUygula()
    bildir()
  }
  window.addEventListener(OLAY, yenile)
  window.addEventListener("storage", yenile)
  const mq = typeof window.matchMedia === "function" ? window.matchMedia("(prefers-reduced-motion: reduce)") : null
  mq?.addEventListener("change", yenile)
  hareketUygula()
  return () => {
    window.removeEventListener(OLAY, yenile)
    window.removeEventListener("storage", yenile)
    mq?.removeEventListener("change", yenile)
  }
}

/** Gecerli animasyon durumu (true = hareket serbest). Tercih degisince tum kullananlar yenilenir. */
export function useHareket(): boolean {
  return useSyncExternalStore(abone, () => hareketVarMi(), () => true)
}
