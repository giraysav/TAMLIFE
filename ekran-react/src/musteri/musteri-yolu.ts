import { createContext, useContext } from "react"

/** Musteri ekraninin acik oldugu menu kimligi (#/<yol>?m=..). Ayni ekran Baglantili Araclar ve Toptan
 *  modullerinde de acilir; kart / rapor / TopoMaker baglantilari kullanicinin bulundugu modulde kalsin diye yol buradan okunur. */
export const MusteriYolu = createContext("musteri")

export function useMusteriYolu(): string {
  return useContext(MusteriYolu)
}

/** Kartin sunucudaki modulu (musteri | toptan | baglantili) bulunulan ekrandan farkliysa o modulun yolu (2026-10-20: segmenti WHOLESALE
 *  olan cati kart iştirakleriyle Toptan'a gecer; kayittan sonra kart o ekranda acilir). Modul anahtarlari menu yollariyla aynidir. */
export function modulYolu(modul: string | undefined, yol: string): string {
  return modul && modul !== yol ? modul : yol
}
