import { createContext, useContext, type ComponentProps, type CSSProperties, type ReactNode } from "react"
import { Legend, ResponsiveContainer, Tooltip } from "recharts"

import { cn } from "@/lib/utils"

export type ChartConfig = Record<
  string,
  {
    label?: ReactNode
    color?: string
  }
>

const ChartContext = createContext<{ config: ChartConfig } | null>(null)

function useChart() {
  const context = useContext(ChartContext)
  if (!context) {
    throw new Error("useChart must be used within a ChartContainer")
  }
  return context
}

export function ChartContainer({
  id,
  className,
  children,
  config,
  ...props
}: ComponentProps<"div"> & {
  config: ChartConfig
  children: ComponentProps<typeof ResponsiveContainer>["children"]
}) {
  const chartId = id ?? "chart"
  const style = Object.fromEntries(
    Object.entries(config)
      .filter(([, value]) => value.color)
      .map(([key, value]) => [`--color-${key}`, value.color]),
  ) as CSSProperties

  return (
    <ChartContext.Provider value={{ config }}>
      <div
        data-chart={chartId}
        className={cn(
          "flex w-full justify-center text-xs [&_.recharts-cartesian-axis-tick_text]:fill-muted-foreground [&_.recharts-cartesian-grid_line]:stroke-border",
          className,
        )}
        style={style}
        {...props}
      >
        <ResponsiveContainer width="100%" height="100%">
          {children}
        </ResponsiveContainer>
      </div>
    </ChartContext.Provider>
  )
}

export const ChartTooltip = Tooltip
export const ChartLegend = Legend

type TooltipPayloadItem = {
  dataKey?: string | number
  name?: string
  value?: number | string
  color?: string
}

export function ChartTooltipContent({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: TooltipPayloadItem[]
  label?: string | number
}) {
  const { config } = useChart()
  if (!active || !payload?.length) return null

  return (
    <div className="grid min-w-32 gap-1.5 rounded-lg border bg-background px-2.5 py-1.5 text-xs shadow-xl">
      {label != null ? <div className="font-medium">{label}</div> : null}
      {payload.map((item) => {
        const key = String(item.dataKey ?? item.name ?? "")
        const itemConfig = config[key]
        return (
          <div key={key} className="flex items-center gap-2">
            <span className="size-2 rounded-sm" style={{ background: item.color || itemConfig?.color }} />
            <span className="text-muted-foreground">{itemConfig?.label ?? key}</span>
            <span className="ml-auto font-mono font-medium tabular-nums">{item.value}</span>
          </div>
        )
      })}
    </div>
  )
}

export function ChartLegendContent({
  payload,
}: {
  payload?: Array<{ dataKey?: string | number; value?: string; color?: string }>
}) {
  const { config } = useChart()
  if (!payload?.length) return null

  return (
    <div className="flex items-center justify-center gap-4 pt-2">
      {payload.map((item) => {
        const key = String(item.dataKey ?? item.value ?? "")
        const itemConfig = config[key]
        return (
          <div key={key} className="flex items-center gap-1.5">
            <span className="size-2 rounded-sm" style={{ background: item.color || itemConfig?.color }} />
            <span>{itemConfig?.label ?? item.value}</span>
          </div>
        )
      })}
    </div>
  )
}