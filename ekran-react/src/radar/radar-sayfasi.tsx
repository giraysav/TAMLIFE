import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link2, Radar } from "lucide-react"
import { AtamaPaneli, ElleAtamalar, atamaMetin } from "@/components/temip-atama"
import type { AtamaHedefi } from "@/components/temip-atama"
import { Bildirim, BosKutu, DUGME, GIRDI, HataKutu, Panel, Rozet, SayfaKabi, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { sayi, zaman } from "@/lib/bicim"
import { hataMesaji, oku, sorguMetni } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"
import { radarMetin } from "@/radar/radar-metin"

type Aday = {
  sira: number
  musteri_no: string
  unvan: string
  aktif: number
  kapanan: number
  toplam: number
  ticketli?: number
  son_kayit?: string | null
  kart_adayi?: { id: number; ad: string } | null
}
type RadarVeri = {
  var: boolean
  taze: boolean
  veri_zamani: string | null
  kaynak?: "kayit" | "ozet" | ""
  satirlar: Aday[]
  toplam_musteri?: number
  toplam_kayit?: number
  sayfa?: number
  adet?: number
}
type Kayit = { kimlik: string; ticket: string; ci: string; baslik: string; durum: string; ayrinti: string; acilis: string | null; kapanis: string | null }
type Kayitlar = { musteri_no: string; unvan: string; toplam: number; sayfa: number; adet: number; kayitlar: Kayit[] }

const ADET = 50

/** TAM Radar: Musteri No'su hicbir kartla eslesmeyen TEMIP alarm kayitlari, musteri bazinda; elle giris yok. Sikayet/talep OneDesk'ten gelir (erisim bekleniyor). */
/** yonetici (admin): her satirda "Personele ata" (TEMIP Musteri No'sunu personelin mevcut kartina ekle ya da personele yeni kart ac;
 *  Veri Girisi > TEMIP eslesmesi ile ayni bilesen ve ayni uclar) ve elle atamalar listesi. */
export function RadarSayfasi({ dil, yonetici = false }: { dil: Dil; yonetici?: boolean }) {
  const t = radarMetin(dil)
  const [sayfa, setSayfa] = useState(1)
  const [arama, setArama] = useState("")
  const [secili, setSecili] = useState<string | null>(null)
  const [hedef, setHedef] = useState<AtamaHedefi | null>(null)
  const a = atamaMetin(dil)
  const q = useQuery({
    queryKey: ["radar", sayfa, arama],
    queryFn: () => oku<RadarVeri>(`/api/v1/radar${sorguMetni({ sayfa, adet: ADET, q: arama.trim() || undefined })}`),
  })
  const v = q.data
  const kayitModu = v?.kaynak === "kayit"
  const toplamSayfa = v?.toplam_musteri && v.adet ? Math.max(1, Math.ceil(v.toplam_musteri / v.adet)) : 1
  const bilet = (
    <span className="text-slate-400" title={t.biletYok}>
      —
    </span>
  )

  return (
    <div className="grid grid-cols-1 gap-4">
      <SayfaKabi ikon={Radar} baslik={t.baslik} aciklama={t.aciklama} />
      <Bildirim>{kayitModu ? t.kuralKayit : t.kural}</Bildirim>
      <Panel>
        {q.isPending ? (
          <Yukleniyor metin={t.yukleniyor} />
        ) : q.isError ? (
          <HataKutu metin={hataMesaji(q.error, t.yuklenemedi)} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
        ) : v && !v.var ? (
          <BosKutu ikon={Radar} baslik={t.veriYok} />
        ) : v ? (
          <div className="grid gap-3">
            {!v.taze ? <Bildirim ton="amber">{t.bayat}</Bildirim> : null}
            {kayitModu ? (
              <div className="flex flex-wrap items-end gap-3">
                <label className="grid gap-1 text-xs font-bold text-slate-600">
                  {t.ara}
                  <input
                    className={GIRDI}
                    value={arama}
                    maxLength={100}
                    placeholder={t.araIpucu}
                    onChange={(e) => {
                      setArama(e.target.value)
                      setSayfa(1)
                    }}
                  />
                </label>
                <p className="text-xs font-bold text-slate-500">
                  {t.ozet(sayi(v.toplam_musteri ?? 0), sayi(v.toplam_kayit ?? 0))}
                </p>
              </div>
            ) : null}
            <VeriTablosu
              baslik={t.baslik}
              satirlar={v.satirlar}
              anahtar={(a) => a.musteri_no}
              vurgulu={(a) => a.musteri_no === secili}
              bos={<BosKutu ikon={Radar} baslik={t.bos} />}
              kolonlar={[
                { baslik: "#", hucre: (a) => a.sira, sinif: "w-10 text-center text-slate-400" },
                {
                  baslik: t.kolUnvan,
                  hucre: (a) => (
                    <div className="grid gap-1">
                      <span className="font-black text-tl-navy">{a.unvan}</span>
                      {a.kart_adayi ? <Rozet ton="amber">{t.kartAdayi(a.kart_adayi.ad)}</Rozet> : null}
                    </div>
                  ),
                },
                { baslik: t.kolNo, hucre: (a) => <span className="font-mono">{a.musteri_no}</span> },
                { baslik: t.kolAlarm, hucre: (a) => `${sayi(a.aktif)} / ${sayi(a.kapanan)}`, sinif: "text-center" },
                ...(kayitModu ? [{ baslik: t.kolTicket, hucre: (a: Aday) => sayi(a.ticketli ?? 0), sinif: "text-center" }] : []),
                { baslik: t.kolToplam, hucre: (a) => <span className="font-black text-rose-600">{sayi(a.toplam)}</span>, sinif: "text-center" },
                ...(kayitModu ? [{ baslik: t.kolSon, hucre: (a: Aday) => zaman(a.son_kayit), sinif: "whitespace-nowrap" }] : []),
                { baslik: t.kolSikayet, hucre: () => bilet, sinif: "text-center" },
                { baslik: t.kolTalep, hucre: () => bilet, sinif: "text-center" },
                ...(kayitModu
                  ? [
                      {
                        baslik: "",
                        hucre: (s: Aday) => (
                          <span className="flex flex-wrap justify-end gap-1">
                            {yonetici ? (
                              <button type="button" className={DUGME} onClick={() => setHedef({ musteri_no: s.musteri_no, temip_unvan: s.unvan })}>
                                <Link2 aria-hidden className="size-3.5" />
                                {a.karttaAta}
                              </button>
                            ) : null}
                            <button type="button" className={DUGME} aria-expanded={secili === s.musteri_no} onClick={() => setSecili(secili === s.musteri_no ? null : s.musteri_no)}>
                              {secili === s.musteri_no ? t.kapat : t.kayitlar}
                            </button>
                          </span>
                        ),
                      },
                    ]
                  : []),
              ]}
            />
            {kayitModu && toplamSayfa > 1 ? (
              <div className="flex items-center gap-2 text-xs font-bold text-slate-600">
                <button type="button" className={DUGME} disabled={sayfa <= 1} onClick={() => setSayfa(sayfa - 1)}>
                  {t.onceki}
                </button>
                <span>{t.sayfa(sayfa, toplamSayfa)}</span>
                <button type="button" className={DUGME} disabled={sayfa >= toplamSayfa} onClick={() => setSayfa(sayfa + 1)}>
                  {t.sonraki}
                </button>
              </div>
            ) : null}
            {kayitModu && secili ? <KayitListesi musteriNo={secili} dil={dil} /> : null}
            {yonetici && hedef ? <AtamaPaneli key={hedef.musteri_no} dil={dil} hedef={hedef} onKapat={() => setHedef(null)} /> : null}
            {yonetici && kayitModu ? <ElleAtamalar dil={dil} /> : null}
            <p className="text-[0.6875rem] font-bold text-slate-400">
              {kayitModu ? t.dipnotKayit : t.dipnot}
              {v.veri_zamani ? ` · ${t.veriZamani}: ${kayitModu ? zaman(v.veri_zamani) : v.veri_zamani}` : ""}
            </p>
          </div>
        ) : null}
      </Panel>
    </div>
  )
}

function KayitListesi({ musteriNo, dil }: { musteriNo: string; dil: Dil }) {
  const t = radarMetin(dil)
  const [sayfa, setSayfa] = useState(1)
  const q = useQuery({
    queryKey: ["radar-kayit", musteriNo, sayfa],
    queryFn: () => oku<Kayitlar>(`/api/v1/radar/${encodeURIComponent(musteriNo)}/kayitlar${sorguMetni({ sayfa })}`),
  })
  const v = q.data
  const toplamSayfa = v ? Math.max(1, Math.ceil(v.toplam / v.adet)) : 1
  return (
    <section className="grid gap-2 rounded-xl border border-slate-200 p-3" aria-label={t.kayitBaslik(musteriNo)}>
      {q.isPending ? (
        <Yukleniyor metin={t.yukleniyor} />
      ) : q.isError ? (
        <HataKutu metin={hataMesaji(q.error, t.yuklenemedi)} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
      ) : v ? (
        <>
          <p className="text-xs font-black text-tl-navy">
            {v.unvan} · <span className="font-mono">{v.musteri_no}</span> · {t.kayitSayisi(sayi(v.toplam))}
          </p>
          <VeriTablosu
            baslik={t.kayitBaslik(v.musteri_no)}
            satirlar={v.kayitlar}
            anahtar={(k) => k.kimlik}
            kolonlar={[
              { baslik: t.kolTicketNo, hucre: (k) => <span className="font-mono">{k.ticket || "—"}</span> },
              { baslik: t.kolCi, hucre: (k) => <span className="break-all">{k.ci || "—"}</span> },
              { baslik: t.kolBaslik, hucre: (k) => k.baslik || "—" },
              {
                baslik: t.kolDurum,
                hucre: (k) => (
                  <div className="grid gap-0.5">
                    <Rozet ton={k.durum === "open" ? "kirmizi" : "yesil"}>{k.durum === "open" ? t.acik : t.kapali}</Rozet>
                    {k.ayrinti ? <span className="text-[0.625rem] text-slate-500">{k.ayrinti}</span> : null}
                  </div>
                ),
              },
              { baslik: t.kolAcilis, hucre: (k) => zaman(k.acilis), sinif: "whitespace-nowrap" },
              { baslik: t.kolKapanis, hucre: (k) => (k.kapanis ? zaman(k.kapanis) : "—"), sinif: "whitespace-nowrap" },
            ]}
          />
          {toplamSayfa > 1 ? (
            <div className="flex items-center gap-2 text-xs font-bold text-slate-600">
              <button type="button" className={DUGME} disabled={sayfa <= 1} onClick={() => setSayfa(sayfa - 1)}>
                {t.onceki}
              </button>
              <span>{t.sayfa(sayfa, toplamSayfa)}</span>
              <button type="button" className={DUGME} disabled={sayfa >= toplamSayfa} onClick={() => setSayfa(sayfa + 1)}>
                {t.sonraki}
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  )
}
