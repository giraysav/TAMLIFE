import { useEffect, useState } from "react"
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link2, Plus, Undo2, X } from "lucide-react"
import { Alan, Bildirim, DUGME, DUGME_ANA, GIRDI, Rozet, Sekmeler, VeriTablosu } from "@/components/sayfa-ui"
import { hataMesaji, oku, sorguMetni, yaz } from "@/lib/sorgu"
import { sayi, zaman } from "@/lib/bicim"
import type { Dil } from "@/shell/metin"

/** TEMIP Musteri No'sunu elle atama (yalniz admin; /api/v1/tampon/temip/*): TAM Radar ve Veri Girisi > TEMIP eslesmesi AYNI bileseni
 *  kullanir; bir yerde yapilan atama iki ekrani da tazeler. Iki yol: personelin MEVCUT kartina ekle (CRM isim karisikligi) ya da
 *  personele YENI kart ac (musteri hic kartli degilse). */
type KartAday = { id: number; ad: string; musteri_no: string }
type Personel = { id: number; ad: string }
type ElleAtama = { musteri_no: string; temip_unvan: string; kart_id: number; kart: string; personel?: string; yeni_kart?: boolean; kayit: number; kim: string; zaman: string }
type AtamaSonucu = { musteri_no: string; kart: string; kayit: number; yeniden_baglanan: number; yeni_kart: boolean }
export type AtamaHedefi = { musteri_no: string; temip_unvan: string }

const TR = {
  baslik: (no: string) => `${no} numarasını personele ata`,
  aciklama: "Müşteri personel kartlarında yok ya da CRM ünvan farkı yüzünden eşleşmedi. Numara seçilen karta eklenir; kayıtlar hemen o karta ve personele geçer, sonraki içeri almalarda da korunur.",
  personel: "Personel",
  tumPersonel: "Tüm personel",
  yontem: "Atama yöntemi",
  mevcut: "Mevcut karta ekle",
  yeni: "Yeni kart aç",
  kartAra: "Kart ara (ünvan ya da numara)",
  kartYok: "Aramaya uyan kart yok.",
  personelSec: "Yeni kart için önce personel seçin.",
  numarasiz: "numara yok",
  ata: "Bu karta ata",
  yeniUnvan: "Yeni kartın ünvanı",
  yeniAc: "Yeni kart aç ve ata",
  onay: (no: string, kart: string) => `${no} numarası "${kart}" kartına eklensin ve kayıtları bu karta bağlansın mı?`,
  yeniOnay: (no: string, kart: string, kisi: string) => `${kisi} adına "${kart}" kartı açılsın ve ${no} numarasının kayıtları bu karta bağlansın mı?`,
  atandi: (no: string, kart: string, n: string) => `${no} → ${kart}: ${n} kayıt karta bağlandı.`,
  kapat: "Kapat",
  karttaAta: "Personele ata",
  liste: (n: number) => `Elle atamalar (${n})`,
  musteriNo: "Müşteri No",
  temipUnvan: "TEMIP ünvanı",
  kart: "Kart",
  yeniKart: "yeni kart",
  kayit: "Kayıt",
  kim: "Atayan",
  geriAl: "Geri al",
  geriAlOnay: (no: string, kart: string) => `${no} numarası "${kart}" kartından çıkarılsın mı? Kayıtları TAM Radar'a döner (atamayla açılan kart silinmez).`,
  geriAlindi: (no: string) => `${no} ataması geri alındı.`,
  islemBasarisiz: "İşlem tamamlanamadı.",
}
const EN: typeof TR = {
  baslik: (no: string) => `Assign ${no} to staff`,
  aciklama: "The customer is not on any staff card or did not match because of a CRM name difference. The number is added to the chosen card; records move to that card and staff immediately and stay there on later imports.",
  personel: "Staff",
  tumPersonel: "All staff",
  yontem: "Assignment method",
  mevcut: "Add to existing card",
  yeni: "Open new card",
  kartAra: "Search cards (name or number)",
  kartYok: "No card matches the search.",
  personelSec: "Select staff for a new card first.",
  numarasiz: "no number",
  ata: "Assign to this card",
  yeniUnvan: "New card name",
  yeniAc: "Open card and assign",
  onay: (no: string, kart: string) => `Add ${no} to "${kart}" and link its records to this card?`,
  yeniOnay: (no: string, kart: string, kisi: string) => `Open "${kart}" for ${kisi} and link the records of ${no} to it?`,
  atandi: (no: string, kart: string, n: string) => `${no} → ${kart}: ${n} records linked.`,
  kapat: "Close",
  karttaAta: "Assign to staff",
  liste: (n: number) => `Manual assignments (${n})`,
  musteriNo: "Customer No",
  temipUnvan: "TEMIP name",
  kart: "Card",
  yeniKart: "new card",
  kayit: "Records",
  kim: "Assigned by",
  geriAl: "Undo",
  geriAlOnay: (no: string, kart: string) => `Remove ${no} from "${kart}"? Its records return to TAM Radar (a card opened by the assignment is kept).`,
  geriAlindi: (no: string) => `Assignment of ${no} undone.`,
  islemBasarisiz: "The operation could not be completed.",
}
export const atamaMetin = (dil: Dil) => (dil === "en" ? EN : TR)
const TABAN = "/api/v1/tampon/temip"

