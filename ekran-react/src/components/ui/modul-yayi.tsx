import { useLayoutEffect, useRef, useState } from "react"
import type { CSSProperties, ReactNode } from "react"
import { motion } from "framer-motion"
import { useHareket } from "@/lib/hareket"
import { useYazi, YAZI_OLCEKLERI } from "@/lib/yazi"

/**
 * Genel Bakis yarim yayi: modul kartlari iki es merkezli (yatayda gerilmis) yay uzerinde; ortada Teknocan durur.
 *
 * Arka plan (2026-10-14 kullanici istegi): `arkaPlan` verilirse sahnenin arkasina tam gorsel konur; Teknocan gorselin icindeki
 * maskottur ve gorselin ortasindadir. Kartlar maskotu KAPATMAZ: yaylar gorselin tam ortasinda (MASKOT bandi) KESILIR, kartlar yalniz
 * sol ve sag yan taraflarda yay boyunca dizilir. Gorsel sahneye `cover` gibi oturur (genislige gore olceklenir, ustten GORSEL_UST px kirpilir);
 * MASKOT bandi bu olcege gore, gorseldeki maskotun gercek sinirlarindan (x 655-1040, y 108-770 piksel) turetilmistir; gorselin sol altindaki
 * baslik yazisi (en fazla BASLIK_USTU yuksekliginde) ve sol ustteki logo (LOGO) da kartlarla kapanmaz: halkalar KALKIS kadar yukari alinmistir.
 * `arkaPlan` yoksa (testler, baska gorsel) ortadaki bos alan `alt` icerigine (104 x 180) ayrilir ve yaylar tam cizilir.
 *
 * Yerlesim: yaylarin merkezi sahnenin alt ortasidir. Kartlar kucuk (92 x 68) tutulur; hicbir kart birbirine, sahne disina ya da
 * maskot bandina tasmaz (modul-yayi.test.ts 1-12 kart icin dener).
 *
 * Netlik ilkeleri (bulaniklik ve piksel kaymasi yasanmasin diye):
 *  - 3B egim, perspektif ve imlece gore kayma YOK; sahne `scale()` ile kucultulmez. Olcek yalniz yaricap/kart/yazi boyutlarina
 *    uygulanir, kartlar sabit boyutlu kutulardir ve tam sayi left/top alir (translate(-50%) kullanilmaz).
 *  - Yuzme animasyonu yok; yalniz giris, yayin cizilmesi, yayda akan isik ve ustune gelince 2 px yukselme vardir.
 *  - Sahne, ust kutunun gercek genisligi VE yuksekligine gore olceklenir: sayfa kaydirma cubugu cikarmadan tek ekrana sigar.
 * Animasyon tercihi kapaliyken ve dar ekranda animasyon yoktur; dar ekranda kartlar liste olur (arka plan gorseli listenin ustunde bant).
 */

export type YayOgesi = {
  anahtar: string
  etiket: string
  ikon: ReactNode
  /** [acik, koyu] simge zemini gradyani */
  renk: readonly [string, string]
  onClick?: () => void
}

/** Sahnenin arkasindaki gorsel (iclerinde maskot var). `alt`: erisilebilir ad. */
export type ArkaPlan = { src: string; alt: string }

/** Tasarim olcusu (olcek 1): sahne 1090 x 500; kartlar 92 x 68. Kutu daha kucukse sahne orantili kuculur. */
const TASARIM_G = 1090
export const TASARIM_Y = 500
export const KART = { g: 92, y: 68 } as const
/** Arka plan gorselinin piksel olculeri ve ustten kirpilan kisim (gorsel genislige gore olceklenir). */
const GORSEL = { g: 1672, y: 941, ust: 18 } as const
/**
 * Tasarim olcusunde maskot bandi: merkezden +-yarim yatay (gorseldeki maskot, olcek 1090/1672). Kartlar bu banda girmez.
 * BASLIK_USTU: gorselin sol altindaki yazinin sahne altindan yuksekligi; hicbir kartin alt kenari bunun altina inmez.
 */
