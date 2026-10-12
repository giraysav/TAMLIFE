import { useEffect, useMemo, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CornerDownRight, Plus, Search, Trash2, X } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { CokluSecim } from "@/components/coklu-secim"
import { Alan, Bildirim, Bos, DUGME, DUGME_SARI, GIRDI, HataKutu, Panel, Rozet, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import type { MusteriEkleSonucu, MusteriListesi as MusteriListesiVeri, MusteriSatiri, MusteriSilSonucu } from "@/yonetim/api"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { ym } from "@/yonetim/metin"

const DUGME_TEHLIKE =
  "inline-flex items-center justify-center gap-1.5 rounded-xl border border-rose-300 bg-white px-3 py-2 text-xs font-bold text-rose-600 shadow-sm transition-colors hover:bg-rose-50 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-rose-300 disabled:opacity-50"
const DUGME_TEHLIKE_DOLU =
  "inline-flex items-center justify-center gap-1.5 rounded-xl bg-rose-600 px-4 py-2 text-xs font-black text-white shadow-sm transition-colors hover:bg-rose-700 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-rose-300 disabled:cursor-not-allowed disabled:opacity-50"

type Girdi = { name: string; segment?: string; ham: string }

/** "Unvan" ya da "Unvan; Segment" satirlari (Excel'den yapistirilan sekmeyle ayrilmis iki sutun da olur); bos satirlar atilir. */
export function satirlariAyir(metin: string): Girdi[] {
  const sonuc: Girdi[] = []
  for (const ham of metin.split(/\r?\n/)) {
    const satir = ham.trim()
    if (!satir) continue
    let ad = satir
    let segment = ""
    if (satir.includes("\t")) {
      const parcalar = satir.split("\t").map((p) => p.trim())
      ad = parcalar[0] ?? ""
      segment = parcalar[1] ?? ""
    } else if (satir.includes(";")) {
      const i = satir.lastIndexOf(";")
      ad = satir.slice(0, i).trim()
      segment = satir.slice(i + 1).trim()
    }
    if (ad) sonuc.push({ name: ad, segment: segment || undefined, ham: satir })
  }
  return sonuc
}

const SAHIPSIZ = "yok"
const sahipAnahtari = (s: MusteriSatiri) => ((s.owner_id ?? null) === null ? SAHIPSIZ : String(s.owner_id))

const SIL_ONAYI = (yazi: string) => yazi.trim().toLocaleUpperCase("tr-TR").replace("İ", "I") === "SIL"

/**
 * TAM Utilizasyon > Musteri Listesi: panelde kayitli tum musteriler (agac sirasiyla cati ve istirak); tek tek ya da toplu ekleme,
 * onay kutusuyla secilenleri ya da TUM musterileri silme. Yalniz admin (sunucu da zorlar). Silme geri alinamaz: onay kutusu cikar,
 * "Tumunu sil" icin ayrica SIL yazilmasi gerekir.
 */
export function MusteriListesi({ dil }: { dil: Dil }) {
  const t = ym(dil)
  const m = t.util.musteriler
  const qc = useQueryClient()
  const sorgu = useQuery({ queryKey: ANAHTAR.musteriListesi, queryFn: () => oku<MusteriListesiVeri>("/api/v1/yonetim/musteriler") })
  const [ara, setAra] = useState("")
  const [sorumlular, setSorumlular] = useState<Set<string>>(new Set())
  const [secili, setSecili] = useState<Set<number>>(new Set())
  const [ekleAcik, setEkleAcik] = useState(false)
  const [onay, setOnay] = useState<"secili" | "hepsi" | null>(null)
  const [yazi, setYazi] = useState("")
  const [bildirim, setBildirim] = useState<{ ton: "yesil" | "amber" | "kirmizi"; metin: string } | null>(null)
  const [satirMetni, setSatirMetni] = useState("")
  const [ustId, setUstId] = useState("")
  const [tamId, setTamId] = useState("")
  const [atlanan, setAtlanan] = useState<{ ad: string; sebep: string }[]>([])
  const tumKutu = useRef<HTMLInputElement>(null)

  const secenek = useQuery({ queryKey: ["musteri", "secenekler"], queryFn: () => oku<{ tam: { id: number; ad: string }[] }>("/api/v1/musteri/secenekler"), enabled: ekleAcik })
  const hepsi = sorgu.data?.items
  const liste = useMemo(() => hepsi ?? [], [hepsi])
  const catilar = useMemo(() => liste.filter((s) => s.parent_id === null), [liste])
  const aranan = ara.trim().toLocaleLowerCase("tr-TR")
  // Personel filtresi: secenekler listedeki sorumlulardan gelir (sayilariyla); "Sorumlusuz" sahibi olmayanlar icindir.
  const personel = useMemo(() => {
    const sayim = new Map<string, { etiket: string; sayi: number }>()
    for (const s of liste) {
      const anahtar = sahipAnahtari(s)
      const o = sayim.get(anahtar)
      if (o) o.sayi += 1
      else sayim.set(anahtar, { etiket: s.owner ?? m.sorumlusuz, sayi: 1 })
    }
    return [...sayim.entries()]
      .map(([deger, o]) => ({ deger, ...o }))
      .sort((a, b) => (a.deger === SAHIPSIZ ? 1 : b.deger === SAHIPSIZ ? -1 : a.etiket.localeCompare(b.etiket, "tr-TR")))
  }, [liste, m.sorumlusuz])
  // Artik listede olmayan kisiler filtreden duser.
  const etkinSorumlular = useMemo(() => new Set([...sorumlular].filter((k) => personel.some((p) => p.deger === k))), [sorumlular, personel])
  const gorunen = useMemo(
    () =>
      liste.filter(
        (s) =>
          (etkinSorumlular.size === 0 || etkinSorumlular.has(sahipAnahtari(s))) &&
          (!aranan || [s.name, s.parent_name, s.owner, s.segment].some((d) => (d ?? "").toLocaleLowerCase("tr-TR").includes(aranan))),
      ),
    [liste, aranan, etkinSorumlular],
  )

  // Silinen ya da artik listede olmayan kimlikler secimden duser.
  useEffect(() => {
    setSecili((o) => {
      const var_ = new Set(liste.map((s) => s.id))
      const yeni = new Set([...o].filter((k) => var_.has(k)))
      return yeni.size === o.size ? o : yeni
    })
  }, [liste])

  const gorunenSecili = gorunen.filter((s) => secili.has(s.id)).length
  const tumuSecili = gorunen.length > 0 && gorunenSecili === gorunen.length
  useEffect(() => {
    if (tumKutu.current) tumKutu.current.indeterminate = gorunenSecili > 0 && !tumuSecili
  }, [gorunenSecili, tumuSecili])

  /** Secilenler ve (secilmemis olsalar da) iştirakleri: cati silinince istirakleri de gider. */
  const silinecek = useMemo(() => {
    const cocuklar = new Map<number, number[]>()
    for (const s of liste) if (s.parent_id !== null) cocuklar.set(s.parent_id, [...(cocuklar.get(s.parent_id) ?? []), s.id])
    const kume = new Set<number>()
    const kuyruk = [...secili]
    while (kuyruk.length > 0) {
      const k = kuyruk.pop() as number
      if (kume.has(k)) continue
      kume.add(k)
      kuyruk.push(...(cocuklar.get(k) ?? []))
    }
    return kume.size
  }, [liste, secili])

  const yenile = () => void qc.invalidateQueries()

  const sil = useMutation({
    mutationFn: (govde: { ids: number[] } | { hepsi: true; onay: string }) => yaz<MusteriSilSonucu>("POST", "/api/v1/yonetim/musteriler/sil", govde),
    onSuccess: (s) => {
      setSecili(new Set())
      setOnay(null)
      setYazi("")
      setBildirim({ ton: "yesil", metin: m.silindi(s.silinen) })
      yenile()
    },
    onError: (e) => setBildirim({ ton: "kirmizi", metin: hataMesaji(e, m.silinemedi) }),
  })

  const girdiler = satirlariAyir(satirMetni)
  const ekle = useMutation({
    mutationFn: () =>
      yaz<MusteriEkleSonucu>("POST", "/api/v1/yonetim/musteriler/toplu-ekle", {
        satirlar: girdiler.map((g) => ({ name: g.name, segment: g.segment ?? null })),
        parent_id: ustId ? Number(ustId) : null,
        owner_id: tamId ? Number(tamId) : null,
      }),
    onSuccess: (s) => {
      setAtlanan(s.atlanan)
      // Eklenenler metinden duser; eklenemeyen satirlar duzeltilsin diye kalir.
      const kalan = new Set(s.atlanan.map((a) => a.ad))
      setSatirMetni(girdiler.filter((g) => kalan.has(g.name)).map((g) => g.ham).join("\n"))
      setBildirim(s.eklenen > 0 ? { ton: s.atlanan.length > 0 ? "amber" : "yesil", metin: m.eklendi(s.eklenen) } : { ton: "amber", metin: m.eklenemedi })
      yenile()
    },
    onError: (e) => setBildirim({ ton: "kirmizi", metin: hataMesaji(e, m.eklenemedi) }),
  })

  function sec(id: number, acik: boolean) {
    setSecili((o) => {
      const yeni = new Set(o)
      if (acik) yeni.add(id)
      else yeni.delete(id)
      return yeni
    })
  }
  function tumunuSec(acik: boolean) {
    setSecili((o) => {
      const yeni = new Set(o)
      for (const s of gorunen) {
        if (acik) yeni.add(s.id)
        else yeni.delete(s.id)
      }
      return yeni
    })
  }
  function onayAc(tur: "secili" | "hepsi") {
    setOnay(tur)
    setYazi("")
    setBildirim(null)
  }
  function onayla() {
    if (onay === "hepsi") sil.mutate({ hepsi: true, onay: yazi })
    else if (onay === "secili") sil.mutate({ ids: [...secili] })
  }

  const toplam = sorgu.data?.total ?? 0

  return (
    <div className="grid gap-4">
      <Panel baslik={m.baslik} aciklama={m.aciklama}>
        <div className="grid gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <label className="relative block min-w-56 flex-1 sm:max-w-sm">
              <span className="sr-only">{m.araEtiket}</span>
              <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-slate-400" />
              <input type="search" className={`${GIRDI} !pl-8`} value={ara} onChange={(e) => setAra(e.target.value)} placeholder={m.ara} />
            </label>
            <CokluSecim
              etiket={m.personelSuzgec}
              tumuEtiketi={m.tumPersonel}
              secimOzeti={m.personelSecili}
              temizleEtiketi={m.suzgeciTemizle}
              ogeler={personel}
              secili={etkinSorumlular}
              onDegis={setSorumlular}
            />
            <span className="text-xs font-bold text-slate-500" aria-live="polite">
              {m.toplam(toplam, gorunen.length)}
              {secili.size > 0 ? ` · ${m.secili(secili.size)}` : ""}
            </span>
            <span className="ml-auto flex flex-wrap items-center gap-2">
              <button type="button" className={ekleAcik ? DUGME : DUGME_SARI} aria-expanded={ekleAcik} onClick={() => setEkleAcik((a) => !a)}>
                {ekleAcik ? <X aria-hidden className="size-4" /> : <Plus aria-hidden className="size-4" />}
                {ekleAcik ? m.ekleKapat : m.ekleAc}
              </button>
              <button type="button" className={DUGME_TEHLIKE} disabled={secili.size === 0 || sil.isPending} onClick={() => onayAc("secili")}>
                <Trash2 aria-hidden className="size-4" />
                {m.seciliyiSil(secili.size)}
              </button>
              <button type="button" className={DUGME_TEHLIKE} disabled={toplam === 0 || sil.isPending} onClick={() => onayAc("hepsi")}>
                <Trash2 aria-hidden className="size-4" />
                {m.hepsiniSil}
              </button>
            </span>
          </div>

          {onay ? (
            <div role="alert" className="grid gap-3 rounded-xl border border-rose-300 bg-rose-50 p-4">
              <p className="text-xs font-black uppercase tracking-wide text-rose-700">{m.silOnayBaslik}</p>
              <p className="text-sm font-bold text-rose-900">{onay === "hepsi" ? m.hepsiSilOnay(toplam) : m.seciliSilOnay(secili.size, silinecek)}</p>
              <p className="text-xs font-bold text-rose-700">{m.geriAlinamaz}</p>
              <div className="flex flex-wrap items-end gap-3">
                {onay === "hepsi" ? (
                  <Alan etiket={m.yazinOnay}>
                    <input className={`${GIRDI} !w-40 uppercase`} value={yazi} onChange={(e) => setYazi(e.target.value)} autoComplete="off" autoFocus />
                  </Alan>
                ) : null}
                <button type="button" className={DUGME_TEHLIKE_DOLU} disabled={sil.isPending || (onay === "hepsi" && !SIL_ONAYI(yazi))} onClick={onayla}>
                  <Trash2 aria-hidden className="size-4" />
                  {m.evetSil}
                </button>
                <button type="button" className={DUGME} onClick={() => setOnay(null)}>
                  {t.vazgec}
                </button>
              </div>
            </div>
          ) : null}

          {bildirim ? <Bildirim ton={bildirim.ton}>{bildirim.metin}</Bildirim> : null}

          {ekleAcik ? (
            <form
              className="grid gap-3 rounded-xl border border-slate-200 bg-slate-50/60 p-4"
              aria-label={m.ekleBaslik}
              onSubmit={(e) => {
                e.preventDefault()
                if (girdiler.length > 0) ekle.mutate()
              }}
            >
              <p className="text-xs font-bold text-slate-500">{m.ekleAciklama}</p>
              <Alan etiket={m.satirlar} ipucu={m.satirlarIpucu(girdiler.length)}>
                <textarea className={`${GIRDI} min-h-32 font-mono`} value={satirMetni} onChange={(e) => setSatirMetni(e.target.value)} placeholder={m.satirYer} rows={6} />
              </Alan>
              <div className="grid items-start gap-3 sm:grid-cols-2">
                <Alan etiket={m.ust} ipucu={m.ustIpucu}>
                  <select className={GIRDI} value={ustId} onChange={(e) => setUstId(e.target.value)}>
                    <option value="">{m.ustCati}</option>
                    {catilar.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </Alan>
                <Alan etiket={m.tam}>
                  <select className={GIRDI} value={tamId} onChange={(e) => setTamId(e.target.value)}>
                    <option value="">{m.tamVarsayilan}</option>
                    {(secenek.data?.tam ?? []).map((k) => (
                      <option key={k.id} value={k.id}>
                        {k.ad}
                      </option>
                    ))}
                  </select>
                </Alan>
              </div>
              {atlanan.length > 0 ? (
                <div className="grid gap-1 text-xs font-bold text-amber-800">
                  <p>{m.atlandi(atlanan.length)}</p>
                  <ul className="list-disc pl-5">
                    {atlanan.map((a, i) => (
                      <li key={`${a.ad}-${i}`}>
                        <span className="font-black">{a.ad || "—"}</span>: {a.sebep}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <div>
                <button type="submit" className={`${DUGME_SARI} !min-w-0`} disabled={girdiler.length === 0 || ekle.isPending}>
                  <Plus aria-hidden className="size-4" />
                  {ekle.isPending ? m.ekleniyor : m.ekle(girdiler.length)}
                </button>
              </div>
            </form>
          ) : null}

          {sorgu.isPending ? (
            <Yukleniyor metin={t.yukleniyor} />
          ) : sorgu.isError ? (
            <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void sorgu.refetch()} />
          ) : liste.length === 0 ? (
            <Bos>{m.bos}</Bos>
          ) : gorunen.length === 0 ? (
            <Bos>{m.aramaBos}</Bos>
          ) : (
            <div className="max-h-[60vh] overflow-auto rounded-xl border border-slate-200">
              <table className="w-full text-left text-xs">
                <caption className="sr-only">{m.baslik}</caption>
                <thead className="sticky top-0 z-[1] bg-tl-navy text-white">
                  <tr>
                    <th scope="col" className="w-10 px-3 py-2">
                      <input ref={tumKutu} type="checkbox" checked={tumuSecili} onChange={(e) => tumunuSec(e.target.checked)} aria-label={m.tumunuSec} />
                    </th>
                    {[m.sutun.unvan, m.sutun.tur, m.sutun.cati, m.sutun.segment, m.sutun.sorumlu, m.sutun.skor].map((b) => (
                      <th key={b} scope="col" className="whitespace-nowrap px-3 py-2 font-black">
                        {b}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {gorunen.map((s) => (
                    <Satir key={s.id} s={s} secili={secili.has(s.id)} onSec={(a) => sec(s.id, a)} dil={dil} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Panel>
    </div>
  )
}

function Satir({ s, secili, onSec, dil }: { s: MusteriSatiri; secili: boolean; onSec: (acik: boolean) => void; dil: Dil }) {
  const m = ym(dil).util.musteriler
  const cati = s.parent_id === null
  return (
    <tr className={secili ? "bg-tl-yellow/15" : "hover:bg-slate-50"}>
      <td className="px-3 py-2">
        <input type="checkbox" checked={secili} onChange={(e) => onSec(e.target.checked)} aria-label={m.satirSec(s.name)} />
      </td>
      <td className="px-3 py-2 font-bold text-slate-700">
        <span className={`flex items-center gap-1.5 ${cati ? "font-black text-tl-navy" : "pl-5"}`}>
          {cati ? null : <CornerDownRight aria-hidden className="size-3.5 shrink-0 text-slate-400" />}
          {s.name}
        </span>
      </td>
      <td className="whitespace-nowrap px-3 py-2">
        {cati ? <Rozet ton="sari">{s.affiliates > 0 ? `${m.cati} · ${m.istirakAdet(s.affiliates)}` : m.cati}</Rozet> : <Rozet>{m.istirak}</Rozet>}
      </td>
      <td className="px-3 py-2 font-bold text-slate-500">{s.parent_name ?? "—"}</td>
      <td className="px-3 py-2 font-bold text-slate-500">{s.segment || "—"}</td>
      <td className="px-3 py-2 font-bold text-slate-500">{s.owner ?? "—"}</td>
      <td className="px-3 py-2 text-right font-mono font-bold text-slate-700">{s.score === null ? "—" : s.score.toLocaleString(dil === "en" ? "en-GB" : "tr-TR", { maximumFractionDigits: 1 })}</td>
    </tr>
  )
}
