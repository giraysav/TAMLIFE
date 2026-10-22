import type { Dil } from "@/shell/metin"
import { Bos, Panel } from "@/components/sayfa-ui"
import { uym } from "@/yonetim/utilizasyon/metin"

/** TAM Utilizasyon > Iptal talepleri (2026-10-22: sekme acildi, icerik kullanicidan ayrica gelecek). */
export function IptalTalepleri({ dil }: { dil: Dil }) {
  const u = uym(dil).util
  return (
    <Panel baslik={u.sekme.iptal}>
      <Bos>{u.iptalAciklama}</Bos>
    </Panel>
  )
}
