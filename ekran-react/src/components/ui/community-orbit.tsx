import { useEffect, useLayoutEffect, useRef, useState } from "react"
import type { CSSProperties, ReactNode } from "react"
import { animate, motion, useReducedMotion } from "framer-motion"
import { CircleCheck } from "lucide-react"

export type OrbitRing = "outer" | "inner"

interface OrbitBase {
  ring: OrbitRing
  angle: number
}

export interface OrbitPillItem extends OrbitBase {
  kind: "pill"
  icon: ReactNode
  label: string
  onClick?: () => void
}

export interface OrbitStatusItem extends OrbitBase {
  kind: "status"
  label: string
}

export type OrbitItem = OrbitPillItem | OrbitStatusItem

export interface OrbitStat {
  value: string
  label: string
}

export interface OrbitTag {
  icon: ReactNode
  label: string
  href?: string
  onClick?: () => void
}

export interface CommunityOrbitProps {
  items: OrbitItem[]
  stats: OrbitStat[]
  headline: ReactNode
  tags?: OrbitTag[]
  minScale?: number
  className?: string
}

const STAGE_W = 1200
const STAGE_H = 490
const STAGE_H_SADE = 450 // istatistik yokken sahne daha kisa
const CENTER = { x: 600, y: 620 }
const RADIUS: Record<OrbitRing, number> = { outer: 492, inner: 404 }
const COMPACT_BELOW = 640
const EASE = [0.22, 1, 0.36, 1] as const

function positionOnRing(ring: OrbitRing, angle: number): CSSProperties {
  const rad = (angle * Math.PI) / 180
  const r = RADIUS[ring]
  return { left: CENTER.x + r * Math.cos(rad), top: CENTER.y - r * Math.sin(rad) }
}

// Soldan baslar, tepeden gecer, sagda biter.
function arcPath(r: number, stageH: number) {
  const dy = CENTER.y - stageH
  const dx = Math.sqrt(r * r - dy * dy)
  return `M ${CENTER.x - dx} ${stageH} A ${r} ${r} 0 0 1 ${CENTER.x + dx} ${stageH}`
}

const chip = "border border-border bg-card shadow-[0_2px_6px_rgba(0,0,0,0.05)] dark:shadow-none"

function OrbitPill({ icon, label, onClick }: OrbitPillItem) {
  const body = (
    <>
      <span className="flex shrink-0 items-center leading-none [&>svg]:size-[14px]">{icon}</span>
      <span className="leading-none">{label}</span>
    </>
  )
  const cls = `flex min-h-[27px] items-center gap-2 whitespace-nowrap rounded-full px-2.5 py-[5px] text-[12.5px] font-medium text-muted-foreground ${chip}`
  if (!onClick) return <div className={cls}>{body}</div>
  return (
    <button
      type="button"
      onClick={onClick}
      className={`${cls} cursor-pointer transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring`}
    >
      {body}
    </button>
  )
}

function OrbitStatus({ label }: OrbitStatusItem) {
  return (
    <div className="flex h-[30px] items-center gap-1.5 whitespace-nowrap rounded-full border border-[#a3d5b3] bg-[#cbe8d3] px-2.5 text-[13.5px] font-medium text-[#2f5b3a] dark:border-[#2f5b3a] dark:bg-[#17301f] dark:text-[#a8e0b8]">
      <CircleCheck size={15} strokeWidth={2.2} className="fill-[#2e7d3e] text-[#cbe8d3] dark:fill-[#3fa456] dark:text-[#17301f]" />
      {label}
    </div>
  )
}

function renderItem(item: OrbitItem) {
  return item.kind === "pill" ? <OrbitPill {...item} /> : <OrbitStatus {...item} />
}

function splitValue(value: string) {
  const m = value.match(/^([^\d]*)([\d.,]+)(.*)$/)
  if (!m) return null
  const raw = m[2].replace(/,/g, "")
  const decimals = (raw.split(".")[1] ?? "").length
  return { prefix: m[1], target: parseFloat(raw), decimals, suffix: m[3] }
}

function CountUp({ value, delay, still }: { value: string; delay: number; still: boolean }) {
  const parts = splitValue(value)
  const [n, setN] = useState(0)

  useEffect(() => {
    if (!parts || still) return
    const controls = animate(0, parts.target, {
      delay,
      duration: 1.6,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setN(v),
    })
    return () => controls.stop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, delay, still])

  if (!parts) return <>{value}</>
  const shown = still ? parts.target : n
  return (
    <>
      {parts.prefix}
      {shown.toFixed(parts.decimals)}
      {parts.suffix}
    </>
  )
}

const reveal = {
  hidden: { opacity: 0, y: 14, filter: "blur(4px)" },
  show: { opacity: 1, y: 0, filter: "blur(0px)" },
}

function StatBlock({ stat, delay, still, small }: { stat: OrbitStat; delay: number; still: boolean; small?: boolean }) {
  return (
    <motion.div
      className="flex flex-col items-center"
      variants={reveal}
      initial={still ? "show" : "hidden"}
      animate="show"
      transition={{ duration: 0.6, delay, ease: EASE }}
    >
      <span className={`${small ? "text-3xl" : "text-[48px]"} font-medium leading-none tracking-[-0.02em] text-foreground tabular-nums`}>
        <CountUp value={stat.value} delay={delay} still={still} />
      </span>
      <span className={`${small ? "mt-2" : "mt-[15px]"} text-[14px] leading-none text-muted-foreground`}>{stat.label}</span>
    </motion.div>
  )
}

