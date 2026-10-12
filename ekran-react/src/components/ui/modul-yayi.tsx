import { useLayoutEffect, useRef, useState } from "react"
import type { CSSProperties, ReactNode } from "react"
import { motion } from "framer-motion"
import { useHareket } from "@/lib/hareket"
import { useYazi, YAZI_OLCEKLERI } from "@/lib/yazi"

/**
 * Genel Bakis yarim yayi: modul kartlari iki es merkezli (yatayda gerilmis) yay uzerinde; ortada Teknocan durur.
 *
 * Yerlesim: yaylarin merkezi sahnenin alt ortasindadir. Kartlar kucuk (92 x 68) tutulur; ortadaki bos alan Teknocan'a ayrilmistir
 * (MASKOT kutusu) ve hicbir kart bu kutuya, birbirine ya da sahne disina tasmaz (modul-yayi.test.ts 1-12 kart icin dener).
 *
 * Netlik ilkeleri (bulaniklik ve piksel kaymasi yasanmasin diye):
 *  - 3B egim, perspektif ve imlece gore kayma YOK; sahne `scale()` ile kucultulmez. Olcek yalniz yaricap/kart/yazi boyutlarina
 *    uygulanir, kartlar sabit boyutlu kutulardir ve tam sayi left/top alir (translate(-50%) kullanilmaz).
 *  - Yuzme animasyonu yok; yalniz giris, yayin cizilmesi, yayda akan isik ve ustune gelince 2 px yukselme vardir.
 *  - Sahne, ust kutunun gercek genisligi VE yuksekligine gore olceklenir: sayfa kaydirma cubugu cikarmadan tek ekrana sigar.
 * Animasyon tercihi kapaliyken ve dar ekranda animasyon yoktur; dar ekranda kartlar liste olur.
 */

export type YayOgesi = {
  anahtar: string
  etiket: string
  ikon: ReactNode
  /** [acik, koyu] simge zemini gradyani */
  renk: readonly [string, string]
  onClick?: () => void
}

/** Tasarim olcusu (olcek 1): sahne 1090 x 350; kartlar 92 x 68. Kutu daha kucukse sahne orantili kuculur. */
const TASARIM_G = 1090
export const TASARIM_Y = 350
export const KART = { g: 92, y: 68 } as const
/** Yaylar yatayda YATAY kati gerilmis yarim elipstir (merkez: sahnenin alt orta noktasi). */
export const YATAY = 1.65
export const YARICAP = { dis: 310, ic: 232 } as const
/** Teknocan kutusu: sahnenin alt ortasi; kartlar bu kutuya girmez. */
export const MASKOT = { g: 104, y: 180 } as const
const ADIM = { dis: 24, ic: 30 } as const
const EN_KUCUK_OLCEK = 0.7
const EN_BUYUK_OLCEK = 1
const DAR_ESIK = 840
const EASE = [0.22, 1, 0.36, 1] as const

/** Halka uzerindeki adet kadar kartin acisi: 90 derece etrafinda simetrik, adet arttikca genisler. */
function acilar(adet: number, adim: number): number[] {
  if (adet <= 0) return []
  const yayi = adim * (adet - 1)
  return Array.from({ length: adet }, (_, i) => 90 + yayi / 2 - i * adim)
}

/**
 * Kart adedine gore halka dizilimi (derece, 90 = tepe). Dis halka en fazla 7 kart; 11 kartta cakismamasi icin 7 + 4. Ic halka,
 * disin bir eksigi kadarsa dis kartlarin orta acilarina oturur. Kartlar birbirine binmez (modul-yayi.test.ts tum adetleri dener).
 */
