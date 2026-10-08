import { useLayoutEffect, useRef, useState } from "react"
import type { CSSProperties, ReactNode } from "react"
import { motion, useMotionValue, useSpring, useTransform } from "framer-motion"
import { useHareket } from "@/lib/hareket"

/**
 * Genel Bakis yarim yayi: modul kartlari iki eş merkezli yay uzerinde, cam goruntulu ve derinlikli.
 * 3B: sahne `perspective` icinde imlece gore +-5 derece egilir; ic yay kartlari one (translateZ) alinir, boylece paralaks olusur.
 * Hareket: giris, hafif yuzme, yay uzerinde akan isik. Animasyon tercihi kapaliyken (sistem ayari ya da hesap menusu) ve dokunmatik ekranda egilme/animasyon yoktur.
 */

export type YayOgesi = {
  anahtar: string
  etiket: string
  ikon: ReactNode
  /** [acik, koyu] simge zemini gradyani */
  renk: readonly [string, string]
  onClick?: () => void
}

const SAHNE_G = 1200
const SAHNE_Y = 470
const MERKEZ = { x: 600, y: 640 }
const YARICAP = { dis: 520, ic: 385 } as const
const DAR_ESIK = 640
const EASE = [0.22, 1, 0.36, 1] as const

/** Halka uzerindeki adet kadar kartin acisi: 90 derece etrafinda simetrik, adet arttikca genisler. */
function acilar(adet: number, adim: number): number[] {
  if (adet <= 0) return []
  const yayi = adim * (adet - 1)
  return Array.from({ length: adet }, (_, i) => 90 + yayi / 2 - i * adim)
}

function konum(yaricap: number, aci: number): CSSProperties {
  const rad = (aci * Math.PI) / 180
  return { left: MERKEZ.x + yaricap * Math.cos(rad), top: MERKEZ.y - yaricap * Math.sin(rad) }
}

function yayYolu(yaricap: number, alt: number) {
  const dy = MERKEZ.y - alt
  const dx = Math.sqrt(yaricap * yaricap - dy * dy)
  return `M ${MERKEZ.x - dx} ${alt} A ${yaricap} ${yaricap} 0 0 1 ${MERKEZ.x + dx} ${alt}`
}

function Kart({ oge, sira, azHareket }: { oge: YayOgesi; sira: number; azHareket: boolean }) {
  const icerik = (
    <>
      <span
        className="flex size-11 shrink-0 items-center justify-center rounded-2xl text-white shadow-lg ring-2 ring-white/70 transition-transform duration-300 group-hover:scale-110 [&>svg]:size-[22px]"
        style={{ background: `linear-gradient(135deg, ${oge.renk[0]}, ${oge.renk[1]})`, boxShadow: `0 8px 18px -6px ${oge.renk[1]}` }}
      >
        {oge.ikon}
      </span>
      <span className="line-clamp-2 text-center text-[12px] font-bold leading-[1.15] text-slate-700 transition-colors group-hover:text-tl-navy">{oge.etiket}</span>
    </>
  )
  const sinif =
    "group flex w-[118px] flex-col items-center gap-2 rounded-[20px] border border-white/80 bg-white/75 px-2.5 py-3 shadow-[0_14px_30px_-14px_rgba(0,40,85,0.45)] backdrop-blur-md transition-all duration-300 hover:-translate-y-1.5 hover:bg-white hover:shadow-[0_22px_40px_-14px_rgba(0,40,85,0.55)] focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
  return (
    <motion.div
      className="absolute -translate-x-1/2 -translate-y-1/2"
      initial={azHareket ? false : { opacity: 0, scale: 0.6, y: 24 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ duration: 0.6, delay: 0.35 + sira * 0.06, ease: EASE }}
    >
      <div className="tl-hareket" style={azHareket ? undefined : { animation: `tl-yuz ${5 + (sira % 4) * 0.7}s ease-in-out ${(sira * 0.37) % 2}s infinite` }}>
        {oge.onClick ? (
          <button type="button" onClick={oge.onClick} className={`${sinif} cursor-pointer`}>
            {icerik}
          </button>
        ) : (
          <div className={sinif}>{icerik}</div>
        )}
      </div>
    </motion.div>
  )
}

