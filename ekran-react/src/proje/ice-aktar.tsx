import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Upload } from "lucide-react"
import { Cekmece } from "@/components/cekmece"
import { Alan, Bildirim, DUGME, DUGME_SARI, GIRDI, Panel, Rozet, Yukleniyor } from "@/components/sayfa-ui"
import { hataMesaji, sorguMetni, yukle } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"
import { projeMetin } from "@/proje/proje-metin"
import type { Kategori } from "@/proje/proje-metin"

/** Sunucu sinirinin aynisi: daha buyuk dosya hic gonderilmez. */
const AZAMI_BAYT = 5 * 1024 * 1024
const EXCEL = "application/vnd.ms-excel.sheet.macroEnabled.12"
const DURUMLAR = ["yeni", "var", "tekrar", "tam_yok"] as const
type SatirDurumu = (typeof DURUMLAR)[number]
const TON: Record<SatirDurumu, "yesil" | "gri" | "amber" | "kirmizi"> = { yeni: "yesil", var: "gri", tekrar: "gri", tam_yok: "amber" }

type Satir = { satir: number; ceyrek: string; tam: string; sahip: string; kategori: Kategori; baslik: string; durum: SatirDurumu }
type Onizleme = {
  dosya: string
  yil: number
  plan: Record<SatirDurumu | "toplam", number>
  eslesmeyen: { ad: string; anahtar: string; kayit: number }[]
  kisiler: { id: number; ad: string }[]
  satirlar: Satir[]
}
type Sonuc = Onizleme["plan"] & { eklendi: number }

/** TAM ceyrek Excel'inden proje ice aktarma (Veri Girisi > Import, yalniz admin): dosya -> onizleme (yazmaz) -> eslesmeyen TAM'a
 *  kisi secimi (secim onizlemeyi yeniler) -> yalniz yeni kayitlari ekle. Ayni dosya yeniden yuklenince eklenen olmaz. */