export const MASKOT = { yarim: 126 } as const
export const BASLIK_USTU = 126
/** Gorselin sol ustundeki logo: sahnenin solundan 240 px, sahne altindan 440 px ustu; kartlar buraya girmez. */
export const LOGO = { sag: 240, alt: 440 } as const
/** Halkalarin merkezi sahne altindan bu kadar yukaridadir (kartlar alttaki yazinin ustunde kalsin). */
export const KALKIS = 130
/** Halka tanimi: yatay/dikey yaricap (tasarim px) ve kartlarin dizilecegi aci araligi (derece, 0 = yatay, 90 = tepe; her yanda ayri). */
export const HALKA = { dis: { rx: 484, ry: 330, aci: [9, 51] }, ic: { rx: 367, ry: 237, aci: [8, 59] } } as const
const EN_FAZLA_KART = 12
/** `alt` (eski maskot kutusu) icin: arka plan yokken ortada ayrilan alan; yaylar tam cizilir. */
const ALT_KUTU = { g: 104, y: 180 } as const
const EN_KUCUK_OLCEK = 0.7
const EN_BUYUK_OLCEK = 1
const DAR_ESIK = 840
const EASE = [0.22, 1, 0.36, 1] as const

/** Bir yanin aci dizisi: alttan yukari, bas..son arasina esit dagilir (tek kartta ortaya). */
function taraf(adet: number, bas: number, son: number): number[] {
  if (adet <= 0) return []
  if (adet === 1) return [(bas + son) / 2]
  return Array.from({ length: adet }, (_, i) => bas + ((son - bas) * i) / (adet - 1))
}

/** Halkadaki kartlarin acilari (derece, 0 = sag yatay, 90 = tepe): sol yanda alttan yukari, sonra sag yanda yukaridan asagi. Tepe bos kalir. */
function halkaAcilari(adet: number, [bas, son]: readonly [number, number]): number[] {
  const sol = Math.ceil(adet / 2)
  return [...taraf(sol, bas, son).map((a) => 180 - a), ...taraf(adet - sol, bas, son).reverse()]
}

/** Kart adedine gore halka dizilimi: dis halka en fazla 6 kart, kalani ic halka; her halkada yarisi sol, yarisi sag yanda (maskot ortada kalir). */
export function halkalar(adet: number): { disAci: number[]; icAci: number[] } {
  const n = Math.min(EN_FAZLA_KART, Math.max(0, adet))
  const disAdet = Math.min(6, Math.ceil(n / 2))
  return { disAci: halkaAcilari(disAdet, HALKA.dis.aci), icAci: halkaAcilari(Math.min(6, n - disAdet), HALKA.ic.aci) }
}

/** Olceklenmis kart olculeri (px, tam sayi). Yazi boyutu yarim piksel adimlidir. */
function olculer(s: number) {
  return {
    g: Math.round(KART.g * s),
    y: Math.round(KART.y * s),
    ikon: Math.round(26 * s),
    glif: Math.round(14 * s),
    yazi: Math.max(10, Math.round(10.5 * s * 2) / 2),
    bosluk: Math.round(3 * s),
    dolgu: Math.round(5 * s),
  }
}

/** Elips uzerindeki nokta (derece: 0 = sag yatay, 90 = tepe); merkez (cx, cy) sahnenin alt ortasi. */
function nokta(cx: number, cy: number, rx: number, ry: number, aci: number) {
  const rad = (aci * Math.PI) / 180
  return { x: cx + rx * Math.cos(rad), y: cy - ry * Math.sin(rad) }
}

/** Yayin iki parcasi (maskotun iki yaninda): sol parca alttan yukari, sag parca yukaridan asagi; ikisi de saat yonunde akar. */
function yayParcalari(cx: number, cy: number, rx: number, ry: number, [bas, son]: readonly [number, number]) {
  const alt = Math.max(2, bas - 8)
  const ust = son + 6
  const p = (aci: number) => {
    const n = nokta(cx, cy, rx, ry, aci)
    return `${n.x.toFixed(1)} ${n.y.toFixed(1)}`
  }
  const parca = (bas2: number, son2: number) => `M ${p(bas2)} A ${rx} ${ry} 0 0 1 ${p(son2)}`
  return { sol: parca(180 - alt, 180 - ust), sag: parca(ust, alt) }
}

