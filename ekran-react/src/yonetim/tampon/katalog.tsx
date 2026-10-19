import { useEffect, useMemo, useRef, useState } from "react"
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowDownAZ, ArrowUpZA, ChevronDown, Database, Filter, RefreshCw, X } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Alan, Bildirim, Bolum, BosKutu, DUGME, DUGME_ANA, GIRDI, HataKutu, Rozet, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import type { KatalogDegerleri, KatalogVerisi, KaynakKatalogu } from "@/yonetim/api"
import { hataMesaji, oku, sorguMetni, yaz } from "@/lib/sorgu"
import { sayi, zaman } from "@/lib/bicim"
import { Sayfalama } from "@/yonetim/ui"
import { tm } from "@/yonetim/tampon/metin"
import type { TM } from "@/yonetim/tampon/metin"

const SAYFA = 100
type Filtre = Record<string, string[]>
type Siralama = { sutun: string; yon: "asc" | "desc" } | null
type Sorgu = { nesne: number; sayfa: number; adet: number; q: string; filtre: string; sirala: string; yon: string }

/** Yazarken her harfte istek gitmesin: deger `ms` boyunca degismezse doner. */
function useGeciken<T>(deger: T, ms = 300): T {
  const [g, setG] = useState(deger)
  useEffect(() => {
    const z = window.setTimeout(() => setG(deger), ms)
    return () => window.clearTimeout(z)
  }, [deger, ms])
  return g
}

/** domain tekrarli parametre: ?domain=ACCESS&domain=NOC%20DESTECH (sorguMetni tek deger yazar). */
function veriSorgusu(degerler: Record<string, string | number>, domainler: string[]) {
  const temel = sorguMetni(degerler)
  const ek = domainler.map((d) => `domain=${encodeURIComponent(d)}`).join("&")
  if (!ek) return temel
  return temel ? `${temel}&${ek}` : `?${ek}`
}

/** Veri Girisi'nin ilk blogu: ReportDB ham verisi. Tarama isci surecinde (domain + arama metni); burada suzulur ve okunur. */
export function ReportdbKatalogu({ dil }: { dil: Dil }) {
  const t = tm(dil)
  const k = t.katalog
  const qc = useQueryClient()
  const [bilgi, setBilgi] = useState<{ ton: "yesil" | "amber"; metin: string } | null>(null)
  const q = useQuery({
    queryKey: ANAHTAR.katalog,
    queryFn: () => oku<KaynakKatalogu>("/api/v1/tampon/katalog"),
    refetchInterval: (s) => (s.state.data?.calisiyor ? 3_000 : false),
  })
  const yenile = useMutation({
    mutationFn: () => yaz<{ basladi: boolean; calisiyor: boolean }>("POST", "/api/v1/tampon/katalog/yenile"),
    onSuccess: () => {
      setBilgi({ ton: "yesil", metin: k.basladi })
      void qc.invalidateQueries({ queryKey: ANAHTAR.katalog })
    },
    onError: (e) => setBilgi({ ton: "amber", metin: hataMesaji(e, t.islemBasarisiz) }),
  })
  const calisiyor = q.data?.calisiyor || yenile.isPending
  const kat = q.data?.katalog

  return (
    <Bolum anahtar="yonetim-tampon-katalog" baslik={k.baslik}>
      <div className="grid gap-3">
        <p className="max-w-4xl text-[0.6875rem] font-bold text-slate-500">{k.aciklama}</p>
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className={DUGME_ANA} disabled={calisiyor} onClick={() => yenile.mutate()}>
            <RefreshCw aria-hidden className={`size-4 ${calisiyor ? "animate-spin" : ""}`} />
            {calisiyor ? k.taraniyor : k.yenile}
          </button>
          {kat ? (
            <span className="text-[0.6875rem] font-bold text-slate-500">
              {k.bilgi(zaman(kat.bitis ?? kat.baslangic), kat.ozet.nesne ?? 0, kat.ozet.sutun ?? 0, kat.ozet.sure_sn ?? 0, kat.olusturan)}
            </span>
          ) : null}
        </div>
        {q.data?.calisiyor && q.data.ilerleme ? <Bildirim>{k.ilerleme(q.data.ilerleme, Math.round((q.data.ilerleme_sn ?? 0) / 60))}</Bildirim> : null}
        {bilgi && !q.data?.calisiyor ? <Bildirim ton={bilgi.ton}>{bilgi.metin}</Bildirim> : null}
        {q.data?.son_hata ? <Bildirim ton="amber">{k.sonHata(q.data.son_hata)}</Bildirim> : null}
        {q.isPending ? (
          <Yukleniyor metin={t.yukleniyor} iskelet />
        ) : q.isError ? (
          <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void q.refetch()} />
        ) : !kat ? (
          <BosKutu baslik={k.yok} ikon={Database} />
        ) : (
          <VeriOkuyucu veri={q.data} t={t} />
        )}
      </div>
    </Bolum>
  )
}

