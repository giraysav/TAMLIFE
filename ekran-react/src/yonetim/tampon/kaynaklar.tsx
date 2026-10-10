import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { FlaskConical, PlugZap, Upload } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Alan, Bildirim, Bolum, DUGME, DUGME_ANA, GIRDI, HataKutu, Rozet, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import { hataMesaji, oku, sorguMetni, yaz, yukle } from "@/lib/sorgu"
import type { BaglantiTesti, Kaynak, Parti } from "@/yonetim/api"
import { ym } from "@/yonetim/metin"
import { zaman } from "@/lib/bicim"

/** Dosya adindan onerilen kaynak adi: 'alarm-ozeti_2026-10.csv' -> 'alarm-ozeti'. */
export function kaynakAdiOner(dosya: string): string {
  return dosya.replace(/\.[A-Za-z0-9]+$/, "").replace(/[_-]?\d{4}[-_.]?\d{0,2}[-_.]?\d{0,2}$/, "")
}

export function Kaynaklar({ dil, onYeniParti }: { dil: Dil; onYeniParti: (parti: Parti) => void }) {
  const t = ym(dil)
  const qc = useQueryClient()
  const dosyaGirdisi = useRef<HTMLInputElement>(null)
  const [dosya, setDosya] = useState<File | null>(null)
  const [ad, setAd] = useState("")
  const [bilgi, setBilgi] = useState<{ ton: "yesil" | "amber"; metin: string } | null>(null)
  const q = useQuery({ queryKey: ANAHTAR.kaynaklar, queryFn: () => oku<Kaynak[]>("/api/v1/tampon/kaynaklar") })

  const yenile = () => {
    void qc.invalidateQueries({ queryKey: ANAHTAR.kaynaklar })
    void qc.invalidateQueries({ queryKey: ANAHTAR.partiler })
    void qc.invalidateQueries({ queryKey: ANAHTAR.ozet })
  }
  const partiSonucu = (p: Parti) => {
    yenile()
    onYeniParti(p)
    setBilgi(p.durum === "rejected" ? { ton: "amber", metin: t.yuklemeReddedildi } : { ton: "yesil", metin: t.yuklendi(p.satir) })
  }
  const yukleMut = useMutation({
    mutationFn: (d: File) => yukle<Parti>(`/api/v1/tampon/yukle${sorguMetni({ kaynak: ad || kaynakAdiOner(d.name), dosya: d.name })}`, d),
    onSuccess: (p) => {
      partiSonucu(p)
      setDosya(null)
      if (dosyaGirdisi.current) dosyaGirdisi.current.value = ""
    },
    onError: (e) => {
      yenile() // basarisiz parti de listede gorunur
      setBilgi({ ton: "amber", metin: hataMesaji(e, t.islemBasarisiz) })
    },
  })
  const ornek = useMutation({
    mutationFn: () => yaz<Parti>("POST", "/api/v1/tampon/ornek"),
    onSuccess: partiSonucu,
    onError: (e) => setBilgi({ ton: "amber", metin: hataMesaji(e, t.islemBasarisiz) }),
  })
  const test = useMutation({
    mutationFn: (anahtar: string) => yaz<BaglantiTesti>("POST", `/api/v1/tampon/kaynaklar/${encodeURIComponent(anahtar)}/test`),
    onSuccess: (s) => setBilgi({ ton: s.ok ? "yesil" : "amber", metin: [s.mesaj, s.ipucu].filter(Boolean).join(" — ") }),
    onError: (e) => setBilgi({ ton: "amber", metin: hataMesaji(e, t.islemBasarisiz) }),
  })

  return (
    <Bolum anahtar="yonetim-tampon-kaynaklar" baslik={t.kaynaklar}>
      <div className="grid gap-4">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            setBilgi(null)
            if (dosya) yukleMut.mutate(dosya)
          }}
        >
          <Alan etiket={t.csvDosyasi}>
            <input
              ref={dosyaGirdisi}
              type="file"
              accept=".csv,.txt,text/csv"
              className={`${GIRDI} max-w-72`}
              onChange={(e) => {
                const secilen = e.target.files?.[0] ?? null
                setDosya(secilen)
                if (secilen && !ad) setAd(kaynakAdiOner(secilen.name))
              }}
            />
          </Alan>
          <Alan etiket={t.kaynakAdi}>
            <input className={GIRDI} value={ad} maxLength={40} placeholder={t.kaynakAdiIpucu} onChange={(e) => setAd(e.target.value)} />
          </Alan>
          <button type="submit" className={DUGME_ANA} disabled={!dosya || yukleMut.isPending}>
            <Upload aria-hidden className="size-4" />
            {yukleMut.isPending ? t.yukleniyorDosya : t.yukle}
          </button>
          {q.data?.some((k) => k.tur === "ornek") ? (
            <span className="flex flex-col gap-0.5">
              <button type="button" className={DUGME} disabled={ornek.isPending} onClick={() => ornek.mutate()}>
                <FlaskConical aria-hidden className="size-3.5" />
                {t.ornekUret}
              </button>
              <span className="max-w-64 text-[10px] font-bold text-slate-400">{t.ornekAciklama}</span>
            </span>
          ) : null}
        </form>
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
                    <code className="text-[10px] text-slate-400">{k.anahtar}</code>
                  </span>
                ),
              },
              {
                baslik: t.durum,
                hucre: (k) =>
                  k.tur === "oracle" ? (
                    <span className="grid justify-items-start gap-0.5">
                      <Rozet ton={k.hazir ? "yesil" : "gri"}>{k.hazir ? t.canliHazir : t.canliKapali}</Rozet>
                      <span className="text-[10px] text-slate-400">
                        {t.yapilandirma[k.yapilandirma]}
                        {k.eksik.length ? ` · ${t.eksikAnahtar}: ${k.eksik.join(", ")}` : ""}
                      </span>
                      {k.reportdb ? (
                        <span className="text-[10px] text-slate-400">
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
