import { Fragment, useState } from "react"
import type { DragEvent } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { BadgeCheck, ChevronsDownUp, ChevronsUpDown, Info, LayoutList, LockOpen, Maximize2, Pin, Presentation, RefreshCw, Trash2 } from "lucide-react"
import { Cekmece } from "@/components/cekmece"
import { Bildirim, BosKutu, DUGME, DUGME_SARI, GIRDI, HataKutu, SayfaKabi, Yukleniyor } from "@/components/sayfa-ui"
import { zaman } from "@/lib/bicim"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { varsayilanYil, yilSecenekleri } from "@/lib/yillar"
import { yerel } from "@/shell/metin"
import type { Dil } from "@/shell/metin"
import { SayilarSeridi } from "@/sunum/sayilar-seridi"
import { AyrintiTablosu, BantRozeti, GenelOzet, SunumKarti, TakvimAyrinti, TakvimOzet, ayrintiSayisi } from "@/sunum/sunum-kartlari"
import { SunumKaynaklari, useDuzenKaydet, useKaynaklar } from "@/sunum/sunum-kaynaklari"
import { SunumSenkron } from "@/sunum/sunum-senkron"
import { SunumSlayt } from "@/sunum/sunum-slayt"
import { sunumMetin } from "@/sunum/sunum-metin"
import { sayilarMi, takvimMi, tanitimMi } from "@/sunum/sunum-tipleri"
import type { Donem, Oge } from "@/sunum/sunum-tipleri"
import { TanitimIcerigi } from "@/sunum/tanitim-karti"
import { takvimMetin } from "@/takvim/takvim-metin"

const KUCUK_DUGME = `${DUGME} !px-2.5 !py-1`

/** Tam ekranda buyuk tanitim tek sayfa; genis ozetler yarim, kisa kartlar ceyrek sayfa kaplar. */
export function sunumSayfalari(ogeler: Oge[]): Oge[][] {
  const sayfalar: Oge[][] = []
  let sayfa: Oge[] = []
  let doluluk = 0
  const agirlik = (o: Oge) => (o.veri && tanitimMi(o.veri) ? 4 : o.veri && sayilarMi(o.veri) ? 2 : 1)
  for (const o of ogeler) {
    const a = agirlik(o)
    if (sayfa.length && doluluk + a > 4) {
      sayfalar.push(sayfa)
      sayfa = []
      doluluk = 0
    }
    sayfa.push(o)
    doluluk += a
    if (doluluk === 4) {
      sayfalar.push(sayfa)
      sayfa = []
      doluluk = 0
    }
  }
  if (sayfa.length) sayfalar.push(sayfa)
  return sayfalar
}

