import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Pin, Presentation, RefreshCw, Trash2 } from "lucide-react"
import { Bildirim, Bolum, BosKutu, DUGME, GIRDI, HataKutu, Kpi, Panel, Rozet, SayfaKabi, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { para, sayi, zaman } from "@/lib/bicim"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { yerel } from "@/shell/metin"
import type { Dil } from "@/shell/metin"
import { SunumKaynaklari } from "@/sunum/sunum-kaynaklari"
import { sunumMetin } from "@/sunum/sunum-metin"
import { TakvimGrafigi } from "@/takvim/takvim-grafigi"
import type { GrafikUyesi, Ozet } from "@/takvim/takvim-grafigi"
import { takvimMetin } from "@/takvim/takvim-metin"
import { varsayilanYil, yilSecenekleri } from "@/lib/yillar"

type Hucre = string | number | null
type GenelVeri = {
  kpi: { ad: string; ad_en: string; deger: number | null; birim: string; alt: string }[]
  tablo?: { sutunlar: { ad: string; ad_en: string; birim: string }[]; satirlar: Hucre[][] }
}
type TakvimVeri = { genel: Ozet; uyeler: GrafikUyesi[] }
type Oge = {
  kaynak: string
  ad: string
  ad_en: string
  anlik: boolean
  durum: "canli" | "kayitli" | "yok" | "hata"
  gonderen: string
  zaman: string | null
  veri: GenelVeri | TakvimVeri | null
  kayit_no: string
}
type Donem = { yil: number; ceyrek: number; donem: string; zaman: "guncel" | "gecmis" | "gelecek"; ogeler: Oge[]; yonetebilir: boolean }

const hucre = (v: Hucre | undefined, birim: string) => (v === null || v === undefined ? "—" : typeof v === "number" ? (birim ? para(v, birim) : sayi(v)) : v)

/** Modul/rapor kaynaklarinin genel karti: sunucunun verdigi KPI'lar ve tablo (etiketler TR/EN sunucudan). */
function GenelKart({ veri, dil, baslik }: { veri: GenelVeri; dil: Dil; baslik: string }) {
  const t = sunumMetin(dil)
  const tablo = veri.tablo
  return (
    <div className="grid gap-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {veri.kpi.map((k) => (
          <Kpi key={k.ad} etiket={yerel(dil, k.ad, k.ad_en)} deger={k.birim ? para(k.deger, k.birim) : sayi(k.deger)} alt={k.alt || undefined} />
        ))}
      </div>
      {tablo ? (
        <VeriTablosu
          baslik={baslik}
          kolonlar={tablo.sutunlar.map((s, i) => ({ baslik: yerel(dil, s.ad, s.ad_en), hucre: (satir: Hucre[]) => hucre(satir[i], s.birim) }))}
          satirlar={tablo.satirlar}
          bos={<p className="text-xs font-bold text-slate-400">{t.tabloBos}</p>}
        />
      ) : null}
    </div>
  )
}

/**
 * Ceyrek Bazli Sunum: secilen ceyregin ogeleri kaynak basina bir kart. Bu ceyrekte isaretli kaynaklar canli, gecmis ceyrekte
 * dondurulmus/gonderilmis kayitlar. Yetkili rol kaynaklari secer ve ogeyi sabitler/gunceller/kaldirir (sunucu zorlar).
 */
