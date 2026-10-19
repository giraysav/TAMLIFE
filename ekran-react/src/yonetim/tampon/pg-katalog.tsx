import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ChevronDown, ChevronRight, Database, RefreshCw } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Bildirim, Bolum, DUGME, DUGME_ANA, HataKutu, Rozet, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import type { PgKaynagi, PgKatalogu, PgNesne } from "@/yonetim/api"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { sayi, zaman } from "@/lib/bicim"

const TON = { ready: "yesil", incomplete: "amber", disabled: "gri" } as const

export function pgMetin(dil: Dil) {
  const tr = dil === "tr"
  return {
    baslik: tr ? "PostgreSQL kaynakları · ONENTDB / ONEDESKDB" : "PostgreSQL sources · ONENTDB / ONEDESKDB",
    aciklama: tr
      ? "Salt okunur katalog: şema → tablo / görünüm → sütunlar ve örnek satırlar. Tarama işçi süreçte yapılır; kişisel veri gibi duran sütunların (telefon, e-posta, adres, kimlik no…) örneği gizlenir. Hangi verinin alınacağını buradan seçersiniz."
      : "Read-only catalog: schema → table / view → columns and sample rows. The scan runs in a worker process; samples of columns that look personal (phone, e-mail, address, ID no…) are hidden. Choose here which data to take.",
    durum: { ready: tr ? "Hazır" : "Ready", incomplete: tr ? "Ayarı yarım" : "Incomplete", disabled: tr ? "Kapalı" : "Off" } as Record<string, string>,
    kapali: (a: string) => (tr ? `Kapalı: backend/.env'de ${a}=true ve bağlantı ayarları gerekir; ardından panel yeniden başlatılır.` : `Off: set ${a}=true and the connection settings in backend/.env, then restart the panel.`),
    eksik: tr ? "Eksik ayarlar" : "Missing settings",
    yenile: tr ? "Kataloğu yenile" : "Refresh catalog",
    taraniyor: tr ? "Taranıyor…" : "Scanning…",
    basladi: tr ? "Tarama işçi süreçte başladı; bitince ağaç kendiliğinden gelir." : "The scan started in a worker process; the tree appears when it finishes.",
    yok: tr ? "Henüz katalog yok: bağlantı hazır olunca \"Kataloğu yenile\"." : "No catalog yet: use \"Refresh catalog\" once the connection is ready.",
    sonHata: tr ? "Son tarama başarısız" : "Last scan failed",
    ozet: (s: number, n: number, c: number, z: string) => (tr ? `${s} şema · ${n} nesne · ${c} sütun · ${z}` : `${s} schemas · ${n} objects · ${c} columns · ${z}`),
    satir: (n: number | null) => (n === null ? (tr ? "satır ?" : "rows ?") : tr ? `~${sayi(n)} satır` : `~${sayi(n)} rows`),
    sutunlar: tr ? "Sütunlar" : "Columns",
    ornek: (n: number) => (tr ? `Örnek satırlar (${n})` : `Sample rows (${n})`),
    ornekYok: tr ? "Örnek satır yok." : "No sample rows.",
    bos: tr ? "boş olabilir" : "nullable",
    yukleniyor: tr ? "Yükleniyor…" : "Loading…",
    yuklenemedi: tr ? "Yüklenemedi." : "Could not load.",
    tekrar: tr ? "Tekrar dene" : "Retry",
    islemBasarisiz: tr ? "İşlem başarısız." : "Operation failed.",
  }
}
type PM = ReturnType<typeof pgMetin>

/** Veri Girisi: PostgreSQL kaynaklarinin (2026-10-19) durum + katalog agaci. Kapali kaynak yalniz acma talimatini gosterir. */
export function PgKataloglari({ dil }: { dil: Dil }) {
  const t = pgMetin(dil)
  const q = useQuery({
    queryKey: ANAHTAR.pg,
    queryFn: () => oku<PgKaynagi[]>("/api/v1/tampon/pg"),
    refetchInterval: (s) => (s.state.data?.some((k) => k.calisiyor) ? 3_000 : false),
  })
  return (
    <Bolum anahtar="yonetim-tampon-pg" baslik={t.baslik} varsayilanAcik={false} tembel>
      <div className="grid gap-4">
        <p className="max-w-4xl text-xs font-bold text-slate-500">{t.aciklama}</p>
        {q.isPending ? <Yukleniyor metin={t.yukleniyor} /> : null}
        {q.isError ? <HataKutu metin={hataMesaji(q.error, t.yuklenemedi)} tekrarEtiket={t.tekrar} tekrar={() => void q.refetch()} /> : null}
        {q.data?.map((k) => <PgKaynakKarti key={k.id} k={k} t={t} />)}
      </div>
    </Bolum>
  )
}

