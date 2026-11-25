import { useEffect, useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import type { UseMutationResult } from "@tanstack/react-query"
import { PlugZap, RefreshCw } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Bildirim, DUGME, DUGME_ANA, HataKutu, Panel, Rozet, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { zaman } from "@/lib/bicim"
import type { AdBaglantisi, AdTesti, KurumBaglantisi, OracleBaglantisi, PostgresBaglantisi } from "@/yonetim/api"
import { ym } from "@/yonetim/metin"
import type { YM } from "@/yonetim/metin"
import { DurumRozeti } from "@/yonetim/ui"

const DURUM_TON = { ready: "yesil", incomplete: "amber", disabled: "gri" } as const
const YENILEME_MS = 30_000

/** "Tumunu test et" her karta bir sayac gonderir; sayac artinca kart kendi testini baslatir (kapali kaynak test edilmez). */
function useTest(yol: string, tetik: number, acik: boolean) {
  const test = useMutation({ mutationFn: () => yaz<AdTesti>("POST", yol) })
  const { mutate } = test
  useEffect(() => {
    if (tetik > 0 && acik) mutate()
  }, [tetik, acik, mutate])
  return test
}

function Ayarlar({ satirlar }: { satirlar: [string, string][] }) {
  return (
    <dl className="grid gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2 lg:grid-cols-3">
      {satirlar.map(([ad, deger]) => (
        <div key={ad} className="flex flex-wrap justify-between gap-2 border-b border-slate-100 py-1">
          <dt className="font-bold text-slate-500">{ad}</dt>
          <dd className="break-all font-black text-tl-navy">{deger}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Test dugmesi + adim adim sonuc (AD ve Oracle ayni gorunum). */
function TestAlani({ test, t, etiket, bekliyor, notu, tamam, adimAdi }: { test: UseMutationResult<AdTesti, Error, void>; t: YM; etiket: string; bekliyor: string; notu: string; tamam: string; adimAdi?: Record<string, string> }) {
  const k = t.kurum
  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className={DUGME_ANA} disabled={test.isPending} onClick={() => test.mutate()}>
          <PlugZap aria-hidden className="size-4" />
          {test.isPending ? bekliyor : etiket}
        </button>
        <span className="max-w-xl text-[0.6875rem] font-bold text-slate-400">{notu}</span>
      </div>
      {test.isError ? <Bildirim ton="amber">{hataMesaji(test.error, t.islemBasarisiz)}</Bildirim> : null}
      {test.data ? (
        <div className="grid gap-2" aria-live="polite">
          <Bildirim ton={test.data.tamam ? "yesil" : "amber"}>{test.data.tamam ? tamam : k.hata}</Bildirim>
          <ol className="grid gap-1.5">
            {test.data.adimlar.map((a) => (
              <li key={a.adim} className="flex flex-wrap items-start gap-x-3 gap-y-1 border-b border-slate-100 py-1.5 text-xs last:border-0">
                <span className="w-24 shrink-0">
                  <DurumRozeti durum={a.durum} t={t} />
                </span>
                <span className="w-64 shrink-0 font-black text-tl-navy">{(adimAdi ?? k.adim)[a.adim] ?? a.baslik}</span>
                <span className="min-w-0 flex-1 whitespace-pre-wrap break-words font-mono text-[0.6875rem] text-slate-500">{a.ayrinti || a.baslik}</span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  )
}

/** AD/LDAPS karti: durum, gizli olmayan ayarlar, eksik anahtarlar ve bind'siz erisim testi (DNS -> TCP -> TLS). */
function AdKarti({ b, t, tetik }: { b: AdBaglantisi; t: YM; tetik: number }) {
  const k = t.kurum
  const test = useTest("/api/v1/yonetim/kurum/ad-testi", tetik, b.state !== "disabled")
  const i = b.bilgiler
  const evetHayir = (v: boolean) => (v ? k.evet : k.hayir)
  return (
    <Panel baslik={k.adBaslik} sag={<Rozet ton={DURUM_TON[b.state]}>{k.durum[b.state] ?? b.state}</Rozet>}>
      <div className="grid gap-4">
        <p className="max-w-3xl text-xs font-bold text-slate-600">{k.adNe}</p>
        {b.state === "disabled" ? <Bildirim>{k.adKapali}</Bildirim> : null}
        {b.missing.length > 0 ? (
          <Bildirim ton="amber">
            {k.eksik}: <code>{b.missing.join(", ")}</code>
          </Bildirim>
        ) : null}
        <Ayarlar
          satirlar={[
            [k.sunucu, i.sunucu || k.tanimsiz],
            [k.port, i.port ? String(i.port) : "—"],
            [k.alan, i.alan || k.tanimsiz],
            [k.sifreli, evetHayir(i.ldaps && i.ssl)],
            [k.ca, i.ca_dosyasi ? k.caVar : k.caYok],
            [k.grup, evetHayir(i.grup_kisiti)],
            [k.otomatikAc, evetHayir(i.otomatik_ac)],
          ]}
        />
        <TestAlani test={test} t={t} etiket={k.test} bekliyor={k.testEdiliyor} notu={k.testNotu} tamam={k.tamam} />
      </div>
    </Panel>
  )
}

/** Oracle karti (REPORTDB / ONENTDB): AD karti ile ayni duzen; sunucu/servis/kullanici gorunur, parola yalniz tanimli mi. */
function OracleKarti({ b, t, tetik }: { b: OracleBaglantisi; t: YM; tetik: number }) {
  const k = t.kurum
  const test = useTest(`/api/v1/yonetim/kurum/${encodeURIComponent(b.id)}/test`, tetik, b.state === "ready")
  const i = b.bilgiler
  const tanimli = (v: boolean) => (v ? k.tanimli : k.tanimsiz)
  const satirlar: [string, string][] = [
    [k.sunucuAdresi, i.sunucu || k.tanimsiz],
    [k.port, String(i.port)],
    [k.servis, i.servis || k.tanimsiz],
    [k.kullanici, i.kullanici || k.tanimsiz],
    [k.parola, tanimli(i.parola)],
    [k.zamanAsimi, k.saniye(i.zaman_asimi)],
    [k.istemci, i.oracle_istemci ? k.thick : k.thin],
  ]
  return (
    <Panel baslik={b.label} sag={<Rozet ton={DURUM_TON[b.state]}>{k.durum[b.state] ?? b.state}</Rozet>}>
      <div className="grid gap-4">
        <p className="max-w-3xl text-xs font-bold text-slate-600">{k.oracleNe[b.id] ?? ""}</p>
        {b.state === "disabled" ? <Bildirim>{k.oracleKapali(b.acma_anahtari)}</Bildirim> : null}
        {b.missing.length > 0 ? (
          <Bildirim ton="amber">
            {k.eksik}: <code>{b.missing.join(", ")}</code>
          </Bildirim>
        ) : null}
        <Ayarlar satirlar={satirlar} />
        <p className="text-[0.625rem] font-bold text-slate-400">{k.gizlilik}</p>
        {b.state === "ready" ? <TestAlani test={test} t={t} etiket={k.test} bekliyor={k.oracleTestEdiliyor} notu={k.oracleTestNotu} tamam={k.oracleTamam} /> : null}
      </div>
    </Panel>
  )
}

/** Kurum Baglantilari: panelin kurum sistemlerine tum baglantilari (AD/LDAPS + Oracle). Durum 30 sn'de bir tazelenir; canli
 *  baglanti yalniz test dugmesiyle (sunucuda, Oracle icin ayri surecte) denenir. */
export default function Kurum({ dil }: { dil: Dil }) {
  const t = ym(dil)
  const k = t.kurum
  const [tetik, setTetik] = useState(0)
  const q = useQuery({
    queryKey: ANAHTAR.kurum,
    queryFn: () => oku<{ baglantilar: KurumBaglantisi[] }>("/api/v1/yonetim/kurum"),
    refetchInterval: YENILEME_MS,
  })

  if (q.isPending) return <Yukleniyor metin={t.yukleniyor} iskelet />
  if (q.isError) return <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void q.refetch()} />
  const liste = q.data.baglantilar
  const oracle = liste.filter((b): b is OracleBaglantisi => b.tur === "oracle")
  const postgres = liste.filter((b): b is PostgresBaglantisi => b.tur === "postgres")
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2">
        {liste.map((b) => (
          // Adres cubugu sayfa rotasidir (#/yonetim/kurum): karta kaydirma baglanti degil dugmeyle
          <button
            key={b.id}
            type="button"
            onClick={() => document.getElementById(`kurum-${b.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" })}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-black text-tl-navy shadow-sm hover:bg-slate-50"
          >
            {b.label}
            <Rozet ton={DURUM_TON[b.state]}>{k.durum[b.state] ?? b.state}</Rozet>
          </button>
        ))}
        <button type="button" className={`${DUGME} ml-auto`} onClick={() => setTetik((n) => n + 1)}>
          <PlugZap aria-hidden className="size-3.5" />
          {k.tumunuTest}
        </button>
        <button type="button" className={DUGME} aria-label={t.tekrar} title={t.tekrar} onClick={() => void q.refetch()}>
          <RefreshCw aria-hidden className={`size-3.5 ${q.isFetching ? "animate-spin" : ""}`} />
        </button>
      </div>
      <p className="text-[0.6875rem] font-bold text-slate-400">{k.guncellendi(zaman(new Date(q.dataUpdatedAt).toISOString()))}</p>
      {liste.map((b) =>
        b.tur === "dizin" ? (
          <section key={b.id} id={`kurum-${b.id}`}>
            <AdKarti b={b} t={t} tetik={tetik} />
          </section>
        ) : null,
      )}
      {oracle.length ? (
        <>
          <h3 className="mt-2 flex items-center gap-2 text-[0.6875rem] font-black uppercase tracking-widest text-tl-navy">
            <span aria-hidden className="h-4 w-1 rounded-full bg-tl-yellow" />
            {t.disVeritabanlari}
          </h3>
          <p className="-mt-2 text-[0.6875rem] font-bold text-slate-500">{t.disVeritabaniNotu}</p>
          {oracle.map((b) => (
            <section key={b.id} id={`kurum-${b.id}`}>
              <OracleKarti b={b} t={t} tetik={tetik} />
            </section>
          ))}
          {postgres.map((b) => (
            <section key={b.id} id={`kurum-${b.id}`}>
              <PostgresKarti b={b} t={t} tetik={tetik} />
            </section>
          ))}
        </>
      ) : null}
    </div>
  )
}

/** PostgreSQL karti (ONENTDB / ONEDESKDB, 2026-10-19): Oracle karti duzeni; veritabani adi ve SSL kipi, parola yalniz tanimli mi. */
function PostgresKarti({ b, t, tetik }: { b: PostgresBaglantisi; t: YM; tetik: number }) {
  const k = t.kurum
  const test = useTest(`/api/v1/yonetim/kurum/${encodeURIComponent(b.id)}/test`, tetik, b.state === "ready")
  const i = b.bilgiler
  const kat = b.katalog
  return (
    <Panel baslik={`${b.label} · PostgreSQL`} sag={<Rozet ton={DURUM_TON[b.state]}>{k.durum[b.state] ?? b.state}</Rozet>}>
      <div className="grid gap-4">
        <p className="max-w-3xl text-xs font-bold text-slate-600">{k.pgNe[b.id] ?? ""}</p>
        {b.state === "disabled" ? <Bildirim>{k.oracleKapali(b.acma_anahtari)}</Bildirim> : null}
        {b.missing.length > 0 ? (
          <Bildirim ton="amber">
            {k.eksik}: <code>{b.missing.join(", ")}</code>
          </Bildirim>
        ) : null}
        <Ayarlar
          satirlar={[
            [k.sunucuAdresi, i.sunucu || k.tanimsiz],
            [k.port, String(i.port)],
            [k.veritabani, i.veritabani || k.tanimsiz],
            [k.kullanici, i.kullanici || k.tanimsiz],
            [k.parola, i.parola ? k.tanimli : k.tanimsiz],
            [k.ssl, i.ssl],
            [k.zamanAsimi, k.saniye(i.zaman_asimi)],
            [k.sonKatalog, kat ? `#${kat.id} · ${kat.durum} · ${zaman(kat.bitis ?? kat.baslangic)}` : k.katalogYok],
          ]}
        />
        <p className="text-[0.625rem] font-bold text-slate-400">{k.gizlilik}</p>
        {b.state === "ready" ? <TestAlani test={test} t={t} etiket={k.test} bekliyor={k.pgTestEdiliyor} notu={k.pgTestNotu} tamam={k.pgTamam} adimAdi={k.pgAdim} /> : null}
      </div>
    </Panel>
  )
}
