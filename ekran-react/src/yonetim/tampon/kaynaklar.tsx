import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import type { UseMutationResult } from "@tanstack/react-query"
import { Download, PlugZap } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Bildirim, Bolum, DUGME, HataKutu, Rozet, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import type { BaglantiTesti, Kaynak } from "@/yonetim/api"
import { zaman } from "@/lib/bicim"
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

/** PostgreSQL iceri alma cekimi (ONEDESKDB / ONENTDB, 2026-10-25): isci ayri surecte; sonuc bildirime yazilir. */
function usePgCek(t: TM, setBilgi: (b: Bilgi) => void) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (anahtar: string) => yaz<{ basladi: boolean }>("POST", `/api/v1/tampon/pg/${encodeURIComponent(anahtar)}/cek`),
    onSuccess: (s) => {
      setBilgi({ ton: s.basladi ? "yesil" : "amber", metin: s.basladi ? t.cekimBasladi : t.cekimSuruyor })
      void qc.invalidateQueries({ queryKey: ANAHTAR.kaynaklar })
    },
    onError: (e) => setBilgi({ ton: "amber", metin: hataMesaji(e, t.islemBasarisiz) }),
  })
}

/** PostgreSQL kaynagi durumu: hazir/kapali, eksik anahtar, iceri alma sorgusu, "Simdi cek" (partisi '<kaynak>_import' satirinda). */
function PgDurum({ k, t, cek }: { k: Kaynak; t: TM; cek: UseMutationResult<{ basladi: boolean }, Error, string> }) {
  return (
    <span className="grid justify-items-start gap-0.5">
      <Rozet ton={k.hazir && k.sorgu_tamam ? "yesil" : k.hazir ? "amber" : "gri"}>{k.hazir ? t.canliHazir : t.canliKapali}</Rozet>
      <span className="text-[0.625rem] text-slate-400">
        {t.yapilandirma[k.yapilandirma]}
        {k.eksik.length ? ` · ${t.eksikAnahtar}: ${k.eksik.join(", ")}` : ""}
      </span>
      {k.hazir && !k.sorgu_tamam ? <span className="text-[0.625rem] text-amber-700">{t.sorguYok(k.sorgu_anahtari ?? "")}</span> : null}
      {k.hazir && k.sorgu_tamam ? (
        <button type="button" className={DUGME} disabled={cek.isPending} onClick={() => cek.mutate(k.anahtar)}>
          <Download aria-hidden className="size-3.5" />
          {cek.isPending && cek.variables === k.anahtar ? t.cekiliyor : t.simdiCek}
        </button>
      ) : null}
    </span>
  )
}

/** Canli DB alt sekmesi: tek Oracle kaynaginin (oracle_reportdb | oracle_galapagos) durumu ve baglanti testi. Kaynak yoksa `yokMetni`. */
export function OracleKaynakKarti({ dil, anahtar, baslik, yokMetni }: { dil: Dil; anahtar: string; baslik: string; yokMetni: string }) {
  const t = tm(dil)
  const [bilgi, setBilgi] = useState<Bilgi | null>(null)
  const q = useQuery({ queryKey: ANAHTAR.kaynaklar, queryFn: () => oku<Kaynak[]>("/api/v1/tampon/kaynaklar") })
  const test = useBaglantiTesti(t, setBilgi)
  const k = q.data?.find((x) => x.anahtar === anahtar)
  return (
    <section aria-label={baslik} className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4">
      <h3 className="text-sm font-black text-tl-navy">{baslik}</h3>
      {bilgi ? <Bildirim ton={bilgi.ton}>{bilgi.metin}</Bildirim> : null}
      {q.isPending ? (
        <Yukleniyor metin={t.yukleniyor} />
      ) : q.isError ? (
        <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void q.refetch()} />
      ) : k ? (
        <OracleDurum k={k} t={t} test={test} />
      ) : (
        <Bildirim>{yokMetni}</Bildirim>
      )}
    </section>
  )
}

/** Kaynak listesi (dosya, Oracle, PostgreSQL, CSV partileri). Dosya yukleme (Ham Musteri Verisi, genel CSV) Import sekmesindedir (2026-10-24). */
export function Kaynaklar({ dil }: { dil: Dil }) {
  const t = tm(dil)
  const [bilgi, setBilgi] = useState<Bilgi | null>(null)
  const q = useQuery({ queryKey: ANAHTAR.kaynaklar, queryFn: () => oku<Kaynak[]>("/api/v1/tampon/kaynaklar") })
  const test = useBaglantiTesti(t, setBilgi)
  const cek = usePgCek(t, setBilgi)

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
                  ) : k.tur === "postgres" ? (
                    <PgDurum k={k} t={t} cek={cek} />
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
      </div>
    </Bolum>
  )
}
