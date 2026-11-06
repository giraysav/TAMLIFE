import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Ban, Download, FileCheck2, Hourglass, Send, Upload, Users } from "lucide-react"
import { Cekmece } from "@/components/cekmece"
import { Halka, Lejant } from "@/components/grafik"
import { BosKutu, DUGME_SARI, GIRDI, HataKutu, Kpi, Panel, Rozet, SayfaKabi, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { zaman } from "@/lib/bicim"
import { apiYolu } from "@/lib/http"
import { oku, sorguMetni } from "@/lib/sorgu"
import { yilSecenekleri } from "@/lib/yillar"
import type { Dil } from "@/shell/metin"
import { musteriMetin } from "@/musteri/musteri-metin"
import { RaporIceAktar } from "@/musteri/rapor-ice-aktar"

type Gonderim = { id: number; customer_id: number; musteri: string; yil: number; ay: number; gonderen: string; zaman: string; konu: string; durum: string; kaynak?: string; dosya?: boolean }
type TamSatiri = { id: number | null; ad: string; musteri: number; atilan: number; bekleyen: number; muaf: number }
type Durum = { yil: number; ay: number; satirlar: TamSatiri[]; toplam: Omit<TamSatiri, "id" | "ad"> }
type Donem = { yil: number; ay: number }
type ListeIstek = { tip: "bekleyen" | "muaf"; tam?: number; tamAdi?: string }
type ListeSatiri = { id: number; ad: string; tam: string; tam_id: number | null; cati: string | null }
type Liste = { yil: number; ay: number; tip: string; satirlar: ListeSatiri[] }

/** Gonderilen Aylik Rapor (APN Kurulum duzeni, 2026-10-31): ay + yil secimi, KPI karolari, gonderim orani halkasi, TAM basina
 *  atilan/bekleyen tablosu ve secilen donemin gonderim gecmisi. Secim yokken sunucunun donemi (bu ay hazirlanan rapor = onceki ay). */
export function RaporSayfasi({ dil }: { dil: Dil }) {
  const t = musteriMetin(dil)
  const [secim, setSecim] = useState<Donem | null>(null)
  const [iceAcik, setIceAcik] = useState(false)
  const [liste, setListe] = useState<ListeIstek | null>(null)
  const durumQ = useQuery({ queryKey: ["rapor", "durum", secim], queryFn: () => oku<Durum>(`/api/v1/rapor/durum${sorguMetni({ yil: secim?.yil, ay: secim?.ay })}`) })
  const donem: Donem | null = secim ?? (durumQ.data ? { yil: durumQ.data.yil, ay: durumQ.data.ay } : null)
  const listeQ = useQuery({
    queryKey: ["rapor", "gonderilenler", donem],
    queryFn: () => oku<Gonderim[]>(`/api/v1/rapor/gonderilenler${sorguMetni({ yil: donem?.yil, ay: donem?.ay })}`),
    enabled: donem !== null,
  })
  const durum = durumQ.data
  const musteriListesiQ = useQuery({
    queryKey: ["rapor", "durum-liste", donem, liste],
    queryFn: () => oku<Liste>(`/api/v1/rapor/durum/liste${sorguMetni({ yil: donem?.yil, ay: donem?.ay, tip: liste?.tip, tam: liste?.tam })}`),
    enabled: donem !== null && liste !== null,
  })
  const seriler = [
    { anahtar: "atilan", ad: t.atilan, renk: "#16a34a" },
    { anahtar: "bekleyen", ad: t.bekleyen, renk: "#f5c400" },
  ]
  const oran = durum?.toplam.musteri ? Math.round((durum.toplam.atilan / durum.toplam.musteri) * 100) : 0
  const donemAdi = donem ? `${t.aylar[donem.ay - 1]} ${donem.yil}` : ""

  const filtre = (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <label className="flex items-center gap-2 text-[0.625rem] font-black uppercase tracking-wide text-slate-400">
        {t.ay}
        <select className={`${GIRDI} !w-auto`} value={donem?.ay ?? ""} disabled={!donem} onChange={(e) => donem && setSecim({ ...donem, ay: Number(e.target.value) })}>
          {t.aylar.map((ad, i) => (
            <option key={ad} value={i + 1}>
              {ad}
            </option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-2 text-[0.625rem] font-black uppercase tracking-wide text-slate-400">
        {t.yil}
        <select className={`${GIRDI} !w-auto`} value={donem?.yil ?? ""} disabled={!donem} onChange={(e) => donem && setSecim({ ...donem, yil: Number(e.target.value) })}>
          {yilSecenekleri().map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
      </label>
    </div>
  )

  return (
    <div className="grid grid-cols-1 gap-4">
      <SayfaKabi ikon={FileCheck2} baslik={t.raporSayfasi} aciklama={t.raporSayfasiAciklama}>
        <button type="button" className={DUGME_SARI} disabled={!donem} onClick={() => setIceAcik(true)}>
          <Upload aria-hidden className="size-4" />
          {t.raporIceAktar}
        </button>
      </SayfaKabi>
      {liste && donem ? (
        <Cekmece
          acik
          onKapat={() => setListe(null)}
          baslik={`${liste.tip === "bekleyen" ? t.listeBekleyenBaslik : t.listeMuafBaslik}${liste.tamAdi ? ` · ${liste.tamAdi}` : ""}`}
          aciklama={liste.tip === "bekleyen" ? t.listeBekleyenAciklama(donemAdi) : t.listeMuafAciklama(donemAdi)}
          kapatEtiketi={t.kapat}
          genis
        >
          {musteriListesiQ.isPending ? (
            <Yukleniyor metin="…" />
          ) : musteriListesiQ.isError || !musteriListesiQ.data ? (
            <HataKutu metin={t.yuklenemedi} tekrar={() => void musteriListesiQ.refetch()} />
          ) : (
            <VeriTablosu<ListeSatiri>
              baslik={t.listeSayisi(musteriListesiQ.data.satirlar.length)}
              satirlar={musteriListesiQ.data.satirlar}
              anahtar={(r) => r.id}
              bos={<BosKutu ikon={Users} baslik={t.sonucYok} />}
              kolonlar={[
                {
                  baslik: t.musteriKolon,
                  hucre: (r) => (
                    <a className="text-tl-blue underline-offset-4 hover:underline" href={`#/musteri?m=${r.id}`}>
                      {r.ad}
                    </a>
                  ),
                },
                { baslik: t.listeCati, hucre: (r) => r.cati ?? "—" },
                { baslik: t.sorumlu, hucre: (r) => r.tam },
              ]}
            />
          )}
        </Cekmece>
      ) : null}
      {iceAcik && donem ? <RaporIceAktar dil={dil} yil={donem.yil} ay={donem.ay} onKapat={() => setIceAcik(false)} /> : null}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi etiket={t.toplamBirim} deger={durum?.toplam.musteri ?? "—"} alt={donemAdi} ikon={Users} ton="mavi" />
        <Kpi etiket={t.atilan} deger={durum?.toplam.atilan ?? "—"} alt={durum ? `%${oran}` : undefined} ikon={Send} ton="yesil" />
        <button type="button" className="rounded-2xl text-left focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-blue" aria-label={t.listeAc(t.bekleyen)} disabled={!durum} onClick={() => setListe({ tip: "bekleyen" })}>
          <Kpi etiket={t.bekleyen} deger={durum?.toplam.bekleyen ?? "—"} ikon={Hourglass} ton="amber" />
        </button>
        <button type="button" className="rounded-2xl text-left focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-blue" aria-label={t.listeAc(t.muaf)} disabled={!durum} onClick={() => setListe({ tip: "muaf" })}>
          <Kpi etiket={t.muaf} deger={durum?.toplam.muaf ?? "—"} ikon={Ban} ton="gri" />
        </button>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-3">{filtre}</div>
        {durumQ.isPending ? (
          <Yukleniyor metin="…" />
        ) : durumQ.isError || !durum ? (
          <HataKutu metin={t.yuklenemedi} tekrar={() => void durumQ.refetch()} />
        ) : (
          <div className="grid gap-4 lg:grid-cols-[auto_1fr] lg:items-start">
            {/* 2026-10-31 kullanici: gonderilen rapor sayisinin rapor birimi toplamina orani (muaflar toplama girmez) */}
            <div className="flex flex-col items-center gap-3 rounded-xl border border-slate-200 p-4">
              <Halka
                dilimler={seriler.map((s) => ({ ...s, deger: durum.toplam[s.anahtar as "atilan" | "bekleyen"] }))}
                baslik={`%${oran}`}
                alt={t.gonderimOrani}
                boyut={136}
                kalinlik={18}
              />
              <Lejant seriler={seriler} sayilar={durum.toplam} />
            </div>
            <VeriTablosu<TamSatiri>
              baslik={`${t.tamDurumu} · ${donemAdi}`}
              satirlar={durum.satirlar}
              anahtar={(s) => s.id ?? s.ad}
              bos={<BosKutu ikon={Users} baslik={t.sonucYok} />}
              kolonlar={[
                { baslik: t.sorumlu, hucre: (s) => s.ad },
                { baslik: t.toplamBirim, hucre: (s) => s.musteri, sinif: "text-right tabular-nums" },
                { baslik: t.atilan, hucre: (s) => s.atilan, sinif: "text-right tabular-nums" },
                {
                  baslik: t.bekleyen,
                  hucre: (s) =>
                    s.bekleyen ? (
                      <button type="button" aria-label={`${t.listeAc(t.bekleyen)}: ${s.ad}`} onClick={() => setListe({ tip: "bekleyen", tam: s.id ?? 0, tamAdi: s.ad })}>
                        <Rozet ton="amber">{s.bekleyen}</Rozet>
                      </button>
                    ) : (
                      0
                    ),
                  sinif: "text-right tabular-nums",
                },
                {
                  baslik: t.muaf,
                  hucre: (s) =>
                    s.muaf ? (
                      <button type="button" className="underline-offset-4 hover:underline" aria-label={`${t.listeAc(t.muaf)}: ${s.ad}`} onClick={() => setListe({ tip: "muaf", tam: s.id ?? 0, tamAdi: s.ad })}>
                        {s.muaf}
                      </button>
                    ) : (
                      0
                    ),
                  sinif: "text-right tabular-nums text-slate-400",
                },
              ]}
            />
          </div>
        )}
      </div>

      <Panel baslik={t.gecmis} aciklama={donemAdi}>
        {listeQ.isPending ? (
          <Yukleniyor metin="…" />
        ) : listeQ.isError ? (
          <HataKutu metin={t.yuklenemedi} tekrar={() => void listeQ.refetch()} />
        ) : (
          <VeriTablosu<Gonderim>
            baslik={t.gecmis}
            satirlar={listeQ.data ?? []}
            anahtar={(g) => g.id}
            bos={<BosKutu ikon={Send} baslik={t.gecmisYok} />}
            kolonlar={[
              {
                baslik: t.musteriKolon,
                hucre: (g) => (
                  <a className="text-tl-blue underline-offset-4 hover:underline" href={`#/musteri?m=${g.customer_id}`}>
                    {g.musteri}
                  </a>
                ),
              },
              { baslik: t.konuKolon, hucre: (g) => <span className="font-normal text-slate-600">{g.konu}</span> },
              { baslik: t.gonderen, hucre: (g) => g.gonderen },
              { baslik: t.zamanKolon, hucre: (g) => <span className="font-mono text-slate-500">{zaman(g.zaman)}</span>, sinif: "whitespace-nowrap" },
              {
                baslik: "",
                sinif: "whitespace-nowrap text-right",
                hucre: (g) => (
                  <span className="inline-flex items-center gap-1.5">
                    {g.kaynak === "ice_aktarma" ? <Rozet ton="sari">{t.iceAktarildiRozet}</Rozet> : null}
                    {g.durum === "reverted" ? <Rozet>{t.geriAlindi}</Rozet> : null}
                    {g.dosya ? (
                      <a href={apiYolu(`/api/v1/rapor/gonderim/${g.id}/dosya`)} className="inline-flex text-tl-blue hover:text-tl-navy" title={t.dosyaIndir} aria-label={`${t.dosyaIndir}: ${g.musteri}`}>
                        <Download aria-hidden className="size-4" />
                      </a>
                    ) : null}
                  </span>
                ),
              },
            ]}
          />
        )}
      </Panel>
    </div>
  )
}