/** Unvandan arama tohumu: yasal ekler atilir, ilk iki kelime ('TURK EKONOMI BANKASI A.S.' -> 'TURK EKONOMI'). */
function tohum(unvan: string) {
  const ekler = new Set(["A.S.", "A.S", "AS", "A.Ş.", "ANONIM", "SIRKETI", "ŞİRKETİ", "LTD", "STI", "TIC", "SAN", "VE"])
  return unvan.split(/\s+/).filter((w) => w && !ekler.has(w.toUpperCase())).slice(0, 2).join(" ")
}

/** Atama sonrasi: Radar, TEMIP eslesmesi, Fark, Musteri eslesmesi, veri akislari ve musteri kartlari tazelenir (ekranlar senkron). */
export function useAtamaYenile() {
  const qc = useQueryClient()
  return () => {
    for (const k of [["tampon", "temip"], ["tampon", "fark"], ["tampon", "eslesme"], ["tampon", "akislar"], ["radar"], ["musteri"]]) {
      void qc.invalidateQueries({ queryKey: k })
    }
  }
}

export function AtamaPaneli({ dil, hedef, onKapat }: { dil: Dil; hedef: AtamaHedefi; onKapat: () => void }) {
  const a = atamaMetin(dil)
  const yenile = useAtamaYenile()
  const [tam, setTam] = useState("")
  const [yontem, setYontem] = useState<"mevcut" | "yeni">("mevcut")
  const [arama, setArama] = useState(() => tohum(hedef.temip_unvan))
  const [gecikmeli, setGecikmeli] = useState(arama)
  const [unvan, setUnvan] = useState(hedef.temip_unvan)
  const [sonuc, setSonuc] = useState<{ ton: "yesil" | "amber"; metin: string } | null>(null)
  useEffect(() => {
    const z = window.setTimeout(() => setGecikmeli(arama.trim()), 300)
    return () => window.clearTimeout(z)
  }, [arama])
  const personel = useQuery({ queryKey: ["tampon", "temip", "personel"], queryFn: () => oku<Personel[]>(`${TABAN}/personel`), staleTime: 300_000 })
  const kartlar = useQuery({
    queryKey: ["tampon", "temip", "kartlar", gecikmeli, tam],
    queryFn: () => oku<KartAday[]>(`${TABAN}/kartlar${sorguMetni({ q: gecikmeli, tam })}`),
    enabled: yontem === "mevcut" && (gecikmeli.length >= 2 || Boolean(tam)),
    placeholderData: keepPreviousData,
  })
  const ata = useMutation({
    mutationFn: (govde: { kart_id?: number; tam_id?: number; unvan?: string }) => yaz<AtamaSonucu>("POST", `${TABAN}/ata`, { musteri_no: hedef.musteri_no, ...govde }),
    onSuccess: (s) => {
      setSonuc({ ton: "yesil", metin: a.atandi(s.musteri_no, s.kart, sayi(s.yeniden_baglanan)) })
      yenile()
    },
    onError: (e) => setSonuc({ ton: "amber", metin: hataMesaji(e, a.islemBasarisiz) }),
  })
  const kisi = personel.data?.find((p) => String(p.id) === tam)
  const bitti = ata.isPending || ata.isSuccess
  return (
    <section aria-label={a.baslik(hedef.musteri_no)} className="grid gap-3 rounded-xl border-2 border-tl-yellow/70 bg-tl-yellow/5 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Link2 aria-hidden className="size-4 text-tl-navy" />
        <h4 className="text-xs font-black uppercase tracking-widest text-tl-navy">{a.baslik(hedef.musteri_no)}</h4>
        <span className="text-[0.6875rem] font-bold text-slate-500">{hedef.temip_unvan}</span>
        <button type="button" className={`${DUGME} ml-auto !px-2 !py-1`} aria-label={a.kapat} onClick={onKapat}>
          <X aria-hidden className="size-3.5" />
        </button>
      </div>
      <p className="text-[0.6875rem] font-bold text-slate-500">{a.aciklama}</p>
      <div className="flex flex-wrap items-end gap-3">
        <Alan etiket={a.personel} sinif="w-64">
          <select className={GIRDI} value={tam} onChange={(e) => setTam(e.target.value)}>
            <option value="">{a.tumPersonel}</option>
            {(personel.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.ad}
              </option>
            ))}
          </select>
        </Alan>
        <Sekmeler
          etiket={a.yontem}
          deger={yontem}
          onDegis={setYontem}
          secenekler={[
            { id: "mevcut", etiket: a.mevcut },
            { id: "yeni", etiket: a.yeni },
          ]}
        />
      </div>
      {sonuc ? <Bildirim ton={sonuc.ton}>{sonuc.metin}</Bildirim> : null}
      {yontem === "mevcut" ? (
        <>
          <Alan etiket={a.kartAra} sinif="max-w-md">
            <input className={GIRDI} value={arama} maxLength={100} onChange={(e) => setArama(e.target.value)} />
          </Alan>
          {kartlar.data && kartlar.data.length === 0 ? (
            <p className="text-xs font-bold text-slate-400">{a.kartYok}</p>
          ) : (
            <ul className="grid max-h-72 gap-1 overflow-auto">
              {(kartlar.data ?? []).map((k) => (
                <li key={k.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs">
                  <span className="font-black text-tl-navy">{k.ad}</span>
                  <span className="font-mono text-[0.6875rem] text-slate-500">{k.musteri_no || a.numarasiz}</span>
                  <button
                    type="button"
                    className={`${DUGME_ANA} ml-auto !px-3 !py-1`}
                    disabled={bitti}
                    onClick={() => {
                      if (window.confirm(a.onay(hedef.musteri_no, k.ad))) ata.mutate({ kart_id: k.id })
                    }}
                  >
                    {a.ata}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <div className="flex flex-wrap items-end gap-3">
          <Alan etiket={a.yeniUnvan} sinif="min-w-80 flex-1">
            <input className={GIRDI} value={unvan} maxLength={150} onChange={(e) => setUnvan(e.target.value)} />
          </Alan>
          <button
            type="button"
            className={DUGME_ANA}
            disabled={bitti || !kisi || !unvan.trim()}
            onClick={() => {
              if (kisi && window.confirm(a.yeniOnay(hedef.musteri_no, unvan.trim(), kisi.ad))) ata.mutate({ tam_id: kisi.id, unvan: unvan.trim() })
            }}
          >
            <Plus aria-hidden className="size-4" />
            {a.yeniAc}
          </button>
          {!kisi ? <span className="text-[0.6875rem] font-bold text-amber-600">{a.personelSec}</span> : null}
        </div>
      )}
    </section>
  )
}

/** Elle yapilan atamalar ve geri alma (numara karttan silinir, kayitlar Radar'a doner). */
export function ElleAtamalar({ dil }: { dil: Dil }) {
  const a = atamaMetin(dil)
  const yenile = useAtamaYenile()
  const [bilgi, setBilgi] = useState<{ ton: "yesil" | "amber"; metin: string } | null>(null)
  const q = useQuery({ queryKey: ["tampon", "temip", "atamalar"], queryFn: () => oku<ElleAtama[]>(`${TABAN}/atamalar`) })
  const kaldir = useMutation({
    mutationFn: (no: string) => yaz<{ musteri_no: string }>("POST", `${TABAN}/ata/kaldir`, { musteri_no: no }),
    onSuccess: (s) => {
      setBilgi({ ton: "yesil", metin: a.geriAlindi(s.musteri_no) })
      yenile()
    },
    onError: (e) => setBilgi({ ton: "amber", metin: hataMesaji(e, a.islemBasarisiz) }),
  })
  if (!q.data?.length) return null
  return (
    <div className="grid gap-2">
      <h4 className="text-[0.6875rem] font-black uppercase tracking-widest text-tl-navy">{a.liste(q.data.length)}</h4>
      {bilgi ? <Bildirim ton={bilgi.ton}>{bilgi.metin}</Bildirim> : null}
      <VeriTablosu<ElleAtama>
        baslik={a.liste(q.data.length)}
        satirlar={q.data}
        anahtar={(x) => x.musteri_no}
        kolonlar={[
          { baslik: a.musteriNo, hucre: (x) => <code className="text-[0.6875rem]">{x.musteri_no}</code> },
          { baslik: a.temipUnvan, hucre: (x) => <span className="line-clamp-1 max-w-64 font-normal">{x.temip_unvan}</span> },
          {
            baslik: a.kart,
            hucre: (x) => (
              <span className="flex flex-wrap items-center gap-1">
                <a href={`#/musteri?m=${x.kart_id}`} className="font-black text-tl-blue underline-offset-2 hover:underline">
                  {x.kart}
                </a>
                {x.yeni_kart ? <Rozet ton="sari">{a.yeniKart}</Rozet> : null}
              </span>
            ),
          },
          { baslik: a.personel, hucre: (x) => x.personel || "—" },
          { baslik: a.kayit, hucre: (x) => sayi(x.kayit), sinif: "text-right font-mono" },
          { baslik: a.kim, hucre: (x) => `${x.kim} · ${zaman(x.zaman)}` },
          {
            baslik: "",
            hucre: (x) => (
              <button
                type="button"
                className={DUGME}
                disabled={kaldir.isPending}
                onClick={() => {
                  if (window.confirm(a.geriAlOnay(x.musteri_no, x.kart))) kaldir.mutate(x.musteri_no)
                }}
              >
                <Undo2 aria-hidden className="size-3.5" />
                {a.geriAl}
              </button>
            ),
          },
        ]}
      />
    </div>
  )
}
