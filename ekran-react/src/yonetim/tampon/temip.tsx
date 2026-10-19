import { useState } from "react"
import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { Link2 } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Alan, Bildirim, Bolum, DUGME, GIRDI, HataKutu, Rozet, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import type { TemipDurumu, TemipEslesme, TemipMusterisi, TemipPersoneli } from "@/yonetim/api"
import { oku, sorguMetni } from "@/lib/sorgu"
import { sayi } from "@/lib/bicim"
import { Gosterge, Sayfalama } from "@/yonetim/ui"
import { tm } from "@/yonetim/tampon/metin"
import { AtamaPaneli, ElleAtamalar, atamaMetin } from "@/components/temip-atama"

const DURUMLAR: TemipDurumu[] = ["kart", "kart_personelsiz", "radar", "belirsiz"]
const TON: Record<TemipDurumu, "yesil" | "amber" | "gri" | "kirmizi"> = { kart: "yesil", kart_personelsiz: "amber", radar: "gri", belirsiz: "kirmizi" }
const GOSTERGE_TON = { kart: "ok", kart_personelsiz: "uyari", radar: "notr", belirsiz: "hata" } as const

function kisa(liste: string[]) {
  return liste.slice(0, 10).join(", ") + (liste.length > 10 ? "…" : "")
}

/** TEMIP alarm kayitlarinin eslesmesi (isci `temip-eslesme` ile ayni rapor). Tembel blok: acilmadan sunucuya istek gitmez. */
export function TemipEslesmesi({ dil }: { dil: Dil }) {
  const k = tm(dil).temip
  return (
    <Bolum anahtar="yonetim-tampon-temip" baslik={k.baslik} varsayilanAcik={false} tembel>
      <Icerik dil={dil} />
    </Bolum>
  )
}