function PgKaynakKarti({ k, t }: { k: PgKaynagi; t: PM }) {
  const qc = useQueryClient()
  const [bilgi, setBilgi] = useState<{ ton: "yesil" | "amber"; metin: string } | null>(null)
  const agac = useQuery({
    queryKey: [...ANAHTAR.pg, k.id, k.katalog?.id ?? 0],
    queryFn: () => oku<PgKatalogu>(`/api/v1/tampon/pg/${k.id}/katalog`),
    enabled: Boolean(k.katalog),
  })
  const yenile = useMutation({
    mutationFn: () => yaz<{ basladi: boolean }>("POST", `/api/v1/tampon/pg/${k.id}/katalog/yenile`),
    onSuccess: () => {
      setBilgi({ ton: "yesil", metin: t.basladi })
      void qc.invalidateQueries({ queryKey: ANAHTAR.pg })
    },
    onError: (e) => setBilgi({ ton: "amber", metin: hataMesaji(e, t.islemBasarisiz) }),
  })
  const kat = k.katalog
  const calisiyor = k.calisiyor || yenile.isPending
  return (
    <section aria-label={k.label} className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Database aria-hidden className="size-4 text-tl-blue" />
        <h3 className="text-sm font-black text-tl-navy">{k.label}</h3>
        <Rozet ton={TON[k.state]}>{t.durum[k.state] ?? k.state}</Rozet>
        {kat ? (
          <span className="text-[0.6875rem] font-bold text-slate-500">
            {t.ozet(kat.ozet.semalar?.length ?? 0, kat.ozet.nesne ?? 0, kat.ozet.sutun ?? 0, zaman(kat.bitis ?? kat.baslangic))}
          </span>
        ) : null}
        <button type="button" className={`${DUGME_ANA} ml-auto`} disabled={!k.hazir || calisiyor} onClick={() => yenile.mutate()}>
          <RefreshCw aria-hidden className={`size-3.5 ${calisiyor ? "animate-spin" : ""}`} />
          {calisiyor ? t.taraniyor : t.yenile}
        </button>
      </div>
      {k.state === "disabled" ? <Bildirim>{t.kapali(k.acma_anahtari)}</Bildirim> : null}
      {k.eksik.length ? (
        <Bildirim ton="amber">
          {t.eksik}: <code>{k.eksik.join(", ")}</code>
        </Bildirim>
      ) : null}
      {bilgi ? <Bildirim ton={bilgi.ton}>{bilgi.metin}</Bildirim> : null}
      {k.son?.durum === "failed" ? (
        <Bildirim ton="amber">
          {t.sonHata}: {k.son.hata}
        </Bildirim>
      ) : null}
      {!kat && k.hazir ? <p className="text-xs font-bold text-slate-400">{t.yok}</p> : null}
      {agac.isError ? <HataKutu metin={hataMesaji(agac.error, t.yuklenemedi)} tekrarEtiket={t.tekrar} tekrar={() => void agac.refetch()} /> : null}
      {agac.data ? <Agac v={agac.data} t={t} /> : null}
    </section>
  )
}

