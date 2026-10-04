/** Vite taban yolu: "/" ya da uretim panelinin arkasinda "/admin/dev/". */
const TABAN = import.meta.env.BASE_URL.replace(/\/+$/, "")
/** Uretim panelinin (Flask) arkasinda mi calisiyoruz: oturum SSO ile acilir, cikis uretim paneline doner. */
export const GOMULU = TABAN !== ""
/** API yoluna taban yolu ekler; tum fetch cagrilari bunu kullanir. */
export const apiYolu = (yol: string) => TABAN + yol

/** Oturum yok: 401, ya da gomulu modda uretim paneli giris sayfasina yonlendirmis (kendi oturumu bitmis). */
export const oturumYok = (cevap: Response) => cevap.status === 401 || (GOMULU && cevap.redirected)

/** Durum degistiren isteklerde CSRF basligi (cift gonderim cerezi). */
export function csrfBasliklari(ekstra: Record<string, string> = {}): Record<string, string> {
  const eslesme = document.cookie.match(/(?:^|;\s*)tamlife_csrf=([^;]+)/)
  return eslesme ? { ...ekstra, "X-CSRF-Token": decodeURIComponent(eslesme[1]) } : ekstra
}
