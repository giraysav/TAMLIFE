import {
  cloneElement,
  createContext,
  isValidElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ButtonHTMLAttributes,
  type ComponentProps,
  type HTMLAttributes,
  type ReactElement,
  type ReactNode,
} from "react"
import { Menu } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Sheet, SheetContent } from "@/components/ui/sheet"
import { cn } from "@/lib/utils"

type SidebarContextValue = {
  open: boolean
  setOpen: (open: boolean) => void
  openMobile: boolean
  setOpenMobile: (open: boolean) => void
  isMobile: boolean
  toggleSidebar: () => void
}

const SidebarContext = createContext<SidebarContextValue | null>(null)

export function useSidebar() {
  const context = useContext(SidebarContext)
  if (!context) {
    throw new Error("useSidebar must be used within SidebarProvider")
  }
  return context
}

export function SidebarProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(true)
  const [openMobile, setOpenMobile] = useState(false)
  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => {
    const query = window.matchMedia("(max-width: 768px)")
    const apply = () => setIsMobile(query.matches)
    apply()
    query.addEventListener("change", apply)
    return () => query.removeEventListener("change", apply)
  }, [])

  const toggleSidebar = useCallback(() => {
    if (isMobile) setOpenMobile((value) => !value)
    else setOpen((value) => !value)
  }, [isMobile])

  const value = useMemo(
    () => ({ open, setOpen, openMobile, setOpenMobile, isMobile, toggleSidebar }),
    [open, openMobile, isMobile, toggleSidebar],
  )

  return (
    <SidebarContext.Provider value={value}>
      {/* Kabuk sayfaya sabit: sr-only gibi mutlak konumlu ogeler belgeyi uzatip ikinci kaydirma cubugu acmasin; kaydiran tek yer SidebarInset. */}
      <div className="relative flex h-full min-h-0 w-full overflow-hidden">{children}</div>
    </SidebarContext.Provider>
  )
}

export function Sidebar({ className, children }: HTMLAttributes<HTMLElement>) {
  const { open, isMobile, openMobile, setOpenMobile } = useSidebar()
  const panel = <div className={cn("flex h-full w-64 flex-col bg-sidebar text-sidebar-foreground", className)}>{children}</div>

  if (isMobile) {
    return (
      <Sheet open={openMobile} onOpenChange={setOpenMobile}>
        <SheetContent side="left" className="w-64 p-0">
          {panel}
        </SheetContent>
      </Sheet>
    )
  }

  if (!open) return null

  return <aside className="h-full shrink-0 border-r border-sidebar-border">{panel}</aside>
}

export function SidebarInset({ className, ...props }: ComponentProps<"main">) {
  return <main className={cn("relative flex min-h-0 min-w-0 flex-1 flex-col overflow-auto bg-background", className)} {...props} />
}

export function SidebarTrigger({ className, onClick, ...props }: ComponentProps<typeof Button>) {
  const { toggleSidebar } = useSidebar()
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className={className}
      {...props}
      onClick={(event) => {
        onClick?.(event)
        toggleSidebar()
      }}
    >
      <Menu />
    </Button>
  )
}

export function SidebarHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-2 p-3", className)} {...props} />
}

export function SidebarContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex min-h-0 flex-1 flex-col gap-2 overflow-auto px-2", className)} {...props} />
}

export function SidebarFooter({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mt-auto border-t border-sidebar-border p-2", className)} {...props} />
}

export function SidebarGroup({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1", className)} {...props} />
}

export function SidebarGroupContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col", className)} {...props} />
}

export function SidebarMenu({ className, ...props }: HTMLAttributes<HTMLUListElement>) {
  return <ul className={cn("flex flex-col gap-1", className)} {...props} />
}

export function SidebarMenuItem({ className, ...props }: HTMLAttributes<HTMLLIElement>) {
  return <li className={cn("list-none", className)} {...props} />
}

type SidebarMenuButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  isActive?: boolean
  render?: ReactElement<{ className?: string; children?: ReactNode }>
}

export function SidebarMenuButton({ className, isActive, render, children, ...props }: SidebarMenuButtonProps) {
  const classes = cn(
    "flex min-h-9 w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
    isActive && "bg-sidebar-accent font-medium text-sidebar-accent-foreground",
    className,
  )

  if (render && isValidElement(render)) {
    return cloneElement(render, {
      className: cn(classes, render.props.className),
      children,
    })
  }

  return (
    <button type="button" className={classes} {...props}>
      {children}
    </button>
  )
}
