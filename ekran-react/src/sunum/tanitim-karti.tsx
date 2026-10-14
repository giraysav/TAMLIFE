import type { ReactNode } from "react"
import { CircleCheck } from "lucide-react"
import logo from "@/assets/tam_life_logo.png"
import { Kpi } from "@/components/sayfa-ui"
import { ondalik, sayi, zaman } from "@/lib/bicim"
import { yerel } from "@/shell/metin"
import type { Dil } from "@/shell/metin"
import { sunumMetin } from "@/sunum/sunum-metin"
import type { TanitimVeri } from "@/sunum/sunum-tipleri"

const DIL_RENK: Record<string, string> = { Python: "#0055a5", TypeScript: "#00a3e0", PowerShell: "#ffc72c", CSS: "#002855" }

const ALT_BASLIK = "mb-2 flex items-center gap-2 text-[0.6875rem] font-black uppercase tracking-widest text-tl-blue"

/** Sari cerceveli kart + kose noktasi (Turkcell sunum dili): Amac / Kapsam / Fayda kutulari. */
function Kutu({ baslik, children }: { baslik: string; children: ReactNode }) {
  return (
    <section className="relative rounded-2xl border-2 border-tl-yellow bg-white p-4">
      <h4 className={ALT_BASLIK}>
        <span aria-hidden className="h-3.5 w-1 rounded-full bg-tl-yellow" />
        {baslik}
      </h4>
      {children}
      <span aria-hidden className="absolute -bottom-1.5 -right-1.5 size-3 rounded-full bg-tl-yellow ring-2 ring-white" />
    </section>
  )
}

/**
 * TAM Life tanitim sayfasi (sunumun "en onemli proje" slayti): amac / kapsam / fayda, kac satir kod, hangi dil, kod ne yapiyor.
 * Sayilar sunucuda OLCULUR (depo, katalog, veritabani); burada yalniz cizilir. `rozet` basligin sag ustune konur.
 */
