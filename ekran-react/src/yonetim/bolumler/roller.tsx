import type { Dil } from "@/shell/metin"
import { RollerSayfasi } from "@/shell/roller-sayfasi"

/** Roller: rol gorunumu ekrani Yonetim altindadir; Yonetim alani yalniz admine acik oldugu icin salt okunur mod yoktur. */
export default function Roller({ dil }: { dil: Dil }) {
  return <RollerSayfasi dil={dil} />
}
