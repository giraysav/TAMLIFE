import { Fragment, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ChevronsDownUp, ChevronsUpDown, Info, Pin, Presentation, RefreshCw, Trash2 } from "lucide-react"
import { Bildirim, Bolum, BosKutu, DUGME, GIRDI, HataKutu, SayfaKabi, Yukleniyor } from "@/components/sayfa-ui"
import { zaman } from "@/lib/bicim"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { varsayilanYil, yilSecenekleri } from "@/lib/yillar"
import { yerel } from "@/shell/metin"
import type { Dil } from "@/shell/metin"
import { SayilarSeridi } from "@/sunum/sayilar-seridi"
import { AyrintiTablosu, BantRozeti, GenelOzet, SunumKarti, TakvimAyrinti, TakvimOzet, ayrintiSayisi, bosMu } from "@/sunum/sunum-kartlari"
import { SunumKaynaklari } from "@/sunum/sunum-kaynaklari"
import { sunumMetin } from "@/sunum/sunum-metin"
import { sayilarMi, takvimMi, tanitimMi } from "@/sunum/sunum-tipleri"
import type { Donem, Oge } from "@/sunum/sunum-tipleri"
import { TanitimIcerigi } from "@/sunum/tanitim-karti"
import { takvimMetin } from "@/takvim/takvim-metin"

const KUCUK_DUGME = `${DUGME} !px-2.5 !py-1`

/**
 * Ceyrek Bazli Sunum: ust yonetim icin KISA ozet. Secilen ceyregin ogeleri kaynak basina bir kart: KPI'lar ve ilk satirlar gorunur,
 * tablolar kartin "Ayrinti" bolumunde (tek tikla ya da "Tum ayrintilari ac" ile) acilir. Bu ceyrekte isaretli kaynaklar canli, gecmis
 * ceyrekte dondurulmus/gonderilmis kayitlar. Yetkili rol kaynaklari secer ve ogeyi sabitler/gunceller/kaldirir (sunucu zorlar).
 */