export function ModulYayi({ ogeler, baslik, altBaslik }: { ogeler: YayOgesi[]; baslik: ReactNode; altBaslik?: ReactNode }) {
  const cerceve = useRef<HTMLDivElement>(null)
  const [olcek, setOlcek] = useState(1)
  const [dar, setDar] = useState(false)
  const azHareket = !useHareket()

  const px = useMotionValue(0)
  const py = useMotionValue(0)
  const x = useSpring(px, { stiffness: 90, damping: 18, mass: 0.6 })
  const y = useSpring(py, { stiffness: 90, damping: 18, mass: 0.6 })
  const donusY = useTransform(x, [-1, 1], [-5, 5])
  const donusX = useTransform(y, [-1, 1], [4, -4])

  useLayoutEffect(() => {
    const el = cerceve.current
    if (!el) return
    const olc = () => {
      setDar(el.clientWidth < DAR_ESIK)
      setOlcek(Math.min(1, Math.max(0.55, el.clientWidth / SAHNE_G)))
    }
    olc()
    const ro = new ResizeObserver(olc)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  function imlec(olay: React.PointerEvent<HTMLElement>) {
    if (azHareket || olay.pointerType !== "mouse") return
    const k = olay.currentTarget.getBoundingClientRect()
    px.set(((olay.clientX - k.left) / k.width - 0.5) * 2)
    py.set(((olay.clientY - k.top) / k.height - 0.5) * 2)
  }
  function imlecCik() {
    px.set(0)
    py.set(0)
  }

  const disAdet = Math.min(7, Math.ceil((ogeler.length + 0.5) / 2))
  const dis = ogeler.slice(0, disAdet)
  const ic = ogeler.slice(disAdet)
  const disAci = acilar(dis.length, 20)
  const icAci = acilar(ic.length, 24)

  return (
    <section
      onPointerMove={imlec}
      onPointerLeave={imlecCik}
      className="relative w-full overflow-hidden rounded-3xl border border-slate-200 bg-gradient-to-b from-slate-50 via-white to-sky-50/70 px-4 pb-10 pt-6 shadow-sm"
    >
      <span aria-hidden className="pointer-events-none absolute left-1/2 top-24 size-[520px] -translate-x-1/2 rounded-full bg-tl-blue/10 blur-3xl" />
      <span aria-hidden className="pointer-events-none absolute -right-24 -top-24 size-72 rounded-full bg-tl-yellow/20 blur-3xl" />
      <div
        ref={cerceve}
        className="relative mx-auto w-full max-w-[1200px] overflow-hidden"
        style={{ height: dar ? "auto" : SAHNE_Y * olcek, perspective: dar ? undefined : 1300 }}
      >
        {dar ? (
          <ul className="grid grid-cols-2 gap-3 py-2 sm:grid-cols-3">
            {ogeler.map((o) => (
              <li key={o.anahtar}>
                <button
                  type="button"
                  onClick={o.onClick}
                  className="flex w-full items-center gap-3 rounded-2xl border border-white/80 bg-white/80 p-3 text-left shadow-sm backdrop-blur focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
                >
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-xl text-white [&>svg]:size-5" style={{ background: `linear-gradient(135deg, ${o.renk[0]}, ${o.renk[1]})` }}>
                    {o.ikon}
                  </span>
                  <span className="text-[12px] font-bold leading-tight text-slate-700">{o.etiket}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <motion.div
            className="absolute left-1/2 top-0"
            style={{ width: SAHNE_G, height: SAHNE_Y, marginLeft: -SAHNE_G / 2, scale: olcek, transformOrigin: "top center", rotateX: azHareket ? 0 : donusX, rotateY: azHareket ? 0 : donusY, transformStyle: "preserve-3d" }}
          >
            <svg className="pointer-events-none absolute inset-0" width={SAHNE_G} height={SAHNE_Y} viewBox={`0 0 ${SAHNE_G} ${SAHNE_Y}`} fill="none" aria-hidden>
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
              <motion.path d={yayYolu(YARICAP.dis, SAHNE_Y)} stroke="url(#yay-dis)" strokeWidth={14} opacity={0.25} filter="url(#yay-parilti)" initial={{ pathLength: azHareket ? 1 : 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.6, ease: "easeOut" }} />
              <motion.path d={yayYolu(YARICAP.dis, SAHNE_Y)} stroke="url(#yay-dis)" strokeWidth={3} strokeLinecap="round" initial={{ pathLength: azHareket ? 1 : 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.6, ease: "easeOut" }} />
              <motion.path
                d={yayYolu(YARICAP.ic, SAHNE_Y)}
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
                    <animateMotion dur="11s" repeatCount="indefinite" path={yayYolu(YARICAP.dis, SAHNE_Y)} />
                  </circle>
                  <circle r={4} fill="#fff">
                    <animateMotion dur="11s" repeatCount="indefinite" path={yayYolu(YARICAP.dis, SAHNE_Y)} />
                  </circle>
                </g>
              )}
            </svg>

            {dis.map((o, i) => (
              <div key={o.anahtar} className="absolute" style={{ ...konum(YARICAP.dis, disAci[i] ?? 90), transformStyle: "preserve-3d" }}>
                <Kart oge={o} sira={i} azHareket={azHareket} />
              </div>
            ))}
            {ic.map((o, i) => (
              <div key={o.anahtar} className="absolute" style={{ ...konum(YARICAP.ic, icAci[i] ?? 90), transform: "translateZ(34px)", transformStyle: "preserve-3d" }}>
                <Kart oge={o} sira={disAdet + i} azHareket={azHareket} />
              </div>
            ))}
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