export function TanitimIcerigi({ veri, dil, rozet }: { veri: TanitimVeri; dil: Dil; rozet: ReactNode }) {
  const t = sunumMetin(dil)
  const k = t.tanitim
  const kod = veri.kod
  const testYuzdesi = kod && kod.satir > 0 ? Math.round((100 * kod.test_satir) / kod.satir) : 0
  return (
    <div className="flex flex-col">
      <div className="relative overflow-hidden bg-[linear-gradient(120deg,#002855_0%,#0055a5_52%,#1f7bc4_70%,#ffc72c_138%)] px-4 py-5 text-white sm:px-6 sm:py-6">
        <span aria-hidden className="pointer-events-none absolute -right-10 -top-14 size-56 rounded-full bg-tl-yellow/30 blur-3xl" />
        <span aria-hidden className="pointer-events-none absolute -bottom-16 left-1/4 size-48 rounded-full bg-tl-accent/25 blur-3xl" />
        <div className="relative flex flex-wrap items-center gap-x-6 gap-y-4">
          <div className="rounded-2xl bg-white px-4 py-3 shadow-lg shadow-black/20">
            <img src={logo} alt="TAM Life" width={459} height={105} className="h-9 w-auto sm:h-11" />
          </div>
          <div className="min-w-[14rem] flex-1">
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.625rem] font-black uppercase tracking-[0.2em] text-tl-yellow">
              {k.ust}
              <span className="normal-case tracking-normal">{rozet}</span>
            </p>
            <h3 className="mt-1 text-xl font-black leading-tight tracking-tight sm:text-2xl">{k.baslik}</h3>
            <p className="mt-1 text-xs font-bold text-white/80 sm:text-sm">{k.alt}</p>
          </div>
          {kod ? (
            <div className="rounded-2xl bg-tl-navy/75 px-5 py-3 shadow-lg shadow-black/20 ring-1 ring-white/15 sm:text-right">
              <div className="text-4xl font-black leading-none tabular-nums text-tl-yellow sm:text-5xl">{sayi(kod.satir)}</div>
              <div className="mt-1.5 text-xs font-black uppercase tracking-widest text-white">{k.satirKod}</div>
              <div className="text-[0.6875rem] font-bold text-white/70">{k.dosyaDil(sayi(kod.dosya), kod.diller.length)}</div>
            </div>
          ) : null}
        </div>
      </div>

      <div className="grid gap-4 p-4 lg:grid-cols-3">
        <Kutu baslik={k.amac}>
          <p className="text-base font-bold leading-relaxed text-tl-navy">{yerel(dil, veri.amac.tr, veri.amac.en)}</p>
        </Kutu>
        <Kutu baslik={k.kapsam}>
          <ul className="flex flex-wrap gap-1.5">
            {veri.kapsam.map((m) => (
              <li key={m.ad} className="rounded-lg bg-tl-blue/10 px-2 py-1 text-[0.6875rem] font-black text-tl-navy">
                {yerel(dil, m.ad, m.ad_en)}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[0.6875rem] font-bold text-slate-500">{k.modulSayisi(veri.kapsam.length)}</p>
        </Kutu>
        <Kutu baslik={k.fayda}>
          <ul className="grid gap-2.5">
            {veri.fayda.map((f) => (
              <li key={f.ad} className="flex items-start gap-2">
                <CircleCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-tl-blue" />
                <span className="text-xs font-bold leading-snug text-slate-600">
                  <span className="font-black text-tl-navy">{yerel(dil, f.ad, f.ad_en)}.</span> {yerel(dil, f.aciklama, f.aciklama_en)}
                </span>
              </li>
            ))}
          </ul>
        </Kutu>
      </div>

      <div className="grid gap-5 border-t border-slate-100 p-4 lg:grid-cols-[1.1fr_1fr]">
        {kod ? (
          <section>
            <h4 className={ALT_BASLIK}>
              <span aria-hidden className="h-3.5 w-1 rounded-full bg-tl-yellow" />
              {k.kodBaslik}
            </h4>
            <div className="flex h-3 overflow-hidden rounded-full bg-slate-100" role="img" aria-label={kod.diller.map((d) => `${d.dil}: ${sayi(d.satir)}`).join(", ")}>
              {kod.diller.map((d) => (
                <span key={d.dil} title={`${d.dil}: ${sayi(d.satir)}`} className="h-full" style={{ width: `${d.pay}%`, background: DIL_RENK[d.dil] ?? "#64748b" }} />
              ))}
            </div>
            <ul className="mt-3 grid gap-2.5">
              {kod.diller.map((d) => (
                <li key={d.dil} className="grid grid-cols-[0.75rem_minmax(0,1fr)] gap-x-2">
                  <span aria-hidden className="mt-1 size-3 rounded-sm" style={{ background: DIL_RENK[d.dil] ?? "#64748b" }} />
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                      <span className="text-sm font-black text-tl-navy">{d.dil}</span>
                      <span className="text-xs font-black tabular-nums text-slate-600">
                        {sayi(d.satir)} · %{ondalik(d.pay)}
                      </span>
                    </div>
                    <p className="text-xs font-bold text-slate-500">{yerel(dil, d.rol, d.rol_en)}</p>
                  </div>
                </li>
              ))}
            </ul>
            {testYuzdesi > 0 ? <p className="mt-3 text-[0.6875rem] font-bold text-slate-500">{k.testPayi(sayi(testYuzdesi), sayi(kod.test_satir))}</p> : null}
          </section>
        ) : null}

        <div className="grid content-start gap-4">
          <section>
            <h4 className={ALT_BASLIK}>
              <span aria-hidden className="h-3.5 w-1 rounded-full bg-tl-yellow" />
              {k.sayilarBaslik}
            </h4>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {veri.sayilar.map((s) => (
                <Kpi key={s.kod} kucuk sans etiket={yerel(dil, s.ad, s.ad_en)} deger={sayi(s.deger)} />
              ))}
            </div>
          </section>
          {veri.canli.length > 0 ? (
            <section>
              <h4 className={ALT_BASLIK}>
                <span aria-hidden className="h-3.5 w-1 rounded-full bg-tl-yellow" />
                {k.canliBaslik}
              </h4>
              <ul className="flex flex-wrap gap-2">
                {veri.canli.map((c) => (
                  <li key={c.ad} className="rounded-xl bg-tl-yellow/25 px-2.5 py-1.5 text-xs font-bold text-tl-navy">
                    <span className="font-black tabular-nums">{sayi(c.deger)}</span> {yerel(dil, c.ad, c.ad_en)}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-t border-slate-100 px-4 py-2.5">
        <ul aria-label={k.yiginBaslik} className="flex flex-wrap items-center gap-1.5">
          <li aria-hidden className="mr-1 text-[0.625rem] font-black uppercase tracking-widest text-tl-blue">
            {k.yiginBaslik}
          </li>
          {veri.yigin.map((y) => (
            <li key={y} className="rounded-md bg-slate-100 px-2 py-0.5 text-[0.6875rem] font-black text-slate-600">
              {y}
            </li>
          ))}
        </ul>
        <p className="text-[0.625rem] font-bold text-slate-400">{k.olcum(zaman(veri.olcum))}</p>
      </div>
    </div>
  )
}
