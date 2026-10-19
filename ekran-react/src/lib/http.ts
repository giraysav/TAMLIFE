/** Vite taban yolu: "/" ya da arayuz bir alt yolda sunuluyorsa "/panel/". */
const TABAN = import.meta.env.BASE_URL.replace(/\/+$/, "")
/** API yoluna taban yolunu ekler; tum fetch cagrilari bunu kullanir. */
export const apiYolu = (yol: string) => TABAN + yol

/** Oturum yok: sunucu 401 dondu. */
export const oturumYok = (cevap: Response) => cevap.status === 401

/** Sunucu metinlerinin dili (X-Dil): arayuzun secili dili; okunamazsa Turkce. */
export function dilBasligi(): Record<string, string> {
  try {
    return { "X-Dil": window.localStorage.getItem("tamlife.dil") === "en" ? "en" : "tr" }
  } catch {
    return { "X-Dil": "tr" }
  }
}

/** Toptan / Baglantili Araclar kartlari Musteri Yonetimi'nden ayridir (sunucu app.musteri_alani): bu ekranlardayken musteri karti
 *  uclarina (musteri, topoloji, rapor gonderimi) X-Musteri-Alani gider. Diger uclara gitmez; baslik yoksa alan Musteri Yonetimi'dir. */
const ALANLI_MODULLER = ["toptan", "baglantili"]
const ALANLI_UCLAR = ["/api/v1/musteri", "/api/v1/topoloji", "/api/v1/rapor/gonderim/"]
export function musteriAlaniBasligi(yol: string): Record<string, string> {
  const modul = window.location.hash.replace(/^#\/?/, "").split(/[?/]/)[0]
  return ALANLI_MODULLER.includes(modul) && ALANLI_UCLAR.some((u) => yol.startsWith(u)) ? { "X-Musteri-Alani": modul } : {}
}

/** Durum degistiren isteklerde CSRF basligi (cift gonderim cerezi). */
export function csrfBasliklari(ekstra: Record<string, string> = {}): Record<string, string> {
  const eslesme = document.cookie.match(/(?:^|;\s*)tamlife_csrf=([^;]+)/)
  return eslesme ? { ...ekstra, "X-CSRF-Token": decodeURIComponent(eslesme[1]) } : ekstra
}
