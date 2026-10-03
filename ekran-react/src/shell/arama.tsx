import { useEffect, useRef, useState } from "react"
import { Search } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { MenuOgesi } from "@/lib/oturum"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

function tr(s: string) {
  return s.toLocaleLowerCase("tr-TR")
}

/** Ctrl/Cmd+K ile acilan menu aramasi. Yalniz yetkili ogeler listelenir. */
export function Arama({ ogeler, dil, onGit }: { ogeler: MenuOgesi[]; dil: Dil; onGit: (id: string) => void }) {
  const t = metin(dil)
  const [acik, setAcik] = useState(false)
  const [sorgu, setSorgu] = useState("")
  const kutu = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const tus = (olay: KeyboardEvent) => {
      if ((olay.ctrlKey || olay.metaKey) && olay.key.toLowerCase() === "k") {
        olay.preventDefault()
        setAcik((a) => !a)
      }
    }
    document.addEventListener("keydown", tus)
    return () => document.removeEventListener("keydown", tus)
  }, [])

  useEffect(() => {
    const d = kutu.current
    if (!d) return
    if (acik) {
      setSorgu("")
      if (!d.open) d.showModal()
    } else if (d.open) d.close()
  }, [acik])

  const sonuc = ogeler.filter((o) => tr(`${o.label} ${o.description}`).includes(tr(sorgu)))

  return (
    <>
      <Button type="button" variant="ghost" size="icon" aria-label={t.ara} onClick={() => setAcik(true)}>
        <Search aria-hidden />
      </Button>
      <dialog
        ref={kutu}
        onClose={() => setAcik(false)}
        onClick={(e) => {
          if (e.target === kutu.current) setAcik(false)
        }}
        aria-label={t.ara}
        className="m-auto w-full max-w-lg rounded-xl border bg-popover p-3 text-popover-foreground shadow-lg backdrop:bg-black/40"
      >
        <Input autoFocus value={sorgu} onChange={(e) => setSorgu(e.target.value)} placeholder={t.aramaIpucu} aria-label={t.ara} />
        <ul className="mt-2 max-h-72 overflow-auto">
          {sonuc.length === 0 ? <li className="px-2 py-3 text-sm text-muted-foreground">{t.sonucYok}</li> : null}
          {sonuc.map((o) => (
            <li key={o.id}>
              <button
                type="button"
                className="flex w-full flex-col rounded-md px-2 py-2 text-left hover:bg-accent focus-visible:bg-accent focus-visible:outline-hidden"
                onClick={() => {
                  setAcik(false)
                  onGit(o.id)
                }}
              >
                <span className="text-sm font-medium">{o.label}</span>
                <span className="text-xs text-muted-foreground">{o.description}</span>
              </button>
            </li>
          ))}
        </ul>
      </dialog>
    </>
  )
}