export function SunumSayfasi({ dil }: { dil: Dil }) {
  const t = sunumMetin(dil)
  const tt = takvimMetin(dil)
  const qc = useQueryClient()
  const simdi = new Date()
  const [yil, setYil] = useState(varsayilanYil(simdi))
  const [ceyrek, setCeyrek] = useState(Math.floor(simdi.getMonth() / 3) + 1)
  const [bilgi, setBilgi] = useState("")

  const q = useQuery({ queryKey: ["sunum", "donem", yil, ceyrek], queryFn: () => oku<Donem>(`/api/v1/sunum/donem?yil=${yil}&ceyrek=${ceyrek}`) })
  const islem = useMutation({
    mutationFn: ({ kaynak, gonder }: { kaynak: string; gonder: boolean }) => yaz("POST", "/api/v1/sunum/gonder", { kaynak, yil, ceyrek, gonder }),
    onMutate: () => setBilgi(""),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["sunum", "donem"] })
      void qc.invalidateQueries({ queryKey: ["takvim", "ekip"] })
    },
    onError: (e) => setBilgi(hataMesaji(e, t.islemHata)),
  })
  const v = q.data
  const gorunen = v?.ogeler.filter((o) => o.durum !== "yok") ?? []
  const kayitsiz = v?.ogeler.filter((o) => o.durum === "yok") ?? []

  function alt(o: Oge): string {
    const ek = o.anlik ? ` · ${t.anlikNot}` : ""
    if (o.durum === "canli") return t.canliAlt(zaman(o.zaman)) + ek
    if (o.durum === "kayitli") return (o.gonderen ? t.gonderildiAlt(o.gonderen, zaman(o.zaman)) : t.dondurulduAlt(zaman(o.zaman))) + ek
    return ""
  }

  function sag(o: Oge) {
    const rozet =
      o.durum === "canli" ? <Rozet ton="yesil">{t.canli}</Rozet> : o.durum === "hata" ? <Rozet ton="kirmizi">{t.hata}</Rozet> : o.gonderen ? <Rozet ton="sari">{t.gonderildi}</Rozet> : <Rozet>{t.donduruldu}</Rozet>
    const dugme = (etiket: string, Ikon: typeof Pin, gonder: boolean, ipucu?: string) => (
      <button type="button" className={DUGME} title={ipucu} disabled={islem.isPending} onClick={() => islem.mutate({ kaynak: o.kaynak, gonder })}>
        <Ikon aria-hidden className="size-3.5" />
        {etiket}
      </button>
    )
    return (
      <div className="flex flex-wrap items-center gap-2">
        {rozet}
        {v?.yonetebilir && o.durum === "canli" ? dugme(t.sabitle, Pin, true, t.sabitleIpucu) : null}
        {v?.yonetebilir && o.durum === "kayitli" ? (
          <>
            {dugme(t.guncelle, RefreshCw, true)}
            {dugme(t.kaldir, Trash2, false)}
          </>
        ) : null}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4">
      <SayfaKabi ikon={Presentation} baslik={t.baslik} aciklama={t.aciklama}>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-[0.625rem] font-black uppercase tracking-wide text-white/70">
            {t.yil}
            <select className={`${GIRDI} !w-auto !py-2`} value={yil} onChange={(e) => setYil(Number(e.target.value))}>
              {yilSecenekleri(2, simdi).map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </label>
          <div role="group" aria-label={t.donem} className="flex overflow-hidden rounded-xl border border-white/30">
            {[1, 2, 3, 4].map((c) => (
              <button
                key={c}
                type="button"
                aria-pressed={ceyrek === c}
                onClick={() => setCeyrek(c)}
                className={`px-3 py-2 text-xs font-black transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow ${ceyrek === c ? "bg-tl-yellow text-tl-navy" : "text-white/80 hover:bg-white/10"}`}
              >
                {t.ceyrekKisa(c)}
              </button>
            ))}
          </div>
        </div>
      </SayfaKabi>

      {v?.yonetebilir ? (
        <Bolum anahtar="sunum-kaynaklar" baslik={t.kaynaklarBaslik} varsayilanAcik={false}>
          <SunumKaynaklari dil={dil} />
        </Bolum>
      ) : null}

      {q.isPending ? (
        <Yukleniyor metin={t.yukleniyor} />
      ) : q.isError || !v ? (
        <HataKutu metin={t.yuklenemedi} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
      ) : (
        <>
          <Bildirim>{v.zaman === "guncel" ? t.zamanGuncel : v.zaman === "gecmis" ? t.zamanGecmis : t.zamanGelecek}</Bildirim>
          {bilgi ? <Bildirim ton="kirmizi">{bilgi}</Bildirim> : null}
          {gorunen.length === 0 ? (
            <BosKutu ikon={Presentation} baslik={t.bos} aciklama={v.zaman === "gelecek" ? t.gelecekAlt : v.yonetebilir ? t.bosAltYetkili : t.bosAlt} />
          ) : (
            gorunen.map((o) => {
              const ad = yerel(dil, o.ad, o.ad_en)
              return (
                <Panel key={o.kaynak} baslik={ad} aciklama={alt(o)} sag={sag(o)}>
                  {o.durum === "hata" || !o.veri ? (
                    <HataKutu metin={t.kaynakHata(o.kayit_no)} />
                  ) : o.kaynak === "takvim" ? (
                    <TakvimGrafigi genel={(o.veri as TakvimVeri).genel} uyeler={(o.veri as TakvimVeri).uyeler} t={tt} />
                  ) : (
                    <GenelKart veri={o.veri as GenelVeri} dil={dil} baslik={ad} />
                  )}
                </Panel>
              )
            })
          )}
          {kayitsiz.length > 0 ? <Bildirim ton="amber">{t.kayitYok(kayitsiz.map((o) => yerel(dil, o.ad, o.ad_en)).join(", "))}</Bildirim> : null}
        </>
      )}
    </div>
  )
}