export function halkalar(adet: number): { disAci: number[]; icAci: number[] } {
  const disAdet = adet === 11 ? 7 : Math.min(7, Math.ceil((adet + 0.5) / 2))
  const icAdet = Math.max(0, adet - disAdet)
  const disAci = acilar(disAdet, ADIM.dis)
  const icAci = icAdet === disAdet - 1 ? Array.from({ length: icAdet }, (_, i) => ((disAci[i] ?? 90) + (disAci[i + 1] ?? 90)) / 2) : acilar(icAdet, disAdet === 7 && icAdet === 4 ? 28 : ADIM.ic)
  return { disAci, icAci }
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

/** Alt orta noktadan (cx, alt) cizilen yarim elips: soldan saga, tepeden gecer. */
function yayYolu(cx: number, alt: number, ry: number) {
  const rx = ry * YATAY
  return `M ${cx - rx} ${alt} A ${rx} ${ry} 0 0 1 ${cx + rx} ${alt}`
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
 * alt: yayin ICINDE, alt ortadaki MASKOT kutusuna (104 x 180 x olcek) yerlesir; kutu kartlardan bos tutulur. Dar ekranda kart listesinin
 * altinda durur. `yukseklik`: ust kutunun CSS yuksekligi (varsayilan ekran yuksekligine gore); sahne bu kutuya sigacak sekilde olceklenir.
 */
export function ModulYayi({ ogeler, alt, yukseklik = "clamp(18.75rem, 42dvh, 25rem)" }: { ogeler: YayOgesi[]; alt?: ReactNode; yukseklik?: string }) {
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
  const cy = Y

  const { disAci, icAci } = halkalar(ogeler.length)
  const disAdet = disAci.length
  const dis = ogeler.slice(0, disAdet)
  const ic = ogeler.slice(disAdet)

  /** Kartin sol-ust kosesi (tam sayi): merkezden yaricap/aci ile bulunur (yatayda YATAY kat gerilmis). */
  function yer(yaricap: number, aci: number): CSSProperties {
    const rad = (aci * Math.PI) / 180
    return { left: Math.round(cx + YATAY * yaricap * s * Math.cos(rad) - b.g / 2), top: Math.round(cy - yaricap * s * Math.sin(rad) - b.y / 2) }
  }

  const maskotG = Math.round(MASKOT.g * s)
  const maskotY = Math.round(MASKOT.y * s)
  const disYol = yayYolu(cx, Y, YARICAP.dis * s)
  const icYol = yayYolu(cx, Y, YARICAP.ic * s)

  return (
    <section
      className="relative flex w-full shrink-0 flex-col overflow-hidden rounded-3xl border border-slate-200 bg-gradient-to-b from-slate-50 via-white to-sky-50/70 px-4 py-3 shadow-sm"
      style={dar ? undefined : { height: yukseklik }}
    >
      <span aria-hidden className="pointer-events-none absolute left-1/2 top-1/3 size-[420px] -translate-x-1/2 rounded-full bg-tl-blue/10 blur-3xl" />
      <span aria-hidden className="pointer-events-none absolute -right-20 -top-20 size-60 rounded-full bg-tl-yellow/20 blur-3xl" />
      <div ref={cerceve} className={`relative mx-auto flex w-full max-w-[93.75rem] justify-center ${dar ? "" : "min-h-0 flex-1 items-center"}`}>
        {dar ? (
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
        ) : (
          <div className="pointer-events-none relative shrink-0" style={{ width: G, height: Y }} data-testid="yay-sahne">
            <svg className="absolute inset-0" width={G} height={Y} viewBox={`0 0 ${G} ${Y}`} fill="none" aria-hidden shapeRendering="geometricPrecision">
              <defs>
                <linearGradient id="yay-dis" x1="0" x2="1" y1="0" y2="0">
                  <stop offset="0" stopColor="#00a3e0" stopOpacity="0.15" />
                  <stop offset="0.5" stopColor="#0055a5" stopOpacity="0.8" />
                  <stop offset="1" stopColor="#ffc72c" stopOpacity="0.9" />
                </linearGradient>
                <linearGradient id="yay-ic" x1="0" x2="1" y1="0" y2="0">
                  <stop offset="0" stopColor="#ffc72c" stopOpacity="0.8" />
                  <stop offset="0.5" stopColor="#00a3e0" stopOpacity="0.7" />
                  <stop offset="1" stopColor="#002855" stopOpacity="0.2" />
                </linearGradient>
                <radialGradient id="yay-isik" cx="50%" cy="50%" r="50%">
                  <stop offset="0" stopColor="#ffc72c" stopOpacity="1" />
                  <stop offset="1" stopColor="#ffc72c" stopOpacity="0" />
                </radialGradient>
              </defs>
              <motion.path d={disYol} stroke="url(#yay-dis)" strokeWidth={2.5} strokeLinecap="round" initial={{ pathLength: azHareket ? 1 : 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.4, ease: "easeOut" }} />
              <motion.path
                d={icYol}
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
              {azHareket ? null : (
                <g>
                  <circle r={12} fill="url(#yay-isik)" opacity={0.8}>
                    <animateMotion dur="11s" repeatCount="indefinite" path={disYol} />
                  </circle>
                  <circle r={3} fill="#fff">
                    <animateMotion dur="11s" repeatCount="indefinite" path={disYol} />
                  </circle>
                </g>
              )}
            </svg>

            {dis.map((o, i) => (
              <Kart key={o.anahtar} oge={o} sira={i} azHareket={azHareket} b={b} stil={yer(YARICAP.dis, disAci[i] ?? 90)} />
            ))}
            {ic.map((o, i) => (
              <Kart key={o.anahtar} oge={o} sira={disAdet + i} azHareket={azHareket} b={b} stil={yer(YARICAP.ic, icAci[i] ?? 90)} />
            ))}
            {alt ? (
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

      {alt && dar ? (
        <div className="relative flex h-32 items-center justify-center pt-2">{alt}</div>
      ) : null}
    </section>
  )
}
