import { useState } from "react"
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query"
import { Link2, UserPlus, X } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Alan, Bildirim, Bos, DUGME, DUGME_ANA, GIRDI, HataKutu, Panel, Rozet, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import type { FarkListesi, FarkSatiri, FarkTuru, RadarAtamaSonucu, TopluAtamaSonucu } from "@/yonetim/api"
import { hataMesaji, oku, sorguMetni, yaz } from "@/lib/sorgu"
import { sayi } from "@/lib/bicim"
import { Gosterge, Sayfalama } from "@/yonetim/ui"
import { tm } from "@/yonetim/tampon/metin"
import { AtamaPaneli, ElleAtamalar, atamaMetin, useAtamaYenile } from "@/components/temip-atama"
import type { AtamaHedefi } from "@/components/temip-atama"

const TURLER: FarkTuru[] = ["radar", "belirsiz", "kart_personelsiz"]
const TON: Record<FarkTuru, "kirmizi" | "amber" | "gri"> = { radar: "gri", belirsiz: "kirmizi", kart_personelsiz: "amber" }
const GOSTERGE_TON = { radar: "notr", belirsiz: "hata", kart_personelsiz: "uyari" } as const
const BAG = "font-black text-tl-blue underline-offset-2 hover:underline"
const RADAR = "radar" // toplu atamada personel gibi secilen Musteri Radar (kart acilmaz, numara Radar'a gider)
type Personel = { id: number; ad: string }
type Mesaj = { ton: "yesil" | "amber"; metin: string }

function usePersonel() {
  return useQuery({ queryKey: ["tampon", "temip", "personel"], queryFn: () => oku<Personel[]>("/api/v1/tampon/temip/personel"), staleTime: 300_000 })
}

function PersonelSecimi({ dil, deger, onDegis, etiket, radar = false }: { dil: Dil; deger: string; onDegis: (v: string) => void; etiket: string; radar?: boolean }) {
  const f = tm(dil).fark
  const personel = usePersonel()
  return (
    <select className={GIRDI} aria-label={etiket} value={deger} onChange={(e) => onDegis(e.target.value)}>
      <option value="">{f.personelSec}</option>
      {radar ? <option value={RADAR}>{f.radarSecenek}</option> : null}
      {(personel.data ?? []).map((p) => (
        <option key={p.id} value={p.id}>
          {p.ad}
        </option>
      ))}
    </select>
  )
}

/** Veri Girisi > Fark (2026-10-24): canli DB (TEMIP) kayitlarinin kartla / TAM ile eslesmeyen musteri numaralari. Kartsiz numara tek tek
 *  (AtamaPaneli: mevcut karta ekle / yeni kart) ya da secilerek toplu (personel adina yeni kartlar) atanir; TAM'siz karta TAM secilir. */