function VeriOkuyucu({ veri, t }: { veri: KaynakKatalogu; t: TM }) {
  const k = t.katalog
  const p = veri.parametreler && "ara" in veri.parametreler ? veri.parametreler : null
  const dallar = useMemo(() => veri.parametre_agaci ?? [], [veri.parametre_agaci])
  const [domainler, setDomainler] = useState<string[]>(() => p?.degerler ?? [])
  const [secilen, setSecilen] = useState<number | null>(null)
  const [arama, setArama] = useState("")
  const [filtre, setFiltre] = useState<Filtre>({})
  const [siralama, setSiralama] = useState<Siralama>(null)
  const [sayfa, setSayfa] = useState(1)
  const geciken = useGeciken(arama.trim())

  // Secili domainlerde isabeti olan tablolar (isabet toplamina gore); isabetsiz tablo listede yok
  const tablolar = useMemo(() => {
    const top = new Map<number, { id: number; etiket: string; isabet: number }>()
    for (const d of dallar) {
      if (!domainler.includes(d.domain)) continue
      for (const x of d.tablolar) {
        if (!x.isabet) continue
        const o = top.get(x.id) ?? { id: x.id, etiket: x.ust ? `${x.ust} › ${x.ad}` : x.ad, isabet: 0 }
        o.isabet += x.isabet
        top.set(x.id, o)
      }
    }
    return [...top.values()].sort((a, b) => b.isabet - a.isabet)
  }, [dallar, domainler])
  const tablo = tablolar.find((x) => x.id === secilen)?.id ?? tablolar[0]?.id ?? null

  const sifirla = () => {
    setFiltre({})
    setSiralama(null)
    setSayfa(1)
  }
  if (!p) return <Bildirim ton="amber">{k.eskiKatalog}</Bildirim>
  const sorgu: Sorgu = {
    nesne: tablo ?? 0,
    sayfa,
    adet: SAYFA,
    q: geciken,
    filtre: Object.keys(filtre).length ? JSON.stringify(filtre) : "",
    sirala: siralama?.sutun ?? "",
    yon: siralama?.yon ?? "asc",
  }

  return (
    <div className="grid gap-3">
      <fieldset className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
        <legend className="px-1 text-[0.625rem] font-black uppercase tracking-widest text-tl-navy">{k.filtreler}</legend>
        <div className="grid gap-1">
          <span className="text-[0.625rem] font-black uppercase tracking-wide text-slate-500">{k.domainSec}</span>
          <span className="flex flex-wrap gap-1">
            {p.degerler.map((d) => {
              const acik = domainler.includes(d)
              return (
                <button
                  key={d}
                  type="button"
                  aria-pressed={acik}
                  onClick={() => {
                    setDomainler((x) => (acik ? x.filter((y) => y !== d) : [...x, d]))
                    sifirla()
                  }}
                  className={`rounded-lg border px-2.5 py-1 font-mono text-xs font-black ${acik ? "border-tl-navy bg-tl-navy text-white" : "border-slate-300 bg-white text-slate-500"}`}
                >
                  {p.alan} = {d}
                </button>
              )
            })}
          </span>
        </div>
        <Rozet ton="sari">{k.taramaFiltresi(p.ara)}</Rozet>
        {p.baslangic ? <Rozet ton="sari">{k.baslangicRozeti(p.baslangic)}</Rozet> : null}
        <Alan etiket={k.tablo} sinif="min-w-64 flex-1">
          <select
            className={GIRDI}
            value={tablo ?? ""}
            onChange={(e) => {
              setSecilen(Number(e.target.value))
              sifirla()
            }}
          >
            {tablolar.map((x) => (
              <option key={x.id} value={x.id}>
                {k.tabloSecenegi(x.etiket, sayi(x.isabet))}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={k.tumSutunlardaAra} sinif="w-56">
          <input
            className={GIRDI}
            value={arama}
            maxLength={100}
            onChange={(e) => {
              setArama(e.target.value)
              setSayfa(1)
            }}
          />
        </Alan>
        <button
          type="button"
          className={DUGME}
          disabled={!Object.keys(filtre).length && !siralama && !arama}
          onClick={() => {
            setArama("")
            sifirla()
          }}
        >
          <X aria-hidden className="size-3.5" />
          {k.temizle}
        </button>
      </fieldset>
      {!domainler.length ? (
        <Bildirim ton="amber">{k.domainEnAzBir}</Bildirim>
      ) : tablo === null ? (
        <Bildirim>{k.tabloYok}</Bildirim>
      ) : (
        <FiltreliTablo
          key={`${tablo}-${domainler.join("|")}`}
          sorgu={sorgu}
          domainler={domainler}
          filtre={filtre}
          siralama={siralama}
          vurgu={p.ara}
          t={t}
          onFiltre={(sutun, degerler) => {
            setFiltre((f) => {
              const yeni = { ...f }
              if (degerler === null) delete yeni[sutun]
              else yeni[sutun] = degerler
              return yeni
            })
            setSayfa(1)
          }}
          onSirala={(s) => {
            setSiralama(s)
            setSayfa(1)
          }}
          onSayfa={setSayfa}
        />
      )}
    </div>
  )
}

type TabloOzellik = {
  sorgu: Sorgu
  domainler: string[]
  filtre: Filtre
  siralama: Siralama
  vurgu: string
  t: TM
  onFiltre: (sutun: string, degerler: string[] | null) => void
  onSirala: (s: Siralama) => void
  onSayfa: (sayfa: number) => void
}

function FiltreliTablo({ sorgu, domainler, filtre, siralama, vurgu, t, onFiltre, onSirala, onSayfa }: TabloOzellik) {
  const k = t.katalog
  const [menu, setMenu] = useState<{ sutun: string; x: number; y: number } | null>(null)
  const q = useQuery({
    queryKey: [...ANAHTAR.katalog, "veri", sorgu, domainler],
    queryFn: () => oku<KatalogVerisi>(`/api/v1/tampon/katalog/veri${veriSorgusu(sorgu, domainler)}`),
    placeholderData: keepPreviousData,
  })
  if (q.isPending) return <Yukleniyor metin={t.yukleniyor} iskelet />
  if (q.isError) return <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void q.refetch()} />
  const v = q.data
  const isaret = vurgu.toLowerCase()
  return (
    <div className={`grid gap-2 ${q.isPlaceholderData ? "opacity-70" : ""}`}>
      <p className="flex flex-wrap gap-3 text-[0.6875rem] font-bold text-slate-500">
        <span className="font-mono font-black text-tl-navy">{v.ad}</span>
        <span>{k.veriOzeti(sayi(v.toplam), sayi(v.toplam_ham), v.pencere)}</span>
        {v.gizlenen_bos ? <span>{k.gizlenenBos(v.gizlenen_bos)}</span> : null}
      </p>
      <div className="max-h-[36rem] overflow-auto rounded-xl border border-slate-200">
        <table className="text-left text-[0.6875rem]">
          <caption className="sr-only">{v.ad}</caption>
          <thead className="sticky top-0 z-[1] bg-tl-navy text-white">
            <tr>
              {v.sutunlar.map((s) => {
                const aktif = s in filtre || siralama?.sutun === s
                return (
                  <th key={s} scope="col" className={`whitespace-nowrap px-1 py-1 font-mono font-black ${v.isabetli.includes(s) ? "text-tl-yellow" : ""}`}>
                    <button
                      type="button"
                      aria-haspopup="dialog"
                      aria-expanded={menu?.sutun === s}
                      aria-label={k.filtreMenusu(s)}
                      onClick={(e) => {
                        const r = e.currentTarget.getBoundingClientRect()
                        setMenu(menu?.sutun === s ? null : { sutun: s, x: Math.min(r.left, window.innerWidth - 300), y: r.bottom + 4 })
                      }}
                      className={`flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-white/15 ${aktif ? "bg-tl-yellow/30" : ""}`}
                    >
                      {s}
                      {s in filtre ? <Filter aria-hidden className="size-3" /> : null}
                      {siralama?.sutun === s ? (
                        siralama.yon === "asc" ? (
                          <ArrowDownAZ aria-hidden className="size-3" />
                        ) : (
                          <ArrowUpZA aria-hidden className="size-3" />
                        )
                      ) : null}
                      <ChevronDown aria-hidden className="size-3 opacity-70" />
                    </button>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {v.satirlar.length ? (
              v.satirlar.map((satir, i) => (
                <tr key={i} className="border-t border-slate-100 odd:bg-slate-50/60">
                  {satir.map((h, j) => {
                    const metin = h === null || h === undefined ? "" : String(h)
                    return (
                      <td
                        key={j}
                        title={metin}
                        className={`max-w-72 truncate whitespace-nowrap px-2 py-1 font-mono ${isaret && metin.toLowerCase().includes(isaret) ? "bg-tl-yellow/40" : ""}`}
                      >
                        {metin === "" ? <span className="text-slate-300">∅</span> : metin}
                      </td>
                    )
                  })}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={v.sutunlar.length || 1} className="px-3 py-4 text-xs font-bold text-slate-400">
                  {k.satirYokFiltre}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Sayfalama t={t} sayfa={v.sayfa} adet={v.adet} toplam={v.toplam} onSayfa={onSayfa} />
      {menu ? (
        <SutunFiltresi
          key={menu.sutun}
          konum={menu}
          sorgu={sorgu}
          domainler={domainler}
          filtre={filtre}
          t={t}
          onKapat={() => setMenu(null)}
          onUygula={(d) => {
            onFiltre(menu.sutun, d)
            setMenu(null)
          }}
          onSirala={(yon) => {
            onSirala({ sutun: menu.sutun, yon })
            setMenu(null)
          }}
        />
      ) : null}
    </div>
  )
}

type MenuOzellik = {
  konum: { sutun: string; x: number; y: number }
  sorgu: Sorgu
  domainler: string[]
  filtre: Filtre
  t: TM
  onKapat: () => void
  onUygula: (degerler: string[] | null) => void
  onSirala: (yon: "asc" | "desc") => void
}

/** Excel filtresi: siralama, deger arama, adetli onay kutusu listesi. Liste diger sutunlarin filtresiyle daraltilmistir. */
function SutunFiltresi({ konum, sorgu, domainler, filtre, t, onKapat, onUygula, onSirala }: MenuOzellik) {
  const k = t.katalog
  const kutu = useRef<HTMLDivElement>(null)
  const kapat = useRef(onKapat)
  kapat.current = onKapat
  const [ara, setAra] = useState("")
  const geciken = useGeciken(ara.trim())
  const mevcut = filtre[konum.sutun]
  const [secili, setSecili] = useState<Set<string> | null>(mevcut ? new Set(mevcut) : null) // null = hepsi
  const q = useQuery({
    queryKey: [...ANAHTAR.katalog, "degerler", sorgu.nesne, domainler, konum.sutun, sorgu.q, sorgu.filtre, geciken],
    queryFn: () =>
      oku<KatalogDegerleri>(
        `/api/v1/tampon/katalog/veri/degerler${veriSorgusu({ nesne: sorgu.nesne, sutun: konum.sutun, q: sorgu.q, filtre: sorgu.filtre, ara: geciken }, domainler)}`,
      ),
    placeholderData: keepPreviousData,
  })
  useEffect(() => {
    const disari = (e: MouseEvent) => {
      if (kutu.current && !kutu.current.contains(e.target as Node)) kapat.current()
    }
    const tus = (e: KeyboardEvent) => {
      if (e.key === "Escape") kapat.current()
    }
    document.addEventListener("mousedown", disari)
    document.addEventListener("keydown", tus)
    kutu.current?.querySelector("input")?.focus()
    return () => {
      document.removeEventListener("mousedown", disari)
      document.removeEventListener("keydown", tus)
    }
  }, [])
  const liste = q.data?.degerler ?? []
  const isaretli = (d: string) => secili === null || secili.has(d)
  const hepsi = liste.length > 0 && liste.every((d) => isaretli(d.deger))
  const degistir = (d: string) =>
    setSecili((s) => {
      const yeni = new Set(s ?? liste.map((x) => x.deger))
      if (yeni.has(d)) yeni.delete(d)
      else yeni.add(d)
      return yeni
    })
  const uygula = () => {
    // aramasiz, kesilmemis listede hepsi isaretliyse filtre yok (Excel: tumu secili)
    if (secili === null || (hepsi && !geciken && !q.data?.kesildi)) return onUygula(null)
    onUygula(liste.map((x) => x.deger).filter((d) => isaretli(d)))
  }
  return (
    <div
      ref={kutu}
      role="dialog"
      aria-label={k.filtreMenusu(konum.sutun)}
      style={{ position: "fixed", left: Math.max(8, konum.x), top: konum.y }}
      className="z-50 grid w-72 gap-2 rounded-xl border border-slate-200 bg-white p-3 text-xs shadow-xl"
    >
      <button type="button" className="flex items-center gap-2 rounded px-1 py-1 text-left font-bold hover:bg-slate-100" onClick={() => onSirala("asc")}>
        <ArrowDownAZ aria-hidden className="size-4" />
        {k.siralaAz}
      </button>
      <button type="button" className="flex items-center gap-2 rounded px-1 py-1 text-left font-bold hover:bg-slate-100" onClick={() => onSirala("desc")}>
        <ArrowUpZA aria-hidden className="size-4" />
        {k.siralaZa}
      </button>
      <input className={GIRDI} placeholder={k.degerAra} aria-label={k.degerAra} value={ara} maxLength={100} onChange={(e) => setAra(e.target.value)} />
      <div className="max-h-64 overflow-auto rounded-lg border border-slate-200 p-1">
        {q.isPending ? (
          <Yukleniyor metin={t.yukleniyor} />
        ) : (
          <>
            <label className="flex items-center gap-2 px-1 py-0.5 font-black">
              <input type="checkbox" checked={hepsi} onChange={() => setSecili(hepsi ? new Set() : null)} />
              {k.tumunuSec}
            </label>
            {liste.map((d) => (
              <label key={d.deger} className="flex items-center gap-2 px-1 py-0.5" title={d.deger}>
                <input type="checkbox" checked={isaretli(d.deger)} onChange={() => degistir(d.deger)} />
                <span className="min-w-0 flex-1 truncate font-mono">{d.deger}</span>
                <span className="text-slate-400">{sayi(d.adet)}</span>
              </label>
            ))}
          </>
        )}
      </div>
      {q.data?.kesildi ? <p className="text-[0.625rem] font-bold text-amber-600">{k.kesildi(q.data.degerler.length)}</p> : null}
      <div className="flex justify-between gap-2">
        <button type="button" className={DUGME} onClick={() => onUygula(null)}>
          {k.filtreyiKaldir}
        </button>
        <button type="button" className={DUGME_ANA} onClick={uygula}>
          {k.tamam}
        </button>
      </div>
    </div>
  )
}