function Agac({ v, t }: { v: PgKatalogu; t: PM }) {
  const [acik, setAcik] = useState<Record<string, boolean>>({})
  const [secili, setSecili] = useState<number | null>(null)
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(16rem,22rem)_1fr]">
      <ul className="max-h-[32rem] overflow-auto rounded-xl border border-slate-200 p-2 text-xs" role="tree">
        {v.semalar.map((s) => (
          <li key={s.ad} role="treeitem" aria-expanded={Boolean(acik[s.ad])} aria-selected={false}>
            <button type="button" className="flex w-full items-center gap-1 rounded px-1 py-1 text-left font-black text-tl-navy hover:bg-slate-50" onClick={() => setAcik({ ...acik, [s.ad]: !acik[s.ad] })}>
              {acik[s.ad] ? <ChevronDown aria-hidden className="size-3.5" /> : <ChevronRight aria-hidden className="size-3.5" />}
              {s.ad}
              <span className="ml-auto text-slate-400">{s.nesneler.length}</span>
            </button>
            {acik[s.ad] ? (
              <ul role="group" className="ml-4 grid">
                {s.nesneler.map((n) => (
                  <li key={n.id} role="treeitem" aria-selected={secili === n.id}>
                    <button
                      type="button"
                      className={`flex w-full flex-wrap items-baseline gap-x-2 rounded px-1 py-0.5 text-left font-bold hover:bg-slate-50 ${secili === n.id ? "bg-tl-yellow/30 text-tl-navy" : "text-slate-600"}`}
                      onClick={() => setSecili(n.id)}
                    >
                      {n.ad}
                      <span className="text-[0.625rem] text-slate-400">
                        {n.tur} · {n.sutun} · {t.satir(n.satir)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </li>
        ))}
      </ul>
      {secili ? <NesneAyrintisi id={secili} t={t} /> : null}
    </div>
  )
}

function NesneAyrintisi({ id, t }: { id: number; t: PM }) {
  const q = useQuery({ queryKey: [...ANAHTAR.pg, "nesne", id], queryFn: () => oku<PgNesne>(`/api/v1/tampon/pg/nesne/${id}`) })
  if (q.isPending) return <Yukleniyor metin={t.yukleniyor} />
  if (q.isError) return <HataKutu metin={hataMesaji(q.error, t.yuklenemedi)} tekrarEtiket={t.tekrar} tekrar={() => void q.refetch()} />
  const n = q.data
  return (
    <div className="grid min-w-0 gap-3">
      <div>
        <h4 className="text-sm font-black text-tl-navy">
          {n.sema}.{n.ad}
        </h4>
        <p className="text-[0.6875rem] font-bold text-slate-500">
          {n.tur} · {t.satir(n.satir)}
          {n.aciklama ? ` · ${n.aciklama}` : ""}
        </p>
      </div>
      <div>
        <h5 className="mb-1 text-[0.6875rem] font-black uppercase tracking-widest text-slate-500">{t.sutunlar}</h5>
        <ul className="flex flex-wrap gap-1.5 text-[0.6875rem]">
          {n.sutunlar.map((s) => (
            <li key={s.ad} title={s.aciklama || undefined} className="rounded-md border border-slate-200 px-1.5 py-0.5 font-bold text-slate-600">
              <span className="font-black text-tl-navy">{s.ad}</span> {s.tip}
              {s.bos ? <span className="text-slate-400"> · {t.bos}</span> : null}
            </li>
          ))}
        </ul>
      </div>
      <div className="min-w-0">
        <h5 className="mb-1 text-[0.6875rem] font-black uppercase tracking-widest text-slate-500">{t.ornek(n.ornek.satirlar.length)}</h5>
        {n.ornek.not ? <p className="mb-1 text-[0.6875rem] font-bold text-amber-700">{n.ornek.not}</p> : null}
        {n.ornek.satirlar.length ? (
          <div className="max-h-80 overflow-auto rounded-xl border border-slate-200">
            <table className="w-full text-[0.6875rem]">
              <thead className="sticky top-0 bg-tl-navy text-white">
                <tr>
                  {n.ornek.sutunlar.map((s) => (
                    <th key={s} scope="col" className="whitespace-nowrap px-2 py-1 text-left font-black">
                      {s}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-bold text-slate-700">
                {n.ornek.satirlar.map((r, i) => (
                  <tr key={i}>
                    {r.map((h, j) => (
                      <td key={j} className="max-w-64 truncate whitespace-nowrap px-2 py-1" title={h === null ? "" : String(h)}>
                        {h === null ? "" : String(h)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-xs font-bold text-slate-400">{t.ornekYok}</p>
        )}
      </div>
      <button type="button" className={`${DUGME} justify-self-start`} onClick={() => void q.refetch()}>
        <RefreshCw aria-hidden className="size-3.5" />
        {t.tekrar}
      </button>
    </div>
  )
}
