import { createContext, useContext } from "react"

/** Musteri ekraninin acik oldugu menu kimligi (#/<yol>?m=..). Ayni ekran Baglantili Araclar ve Toptan
 *  modullerinde de acilir; kart / rapor / TopoMaker baglantilari kullanicinin bulundugu modulde kalsin diye yol buradan okunur. */
export const MusteriYolu = createContext("musteri")

export function useMusteriYolu(): string {
  return useContext(MusteriYolu)
}
