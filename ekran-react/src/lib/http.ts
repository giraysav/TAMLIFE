/** Vite taban yolu: "/" ya da arayuz bir alt yolda sunuluyorsa "/panel/". */
const TABAN = import.meta.env.BASE_URL.replace(/\/+$/, "")
/** API yoluna taban yolunu ekler; tum fetch cagrilari bunu kullanir. */
export const apiYolu = (yol: string) => TABAN + yol

/** Oturum yok: sunucu 401 dondu. */
export const oturumYok = (cevap: Response) => cevap.status === 401

/** Durum degistiren isteklerde CSRF basligi (cift gonderim cerezi). */
export function csrfBasliklari(ekstra: Record<string, string> = {}): Record<string, string> {
  const eslesme = document.cookie.match(/(?:^|;\s*)tamlife_csrf=([^;]+)/)
  return eslesme ? { ...ekstra, "X-CSRF-Token": decodeURIComponent(eslesme[1]) } : ekstra
}
