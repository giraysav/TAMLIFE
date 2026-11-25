import type { ReactNode } from "react"
import { BadgeCheck, BriefcaseBusiness, ChartNoAxesCombined, Clock, Eye, Landmark, ShieldCheck, Target, UsersRound } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import logo from "@/assets/tam_life_logo.png"
import { sayi, zaman } from "@/lib/bicim"
import { yerel } from "@/shell/metin"
import type { Dil } from "@/shell/metin"
import { sunumMetin } from "@/sunum/sunum-metin"
import type { TanitimVeri } from "@/sunum/sunum-tipleri"

const ALT_BASLIK = "mb-3 flex items-center gap-2 text-[0.6875rem] font-black uppercase tracking-[0.18em] text-tl-blue"
const AMAC_IKON: LucideIcon[] = [Target, Eye, ChartNoAxesCombined]
const DEGER_IKON: LucideIcon[] = [Clock, BadgeCheck, ShieldCheck, Landmark]
const ALAN_IKON: LucideIcon[] = [UsersRound, BriefcaseBusiness, ChartNoAxesCombined, Landmark]

function Baslik({ children }: { children: ReactNode }) {
  return (
    <h4 className={ALT_BASLIK}>
      <span aria-hidden className="h-3.5 w-1 rounded-full bg-tl-yellow" />
      {children}
    </h4>
  )
}

/** Simgeli madde: baslik + tek cumle (Amac ve Sagladigi deger listeleri). */
function Madde({ Ikon, baslik, metin, no }: { Ikon: LucideIcon; baslik: string; metin: string; no?: number }) {
  return (
    <li className="flex items-start gap-3">
      <span className="relative mt-0.5 grid size-8 shrink-0 place-items-center rounded-xl bg-tl-blue/10 text-tl-blue">
        <Ikon aria-hidden className="size-4" />
        {no ? <span className="absolute -right-1 -top-1 grid size-4 place-items-center rounded-full bg-tl-yellow text-[0.5625rem] font-black text-tl-navy">{no}</span> : null}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-black text-tl-navy">{baslik}</span>
        <span className="block text-xs font-bold leading-snug text-slate-600">{metin}</span>
      </span>
    </li>
  )
}

/**
 * TAMLIFE tanitim sayfasi (ust yonetim slayti, 2026-10-20): kisa ozet ve ana rakamlar, 3 maddelik amac, sagladigi deger, is alanlarina
 * gore kapsam ve canli rakamlar; teknik olcumler yalniz alt bilgi. Sayilar sunucuda OLCULUR; burada yalniz cizilir.
 * Eski (2026-10-20 oncesi) kayitli yukte yeni alanlar yoksa eski alanlarla cizilir. `rozet` ust satira konur.
 */
