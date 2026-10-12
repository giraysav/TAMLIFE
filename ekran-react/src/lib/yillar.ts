/**
 * Panelin yil secenekleri: 2026'dan baslar, ileriye dogru gider (2026-10-11 istegi: 2024/2025 gosterilmez, 2027-2028 gibi
 * ileri yillar secilebilir). Yalniz filtre/takvim secimlerini etkiler; yonetim konsolundan iceri alinan verinin tarihine dokunmaz.
 */
export const ILK_YIL = 2026
export const ILK_TARIH = `${ILK_YIL}-01-01`

/** ILK_YIL .. (bu yil + ileri), artan sirada. */
export function yilSecenekleri(ileri = 2, bugun = new Date()): number[] {
  const son = Math.max(ILK_YIL, bugun.getFullYear()) + ileri
  return Array.from({ length: son - ILK_YIL + 1 }, (_, i) => ILK_YIL + i)
}

/** Varsayilan secili yil: bu yil (ILK_YIL'dan once olamaz). */
export function varsayilanYil(bugun = new Date()): number {
  return Math.max(ILK_YIL, bugun.getFullYear())
}
