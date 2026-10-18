import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import type { UseMutationResult } from "@tanstack/react-query"
import { PlugZap } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Bildirim, Bolum, DUGME, HataKutu, Rozet, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import type { BaglantiTesti, Kaynak } from "@/yonetim/api"
import { zaman } from "@/lib/bicim"
import { GenelCsvYukle } from "@/yonetim/tampon/csv-yukle"
import { tm } from "@/yonetim/tampon/metin"
import type { TM } from "@/yonetim/tampon/metin"

type Bilgi = { ton: "yesil" | "amber"; metin: string }

/** Oracle baglanti testi (alt surecte, sonuc maskeli); sonuc bildirime yazilir. */
function useBaglantiTesti(t: TM, setBilgi: (b: Bilgi) => void) {
  return useMutation({
    mutationFn: (anahtar: string) => yaz<BaglantiTesti>("POST", `/api/v1/tampon/kaynaklar/${encodeURIComponent(anahtar)}/test`),
    onSuccess: (s) => setBilgi({ ton: s.ok ? "yesil" : "amber", metin: [s.mesaj, s.ipucu].filter(Boolean).join(" — ") }),
    onError: (e) => setBilgi({ ton: "amber", metin: hataMesaji(e, t.islemBasarisiz) }),
  })
}

/** Oracle kaynagi durumu: hazir/kapali, eksik anahtar, ReportDB tazeligi, baglanti testi (Veri Girisi ve Veritabani ortak). */
function OracleDurum({ k, t, test }: { k: Kaynak; t: TM; test: UseMutationResult<BaglantiTesti, Error, string> }) {
  return (
    <span className="grid justify-items-start gap-0.5">
      <Rozet ton={k.hazir ? "yesil" : "gri"}>{k.hazir ? t.canliHazir : t.canliKapali}</Rozet>
      <span className="text-[0.625rem] text-slate-400">
        {t.yapilandirma[k.yapilandirma]}
        {k.eksik.length ? ` · ${t.eksikAnahtar}: ${k.eksik.join(", ")}` : ""}
      </span>
      {k.reportdb ? (
        <span className="text-[0.625rem] text-slate-400">
          {t.kartlaraYaz(k.reportdb.kartlara_yaz)}
          {k.reportdb.yas_dk !== null ? ` · ${t.sonVeriYasi(k.reportdb.yas_dk, k.reportdb.taze)}` : ""}
        </span>
      ) : null}
      {k.hazir ? (
        <button type="button" className={DUGME} disabled={test.isPending} onClick={() => test.mutate(k.anahtar)}>
          <PlugZap aria-hidden className="size-3.5" />
          {test.isPending && test.variables === k.anahtar ? t.testEdiliyor : t.baglantiTesti}
        </button>
      ) : null}
    </span>
  )
}

/** Kaynak listesi (dosya, Oracle, CSV partileri) + genel CSV yukleme. Ham Musteri Verisi kendi blogundadir (HamMusteriBolumu). */
export function Kaynaklar({ dil, onYeniParti }: { dil: Dil; onYeniParti: (id: number) => void }) {
  const t = tm(dil)
  const [bilgi, setBilgi] = useState<Bilgi | null>(null)
  const q = useQuery({ queryKey: ANAHTAR.kaynaklar, queryFn: () => oku<Kaynak[]>("/api/v1/tampon/kaynaklar") })
  const test = useBaglantiTesti(t, setBilgi)

  return (
    <Bolum anahtar="yonetim-tampon-kaynaklar" baslik={t.kaynaklar}>
      <div className="grid gap-4">
        {bilgi ? <Bildirim ton={bilgi.ton}>{bilgi.metin}</Bildirim> : null}

        {q.isPending ? (
          <Yukleniyor metin={t.yukleniyor} iskelet />
        ) : q.isError ? (
          <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void q.refetch()} />
        ) : (
          <VeriTablosu<Kaynak>
            baslik={t.kaynaklar}
            satirlar={q.data}
            anahtar={(k) => k.anahtar}
            kolonlar={[
              {
                baslik: t.kaynaklar,
                hucre: (k) => (
                  <span className="grid">
                    <span className="font-black text-tl-navy">{k.ad}</span>
                    <code className="text-[0.625rem] text-slate-400">{k.anahtar}</code>
                  </span>
                ),
              },
              {
                baslik: t.durum,
                hucre: (k) =>
                  k.tur === "oracle" ? (
                    <OracleDurum k={k} t={t} test={test} />
                  ) : (
                    <Rozet ton="yesil">{t.yapilandirma.tamam}</Rozet>
                  ),
              },
              { baslik: t.partiler, hucre: (k) => t.partiAdedi(k.parti_sayisi), sinif: "text-right" },
              {
                baslik: t.sonParti,
                hucre: (k) =>
                  k.son ? (
                    <span className="whitespace-nowrap">
                      #{k.son.id} · {t.partiDurum[k.son.durum] ?? k.son.durum} · {zaman(k.son.zaman)}
                    </span>
                  ) : (
                    "—"
                  ),
              },
            ]}
          />
        )}
        <GenelCsvYukle dil={dil} onYeniParti={onYeniParti} />
      </div>
    </Bolum>
  )
}
