import * as Dialog from "@radix-ui/react-dialog"
import { X } from "lucide-react"
import type { ReactNode } from "react"

/** Sagdan acilan form cekmecesi (Radix Dialog: odak tuzagi, Esc ile kapanma, ekran okuyucu basligi hazir). */
export function Cekmece({
  acik,
  onKapat,
  baslik,
  aciklama,
  children,
  alt,
  kapatEtiketi = "Kapat",
  genis = false,
}: {
  acik: boolean
  onKapat: () => void
  baslik: string
  aciklama?: string
  children: ReactNode
  alt?: ReactNode
  kapatEtiketi?: string
  /** Genislik: true = max-w-3xl (genis tablo), "tam" = max-w-7xl, "ekran" = sinirsiz (tam ekran); varsayilan max-w-md */
  genis?: boolean | "tam" | "ekran"
}) {
  const genislik = genis === "ekran" ? "" : genis === "tam" ? "max-w-7xl" : genis ? "max-w-3xl" : "max-w-md"
  return (
    <Dialog.Root open={acik} onOpenChange={(a) => (a ? undefined : onKapat())}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-tl-navy/50 backdrop-blur-[2px]" />
        <Dialog.Content className={`fixed inset-y-0 right-0 z-50 flex w-full flex-col bg-white shadow-2xl focus-visible:outline-hidden ${genislik}`}>
          <div className="relative overflow-hidden bg-gradient-to-br from-tl-navy to-tl-blue px-5 py-4 text-white">
            <span aria-hidden className="pointer-events-none absolute -right-6 -top-8 size-28 rounded-full bg-tl-yellow/25 blur-2xl" />
            <Dialog.Title className="relative text-base font-black tracking-tight">{baslik}</Dialog.Title>
            {aciklama ? <Dialog.Description className="relative mt-0.5 text-xs font-bold text-white/70">{aciklama}</Dialog.Description> : <Dialog.Description className="sr-only">{baslik}</Dialog.Description>}
            <Dialog.Close className="absolute right-3 top-3 rounded-lg p-1.5 text-white/80 hover:bg-white/10 hover:text-white focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow" aria-label={kapatEtiketi}>
              <X aria-hidden className="size-4" />
            </Dialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-5">{children}</div>
          {alt ? <div className="border-t border-slate-200 bg-slate-50 p-4">{alt}</div> : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