export function FarkAlani({ dil }: { dil: Dil }) {
  const t = tm(dil)
  const f = t.fark
  const yenile = useAtamaYenile()
  const [tur, setTur] = useState<FarkTuru | "">("")
  const [arama, setArama] = useState("")
  const [sayfa, setSayfa] = useState(1)
  const [secili, setSecili] = useState<Set<string>>(() => new Set())
  const [tam, setTam] = useState("")
  const [hedef, setHedef] = useState<AtamaHedefi | null>(null)
  const [mesaj, setMesaj] = useState<Mesaj | null>(null)
  const [atlanan, setAtlanan] = useState<TopluAtamaSonucu["atlanan"]>([])
  const personel = usePersonel()
  const sorgu = { tur, q: arama.trim(), sayfa }
  const q = useQuery({
    queryKey: [...ANAHTAR.fark, sorgu],
    queryFn: () => oku<FarkListesi>(`/api/v1/tampon/fark${sorguMetni(sorgu)}`),
    placeholderData: keepPreviousData,
  })
  const toplu = useMutation({
    mutationFn: (govde: { musteri_nolar: string[]; tam_id: number }) => yaz<TopluAtamaSonucu>("POST", "/api/v1/tampon/fark/toplu-ata", govde),
    onSuccess: (s) => {
      setMesaj({ ton: s.atlanan.length ? "amber" : "yesil", metin: f.topluSonuc(s.atanan, sayi(s.yeniden_baglanan), s.atlanan.length) })
      setAtlanan(s.atlanan)
      setSecili(new Set())
      yenile()
    },
    onError: (e) => setMesaj({ ton: "amber", metin: hataMesaji(e, f.islemBasarisiz) }),
  })
  const radar = useMutation({
    mutationFn: (govde: { musteri_nolar: string[] }) => yaz<RadarAtamaSonucu>("POST", "/api/v1/tampon/fark/radara-ata", govde),
    onSuccess: (s) => {
      setMesaj({ ton: s.atlanan.length ? "amber" : "yesil", metin: f.radarSonuc(s.atanan, s.atlanan.length) })
      setAtlanan(s.atlanan)
      setSecili(new Set())
      yenile()
    },
    onError: (e) => setMesaj({ ton: "amber", metin: hataMesaji(e, f.islemBasarisiz) }),
  })
  const sahip = useMutation({
    mutationFn: (govde: { kart_id: number; tam_id: number }) => yaz<{ kart: string; personel: string }>("POST", "/api/v1/tampon/fark/kart-sahibi", govde),
    onSuccess: (s) => {
      setMesaj({ ton: "yesil", metin: f.tamAtandi(s.kart, s.personel) })
      yenile()
    },
    onError: (e) => setMesaj({ ton: "amber", metin: hataMesaji(e, f.islemBasarisiz) }),
  })

  if (q.isPending) return <Yukleniyor metin={t.yukleniyor} iskelet />
  if (q.isError) return <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void q.refetch()} />
  const r = q.data
  if (!r.hazir) return <Bildirim ton="amber">{f.hazirDegil(r.neden)}</Bildirim>
  const farkKayit = TURLER.reduce((n, d) => n + r.ozet[d].kayit, 0)
  const sayfaKartsiz = r.satirlar.filter((m) => m.durum === "radar").map((m) => m.musteri_no)
  const kisi = personel.data?.find((p) => String(p.id) === tam)
  const radaraMi = tam === RADAR
  const degistir = (no: string) =>
    setSecili((onceki) => {
      const yeni = new Set(onceki)
      if (yeni.has(no)) yeni.delete(no)
      else yeni.add(no)
      return yeni
    })
  const filtre = (fn: () => void) => {
    fn()
    setSayfa(1)
  }

  return (
    <div className="grid gap-4">
      <Panel baslik={f.baslik} aciklama={f.aciklama}>
        <div className={`grid gap-3 ${q.isPlaceholderData ? "opacity-70" : ""}`}>
          <p className="text-xs font-black text-tl-navy">
            {f.toplamKayit(sayi(farkKayit), sayi(r.toplam_kayit))}
            {r.radarda ? (
              <>
                {" · "}
                {f.radarda(sayi(r.radarda))}{" "}
                <a href="#/radar" className={BAG}>
                  {f.radaraGit}
                </a>
              </>
            ) : null}
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {TURLER.map((d) => (
              <button key={d} type="button" className="text-left" aria-pressed={tur === d} onClick={() => filtre(() => setTur(tur === d ? "" : d))}>
                <Gosterge
                  etiket={f.turAdi[d]}
                  deger={sayi(r.ozet[d].musteri)}
                  alt={
                    <>
                      {f.ozet(sayi(r.ozet[d].musteri), sayi(r.ozet[d].kayit), sayi(r.ozet[d].acik))}
                      <span className="mt-0.5 block font-normal text-slate-400">{f.turAciklama[d]}</span>
                    </>
                  }
                  ton={r.ozet[d].musteri ? GOSTERGE_TON[d] : "notr"}
                />
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <Alan etiket={f.tur} sinif="max-w-64">
              <select className={GIRDI} value={tur} onChange={(e) => filtre(() => setTur(e.target.value as FarkTuru | ""))}>
                <option value="">{f.hepsi}</option>
                {TURLER.map((d) => (
                  <option key={d} value={d}>
                    {f.turAdi[d]}
                  </option>
                ))}
              </select>
            </Alan>
            <Alan etiket={f.ara} sinif="max-w-72 flex-1">
              <input className={GIRDI} value={arama} maxLength={100} onChange={(e) => filtre(() => setArama(e.target.value))} />
            </Alan>
          </div>

          <section aria-label={f.topluAta} className="grid gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3">
            <div className="flex flex-wrap items-end gap-3">
              <button
                type="button"
                className={DUGME}
                disabled={!sayfaKartsiz.length}
                onClick={() => setSecili((onceki) => new Set([...onceki, ...sayfaKartsiz]))}
              >
                {f.sayfayiSec}
              </button>
              {secili.size ? (
                <button type="button" className={DUGME} onClick={() => setSecili(new Set())}>
                  <X aria-hidden className="size-3.5" />
                  {f.secimiTemizle}
                </button>
              ) : null}
              <span className="text-xs font-black text-tl-navy" aria-live="polite">
                {f.secili(secili.size)}
              </span>
              <Alan etiket={f.topluPersonel} sinif="w-64">
                <PersonelSecimi dil={dil} deger={tam} onDegis={setTam} etiket={f.topluPersonel} radar />
              </Alan>
              <button
                type="button"
                className={DUGME_ANA}
                disabled={!secili.size || !(kisi || radaraMi) || toplu.isPending || radar.isPending}
                onClick={() => {
                  if (radaraMi) {
                    if (window.confirm(f.radarOnay(secili.size))) radar.mutate({ musteri_nolar: [...secili] })
                  } else if (kisi && window.confirm(f.topluOnay(secili.size, kisi.ad))) toplu.mutate({ musteri_nolar: [...secili], tam_id: kisi.id })
                }}
              >
                <UserPlus aria-hidden className="size-4" />
                {f.topluAta}
              </button>
            </div>
            <p className="text-[0.625rem] font-bold text-slate-400">{f.topluAciklama}</p>
          </section>

          {mesaj ? <Bildirim ton={mesaj.ton}>{mesaj.metin}</Bildirim> : null}
          {atlanan.length ? (
            <details className="text-[0.6875rem] font-bold text-slate-500">
              <summary className="cursor-pointer text-amber-700">
                {f.atlananBaslik} ({atlanan.length})
              </summary>
              <ul className="mt-1 grid gap-0.5">
                {atlanan.map((x) => (
                  <li key={x.musteri_no}>
                    <code>{x.musteri_no}</code> · {x.neden}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}

          <VeriTablosu<FarkSatiri>
            baslik={f.baslik}
            satirlar={r.satirlar}
            anahtar={(m) => m.musteri_no}
            vurgulu={(m) => secili.has(m.musteri_no)}
            bos={<Bos>{f.farkYok}</Bos>}
            kolonlar={[
              {
                baslik: "",
                hucre: (m) =>
                  m.durum === "radar" ? (
                    <input type="checkbox" className="size-4 accent-tl-navy" aria-label={f.sec(m.musteri_no)} checked={secili.has(m.musteri_no)} onChange={() => degistir(m.musteri_no)} />
                  ) : null,
              },
              { baslik: f.musteriNo, hucre: (m) => <code className="text-[0.6875rem]">{m.musteri_no}</code> },
              { baslik: f.unvan, hucre: (m) => <span className="line-clamp-1 max-w-64 font-normal">{m.temip_unvan || "—"}</span> },
              { baslik: f.kaynak, hucre: (m) => m.kaynak },
              { baslik: f.durum, hucre: (m) => <Rozet ton={TON[m.durum]}>{f.turAdi[m.durum]}</Rozet> },
              {
                baslik: f.kart,
                hucre: (m) =>
                  m.kart_id ? (
                    <a href={`#/musteri?m=${m.kart_id}`} className={BAG}>
                      {m.panel_unvan}
                    </a>
                  ) : (
                    <span className="font-normal text-slate-400">{m.aday_kartlar || "—"}</span>
                  ),
              },
              { baslik: f.acik, hucre: (m) => sayi(m.acik), sinif: "text-right font-mono" },
              { baslik: f.toplam, hucre: (m) => sayi(m.toplam), sinif: "text-right font-mono" },
              {
                baslik: "",
                hucre: (m) =>
                  m.durum === "radar" ? (
                    <button type="button" className={`${DUGME} !px-2 !py-1`} onClick={() => setHedef({ musteri_no: m.musteri_no, temip_unvan: m.temip_unvan })}>
                      <Link2 aria-hidden className="size-3.5" />
                      {atamaMetin(dil).karttaAta}
                    </button>
                  ) : m.durum === "kart_personelsiz" && m.kart_id ? (
                    <KartTami dil={dil} kartId={m.kart_id} kart={m.panel_unvan} bekliyor={sahip.isPending} onAta={(tamId) => sahip.mutate({ kart_id: Number(m.kart_id), tam_id: tamId })} />
                  ) : null,
              },
            ]}
          />
          <Sayfalama t={t} sayfa={r.sayfa} adet={r.adet} toplam={r.toplam} onSayfa={setSayfa} />
          {hedef ? <AtamaPaneli key={hedef.musteri_no} dil={dil} hedef={hedef} onKapat={() => setHedef(null)} /> : null}
        </div>
      </Panel>
      <ElleAtamalar dil={dil} />
    </div>
  )
}

/** TAM'siz kart satiri: personel sec + onayla (Musteri Yonetimi'ndeki sorumlu devriyle ayni kural). */
function KartTami({ dil, kartId, kart, bekliyor, onAta }: { dil: Dil; kartId: number; kart: string; bekliyor: boolean; onAta: (tamId: number) => void }) {
  const f = tm(dil).fark
  const [tam, setTam] = useState("")
  const personel = usePersonel()
  const kisi = personel.data?.find((p) => String(p.id) === tam)
  return (
    <span className="flex items-center gap-2 whitespace-nowrap">
      <span className="w-44">
        <PersonelSecimi dil={dil} deger={tam} onDegis={setTam} etiket={`${f.tamSec} · ${kart || kartId}`} />
      </span>
      <button
        type="button"
        className={`${DUGME} !px-2 !py-1`}
        disabled={!kisi || bekliyor}
        onClick={() => {
          if (kisi && window.confirm(f.tamOnay(kart, kisi.ad))) onAta(kisi.id)
        }}
      >
        {f.tamSec}
      </button>
    </span>
  )
}