export function TanitimIcerigi({ veri, dil, rozet }: { veri: TanitimVeri; dil: Dil; rozet: ReactNode }) {
  const k = sunumMetin(dil).tanitim
  const kod = veri.kod
  const sayiAl = (kodu: string) => veri.sayilar.find((s) => s.kod === kodu)?.deger
  const canli = (ad: string) => veri.canli.find((c) => c.ad === ad)?.deger ?? 0
  const musteri = canli("Çatı müşteri") + canli("İştirak")
  const tam = veri.canli.find((c) => c.ad === "TAM")?.deger
  const modul = sayiAl("modul") ?? veri.kapsam.length
  const alanlar = veri.alanlar?.length ? veri.alanlar : [{ ad: k.kapsam, ad_en: k.kapsam, moduller: veri.kapsam }]
  const amaclar = veri.amac_maddeleri ?? []
  const ana = [
    ...(musteri ? [{ deger: musteri, ad: k.musteriKarti }] : []),
    ...(tam ? [{ deger: tam, ad: k.tamUzmani }] : []),
    { deger: modul, ad: k.modul },
  ]
  const teknik = [
    kod ? k.satirKod(sayi(kod.satir)) : "",
    ...(["uc", "test"] as const).map((x) => (sayiAl(x) !== undefined ? k.teknikSayi[x](sayi(sayiAl(x) ?? 0)) : "")),
    kod ? kod.diller.map((d) => d.dil).join(", ") : "",
  ].filter(Boolean)
  return (
    <div className="flex flex-col">
      <div className="relative overflow-hidden bg-[linear-gradient(120deg,#002855_0%,#0055a5_58%,#1f7bc4_80%,#ffc72c_150%)] px-5 py-6 text-white sm:px-7">
        <span aria-hidden className="pointer-events-none absolute -right-12 -top-16 size-60 rounded-full bg-tl-yellow/25 blur-3xl" />
        <div className="relative grid gap-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <div className="rounded-xl bg-white px-3 py-2 shadow-lg shadow-black/20">
                <img src={logo} alt="TAMLIFE" width={459} height={105} className="h-7 w-auto sm:h-8" />
              </div>
              <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.625rem] font-black uppercase tracking-[0.22em] text-tl-yellow">
                {k.ust}
                <span className="normal-case tracking-normal">{rozet}</span>
              </p>
            </div>
            <h3 className="mt-3 text-2xl font-black leading-tight tracking-tight sm:text-3xl">{veri.slogan ? yerel(dil, veri.slogan.tr, veri.slogan.en) : k.baslik}</h3>
            <p className="mt-2 max-w-3xl text-sm font-bold leading-relaxed text-white/85">{veri.ozet ? yerel(dil, veri.ozet.tr, veri.ozet.en) : yerel(dil, veri.amac.tr, veri.amac.en)}</p>
          </div>
          <dl className="grid grid-cols-3 gap-2 sm:gap-3">
            {ana.map((a) => (
              <div key={a.ad} className="min-w-[6.5rem] rounded-2xl bg-tl-navy/70 px-4 py-3 text-center ring-1 ring-white/15">
                <dd className="text-3xl font-black leading-none tabular-nums text-tl-yellow">{sayi(a.deger)}</dd>
                <dt className="mt-1.5 text-[0.625rem] font-black uppercase tracking-widest text-white/85">{a.ad}</dt>
              </div>
            ))}
          </dl>
        </div>
      </div>

      <div className="grid gap-5 p-5 lg:grid-cols-2">
        <section>
          <Baslik>{k.amac}</Baslik>
          {amaclar.length ? (
            <ul className="grid gap-3">
              {amaclar.map((m, i) => (
                <Madde key={m.ad} no={i + 1} Ikon={AMAC_IKON[i % AMAC_IKON.length]} baslik={yerel(dil, m.ad, m.ad_en)} metin={yerel(dil, m.aciklama, m.aciklama_en)} />
              ))}
            </ul>
          ) : (
            <p className="text-sm font-bold leading-relaxed text-tl-navy">{yerel(dil, veri.amac.tr, veri.amac.en)}</p>
          )}
        </section>
        <section>
          <Baslik>{k.fayda}</Baslik>
          <ul className="grid gap-3">
            {veri.fayda.map((f, i) => (
              <Madde key={f.ad} Ikon={DEGER_IKON[i % DEGER_IKON.length]} baslik={yerel(dil, f.ad, f.ad_en)} metin={yerel(dil, f.aciklama, f.aciklama_en)} />
            ))}
          </ul>
        </section>
      </div>

      <section className="border-t border-slate-100 p-5">
        <Baslik>{k.kapsamAlt(modul)}</Baslik>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {alanlar.map((a, i) => {
            const Ikon = ALAN_IKON[i % ALAN_IKON.length]
            return (
              <div key={a.ad} className="rounded-2xl border border-slate-200 border-t-4 border-t-tl-yellow bg-white p-3">
                <p className="mb-2 flex items-center gap-2 text-xs font-black text-tl-navy">
                  <Ikon aria-hidden className="size-4 text-tl-blue" />
                  {yerel(dil, a.ad, a.ad_en)}
                </p>
                <ul className="grid gap-1">
                  {a.moduller.map((m) => (
                    <li key={m.ad} className="flex items-center gap-1.5 text-[0.6875rem] font-bold text-slate-600">
                      <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-tl-blue" />
                      {yerel(dil, m.ad, m.ad_en)}
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>
      </section>

      {veri.canli.length > 0 ? (
        <section className="border-t border-slate-100 bg-slate-50/60 p-5">
          <Baslik>{k.canliBaslik}</Baslik>
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            {veri.canli.map((c) => (
              <div key={c.ad} className="rounded-xl bg-white px-3 py-2.5 ring-1 ring-slate-200">
                <dd className="text-xl font-black tabular-nums text-tl-navy">{sayi(c.deger)}</dd>
                <dt className="text-[0.6875rem] font-bold text-slate-500">{yerel(dil, c.ad, c.ad_en)}</dt>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      <footer className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 border-t border-slate-100 px-5 py-2.5 text-[0.6875rem] font-bold text-slate-500">
        <p>
          <span className="mr-2 font-black uppercase tracking-widest text-tl-blue">{k.yiginBaslik}</span>
          {[...teknik, veri.yigin.slice(0, 5).join(" · ")].filter(Boolean).join(" · ")}
        </p>
        <p className="text-[0.625rem] text-slate-400">{k.olcum(zaman(veri.olcum))}</p>
      </footer>
    </div>
  )
}
