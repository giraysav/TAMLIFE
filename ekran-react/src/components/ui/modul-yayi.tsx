import { useLayoutEffect, useRef, useState } from "react"
import type { CSSProperties, PointerEvent as ReactPointerEvent, ReactNode } from "react"
import { motion, useMotionValue, useSpring, useTransform } from "framer-motion"
import { useHareket } from "@/lib/hareket"

/**
 * Genel Bakis yarim yayi: modul kartlari iki es merkezli yay uzerinde, derinlikli.
 *
 * Netlik ilkeleri (bulaniklik yasanmasin diye):
 *  - Sahne `scale()` ile kucultulmez; olcek yalniz yaricap/kart/yazi boyutlarina uygulanir, her sey gercek piksel ve TAM SAYI konumdadir.
 *  - Kartlar `translate(-50%)` ile ortalanmaz (yarim piksel kaymasi); sabit boyutlu kutular tam sayi left/top alir.
 *  - `backdrop-filter` yok; yuzme animasyonu yalniz simgeye uygulanir, etiket metni hep sabit ve keskin kalir.
 *  - 3B egim yalniz imlec sahne uzerindeyken vardir; durgunken donus ve derinlik (translateZ) tam sifirdir (katman olceklenmez).
 * Hareket: giris, simge yuzmesi, yayda akan isik, imlece gore +-5 derece egim ve ic yayda paralaks. Animasyon tercihi kapaliyken ve
 * dokunmatik/dar ekranda egim ve animasyon yoktur.
 */

export type YayOgesi = {
  anahtar: string
  etiket: string
  ikon: ReactNode
  /** [acik, koyu] simge zemini gradyani */
  renk: readonly [string, string]
  onClick?: () => void
}

const TASARIM_G = 1200
const TASARIM_Y = 470
const MERKEZ_Y = 640
const YARICAP = { dis: 520, ic: 385 } as const
const EN_KUCUK_OLCEK = 0.7
const DAR_ESIK = 840
const EASE = [0.22, 1, 0.36, 1] as const

/** Halka uzerindeki adet kadar kartin acisi: 90 derece etrafinda simetrik, adet arttikca genisler. */
function acilar(adet: number, adim: number): number[] {
  if (adet <= 0) return []
  const yayi = adim * (adet - 1)
  return Array.from({ length: adet }, (_, i) => 90 + yayi / 2 - i * adim)
}

/** Olceklenmis kart olculeri (px, tam sayi). Yazi boyutu yarim piksel adimlidir. */
function olculer(s: number) {
  return {
    g: Math.round(118 * s),
    y: Math.round(108 * s),
    ikon: Math.round(44 * s),
    glif: Math.round(22 * s),
    yazi: Math.max(10, Math.round(12 * s * 2) / 2),
    bosluk: Math.round(8 * s),
    dolgu: Math.round(10 * s),
  }
}

function yayYolu(cx: number, cy: number, r: number, alt: number) {
  const dx = Math.sqrt(r * r - (cy - alt) * (cy - alt))
  return `M ${cx - dx} ${alt} A ${r} ${r} 0 0 1 ${cx + dx} ${alt}`
}

type Boyut = ReturnType<typeof olculer>

