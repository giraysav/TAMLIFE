import { useState } from "react"
import type { ReactNode } from "react"
import { hataMesaji, yaz, yukle } from "@/lib/sorgu"
import { DUGME, DUGME_ANA, Rozet } from "@/components/sayfa-ui"
import type { musteriMetin } from "@/musteri/musteri-metin"

export type SlaGrafik = {
  anahtar: string
  kategori: string
  tur: string
  baslik: { tr: string; en: string }
  pivot?: string
  gorsel: string | null
  aylar: string[]
  seriler: Record<string, (number | null)[]>
}
export type SlaVeri = {
  yil: number
  ay: number
  ozet: { dosya: string | null; boyut: number | null; zaman: string | null; yukleyen: string | null; grafik: number; ek_gorsel: number; ek_dosya: number } | null
  analiz: { grafikler: SlaGrafik[]; sayilar: Record<string, { donem: number; toplam: number }>; eksik: string[]; dosya_donemi: string | null; donem: string } | null
  ekler: { no: number; baslik: string; gorsel: string }[]
  dosyalar: { no: number; ad: string; boyut: number }[]
  araclar: { ceviri: { hazir: boolean; kaynak: string | null }; yz: boolean }
}

type Ortak = { adres: (yol: string, sorgu?: Record<string, string>) => string; t: ReturnType<typeof musteriMetin>; veri: SlaVeri | undefined; kilitli: boolean; onDegisti: (v: SlaVeri) => void }

const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

/** Sag sutundaki kucuk kart: baslik, aciklama, icerik ve durum satiri. */
export function KucukKart({ baslik, aciklama, children, mesaj }: { baslik: string; aciklama: string; children: ReactNode; mesaj: string }) {
  return (
    <div className="space-y-2.5 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start gap-2">
        <span aria-hidden className="mt-0.5 h-4 w-1 shrink-0 rounded-full bg-tl-yellow" />
        <div className="min-w-0">
          <h4 className="text-sm font-black text-tl-navy">{baslik}</h4>
          <p className="mt-0.5 text-[0.6875rem] leading-snug text-slate-500">{aciklama}</p>
        </div>
      </div>
      {children}
      {mesaj ? (
        <p role="status" className="text-[0.6875rem] font-bold text-slate-500">
          {mesaj}
        </p>
      ) : null}
    </div>
  )
}

/** Dosya secici dugme. `relative`: sr-only girdi mutlak konumludur; kapsayici olmazsa sayfa koku tasar ve ikinci kaydirma cubugu cikar. */
function DosyaDugmesi({ etiket, kabul, coklu = false, mesgul, ana = false, onSec }: { etiket: string; kabul: string; coklu?: boolean; mesgul: boolean; ana?: boolean; onSec: (d: File[]) => void }) {
  const [anahtar, setAnahtar] = useState(0)
  return (
    <label className={`${ana ? DUGME_ANA : DUGME} relative cursor-pointer ${mesgul ? "pointer-events-none opacity-60" : ""}`}>
      {etiket}
      <input
        key={anahtar}
        type="file"
        accept={kabul}
        multiple={coklu}
        className="sr-only"
        disabled={mesgul}
        onChange={(ev) => {
          const secilen = Array.from(ev.target.files ?? [])
          setAnahtar((n) => n + 1)
          if (secilen.length) onSec(secilen)
        }}
      />
    </label>
  )
}

function useIslem({ t, onDegisti }: Pick<Ortak, "t" | "onDegisti">) {
  const [mesaj, setMesaj] = useState("")
  const [mesgul, setMesgul] = useState(false)
  async function calistir(islemler: (() => Promise<SlaVeri>)[], basari: (n: number) => string = () => "") {
    setMesgul(true)
    let tamam = 0
    try {
      for (const islem of islemler) {
        onDegisti(await islem())
        tamam += 1
      }
      setMesaj(basari(tamam))
    } catch (h) {
      setMesaj(hataMesaji(h, t.kaydedilemedi))
    } finally {
      setMesgul(false)
    }
  }
  return { mesaj, mesgul, calistir }
}

function boyutYaz(bayt: number): string {
  return bayt >= 1024 * 1024 ? `${(bayt / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bayt / 1024))} KB`
}

