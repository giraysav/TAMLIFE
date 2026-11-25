import * as SheetPrimitive from "@radix-ui/react-dialog"
import { X } from "lucide-react"
import type { ComponentProps } from "react"

import { cn } from "@/lib/utils"

export function Sheet({ ...props }: ComponentProps<typeof SheetPrimitive.Root>) {
  return <SheetPrimitive.Root {...props} />
}

export function SheetContent({
  className,
  children,
  side = "right",
  ...props
}: ComponentProps<typeof SheetPrimitive.Content> & { side?: "left" | "right" }) {
  return (
    <SheetPrimitive.Portal>
      <SheetPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40" />
      <SheetPrimitive.Content
        className={cn(
          "fixed z-50 flex h-full w-72 flex-col bg-sidebar text-sidebar-foreground shadow-lg",
          side === "left" ? "inset-y-0 left-0" : "inset-y-0 right-0",
          className,
        )}
        {...props}
      >
        <SheetPrimitive.Title className="sr-only">Navigation</SheetPrimitive.Title>
        <SheetPrimitive.Description className="sr-only">TAM Life navigation</SheetPrimitive.Description>
        {children}
        <SheetPrimitive.Close
          className="absolute right-3 top-3 rounded-md p-1 text-sidebar-foreground opacity-70 hover:opacity-100"
          aria-label="Close"
        >
          <X className="size-4" />
        </SheetPrimitive.Close>
      </SheetPrimitive.Content>
    </SheetPrimitive.Portal>
  )
}