type Boyut = ReturnType<typeof olculer>

function Kart({ oge, sira, azHareket, b, stil }: { oge: YayOgesi; sira: number; azHareket: boolean; b: Boyut; stil: CSSProperties }) {
  const icerik = (
    <>
      <span
        className="flex shrink-0 items-center justify-center text-white ring-2 ring-white"
        style={{
          width: b.ikon,
          height: b.ikon,
          borderRadius: Math.round(b.ikon * 0.3),
          background: `linear-gradient(145deg, ${oge.renk[0]}, ${oge.renk[1]})`,
          boxShadow: `inset 0 1px 0 rgba(255,255,255,.45), inset 0 -6px 10px -6px rgba(0,0,0,.25), 0 6px 12px -6px ${oge.renk[1]}`,
        }}
      >
        <span style={{ width: b.glif, height: b.glif, display: "flex" }} className="[&>svg]:size-full">
          {oge.ikon}
        </span>
      </span>
      <span className="line-clamp-2 text-center font-bold text-slate-700 transition-colors group-hover:text-tl-navy" style={{ fontSize: b.yazi, lineHeight: 1.15 }}>
        {oge.etiket}
      </span>
    </>
  )
  const sinif =
    "group pointer-events-auto flex flex-col items-center justify-center rounded-2xl border border-white bg-white/95 antialiased shadow-[0_8px_20px_-12px_rgba(0,40,85,0.45)] transition-[box-shadow,background-color,translate] duration-200 hover:-translate-y-0.5 hover:bg-white hover:shadow-[0_14px_26px_-12px_rgba(0,40,85,0.55)] focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
  const kutu: CSSProperties = { width: b.g, height: b.y, gap: b.bosluk, padding: `${b.dolgu}px ${Math.max(2, Math.round(b.dolgu * 0.4))}px` }
  return (
    <motion.div
      className="absolute"
      style={stil}
      initial={azHareket ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.45, delay: 0.2 + sira * 0.04, ease: EASE }}
    >
      {oge.onClick ? (
        <button type="button" onClick={oge.onClick} title={oge.etiket} className={`${sinif} cursor-pointer`} style={kutu}>
          {icerik}
        </button>
      ) : (
        <div className={sinif} style={kutu} title={oge.etiket}>
          {icerik}
        </div>
      )}
    </motion.div>
  )
}

/**
 * arkaPlan: sahnenin arkasindaki gorsel (icinde Teknocan var; verilirse `alt` kullanilmaz). alt: arka plan yokken sahnenin
 * alt ortasindaki bos alana (104 x 180 x olcek) yerlesir; dar ekranda kart listesinin altinda durur.
 * `yukseklik`: ust kutunun CSS yuksekligi (varsayilan ekran yuksekligine gore); sahne bu kutuya sigacak sekilde olceklenir.
 */