/** SLA Excel'i: grafikler (kapanan adet + sure ortalamalari) ve ileti eki. Rapor gonderilmisse salt okunur. */
export function SlaKarti({ adres, t, veri, kilitli, onDegisti }: Ortak) {
  const { mesaj, mesgul, calistir } = useIslem({ t, onDegisti })
  const ozet = veri?.ozet
  const analiz = veri?.analiz
  const donem = veri ? `${veri.yil}-${String(veri.ay).padStart(2, "0")}` : ""
  return (
    <KucukKart baslik={t.sla} aciklama={t.slaAciklama} mesaj={mesaj}>
      {ozet?.dosya ? (
        <div className="space-y-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-[0.6875rem]">
          <div className="flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate font-black text-tl-navy" title={ozet.dosya}>
              {ozet.dosya}
            </span>
            <Rozet ton="yesil">{t.grafikSayisi(analiz?.grafikler.length ?? 0)}</Rozet>
          </div>
          <p className="text-slate-400">
            {(ozet.zaman ?? "").slice(0, 16).replace("T", " ")} · {ozet.yukleyen ?? ""}
          </p>
          {analiz && Object.keys(analiz.sayilar).length > 0 ? (
            <p className="text-slate-600">
              <span className="font-bold">{t.donemdeKapanan}:</span>{" "}
              {Object.entries(analiz.sayilar)
                .map(([k, s]) => `${t.kategori[k] ?? k} ${s.donem}`)
                .join(" · ")}
            </p>
          ) : null}
        </div>
      ) : (
        <p className="text-[0.6875rem] font-bold text-slate-400">{t.slaYok}</p>
      )}
      {analiz?.dosya_donemi && analiz.dosya_donemi !== donem ? (
        <p role="alert" className="rounded-lg border border-amber-300 bg-amber-50 px-2.5 py-1.5 text-[0.6875rem] font-bold text-amber-800">
          {t.dosyaDonemiFarkli(analiz.dosya_donemi)}
        </p>
      ) : null}
      {analiz && analiz.eksik.length > 0 ? (
        <p className="text-[0.625rem] text-slate-500">
          {t.eksikSayfalar}: {analiz.eksik.join(", ")}
        </p>
      ) : null}
      {!kilitli ? (
        <div className="flex flex-wrap items-center gap-2">
          <DosyaDugmesi
            ana
            etiket={ozet?.dosya ? t.slaDegistir : t.slaYukle}
            kabul={`.xlsx,${XLSX}`}
            mesgul={mesgul}
            onSec={([d]) => void calistir([() => yukle<SlaVeri>(adres("/sla", { dosya: d.name }), d, XLSX)], () => t.slaYuklendi)}
          />
          {ozet?.dosya ? (
            <button type="button" className={DUGME} disabled={mesgul} onClick={() => window.confirm(t.slaSilOnay) && void calistir([() => yaz<SlaVeri>("DELETE", adres("/sla"))])}>
              {t.slaSil}
            </button>
          ) : null}
        </div>
      ) : null}
    </KucukKart>
  )
}

/** Rapor iletisine eklenecek diger dosyalar. */
export function EkDosyaKarti({ adres, t, veri, kilitli, onDegisti }: Ortak) {
  const { mesaj, mesgul, calistir } = useIslem({ t, onDegisti })
  const dosyalar = veri?.dosyalar ?? []
  function sec(secilen: File[]) {
    void calistir(
      secilen.map((d) => () => yukle<SlaVeri>(adres("/dosya", { ad: d.name }), d, "application/octet-stream", "POST")),
      t.dosyaYuklendi,
    )
  }
  return (
    <KucukKart baslik={t.dosyalar} aciklama={t.dosyaAciklama} mesaj={mesaj}>
      {dosyalar.length > 0 ? (
        <ul className="grid gap-1">
          {dosyalar.map((d) => (
            <li key={d.no} className="flex items-center gap-2 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[0.6875rem]">
              <span className="min-w-0 flex-1 truncate font-bold text-slate-700" title={d.ad}>
                {d.ad}
              </span>
              <span className="shrink-0 text-slate-400">{boyutYaz(d.boyut)}</span>
              {!kilitli ? (
                <button type="button" className="shrink-0 font-bold text-rose-600 hover:underline" disabled={mesgul} onClick={() => void calistir([() => yaz<SlaVeri>("DELETE", adres(`/dosya/${d.no}`))])}>
                  {t.dosyaSil}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[0.6875rem] font-bold text-slate-400">{t.dosyaYok}</p>
      )}
      {!kilitli ? <DosyaDugmesi etiket={t.dosyaYukle} kabul="" coklu mesgul={mesgul} onSec={sec} /> : null}
    </KucukKart>
  )
}