export default function CommunityOrbit({ items, stats, headline, tags = [], minScale = 0.6, className }: CommunityOrbitProps) {
  const frameRef = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(1)
  const [compact, setCompact] = useState(false)
  const reduced = useReducedMotion() ?? false
  const stageH = stats.length > 0 ? STAGE_H : STAGE_H_SADE

  useLayoutEffect(() => {
    const frame = frameRef.current
    if (!frame) return
    const measure = () => {
      setCompact(frame.clientWidth < COMPACT_BELOW)
      setScale(Math.min(1, Math.max(minScale, frame.clientWidth / STAGE_W)))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(frame)
    return () => ro.disconnect()
  }, [minScale])

  return (
    <section className={`w-full rounded-xl border bg-card px-4 pb-10 pt-4 text-card-foreground ${className ?? ""}`}>
      <div
        ref={frameRef}
        className="relative mx-auto w-full max-w-[1200px] overflow-hidden"
        style={{ height: compact ? "auto" : stageH * scale }}
      >
        {compact ? (
          <div className="grid grid-cols-2 gap-6 py-4">
            {stats.map((s, i) => (
              <StatBlock key={s.label} stat={s} delay={0.2 + i * 0.1} still={reduced} small />
            ))}
          </div>
        ) : (
          <div
            className="absolute left-1/2 top-0"
            style={{
              width: STAGE_W,
              height: stageH,
              transform: `translateX(-50%) scale(${scale})`,
              transformOrigin: "top center",
            }}
          >
            <svg
              className="pointer-events-none absolute inset-0"
              width={STAGE_W}
              height={stageH}
              viewBox={`0 0 ${STAGE_W} ${stageH}`}
              fill="none"
              aria-hidden
              style={{
                maskImage: "linear-gradient(to bottom, #000 62%, transparent 100%)",
                WebkitMaskImage: "linear-gradient(to bottom, #000 62%, transparent 100%)",
              }}
            >
              <motion.path
                d={arcPath(RADIUS.outer, stageH)}
                className="stroke-border"
                strokeWidth={2}
                initial={{ pathLength: reduced ? 1 : 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 1.4, ease: "easeOut" }}
              />
              <motion.path
                d={arcPath(RADIUS.inner, stageH)}
                className="stroke-border"
                strokeWidth={3}
                initial={{ pathLength: reduced ? 1 : 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 1.4, ease: "easeOut", delay: 0.1 }}
              />
            </svg>

            {items.map((item, i) => (
              <motion.div
                key={i}
                className="absolute -translate-x-1/2 -translate-y-1/2"
                style={positionOnRing(item.ring, item.angle)}
                initial={reduced ? false : { opacity: 0, scale: 0.7 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.5, delay: 0.5 + i * 0.07, ease: EASE }}
              >
                <motion.div
                  animate={reduced ? undefined : { y: [0, -4, 0] }}
                  transition={{ duration: 4 + (i % 4) * 0.6, repeat: Infinity, ease: "easeInOut", delay: (i * 0.4) % 2 }}
                  whileHover={reduced ? undefined : { scale: 1.06 }}
                >
                  {renderItem(item)}
                </motion.div>
              </motion.div>
            ))}

            <div className="absolute left-1/2 top-[393px] grid -translate-x-1/2 auto-cols-fr grid-flow-col gap-7">
              {stats.map((s, i) => (
                <StatBlock key={s.label} stat={s} delay={0.9 + i * 0.12} still={reduced} />
              ))}
            </div>
          </div>
        )}
      </div>

      <motion.h2
        className="mx-auto mt-2 max-w-[600px] text-center text-[26px] font-[450] leading-[1.18] tracking-[-0.01em] sm:text-[34px]"
        variants={reveal}
        initial={reduced ? "show" : "hidden"}
        animate="show"
        transition={{ duration: 0.7, delay: 1.3, ease: EASE }}
      >
        {headline}
      </motion.h2>

      {tags.length > 0 && (
        <div className="mx-auto mt-[35px] flex max-w-[760px] flex-wrap justify-center gap-3">
          {tags.map((t, i) => {
            const Tag = (t.href ? motion.a : motion.button) as typeof motion.a
            return (
              <Tag
                key={t.label}
                {...(t.href ? { href: t.href } : { type: "button" as const })}
                onClick={t.onClick}
                variants={reveal}
                initial={reduced ? "show" : "hidden"}
                animate="show"
                transition={{ duration: 0.5, delay: 1.6 + i * 0.08, ease: EASE }}
                whileHover={reduced ? undefined : { y: -2 }}
                className="group flex h-10 items-center gap-2.5 rounded-full border border-border bg-card pl-1.5 pr-4 text-[14px] font-medium text-foreground transition-colors hover:bg-accent focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#eef4f0] text-[#2e7d3e] dark:bg-[#1c3a26] dark:text-[#7fd096] [&>svg]:h-[15px] [&>svg]:w-[15px]">
                  {t.icon}
                </span>
                {t.label}
              </Tag>
            )
          })}
        </div>
      )}
    </section>
  )
}

export { CommunityOrbit as Component }