export function ModulYayi({ ogeler, alt, arkaPlan, yukseklik = "clamp(23rem, 58dvh, 33rem)" }: { ogeler: YayOgesi[]; alt?: ReactNode; arkaPlan?: ArkaPlan; yukseklik?: string }) {
  const cerceve = useRef<HTMLDivElement>(null)
  const [kutu, setKutu] = useState({ g: TASARIM_G, y: TASARIM_Y })
  const azHareket = !useHareket()
  const yaziOlcek = YAZI_OLCEKLERI[useYazi()]

  useLayoutEffect(() => {
    const el = cerceve.current
    if (!el) return
    const olc = () => setKutu({ g: Math.round(el.clientWidth), y: Math.round(el.clientHeight) })
    olc()
    const ro = new ResizeObserver(olc)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const dar = kutu.g < DAR_ESIK
  // Sahne piksel olculudur; kok yazi olcegiyle (kullanici secimi) orantili buyuyebilsin diye ust sinir ayni carpanla artar.
  const s = Math.min(EN_BUYUK_OLCEK * yaziOlcek, Math.max(EN_KUCUK_OLCEK, Math.min(kutu.g / TASARIM_G, kutu.y / TASARIM_Y)))
  const b = olculer(s)
  const G = Math.round(Math.min(kutu.g, TASARIM_G * s))
  const Y = Math.round(TASARIM_Y * s)
  const cx = G / 2
  const cy = Y - Math.round(KALKIS * s) // halka merkezi: sahne altindan KALKIS yukarida

  const { disAci, icAci } = halkalar(ogeler.length)
  const disAdet = disAci.length
  const dis = ogeler.slice(0, disAdet)
  const ic = ogeler.slice(disAdet)

  /** Kartin sol-ust kosesi (tam sayi): halka yaricaplariyla aci uzerinden bulunur. */
  function yer(h: { rx: number; ry: number }, aci: number): CSSProperties {
    const n = nokta(cx, cy, h.rx * s, h.ry * s, aci)
    return { left: Math.round(n.x - b.g / 2), top: Math.round(n.y - b.y / 2) }
  }

  // Arka plan gorseli sahneye cover gibi oturur: genislige gore olceklenir, ustten GORSEL.ust px kirpilir, yatayda ortalanir.
  const k = Math.max(G / GORSEL.g, Y / GORSEL.y)
  const gorsel = { width: Math.round(GORSEL.g * k), height: Math.round(GORSEL.y * k) }
  const gorselKonum = { left: Math.round((G - gorsel.width) / 2), top: Math.max(Y - gorsel.height, -Math.round(GORSEL.ust * k)) }

  const maskotG = Math.round(ALT_KUTU.g * s)
  const maskotY = Math.round(ALT_KUTU.y * s)
  const disYay = yayParcalari(cx, cy, HALKA.dis.rx * s, HALKA.dis.ry * s, HALKA.dis.aci)
  const icYay = yayParcalari(cx, cy, HALKA.ic.rx * s, HALKA.ic.ry * s, HALKA.ic.aci)
  const koyu = !!arkaPlan && !dar

  return (
    <section
      className={`relative flex w-full shrink-0 flex-col overflow-hidden rounded-3xl border shadow-sm ${koyu ? "border-tl-navy bg-tl-navy" : "border-slate-200 bg-gradient-to-b from-slate-50 via-white to-sky-50/70"} ${koyu ? "" : "px-4 py-3"}`}
      style={dar ? undefined : { height: yukseklik }}
    >
      {koyu ? (
        // Kenar bosluklarini gorselin bulanik kopyasi doldurur; keskin gorselin kenarlari yumusakca solar.
        <img aria-hidden alt="" src={arkaPlan.src} draggable={false} className="pointer-events-none absolute inset-0 size-full scale-125 select-none object-cover opacity-60 blur-2xl" />
      ) : (
        <>
          <span aria-hidden className="pointer-events-none absolute left-1/2 top-1/3 size-[420px] -translate-x-1/2 rounded-full bg-tl-blue/10 blur-3xl" />
          <span aria-hidden className="pointer-events-none absolute -right-20 -top-20 size-60 rounded-full bg-tl-yellow/20 blur-3xl" />
        </>
      )}
      <div ref={cerceve} className={`relative mx-auto flex w-full max-w-[93.75rem] justify-center ${dar ? "" : "min-h-0 flex-1 items-center"}`}>
        {dar ? (
          <div className="grid w-full gap-3">
            {arkaPlan ? <img src={arkaPlan.src} alt={arkaPlan.alt} draggable={false} className="aspect-[16/9] w-full select-none rounded-2xl object-cover" /> : null}
            <ul className="grid w-full grid-cols-2 gap-3 py-2 sm:grid-cols-3">
              {ogeler.map((o) => (
                <li key={o.anahtar}>
                  <button
                    type="button"
                    onClick={o.onClick}
                    className="flex w-full items-center gap-3 rounded-2xl border border-white bg-white/90 p-3 text-left antialiased shadow-sm focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
                  >
                    <span className="flex size-10 shrink-0 items-center justify-center rounded-xl text-white [&>svg]:size-5" style={{ background: `linear-gradient(145deg, ${o.renk[0]}, ${o.renk[1]})` }}>
                      {o.ikon}
                    </span>
                    <span className="text-[0.75rem] font-bold leading-tight text-slate-700">{o.etiket}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <div className="relative shrink-0 overflow-hidden" style={{ width: G, height: Y, ...(arkaPlan ? { maskImage: "linear-gradient(to right, transparent, #000 6%, #000 94%, transparent)" } : {}) }} data-testid="yay-sahne">
            {arkaPlan ? <img src={arkaPlan.src} alt={arkaPlan.alt} draggable={false} className="pointer-events-none absolute max-w-none select-none" style={{ ...gorsel, ...gorselKonum }} /> : null}
            <svg className="pointer-events-none absolute inset-0" width={G} height={Y} viewBox={`0 0 ${G} ${Y}`} fill="none" aria-hidden shapeRendering="geometricPrecision">
              <defs>
                <linearGradient id="yay-dis" x1="0" x2="1" y1="0" y2="0">
                  <stop offset="0" stopColor="#7dd3fc" stopOpacity="0.95" />
                  <stop offset="0.5" stopColor="#ffffff" stopOpacity="0.9" />
                  <stop offset="1" stopColor="#ffc72c" stopOpacity="1" />
                </linearGradient>
                <linearGradient id="yay-ic" x1="0" x2="1" y1="0" y2="0">
                  <stop offset="0" stopColor="#ffc72c" stopOpacity="1" />
                  <stop offset="0.5" stopColor="#7dd3fc" stopOpacity="0.95" />
                  <stop offset="1" stopColor="#ffffff" stopOpacity="0.8" />
                </linearGradient>
                <radialGradient id="yay-isik" cx="50%" cy="50%" r="50%">
                  <stop offset="0" stopColor="#ffc72c" stopOpacity="1" />
                  <stop offset="1" stopColor="#ffc72c" stopOpacity="0" />
                </radialGradient>
              </defs>
              {[disYay.sol, disYay.sag].map((d) => (
                <motion.path key={d} d={d} stroke="url(#yay-dis)" strokeWidth={3} style={{ filter: "drop-shadow(0 0 4px rgba(125,211,252,0.9))" }} strokeLinecap="round" initial={{ pathLength: azHareket ? 1 : 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.4, ease: "easeOut" }} />
              ))}
              {[icYay.sol, icYay.sag].map((d) => (
                <motion.path
                  key={d}
                  d={d}
                  stroke="url(#yay-ic)"
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeDasharray="2 14"
                  className="tl-hareket"
                  style={azHareket ? undefined : { animation: "tl-akis 4s linear infinite" }}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 1, delay: 0.3 }}
                />
              ))}
              {azHareket ? null : (
                <g>
                  {[disYay.sol, disYay.sag].map((d) => (
                    <g key={d}>
                      <circle r={12} fill="url(#yay-isik)" opacity={0.8}>
                        <animateMotion dur="5.5s" repeatCount="indefinite" path={d} />
                      </circle>
                      <circle r={3} fill="#fff">
                        <animateMotion dur="5.5s" repeatCount="indefinite" path={d} />
                      </circle>
                    </g>
                  ))}
                </g>
              )}
            </svg>

            {dis.map((o, i) => (
              <Kart key={o.anahtar} oge={o} sira={i} azHareket={azHareket} b={b} stil={yer(HALKA.dis, disAci[i] ?? 90)} />
            ))}
            {ic.map((o, i) => (
              <Kart key={o.anahtar} oge={o} sira={disAdet + i} azHareket={azHareket} b={b} stil={yer(HALKA.ic, icAci[i] ?? 90)} />
            ))}
            {alt && !arkaPlan ? (
              <motion.div
                className="pointer-events-none absolute bottom-0 flex items-end justify-center"
                style={{ left: Math.round(cx - maskotG / 2), width: maskotG, height: maskotY }}
                initial={azHareket ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.6, delay: 0.7, ease: EASE }}
              >
                {alt}
              </motion.div>
            ) : null}
          </div>
        )}
      </div>

      {alt && !arkaPlan && dar ? <div className="relative flex h-32 items-center justify-center pt-2">{alt}</div> : null}
    </section>
  )
}
