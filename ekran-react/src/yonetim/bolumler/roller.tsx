import type { Dil } from "@/shell/metin"
import { RollerSayfasi } from "@/shell/roller-sayfasi"

/** Roller: mevcut rol gorunumu ekrani Yonetim altina tasindi (admin tam yetkili; salt okunur mod yalniz admin disi icindir). */
export default function Roller({ dil }: { dil: Dil }) {
  return <RollerSayfasi dil={dil} saltOkunur={false} />
}
