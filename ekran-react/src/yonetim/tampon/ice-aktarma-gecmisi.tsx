import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Undo2 } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Bildirim, DUGME, HataKutu, Panel, Rozet, VeriTablosu } from "@/components/sayfa-ui"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { zaman } from "@/lib/bicim"
import { ANAHTAR } from "@/yonetim/api"
import type { DosyaAktarimi, DosyaAktarimiGeriAl } from "@/yonetim/api"
import { tm } from "@/yonetim/tampon/metin"

/** Elle yuklenen dosya aktarimlari (Urun-Tutar, Gelir Faydasi, Proje) ve geri alma (2026-11-01 kullanici: "importa manuel eklenen
 *  dosya olursa geri alma secenegi de olmali"). Sonradan elle degistirilen kayitlar korunur (sunucu kurali). */
export function IceAktarmaGecmisi({ dil }: { dil: Dil }) {
  const g = tm(dil).gecmis
  const qc = useQueryClient()
  const [bilgi, setBilgi] = useState<{ ton: "yesil" | "kirmizi"; metin: string } | null>(null)
  const liste = useQuery({ queryKey: ANAHTAR.iceAktarmalar, queryFn: () => oku<DosyaAktarimi[]>("/api/v1/tampon/ice-aktarmalar") })
  const geriAl = useMutation({
    mutationFn: (id: number) => yaz<DosyaAktarimiGeriAl>("POST", `/api/v1/tampon/ice-aktarmalar/${id}/geri-al`),
    onSuccess: (s) => {
      setBilgi({ ton: "yesil", metin: g.geriAlindi(s.geri_alinan, s.korunan) })
      void qc.invalidateQueries()  // urun-tutar, gelir ve proje ekranlari da tazelenir
    },
    onError: (h) => setBilgi({ ton: "kirmizi", metin: hataMesaji(h, g.hata) }),
  })

  return (
    <Panel baslik={g.baslik} aciklama={g.aciklama}>
      <div className="grid gap-3">
        {bilgi ? <Bildirim ton={bilgi.ton}>{bilgi.metin}</Bildirim> : null}
        {liste.isError ? <HataKutu metin={hataMesaji(liste.error, g.hata)} /> : null}
        <VeriTablosu<DosyaAktarimi>
          baslik={g.baslik}
          satirlar={liste.data ?? []}
          anahtar={(k) => k.id}
          bos={<p className="text-xs font-bold text-slate-400">{g.yok}</p>}
          kolonlar={[
            { baslik: g.zaman, hucre: (k) => <span className="whitespace-nowrap">{zaman(k.zaman)}</span> },
            { baslik: g.tur, hucre: (k) => <Rozet ton="sari">{g.turler[k.tur] ?? k.tur}</Rozet> },
            { baslik: g.dosya, hucre: (k) => <span className="break-words font-bold text-tl-navy">{k.dosya || "—"}</span> },
            { baslik: g.sonuc, hucre: (k) => g.ozet(k) },
            { baslik: g.kullanici, hucre: (k) => k.kullanici },
            {
              baslik: "",
              sinif: "whitespace-nowrap text-right",
              hucre: (k) =>
                k.geri_alinan ? (
                  <Rozet>{g.geriAlinmis}</Rozet>
                ) : (
                  <button
                    type="button"
                    className={DUGME}
                    disabled={geriAl.isPending}
                    aria-label={`${g.geriAl}: ${k.dosya}`}
                    onClick={() => {
                      if (window.confirm(g.geriAlOnay)) geriAl.mutate(k.id)
                    }}
                  >
                    <Undo2 aria-hidden className="size-3.5" />
                    {g.geriAl}
                  </button>
                ),
            },
          ]}
        />
      </div>
    </Panel>
  )
}
