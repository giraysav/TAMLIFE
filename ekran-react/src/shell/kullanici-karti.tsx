import { useEffect, useRef, useState } from "react"
import { Check, ChevronUp, LogOut, MessageSquare, ShieldCheck, Sparkles, UserRound, Wand2 } from "lucide-react"
import { baslangicHarfleri } from "@/lib/bicim"
import { hareketDegistir, useHareket } from "@/lib/hareket"
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
  "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm font-semibold text-slate-700 hover:bg-slate-100 focus-visible:bg-slate-100 focus-visible:outline-hidden"

/**
 * Sol alttaki hesap karti (eskiden sag ustteki "admin" dugmesi): animasyonlu halkali avatar, rol rozeti, cevrimici noktasi.
 * Admin icin sari parilti ve "Yonetim konsolu" kisayolu one cikar. Menu yukari acilir; Esc / disari tik kapatir.
 */
export function KullaniciKarti({ kullanici, dil, onDil, onGit, onCikis, talepVar }: Props) {
  const t = metin(dil)
  const [acik, setAcik] = useState(false)
  const kutu = useRef<HTMLDivElement>(null)
  const dugme = useRef<HTMLButtonElement>(null)
  const admin = kullanici.is_admin
  const hareket = useHareket()

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

  const rol = t.rolEtiket[kullanici.role] ?? kullanici.role

  return (
    <div className="relative" ref={kutu}>
      {acik ? (
        <div role="menu" aria-label={t.hesapMenusu} className="absolute inset-x-0 bottom-full z-30 mb-2 rounded-2xl border border-slate-200 bg-white p-1.5 shadow-2xl shadow-tl-navy/20">
          {admin ? (
            <button
              type="button"
              role="menuitem"
              className="mb-1 flex w-full items-center gap-3 rounded-xl bg-gradient-to-r from-tl-yellow to-amber-300 px-3 py-2.5 text-left font-black text-tl-navy shadow-sm transition-transform hover:-translate-y-px focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-navy"
              onClick={() => git("yonetim/durum")}
            >
              <ShieldCheck aria-hidden className="size-5 shrink-0" />
              <span className="grid leading-tight">
                <span className="text-sm">{t.yonetim}</span>
                <span className="text-[10px] font-bold uppercase tracking-wide text-tl-navy/70">{t.yonetimKonsolu}</span>
              </span>
            </button>
          ) : null}
          <button type="button" role="menuitem" className={OGE} onClick={() => git("profil")}>
            <UserRound aria-hidden className="size-4 text-slate-400" />
            {t.profil}
          </button>
          {talepVar ? (
            <button type="button" role="menuitem" className={OGE} onClick={() => git("talep")}>
              <MessageSquare aria-hidden className="size-4 text-slate-400" />
              {t.gelistirmeTalepleri}
            </button>
          ) : null}
          <div className="my-1 h-px bg-slate-100" />
          <p className="px-2.5 pb-0.5 pt-1 text-[10px] font-black uppercase tracking-wide text-slate-400">{t.dil}</p>
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
              <span className="flex size-4 items-center justify-center">{dil === d ? <Check aria-hidden className="size-4 text-tl-blue" /> : null}</span>
              {d === "tr" ? "Türkçe (TR)" : "English (EN)"}
            </button>
          ))}
          <button type="button" role="menuitemcheckbox" aria-checked={hareket} className={OGE} onClick={hareketDegistir}>
            <span className="flex size-4 items-center justify-center">{hareket ? <Check aria-hidden className="size-4 text-tl-blue" /> : <Wand2 aria-hidden className="size-4 text-slate-400" />}</span>
            {t.animasyonlar}
          </button>
          <div className="my-1 h-px bg-slate-100" />
          <button
            type="button"
            role="menuitem"
            className={`${OGE} !text-rose-600 hover:!bg-rose-50`}
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

      <button
        ref={dugme}
        type="button"
        aria-haspopup="menu"
        aria-expanded={acik}
        aria-label={`${t.hesapMenusu}: ${kullanici.username}`}
        onClick={() => setAcik((a) => !a)}
        className="group relative block w-full overflow-hidden rounded-2xl bg-gradient-to-br from-tl-navy via-[#02407f] to-tl-blue p-px text-left shadow-lg shadow-tl-navy/25 transition-all hover:-translate-y-0.5 hover:shadow-xl hover:shadow-tl-blue/30 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow"
      >
        <span className="relative flex items-center gap-3 rounded-[15px] bg-gradient-to-br from-tl-navy to-[#01336a] px-3 py-3 text-white">
          {admin ? <span aria-hidden className="tl-hareket pointer-events-none absolute inset-y-0 left-0 w-1/4 bg-gradient-to-r from-transparent via-tl-yellow/25 to-transparent" style={{ animation: "tl-parilti 4.5s ease-in-out infinite" }} /> : null}
          <span className="relative flex size-11 shrink-0 items-center justify-center">
            <span
              aria-hidden
              className="tl-hareket absolute inset-0 rounded-full"
              style={{ background: "conic-gradient(from 0deg, #ffc72c, #00a3e0, #ffc72c 60%, transparent 85%)", animation: "tl-donus 5s linear infinite" }}
            />
            <span className="relative flex size-[38px] items-center justify-center rounded-full bg-tl-navy text-sm font-black tracking-tight text-tl-yellow">{baslangicHarfleri(kullanici.username)}</span>
            <span aria-hidden className="absolute -bottom-0.5 -right-0.5 flex size-3.5 items-center justify-center rounded-full bg-tl-navy">
              <span className="tl-hareket size-2 rounded-full bg-emerald-400" style={{ animation: "tl-nabiz 2.4s ease-in-out infinite" }} />
            </span>
          </span>
          <span className="relative grid min-w-0 flex-1 gap-1">
            <span className="truncate text-sm font-black leading-none">{kullanici.username}</span>
            <span className="flex items-center gap-1.5">
              <span
                key={dil} // rol adi iki dilde ayni; tarayici dil degisiminde buyuk harf donusumunu (ADMIN/ADMİN) tazelemiyor
                className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-black uppercase tracking-wider ${
                  admin ? "bg-tl-yellow text-tl-navy" : "bg-white/15 text-white"
                }`}
              >
                {admin ? <Sparkles aria-hidden className="size-3" /> : null}
                {rol}
              </span>
              <span className="text-[10px] font-bold text-emerald-300">{t.cevrimici}</span>
            </span>
          </span>
          <ChevronUp aria-hidden className={`relative size-4 shrink-0 text-white/70 transition-transform ${acik ? "" : "rotate-180"} group-hover:text-tl-yellow`} />
        </span>
      </button>
    </div>
  )
}