export function SunumSayfasi({ dil }: { dil: Dil }) {
  const t = sunumMetin(dil)
  const tt = takvimMetin(dil)
  const qc = useQueryClient()
  const simdi = new Date()
  const [yil, setYil] = useState(varsayilanYil(simdi))
  const [ceyrek, setCeyrek] = useState(Math.floor(simdi.getMonth() / 3) + 1)
  const [bilgi, setBilgi] = useState("")
  const [acik, setAcik] = useState<Record<string, boolean>>({})

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
  const bosOgeler = gorunen.filter(bosMu)
  const dolu = gorunen.filter((o) => !bosMu(o))
  const ayrintili = dolu.filter((o) => ayrintiSayisi(o) > 0)
  const hepsiAcik = ayrintili.length > 0 && ayrintili.every((o) => acik[o.kaynak])
  const hepsiniDegistir = () => setAcik(Object.fromEntries(ayrintili.map((o) => [o.kaynak, !hepsiAcik])))

  const oncekiYil = v && v.ceyrek === 1 ? v.yil - 1 : (v?.yil ?? 0)
  const oncekiCeyrek = v ? (v.ceyrek === 1 ? 4 : v.ceyrek - 1) : 0
  const oncekiEtiket = v && oncekiYil !== v.yil ? `${t.ceyrekKisa(oncekiCeyrek)} ${oncekiYil}` : t.ceyrekKisa(oncekiCeyrek)

  function alt(o: Oge): string {
    const ek = o.anlik ? ` · ${t.anlikNot}` : ""
    if (o.durum === "canli") return t.canliAlt(zaman(o.zaman)) + ek
    if (o.durum === "kayitli") return (o.gonderen ? t.gonderildiAlt(o.gonderen, zaman(o.zaman)) : t.dondurulduAlt(zaman(o.zaman))) + ek
    return ""
  }

  /** Altbilgideki kisa durum: canli kartta rozet yeter (yalniz 'anlik durum'), kayitlida tarih, gonderilmiste kim ve ne zaman. */
  function kisa(o: Oge): string {
    const ek = o.anlik ? t.anlikNot : ""
    if (o.durum === "kayitli") return [o.gonderen || null, zaman(o.zaman), ek || null].filter(Boolean).join(" · ")
    return ek
  }

  function rozet(o: Oge) {
    return o.durum === "canli" ? <BantRozeti ton="yesil">{t.canli}</BantRozeti> : o.durum === "hata" ? <BantRozeti ton="kirmizi">{t.hata}</BantRozeti> : o.gonderen ? <BantRozeti ton="sari">{t.gonderildi}</BantRozeti> : <BantRozeti ton="gri">{t.donduruldu}</BantRozeti>
  }

  function eylem(o: Oge) {
    if (!v?.yonetebilir) return null
    const dugme = (etiket: string, Ikon: typeof Pin, gonder: boolean, ipucu?: string) => (
      <button type="button" className={KUCUK_DUGME} title={ipucu} disabled={islem.isPending} onClick={() => islem.mutate({ kaynak: o.kaynak, gonder })}>
        <Ikon aria-hidden className="size-3.5" />
        {etiket}
      </button>
    )
    if (o.durum === "canli") return dugme(t.sabitle, Pin, true, t.sabitleIpucu)
    if (o.durum === "kayitli") {
      return (
        <>
          {dugme(t.guncelle, RefreshCw, true)}
          {dugme(t.kaldir, Trash2, false)}
        </>
      )
    }
    return null
  }

  function kart(o: Oge) {
    const ad = yerel(dil, o.ad, o.ad_en)
    const ortak = { baslik: ad, rozet: rozet(o), zaman: kisa(o), zamanAciklama: alt(o), eylem: eylem(o), acik: !!acik[o.kaynak], onAc: (a: boolean) => setAcik((s) => ({ ...s, [o.kaynak]: a })) }
    const veri = o.veri
    if (o.durum === "hata" || !veri) {
      return (
        <SunumKarti {...ortak} zaman="" ayrinti={undefined}>
          <HataKutu metin={t.kaynakHata(o.kayit_no)} />
        </SunumKarti>
      )
    }
    if (tanitimMi(veri)) {
      return (
        <SunumKarti {...ortak} genis bantsiz>
          <TanitimIcerigi veri={veri} dil={dil} rozet={ortak.rozet} />
        </SunumKarti>
      )
    }
    if (takvimMi(o.kaynak, veri)) {
      return (
        <SunumKarti {...ortak} ayrinti={{ etiket: t.ayrintiKisi(veri.uyeler.length), icerik: <TakvimAyrinti veri={veri} t={tt} /> }}>
          <TakvimOzet veri={veri} t={tt} />
        </SunumKarti>
      )
    }
    const ayrinti = veri.tablo && veri.tablo.satirlar.length > 0 ? { etiket: t.ayrintiSatir(veri.tablo.satirlar.length), icerik: <AyrintiTablosu tablo={veri.tablo} dil={dil} baslik={ad} /> } : undefined
    if (sayilarMi(veri)) {
      return (
        <SunumKarti {...ortak} genis ayrinti={ayrinti}>
          <SayilarSeridi veri={veri} dil={dil} oncekiEtiket={oncekiEtiket} farkli={v?.zaman === "gecmis"} />
        </SunumKarti>
      )
    }
    return (
      <SunumKarti {...ortak} ayrinti={ayrinti}>
        <GenelOzet veri={veri} dil={dil} />
      </SunumKarti>
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
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <p className="flex items-center gap-2 text-xs font-bold text-slate-500" title={v.zaman === "guncel" ? t.zamanGuncel : v.zaman === "gecmis" ? t.zamanGecmis : t.zamanGelecek}>
              <Info aria-hidden className="size-4 shrink-0 text-tl-blue" />
              {v.zaman === "guncel" ? t.durumGuncel : v.zaman === "gecmis" ? t.durumGecmis : t.durumGelecek}
            </p>
            {ayrintili.length > 0 ? (
              <button type="button" className={DUGME} onClick={hepsiniDegistir}>
                {hepsiAcik ? <ChevronsDownUp aria-hidden className="size-4" /> : <ChevronsUpDown aria-hidden className="size-4" />}
                {hepsiAcik ? t.hepsiniKapat : t.hepsiniAc}
              </button>
            ) : null}
          </div>
          {bilgi ? <Bildirim ton="kirmizi">{bilgi}</Bildirim> : null}
          {gorunen.length === 0 ? (
            <BosKutu ikon={Presentation} baslik={t.bos} aciklama={v.zaman === "gelecek" ? t.gelecekAlt : v.yonetebilir ? t.bosAltYetkili : t.bosAlt} />
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {dolu.map((o) => (
                <Fragment key={o.kaynak}>{kart(o)}</Fragment>
              ))}
            </div>
          )}
          {bosOgeler.length > 0 ? <Bildirim>{t.bosAlanlar(bosOgeler.map((o) => yerel(dil, o.ad, o.ad_en)).join(", "))}</Bildirim> : null}
          {kayitsiz.length > 0 ? <Bildirim ton="amber">{t.kayitYok(kayitsiz.map((o) => yerel(dil, o.ad, o.ad_en)).join(", "))}</Bildirim> : null}
        </>
      )}
    </div>
  )
}
