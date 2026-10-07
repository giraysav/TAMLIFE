import { useEffect, useRef, useState } from "react"
import { Check, ChevronDown, LogOut, MessageSquare, ShieldCheck, UserRound } from "lucide-react"
import type { Kullanici } from "@/lib/oturum"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

type Props = {
  kullanici: Kullanici
  dil: Dil
  onDil: (dil: Dil) => void
  onGit: (id: string) => void
  onCikis: () => void
  talepVar: boolean
}

const OGE =
  "flex w-full items-center gap-2 rounded-sm px-2 py-2 text-left text-sm hover:bg-accent focus-visible:bg-accent focus-visible:outline-hidden"

/** Sag ustteki kullanici menusu: profil, dil, gelistirme talepleri, yonetim, cikis. */
export function KullaniciMenu({ kullanici, dil, onDil, onGit, onCikis, talepVar }: Props) {
  const t = metin(dil)
  const [acik, setAcik] = useState(false)
  const kutu = useRef<HTMLDivElement>(null)
  const dugme = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!acik) return
    const disariTikla = (olay: MouseEvent) => {
      if (!kutu.current?.contains(olay.target as Node)) setAcik(false)
    }
    const tus = (olay: KeyboardEvent) => {
      if (olay.key === "Escape") {
        setAcik(false)
        dugme.current?.focus()
      }
    }
    document.addEventListener("mousedown", disariTikla)
    document.addEventListener("keydown", tus)
    return () => {
      document.removeEventListener("mousedown", disariTikla)
      document.removeEventListener("keydown", tus)
    }
  }, [acik])

  function git(id: string) {
    setAcik(false)
    onGit(id)
  }

  const bas = kullanici.username.slice(0, 2).toUpperCase()

  return (
    <div className="relative" ref={kutu}>
      <button
        ref={dugme}
        type="button"
        aria-haspopup="menu"
        aria-expanded={acik}
        onClick={() => setAcik((a) => !a)}
        className="flex h-9 items-center gap-2 rounded-md border px-2 text-sm hover:bg-accent focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="flex size-6 items-center justify-center rounded-full bg-muted text-[11px] font-medium">{bas}</span>
        <span className="hidden max-w-32 truncate font-medium sm:inline">{kullanici.username}</span>
        <ChevronDown aria-hidden className={`size-4 transition-transform ${acik ? "rotate-180" : ""}`} />
      </button>
      {acik ? (
        <div
          role="menu"
          aria-label={kullanici.username}
          className="absolute right-0 top-full z-30 mt-1 w-64 rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
        >
          <div className="px-2 py-2">
            <p className="truncate text-sm font-medium">{kullanici.username}</p>
            <p className="truncate text-xs text-muted-foreground">{kullanici.role}</p>
          </div>
          <div className="my-1 h-px bg-border" />
          <button type="button" role="menuitem" className={OGE} onClick={() => git("profil")}>
            <UserRound aria-hidden className="size-4" />
            {t.profil}
          </button>
          {kullanici.is_admin ? (
            <button type="button" role="menuitem" className={OGE} onClick={() => git("yonetim/durum")}>
              <ShieldCheck aria-hidden className="size-4" />
              {t.yonetim}
            </button>
          ) : null}
          {talepVar ? (
            <button type="button" role="menuitem" className={OGE} onClick={() => git("talep")}>
              <MessageSquare aria-hidden className="size-4" />
              {t.gelistirmeTalepleri}
            </button>
          ) : null}
          <div className="my-1 h-px bg-border" />
          <p className="px-2 pb-1 pt-1 text-xs text-muted-foreground">{t.dil}</p>
          {(["tr", "en"] as const).map((d) => (
            <button
              key={d}
              type="button"
              role="menuitemradio"
              aria-checked={dil === d}
              className={OGE}
              onClick={() => {
                onDil(d)
                setAcik(false)
              }}
            >
              <span className="flex size-4 items-center justify-center">{dil === d ? <Check aria-hidden className="size-4" /> : null}</span>
              {d === "tr" ? "Türkçe (TR)" : "English (EN)"}
            </button>
          ))}
          <div className="my-1 h-px bg-border" />
          <button
            type="button"
            role="menuitem"
            className={`${OGE} text-destructive`}
            onClick={() => {
              setAcik(false)
              onCikis()
            }}
          >
            <LogOut aria-hidden className="size-4" />
            {t.cikis}
          </button>
        </div>
      ) : null}
    </div>
  )
}
