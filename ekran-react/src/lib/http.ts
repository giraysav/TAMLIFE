/** Durum degistiren isteklerde CSRF basligi (cift gonderim cerezi). */
export function csrfBasliklari(ekstra: Record<string, string> = {}): Record<string, string> {
  const eslesme = document.cookie.match(/(?:^|;\s*)tamlife_csrf=([^;]+)/)
  return eslesme ? { ...ekstra, "X-CSRF-Token": decodeURIComponent(eslesme[1]) } : ekstra
}