function Kart({ oge, sira, azHareket, b, stil }: { oge: YayOgesi; sira: number; azHareket: boolean; b: Boyut; stil: CSSProperties }) {
  const icerik = (
    <>
      <span
        className="tl-hareket flex shrink-0 items-center justify-center text-white ring-2 ring-white transition-transform duration-300 group-hover:scale-110"
        style={{
          width: b.ikon,
          height: b.ikon,
          borderRadius: Math.round(b.ikon * 0.32),
          background: `linear-gradient(145deg, ${oge.renk[0]}, ${oge.renk[1]})`,
          boxShadow: `inset 0 1px 0 rgba(255,255,255,.5), inset 0 -8px 12px -6px rgba(0,0,0,.28), 0 10px 18px -8px ${oge.renk[1]}`,
          animation: azHareket ? undefined : `tl-yuz ${5 + (sira % 4) * 0.7}s ease-in-out ${(sira * 0.37) % 2}s infinite`,
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
    "group pointer-events-auto flex flex-col items-center justify-center rounded-[18px] border border-white bg-white/90 antialiased shadow-[0_12px_28px_-14px_rgba(0,40,85,0.5)] transition-[box-shadow,background-color,translate] duration-300 hover:-translate-y-1.5 hover:bg-white hover:shadow-[0_20px_36px_-14px_rgba(0,40,85,0.6)] focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
  const kutu: CSSProperties = { width: b.g, height: b.y, gap: b.bosluk, padding: `${b.dolgu}px ${Math.round(b.dolgu * 0.7)}px` }
  return (
    <motion.div
      className="absolute"
      style={stil}
      initial={azHareket ? false : { opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay: 0.3 + sira * 0.06, ease: EASE }}
    >
      {oge.onClick ? (
        <button type="button" onClick={oge.onClick} className={`${sinif} cursor-pointer`} style={kutu}>
          {icerik}
        </button>
      ) : (
        <div className={sinif} style={kutu}>
          {icerik}
        </div>
      )}
    </motion.div>
  )
}

export function ModulYayi({ ogeler, baslik, altBaslik }: { ogeler: YayOgesi[]; baslik: ReactNode; altBaslik?: ReactNode }) {
  const cerceve = useRef<HTMLDivElement>(null)
  const [genislik, setGenislik] = useState(TASARIM_G)
  const azHareket = !useHareket()

  const px = useMotionValue(0)
  const py = useMotionValue(0)
  const x = useSpring(px, { stiffness: 90, damping: 18, mass: 0.6 })
  const y = useSpring(py, { stiffness: 90, damping: 18, mass: 0.6 })
  const donusY = useTransform(x, [-1, 1], [-5, 5])
  const donusX = useTransform(y, [-1, 1], [4, -4])
  // Ic yay one gelir (paralaks) yalniz egim varken; durgunken 0 => katman olceklenmez, metin keskin kalir.
  const icDerinlik = useTransform([x, y], ([a, b]: number[]) => Math.round(34 * Math.min(1, Math.hypot(a ?? 0, b ?? 0))))

  useLayoutEffect(() => {
    const el = cerceve.current
    if (!el) return
    const olc = () => setGenislik(Math.round(el.clientWidth))
    olc()
    const ro = new ResizeObserver(olc)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  function imlec(olay: ReactPointerEvent<HTMLElement>) {
    if (azHareket || olay.pointerType !== "mouse") return
    const k = olay.currentTarget.getBoundingClientRect()
    px.set(((olay.clientX - k.left) / k.width - 0.5) * 2)
    py.set(((olay.clientY - k.top) / k.height - 0.5) * 2)
  }
  function imlecCik() {
    px.set(0)
    py.set(0)
  }

  const dar = genislik < DAR_ESIK
  const s = Math.min(1, Math.max(EN_KUCUK_OLCEK, genislik / TASARIM_G))
  const b = olculer(s)
  const G = Math.round(genislik)
  const Y = Math.round(TASARIM_Y * s)
  const cx = G / 2
  const cy = MERKEZ_Y * s

  const disAdet = Math.min(7, Math.ceil((ogeler.length + 0.5) / 2))
  const dis = ogeler.slice(0, disAdet)
  const ic = ogeler.slice(disAdet)
  const disAci = acilar(dis.length, 20)
  const icAci = acilar(ic.length, 24)

  /** Kartin sol-ust kosesi (tam sayi): merkezden yaricap/aci ile bulunur. */
  function yer(yaricap: number, aci: number): CSSProperties {
    const rad = (aci * Math.PI) / 180
    return { left: Math.round(cx + yaricap * s * Math.cos(rad) - b.g / 2), top: Math.round(cy - yaricap * s * Math.sin(rad) - b.y / 2) }
  }

  const disYol = yayYolu(cx, cy, YARICAP.dis * s, Y)
  const icYol = yayYolu(cx, cy, YARICAP.ic * s, Y)

  return (
    <section
      onPointerMove={imlec}
      onPointerLeave={imlecCik}
      className="relative w-full overflow-hidden rounded-3xl border border-slate-200 bg-gradient-to-b from-slate-50 via-white to-sky-50/70 px-4 pb-10 pt-6 shadow-sm"
    >
      <span aria-hidden className="pointer-events-none absolute left-1/2 top-24 size-[520px] -translate-x-1/2 rounded-full bg-tl-blue/10 blur-3xl" />
      <span aria-hidden className="pointer-events-none absolute -right-24 -top-24 size-72 rounded-full bg-tl-yellow/20 blur-3xl" />
      <div ref={cerceve} className="relative mx-auto w-full max-w-[1200px] overflow-hidden" style={{ height: dar ? "auto" : Y, perspective: dar ? undefined : 1300 }}>
        {dar ? (
          <ul className="grid grid-cols-2 gap-3 py-2 sm:grid-cols-3">
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
                  <span className="text-[12px] font-bold leading-tight text-slate-700">{o.etiket}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <motion.div className="pointer-events-none absolute inset-0" style={{ rotateX: azHareket ? 0 : donusX, rotateY: azHareket ? 0 : donusY, transformStyle: "preserve-3d" }}>
            <svg className="absolute inset-0" width={G} height={Y} viewBox={`0 0 ${G} ${Y}`} fill="none" aria-hidden shapeRendering="geometricPrecision">
              <defs>
                <linearGradient id="yay-dis" x1="0" x2="1" y1="0" y2="0">
                  <stop offset="0" stopColor="#00a3e0" stopOpacity="0.15" />
                  <stop offset="0.5" stopColor="#0055a5" stopOpacity="0.85" />
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
                <filter id="yay-parilti" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="5" />
                </filter>
              </defs>
              <motion.path d={disYol} stroke="url(#yay-dis)" strokeWidth={14} opacity={0.25} filter="url(#yay-parilti)" initial={{ pathLength: azHareket ? 1 : 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.6, ease: "easeOut" }} />
              <motion.path d={disYol} stroke="url(#yay-dis)" strokeWidth={3} strokeLinecap="round" initial={{ pathLength: azHareket ? 1 : 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.6, ease: "easeOut" }} />
              <motion.path
                d={icYol}
                stroke="url(#yay-ic)"
                strokeWidth={2.5}
                strokeLinecap="round"
                strokeDasharray="2 14"
                className="tl-hareket"
                style={azHareket ? undefined : { animation: "tl-akis 4s linear infinite" }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 1.2, delay: 0.3 }}
              />
              {azHareket ? null : (
                <g>
                  <circle r={16} fill="url(#yay-isik)" opacity={0.85}>
                    <animateMotion dur="11s" repeatCount="indefinite" path={disYol} />
                  </circle>
                  <circle r={4} fill="#fff">
                    <animateMotion dur="11s" repeatCount="indefinite" path={disYol} />
                  </circle>
                </g>
              )}
            </svg>

            {dis.map((o, i) => (
              <Kart key={o.anahtar} oge={o} sira={i} azHareket={azHareket} b={b} stil={yer(YARICAP.dis, disAci[i] ?? 90)} />
            ))}
            <motion.div className="pointer-events-none absolute inset-0" style={{ z: azHareket ? 0 : icDerinlik, transformStyle: "preserve-3d" }}>
              {ic.map((o, i) => (
                <Kart key={o.anahtar} oge={o} sira={disAdet + i} azHareket={azHareket} b={b} stil={yer(YARICAP.ic, icAci[i] ?? 90)} />
              ))}
            </motion.div>
          </motion.div>
        )}
      </div>

      <motion.div
        className="relative mx-auto mt-3 max-w-[640px] text-center"
        initial={azHareket ? false : { opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, delay: 1.0, ease: EASE }}
      >
        <h2 className="text-[26px] font-black leading-[1.15] tracking-tight text-tl-navy sm:text-[34px]">{baslik}</h2>
        {altBaslik ? <p className="mt-2 text-sm font-bold text-slate-500">{altBaslik}</p> : null}
        <span aria-hidden className="mx-auto mt-4 block h-1 w-16 rounded-full bg-gradient-to-r from-tl-yellow to-tl-accent" />
      </motion.div>
    </section>
  )
}