/**
 * Ceyrek Bazli Sunum: ust yonetim icin KISA ozet. Panelin her modulunun kendi alani (kart) vardir; o ceyrekte verisi olmasa da alan durur.
 * Hangi alanlarin hangi sirayla yer alacagi "Sunum icerigi" penceresinden secilir; yetkili kartlari surukleyerek de tasiyabilir.
 * "Sunumu onayla" ceyregin o anki halini sabitler (veri degisse de onayli sunum degismez; tasima/sabitleme kapanir). "Tam ekran sunum"
 * alanlari tek tek slayt olarak gosterir. Yetkiyi sunucu zorlar.
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
  const [pencere, setPencere] = useState(false)
  const [senkron, setSenkron] = useState(false)
  const [slayt, setSlayt] = useState(false)
  const [suruklenen, setSuruklenen] = useState<string | null>(null)
  const [hedef, setHedef] = useState<string | null>(null)

  const anahtar = ["sunum", "donem", yil, ceyrek]
  // Icinde bulunulan ceyrek canlidir: 30 sn'de bir ve pencereye donuldugunde yeniden okunur (modullere girilen veri sunuma akar).
  const q = useQuery({
    queryKey: anahtar,
    queryFn: () => oku<Donem>(`/api/v1/sunum/donem?yil=${yil}&ceyrek=${ceyrek}`),
    refetchInterval: (s) => (s.state.data?.zaman === "guncel" && !s.state.data.onay ? 30_000 : false),
    refetchOnWindowFocus: true,
  })
  const v = q.data
  const kq = useKaynaklar()
  const duzen = useDuzenKaydet()
  const yenile = () => {
    void qc.invalidateQueries({ queryKey: ["sunum", "donem"] })
    void qc.invalidateQueries({ queryKey: ["takvim", "ekip"] })
  }
  const islem = useMutation({
    mutationFn: ({ kaynak, gonder }: { kaynak: string; gonder: boolean }) => yaz("POST", "/api/v1/sunum/gonder", { kaynak, yil, ceyrek, gonder }),
    onMutate: () => setBilgi(""),
    onSuccess: yenile,
    onError: (e) => setBilgi(hataMesaji(e, t.islemHata)),
  })
  const onay = useMutation({
    mutationFn: (deger: boolean) => yaz("POST", "/api/v1/sunum/onay", { yil, ceyrek, onay: deger }),
    onMutate: () => setBilgi(""),
    onSuccess: yenile,
    onError: (e) => setBilgi(hataMesaji(e, t.islemHata)),
  })
  const onayli = !!v?.onay
  const ogeler = v?.ogeler ?? []
  const tasinabilir = !!v?.yonetebilir && !onayli && !!kq.data?.duzenleyebilir
  const ayrintili = ogeler.filter((o) => ayrintiSayisi(o) > 0)
  const hepsiAcik = ayrintili.length > 0 && ayrintili.every((o) => acik[o.kaynak])
  const hepsiniDegistir = () => setAcik(Object.fromEntries(ayrintili.map((o) => [o.kaynak, !hepsiAcik])))

  const oncekiYil = v && v.ceyrek === 1 ? v.yil - 1 : (v?.yil ?? 0)
  const oncekiCeyrek = v ? (v.ceyrek === 1 ? 4 : v.ceyrek - 1) : 0
  const oncekiEtiket = v && oncekiYil !== v.yil ? `${t.ceyrekKisa(oncekiCeyrek)} ${oncekiYil}` : t.ceyrekKisa(oncekiCeyrek)

  /** Surukleneni hedefin yerine koyar; tum alan listesindeki gorunur yerler yeni sirayla doldurulur (gizli alanlar yerinde kalir). */
  function birak(hedefId: string) {
    const liste = kq.data?.kaynaklar
    const kaynak = suruklenen
    setSuruklenen(null)
    setHedef(null)
    if (!liste || !kaynak || kaynak === hedefId) return
    const gorunen = ogeler.map((o) => o.kaynak).filter((id) => liste.some((k) => k.id === id))
    const eski = gorunen.indexOf(kaynak)
    const yeniYer = gorunen.indexOf(hedefId)
    if (eski < 0 || yeniYer < 0) return
    const yeni = gorunen.filter((id) => id !== kaynak)
    yeni.splice(yeniYer, 0, kaynak)
    const sirali = yeni.map((id) => liste.find((k) => k.id === id)!)
    let j = 0
    duzen.mutate(liste.map((k) => (yeni.includes(k.id) ? sirali[j++] : k)))
    qc.setQueryData<Donem>(anahtar, (d) => d && { ...d, ogeler: [...d.ogeler].sort((a, b) => yeniSira(a.kaynak) - yeniSira(b.kaynak)) })
    function yeniSira(id: string) {
      const n = yeni.indexOf(id)
      return n < 0 ? yeni.length : n
    }
  }

  function surukle(o: Oge) {
    if (!tasinabilir) return undefined
    return {
      etiket: t.surukle,
      uzerinde: hedef === o.kaynak && suruklenen !== o.kaynak,
      suruklenen: suruklenen === o.kaynak,
      bas: (e: DragEvent) => {
        e.dataTransfer.effectAllowed = "move"
        e.dataTransfer.setData("text/plain", o.kaynak)
        setSuruklenen(o.kaynak)
      },
      uzerinden: (e: DragEvent) => {
        if (!suruklenen) return
        e.preventDefault()
        e.dataTransfer.dropEffect = "move"
        if (hedef !== o.kaynak) setHedef(o.kaynak)
      },
      birak: (e: DragEvent) => {
        e.preventDefault()
        birak(o.kaynak)
      },
      bitir: () => {
        setSuruklenen(null)
        setHedef(null)
      },
    }
  }

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
    if (onayli) return <BantRozeti ton="sari">{t.onayli}</BantRozeti>
    if (o.durum === "yok") return <BantRozeti ton="gri">{t.veriYokRozet}</BantRozeti>
    return o.durum === "canli" ? <BantRozeti ton="yesil">{t.canli}</BantRozeti> : o.durum === "hata" ? <BantRozeti ton="kirmizi">{t.hata}</BantRozeti> : o.gonderen ? <BantRozeti ton="sari">{t.gonderildi}</BantRozeti> : <BantRozeti ton="gri">{t.donduruldu}</BantRozeti>
  }

  function eylem(o: Oge) {
    if (!v?.yonetebilir || onayli) return null
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

  /** Bir alanin karti. Slaytta yalniz ozet gorunur; tasma ve ic kaydirma uretecek ayrinti acilmaz. */
  function kart(o: Oge, slaytta = false) {
    const ad = yerel(dil, o.ad, o.ad_en)
    const ortak = {
      baslik: ad,
      rozet: rozet(o),
      zaman: slaytta ? "" : kisa(o),
      zamanAciklama: alt(o),
      eylem: slaytta ? undefined : eylem(o),
      acik: !slaytta && !!acik[o.kaynak],
      onAc: slaytta ? undefined : (a: boolean) => setAcik((s) => ({ ...s, [o.kaynak]: a })),
      surukle: slaytta ? undefined : surukle(o),
    }
    const veri = o.veri
    const bos = (metin: string) => (
      <SunumKarti {...ortak} zaman="" ayrinti={undefined}>
        <p className="flex items-center gap-2 rounded-xl border border-dashed border-slate-200 bg-slate-50/70 px-3 py-4 text-xs font-bold text-slate-400">
          <Info aria-hidden className="size-4 shrink-0" />
          {metin}
        </p>
      </SunumKarti>
    )
    if (o.durum === "yok") return bos(v?.zaman === "gelecek" ? t.veriYokGelecek : t.veriYok)
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
        <SunumKarti {...ortak} ayrinti={slaytta ? undefined : { etiket: t.ayrintiKisi(veri.uyeler.length), icerik: <TakvimAyrinti veri={veri} t={tt} /> }}>
          <TakvimOzet veri={veri} t={tt} />
        </SunumKarti>
      )
    }
    if (veri.kpi.length === 0 && !(veri.tablo && veri.tablo.satirlar.length > 0)) return bos(t.veriYok)
    const ayrinti = !slaytta && veri.tablo && veri.tablo.satirlar.length > 0 ? { etiket: t.ayrintiSatir(veri.tablo.satirlar.length), icerik: <AyrintiTablosu tablo={veri.tablo} dil={dil} baslik={ad} /> } : undefined
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

      {q.isPending ? (
        <Yukleniyor metin={t.yukleniyor} />
      ) : q.isError || !v ? (
        <HataKutu metin={t.yuklenemedi} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            {v.onay ? (
              <p className="flex items-center gap-2 rounded-xl border border-tl-yellow/70 bg-tl-yellow/15 px-3 py-1.5 text-xs font-black text-tl-navy">
                <BadgeCheck aria-hidden className="size-4 shrink-0" />
                {t.onayliDurum(v.onay.onaylayan, zaman(v.onay.zaman))}
              </p>
            ) : (
              <p className="flex items-center gap-2 text-xs font-bold text-slate-500" title={v.zaman === "guncel" ? t.zamanGuncel : v.zaman === "gecmis" ? t.zamanGecmis : t.zamanGelecek}>
                <Info aria-hidden className="size-4 shrink-0 text-tl-blue" />
                {v.zaman === "guncel" ? t.durumGuncel : v.zaman === "gecmis" ? t.durumGecmis : t.durumGelecek}
              </p>
            )}
            <div className="flex flex-wrap items-center gap-2">
              {ayrintili.length > 0 ? (
                <button type="button" className={DUGME} onClick={hepsiniDegistir}>
                  {hepsiAcik ? <ChevronsDownUp aria-hidden className="size-4" /> : <ChevronsUpDown aria-hidden className="size-4" />}
                  {hepsiAcik ? t.hepsiniKapat : t.hepsiniAc}
                </button>
              ) : null}
              {v.yonetebilir ? (
                <button type="button" className={DUGME} onClick={() => setPencere(true)}>
                  <LayoutList aria-hidden className="size-4" />
                  {t.kaynaklarBaslik}
                </button>
              ) : null}
              {v.yonetebilir && v.zaman !== "gelecek" ? (
                onayli ? (
                  <button type="button" className={DUGME} disabled={onay.isPending} onClick={() => onay.mutate(false)}>
                    <LockOpen aria-hidden className="size-4" />
                    {t.onayKaldir}
                  </button>
                ) : (
                  <button type="button" className={`${DUGME_SARI} !min-w-0`} title={t.onayIpucu} disabled={onay.isPending || ogeler.length === 0} onClick={() => onay.mutate(true)}>
                    <BadgeCheck aria-hidden className="size-4" />
                    {t.onayla}
                  </button>
                )
              ) : null}
              <button type="button" className={DUGME} title={t.senkronAciklama} onClick={() => setSenkron(true)}>
                <RefreshCw aria-hidden className="size-4" />
                {t.senkron}
              </button>
              <button type="button" className={DUGME} disabled={ogeler.length === 0} onClick={() => setSlayt(true)}>
                <Maximize2 aria-hidden className="size-4" />
                {t.tamEkran}
              </button>
            </div>
          </div>
          {bilgi ? <Bildirim ton="kirmizi">{bilgi}</Bildirim> : null}
          {duzen.isError ? <Bildirim ton="kirmizi">{hataMesaji(duzen.error, t.kaydedilemedi)}</Bildirim> : null}
          {ogeler.length === 0 ? (
            <BosKutu ikon={Presentation} baslik={t.bos} aciklama={v.yonetebilir ? t.bosAltYetkili : t.bosAlt} />
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {ogeler.map((o) => (
                <Fragment key={o.kaynak}>{kart(o)}</Fragment>
              ))}
            </div>
          )}
        </>
      )}

      <Cekmece acik={pencere} onKapat={() => setPencere(false)} baslik={t.kaynaklarBaslik} kapatEtiketi={t.kapat} genis>
        {pencere ? <SunumKaynaklari dil={dil} onayli={onayli} /> : null}
      </Cekmece>
      <Cekmece acik={senkron} onKapat={() => setSenkron(false)} baslik={`${t.senkron} · ${t.ceyrekKisa(ceyrek)} ${yil}`} aciklama={t.senkronAciklama} kapatEtiketi={t.kapat} genis>
        {senkron ? <SunumSenkron dil={dil} yil={yil} ceyrek={ceyrek} /> : null}
      </Cekmece>
      {slayt && v && ogeler.length > 0 ? (() => {
        const sayfalar = sunumSayfalari(ogeler)
        return (
          <SunumSlayt
            adet={sayfalar.length}
            ciz={(i) => {
              const sayfa = sayfalar[i]
              const genisVar = sayfa.some((o) => !!o.veri && (sayilarMi(o.veri) || tanitimMi(o.veri)))
              return (
              <div className="grid h-full min-h-0 grid-flow-row-dense grid-cols-2 grid-rows-2 gap-3">
                {sayfa.map((o, sira) => {
                  const genis = !!o.veri && (sayilarMi(o.veri) || tanitimMi(o.veri))
                  const tam = !!o.veri && tanitimMi(o.veri)
                  const tek = sayfa.length === 1
                  const ikiKisa = !genisVar && sayfa.length === 2
                  const ucKisaIlk = !genisVar && sayfa.length === 3 && sira === 0
                  const genisYanindaTek = genisVar && sayfa.length === 2 && !genis
                  return <div key={o.kaynak} className={`min-h-0 [&>section]:h-full ${genis || tek || genisYanindaTek ? "col-span-2" : ""} ${tam || tek || ikiKisa || ucKisaIlk ? "row-span-2" : ""}`}>{kart(o, true)}</div>
                })}
              </div>
              )
            }}
            adlar={sayfalar.map((sayfa) => sayfa.map((o) => yerel(dil, o.ad, o.ad_en)).join(" · "))}
            baslik={`${t.baslik} · ${t.ceyrekKisa(v.ceyrek)} ${v.yil}`}
            t={t}
            onKapat={() => setSlayt(false)}
          />
        )
      })() : null}
    </div>
  )
}