function Icerik({ dil }: { dil: Dil }) {
  const t = tm(dil)
  const k = tm(dil).temip
  const [durum, setDurum] = useState<TemipDurumu | "">("")
  const [arama, setArama] = useState("")
  const [sayfa, setSayfa] = useState(1)
  const [hedef, setHedef] = useState<{ musteri_no: string; temip_unvan: string } | null>(null)
  const sorgu = { durum, q: arama.trim(), sayfa }
  const q = useQuery({
    queryKey: [...ANAHTAR.temipEslesme, sorgu],
    queryFn: () => oku<TemipEslesme>(`/api/v1/tampon/temip/eslesme${sorguMetni(sorgu)}`),
    placeholderData: keepPreviousData,
  })
  if (q.isPending) return <Yukleniyor metin={t.yukleniyor} iskelet />
  if (q.isError) return <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void q.refetch()} />
  const r = q.data
  if (!r.hazir) return <Bildirim ton="amber">{k.hazirDegil(r.neden)}</Bildirim>
  const u = r.uyari
  return (
    <div className={`grid gap-4 ${q.isPlaceholderData ? "opacity-70" : ""}`}>
      <p className="text-[0.6875rem] font-bold text-slate-400">{k.aciklama}</p>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {DURUMLAR.map((d) => (
          <Gosterge
            key={d}
            etiket={k.durumAdi[d]}
            deger={`${sayi(r.ozet[d].musteri)} ${k.musteri}`}
            alt={`${k.acik} ${sayi(r.ozet[d].acik)} · ${k.kapali} ${sayi(r.ozet[d].kapali)}`}
            ton={r.ozet[d].musteri || d === "kart" ? GOSTERGE_TON[d] : "notr"}
          />
        ))}
      </div>
      {u.belirsiz_numara.length ? <Bildirim ton="kirmizi">{k.belirsizUyari(u.belirsiz_numara.length, kisa(u.belirsiz_numara))}</Bildirim> : null}
      {u.personelsiz_kart.length ? <Bildirim ton="amber">{k.personelsizUyari(u.personelsiz_kart.length, kisa(u.personelsiz_kart))}</Bildirim> : null}
      {u.bicimsiz_kart_no.length ? <Bildirim ton="amber">{k.bicimsizUyari(u.bicimsiz_kart_no.length, kisa(u.bicimsiz_kart_no))}</Bildirim> : null}
      <p className="text-[0.6875rem] font-bold text-slate-500">
        {k.kayitsiz(u.kayitsiz_numarali_kart)}
        {r.bagli_olmayan ? ` · ${k.bekleyen(r.bagli_olmayan)}` : ""}
      </p>

      <div className="grid gap-2">
        <h4 className="text-[0.6875rem] font-black uppercase tracking-widest text-tl-navy">{k.personelBaslik}</h4>
        <VeriTablosu<TemipPersoneli>
          baslik={k.personelBaslik}
          satirlar={r.personel}
          anahtar={(p) => p.personel_kullanici || p.personel}
          kolonlar={[
            {
              baslik: k.personel,
              hucre: (p) => (
                <span className="font-black text-tl-navy">
                  {p.personel} {p.tam ? null : <Rozet ton="amber">{k.tamDegil}</Rozet>}
                </span>
              ),
            },
            { baslik: k.kart, hucre: (p) => sayi(p.kart), sinif: "text-right font-mono" },
            { baslik: k.acik, hucre: (p) => `${sayi(p.acik)} (${sayi(p.acik_ticketli)} ${k.ticketli})`, sinif: "text-right font-mono" },
            { baslik: k.kapali, hucre: (p) => sayi(p.kapali), sinif: "text-right font-mono" },
          ]}
        />
      </div>

      <div className="grid gap-2">
        <div className="flex flex-wrap items-end gap-3">
          <Alan etiket={t.durum} sinif="max-w-64">
            <select
              className={GIRDI}
              value={durum}
              onChange={(e) => {
                setDurum(e.target.value as TemipDurumu | "")
                setSayfa(1)
              }}
            >
              <option value="">{k.hepsi}</option>
              {DURUMLAR.map((d) => (
                <option key={d} value={d}>
                  {k.durumAdi[d]}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={k.ara} sinif="max-w-72 flex-1">
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
        </div>
        <VeriTablosu<TemipMusterisi>
          baslik={k.baslik}
          satirlar={r.musteriler}
          anahtar={(m) => m.musteri_no}
          bos={<p className="text-xs font-bold text-slate-400">{t.kayitYok}</p>}
          kolonlar={[
            { baslik: k.musteriNo, hucre: (m) => <code className="text-[0.6875rem]">{m.musteri_no}</code> },
            { baslik: k.temipUnvan, hucre: (m) => <span className="line-clamp-1 max-w-64 font-normal">{m.temip_unvan || "—"}</span> },
            { baslik: t.durum, hucre: (m) => <Rozet ton={TON[m.durum]}>{k.durumAdi[m.durum]}</Rozet> },
            {
              baslik: k.panelUnvan,
              hucre: (m) =>
                m.kart_id ? (
                  <a href={`#/musteri?m=${m.kart_id}`} className="font-black text-tl-blue underline-offset-2 hover:underline">
                    {m.panel_unvan}
                  </a>
                ) : (
                  <span className="font-normal text-slate-400">{m.aday_kartlar || "—"}</span>
                ),
            },
            { baslik: k.personel, hucre: (m) => m.personel || "—" },
            { baslik: k.acik, hucre: (m) => `${sayi(m.acik)} (${sayi(m.acik_ticketli)})`, sinif: "text-right font-mono" },
            { baslik: k.kapali, hucre: (m) => sayi(m.kapali), sinif: "text-right font-mono" },
            {
              baslik: "",
              hucre: (m) =>
                m.durum === "radar" ? (
                  <button type="button" className={`${DUGME} !px-2 !py-1`} onClick={() => setHedef({ musteri_no: m.musteri_no, temip_unvan: m.temip_unvan })}>
                    <Link2 aria-hidden className="size-3.5" />
                    {atamaMetin(dil).karttaAta}
                  </button>
                ) : null,
            },
          ]}
        />
        <Sayfalama t={t} sayfa={r.sayfa} adet={r.adet} toplam={r.toplam} onSayfa={setSayfa} />
        <p className="text-[0.625rem] font-bold text-slate-400">{t.atama.ipucu}</p>
        {hedef ? <AtamaPaneli key={hedef.musteri_no} dil={dil} hedef={hedef} onKapat={() => setHedef(null)} /> : null}
      </div>
      <ElleAtamalar dil={dil} />
    </div>
  )
}
