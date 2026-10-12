import type { ReactNode } from "react"
import type { Dil } from "@/shell/metin"
import { ALT_BASLIK_BANDI, ALT_BASLIK_YAZISI, Bolum } from "@/components/sayfa-ui"
import { ym } from "@/yonetim/metin"

function Katlanir({ baslik, children }: { baslik: string; children: ReactNode }) {
  return (
    <details className="group overflow-hidden rounded-xl border border-slate-200 bg-white">
      <summary className={`${ALT_BASLIK_BANDI} cursor-pointer select-none hover:brightness-95`}>
        <span aria-hidden className="h-3.5 w-1 shrink-0 rounded-full bg-tl-yellow" />
        <span className={ALT_BASLIK_YAZISI}>{baslik}</span>
      </summary>
      <div className="p-3">{children}</div>
    </details>
  )
}

function Tanimlar({ satirlar }: { satirlar: [string, string][] }) {
  return (
    <dl className="grid gap-2 text-xs">
      {satirlar.map(([ad, ne]) => (
        <div key={ad} className="grid gap-0.5 md:grid-cols-[16rem_1fr] md:gap-3">
          <dt className="font-black text-tl-navy">{ad}</dt>
          <dd className="font-bold text-slate-600">{ne}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Veri Girisi rehberi: akis (kaynak -> tampon -> analiz -> dagitim -> kart/Onedesk), kaynaklar, kural alanlari, ornekler,
 * uygula / geri al. Alan aciklamalari kural formundaki ipuclariyla ayni metinden gelir (tek kaynak). */
export function Rehber({ dil }: { dil: Dil }) {
  const t = ym(dil)
  const r = t.rehber
  const ip = t.kuralIpuclari
  const alanlar: [string, string][] = [
    [t.kuralKaynak, ip.kuralKaynak],
    [t.anahtarSutunu, ip.anahtarSutunu],
    [t.eslesmeAlani, ip.eslesmeAlani],
    [t.hedef, ip.hedef],
    [t.islem, ip.islem],
    [t.degerSutunu, ip.degerSutunu],
    [t.kosullar, ip.kosullar],
    [t.eslesmeyeniSifirla, t.eslesmeyeniAciklama],
    [t.enBuyukYas, ip.enBuyukYas],
  ]
  return (
    <Bolum anahtar="yonetim-tampon-rehber" baslik={r.baslik}>
      <div className="grid gap-3">
        <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5" aria-label={r.baslik}>
          {r.akis.map(([ad, ne], i) => (
            <li key={ad} className="rounded-xl border border-slate-200 border-l-4 border-l-tl-yellow bg-white px-3 py-2 shadow-sm">
              <p className="text-xs font-black text-tl-navy">
                {i + 1} · {ad}
              </p>
              <p className="text-[0.6875rem] font-bold text-slate-500">{ne}</p>
            </li>
          ))}
        </ol>
        <Katlanir baslik={r.kaynaklarBaslik}>
          <Tanimlar satirlar={r.kaynaklar} />
        </Katlanir>
        <Katlanir baslik={r.alanlarBaslik}>
          <Tanimlar satirlar={alanlar} />
        </Katlanir>
        <Katlanir baslik={r.ornekBaslik}>
          <Tanimlar satirlar={r.ornekler} />
        </Katlanir>
        <Katlanir baslik={r.uygulaBaslik}>
          <ul className="grid list-disc gap-1 pl-5 text-xs font-bold text-slate-600">
            {r.uygula.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </Katlanir>
      </div>
    </Bolum>
  )
}