export function ProjeIceAktar({ dil, onKapat }: { dil: Dil; onKapat: () => void }) {
  const t = projeMetin(dil)
  const qc = useQueryClient()
  const [dosya, setDosya] = useState<File | null>(null)
  const [atamalar, setAtamalar] = useState<Record<string, number>>({})
  const [suz, setSuz] = useState<SatirDurumu | "">("")
  const [uyari, setUyari] = useState("")
  // Ilk (atamasiz) onizlemedeki eslesmeyen TAM'lar: secim yapilinca da listede kalir, secim geri alinabilir
  const [eslesmeyen, setEslesmeyen] = useState<Onizleme["eslesmeyen"]>([])
  const yol = (son: "onizleme" | "uygula", d: File, a: Record<string, number>) =>
    `/api/v1/proje/ice-al/${son}${sorguMetni({ dosya: d.name.slice(0, 150), atamalar: Object.keys(a).length ? JSON.stringify(a) : "" })}`
  const onizle = useMutation({
    mutationFn: ({ d, a }: { d: File; a: Record<string, number> }) => yukle<Onizleme>(yol("onizleme", d, a), d, EXCEL, "POST"),
    onSuccess: (veri, { a }) => {
      if (Object.keys(a).length === 0) setEslesmeyen(veri.eslesmeyen)
    },
  })
  const uygula = useMutation({
    mutationFn: (d: File) => yukle<Sonuc>(yol("uygula", d, atamalar), d, EXCEL, "POST"),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["proje"] }),
  })

  function sec(d: File | undefined) {
    onizle.reset()
    uygula.reset()
    setSuz("")
    setUyari("")
    setAtamalar({})
    setEslesmeyen([])
    setDosya(null)
    if (!d) return
    if (d.size > AZAMI_BAYT) return setUyari(t.dosyaBuyuk)
    setDosya(d)
    onizle.mutate({ d, a: {} })
  }

  function ata(anahtar: string, kisi: string) {
    if (!dosya) return
    const yeni = { ...atamalar }
    if (kisi) yeni[anahtar] = Number(kisi)
    else delete yeni[anahtar]
    setAtamalar(yeni)
    onizle.mutate({ d: dosya, a: yeni })
  }

  const o = onizle.data
  const sonuc = uygula.data
  const gorunen = o ? o.satirlar.filter((s) => !suz || s.durum === suz) : []

  return (
    <Cekmece
      acik
      genis
      onKapat={onKapat}
      baslik={t.iceBaslik}
      aciklama={t.iceAciklama}
      kapatEtiketi={t.kapat}
      alt={
        <div className="grid gap-2">
          {uygula.isError ? <Bildirim ton="kirmizi">{hataMesaji(uygula.error, t.eklenemedi)}</Bildirim> : null}
          <div className="flex flex-wrap items-center justify-end gap-2">
            <button type="button" className={DUGME} onClick={onKapat}>
              {t.kapat}
            </button>
            {o && !sonuc ? (
              <button type="button" className={DUGME_SARI} disabled={o.plan.yeni === 0 || uygula.isPending || onizle.isPending || !dosya} onClick={() => dosya && uygula.mutate(dosya)}>
                {uygula.isPending ? t.uygulaniyor : t.uygula(o.plan.yeni)}
              </button>
            ) : null}
          </div>
        </div>
      }
    >
      <div className="grid gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex cursor-pointer items-center justify-center gap-1.5 rounded-xl border border-tl-blue bg-white px-4 py-2 text-xs font-bold text-tl-blue shadow-sm transition-colors hover:bg-tl-blue/5 focus-within:ring-2 focus-within:ring-tl-yellow">
            <Upload aria-hidden className="size-4" />
            {dosya ? t.baskaDosya : t.dosyaSec}
            <input
              type="file"
              accept=".xlsx,.xlsm"
              className="sr-only"
              onChange={(e) => {
                sec(e.target.files?.[0])
                e.target.value = ""
              }}
            />
          </label>
          {dosya ? <span className="min-w-0 break-words text-xs font-bold text-slate-500">{dosya.name}</span> : null}
        </div>

        {uyari ? <Bildirim ton="amber">{uyari}</Bildirim> : null}
        {onizle.isPending && !o ? <Yukleniyor metin={t.okunuyor} /> : null}
        {onizle.isError ? <Bildirim ton="kirmizi">{hataMesaji(onizle.error, t.okunamadi)}</Bildirim> : null}
        {!o && !onizle.isPending && !uyari ? <p className="text-xs font-bold text-slate-500">{t.dosyaKural}</p> : null}

        {sonuc ? (
          <Bildirim ton="yesil">{t.eklendi(sonuc.eklendi, sonuc.toplam - sonuc.eklendi)}</Bildirim>
        ) : o ? (
          <div className="grid gap-3">
            <p className="break-words text-xs font-bold text-slate-500">{t.onizlemeDosya(o.dosya || dosya?.name || "", o.yil)}</p>
            {eslesmeyen.length > 0 ? (
              <Panel baslik={t.eslesmeyenBaslik} aciklama={t.eslesmeyenAciklama}>
                <div className="grid gap-3 md:grid-cols-2">
                  {eslesmeyen.map((e) => (
                    <Alan key={e.anahtar} etiket={t.atanacakKisi(e.ad, e.kayit)}>
                      <select className={GIRDI} value={atamalar[e.anahtar] ?? ""} disabled={onizle.isPending} onChange={(ev) => ata(e.anahtar, ev.target.value)}>
                        <option value="">{t.aktarma}</option>
                        {o.kisiler.map((k) => (
                          <option key={k.id} value={k.id}>
                            {k.ad}
                          </option>
                        ))}
                      </select>
                    </Alan>
                  ))}
                </div>
              </Panel>
            ) : null}
            <div role="group" aria-label={t.satirlar} className="flex flex-wrap gap-2">
              {[{ id: "" as const, ad: t.planToplam, n: o.plan.toplam }, ...DURUMLAR.map((id) => ({ id, ad: t.satirDurum_[id], n: o.plan[id] }))].map((c) => (
                <button
                  key={c.id || "toplam"}
                  type="button"
                  aria-pressed={suz === c.id}
                  disabled={c.n === 0 && c.id !== ""}
                  onClick={() => setSuz(c.id === "" || suz === c.id ? "" : c.id)}
                  className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-black transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-tl-yellow disabled:opacity-50 ${
                    suz === c.id ? "border-tl-navy bg-tl-navy text-tl-yellow" : "border-slate-200 bg-white text-slate-600 hover:border-tl-blue/40 hover:bg-slate-50"
                  }`}
                >
                  {c.ad}
                  <span className="font-mono">{c.n}</span>
                </button>
              ))}
            </div>
            {o.plan.yeni === 0 ? <Bildirim ton="gri">{t.hicYeni}</Bildirim> : null}
            <ol aria-label={t.satirlar} className="grid gap-2">
              {gorunen.map((s) => (
                <li key={`${s.ceyrek}-${s.satir}-${s.kategori}`} className="grid min-w-0 gap-1 rounded-xl border border-slate-200 bg-white p-3 text-xs">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-mono text-[0.6875rem] font-bold text-slate-400">
                      {s.ceyrek} #{s.satir}
                    </span>
                    <Rozet ton={TON[s.durum]}>{t.satirDurum_[s.durum]}</Rozet>
                    <Rozet ton="gri">{t.kategori_[s.kategori]}</Rozet>
                    <span className="font-bold text-slate-500">{s.sahip || s.tam}</span>
                  </div>
                  <p className="break-words font-black text-tl-navy">{s.baslik}</p>
                </li>
              ))}
            </ol>
          </div>
        ) : null}
      </div>
    </Cekmece>
  )
}
