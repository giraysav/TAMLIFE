import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Download, Eye, FileSpreadsheet, Undo2, Upload } from "lucide-react"
import { Alan, Bildirim, DUGME, DUGME_ANA, DUGME_SARI, GIRDI, Rozet, VeriTablosu } from "@/components/sayfa-ui"
import { apiYolu } from "@/lib/http"
import { hataMesaji, oku, sorguMetni, yaz, yukle } from "@/lib/sorgu"
import { zaman } from "@/lib/bicim"
import { ANAHTAR } from "@/yonetim/api"
import type { HamAktarim, HamGeriAl, HamOnizleme, HamSatir, HamUyum, Parti } from "@/yonetim/api"
import type { YM } from "@/yonetim/metin"

const TABAN = "/api/v1/tampon/musteri-ham"
type Yuklenen = Parti & { uyum: HamUyum }
type Bilgi = { ton: "yesil" | "amber"; metin: string }
const DURUM_TON = { guncelle: "sari", yeni: "yesil", hata: "kirmizi", degisiklik_yok: "gri" } as const

/** Dosyanin katalogla eslesmesi: bicim, eslesen alan sayisi, eslesen / taninmayan sutunlar. */
function UyumKarti({ u, t }: { u: HamUyum; t: YM }) {
  const h = t.ham
  return (
    <div className="grid gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-black text-tl-navy">{h.tanima}</span>
        <Rozet ton={u.uyumlu ? "yesil" : "kirmizi"}>{h.bicim[u.bicim] ?? u.bicim}</Rozet>
        <span className="font-bold text-slate-500">{h.eslesen(u.eslesen, u.toplam)}</span>
      </div>
      {u.zorunlu_eksik.length ? (
        <p className="font-bold text-rose-700">
          {h.zorunluEksik}: {u.zorunlu_eksik.join(", ")}
        </p>
      ) : null}
      {u.alanlar.length ? (
        <p className="text-slate-600">
          <span className="font-bold">{h.eslesenSutunlar}: </span>
          {u.alanlar.map((a) => (a.sutun === a.alan ? a.alan : `${a.sutun} → ${a.alan}`)).join(" · ")}
        </p>
      ) : null}
      {u.fazla.length ? (
        <p className="text-slate-500">
          <span className="font-bold">{h.fazla}: </span>
          {u.fazla.join(", ")}
        </p>
      ) : null}
    </div>
  )
}

function Degisiklikler({ s }: { s: HamSatir }) {
  return (
    <span className="grid gap-0.5">
      {s.degisiklikler.map((d) => (
        <span key={d.alan}>
          <span className="font-black text-tl-navy">{d.baslik}:</span> <span className="text-slate-400 line-through">{String(d.eski || "—")}</span> →{" "}
          <span className="font-bold">{String(d.yeni)}</span>
        </span>
      ))}
      {s.hatalar.map((x) => (
        <span key={x} className="font-bold text-rose-700">
          {x}
        </span>
      ))}
      {s.uyarilar.map((x) => (
        <span key={x} className="text-amber-700">
          {x}
        </span>
      ))}
    </span>
  )
}

/** Kaynaklar'daki dosya yuklemesi: Ham Musteri Verisi -> tanima -> onizleme -> onayli kartlara yazma -> gecmis / geri alma. */
export function HamMusteriVerisi({ t, sonParti, onYeniParti }: { t: YM; sonParti: { id: number; durum: string } | null; onYeniParti: (p: Parti) => void }) {
  const h = t.ham
  const qc = useQueryClient()
  const girdi = useRef<HTMLInputElement>(null)
  const [dosya, setDosya] = useState<File | null>(null)
  const [yuklenen, setYuklenen] = useState<Yuklenen | null>(null)
  const [yeniOlustur, setYeniOlustur] = useState(false)
  const [onizleme, setOnizleme] = useState<HamOnizleme | null>(null)
  const [bilgi, setBilgi] = useState<Bilgi | null>(null)
  const partiId = yuklenen?.id ?? (sonParti && ["ready", "rejected"].includes(sonParti.durum) ? sonParti.id : null)
  const gecmis = useQuery({ queryKey: ANAHTAR.hamAktarimlar, queryFn: () => oku<HamAktarim[]>(`${TABAN}/aktarimlar`) })

  const yenile = () => {
    for (const k of [ANAHTAR.kaynaklar, ANAHTAR.partiler, ANAHTAR.ozet, ANAHTAR.hamAktarimlar]) void qc.invalidateQueries({ queryKey: k })
    void qc.invalidateQueries({ queryKey: ["musteri"] })
  }
  const hata = (e: unknown) => setBilgi({ ton: "amber", metin: hataMesaji(e, t.islemBasarisiz) })

  const yukleMut = useMutation({
    mutationFn: (d: File) => yukle<Yuklenen>(`${TABAN}/yukle${sorguMetni({ dosya: d.name })}`, d, "application/octet-stream"),
    onSuccess: (p) => {
      setYuklenen(p)
      setOnizleme(null)
      setYeniOlustur(p.uyum.bicim === "genis")
      setDosya(null)
      if (girdi.current) girdi.current.value = ""
      setBilgi(p.durum === "rejected" ? { ton: "amber", metin: t.yuklemeReddedildi } : { ton: "yesil", metin: h.yuklendi(p.satir) })
      yenile()
      onYeniParti(p)
    },
    onError: (e) => {
      yenile()
      hata(e)
    },
  })
  const onizleMut = useMutation({
    mutationFn: (id: number) => yaz<HamOnizleme>("POST", `${TABAN}/onizle`, { parti_id: id, yeni_olustur: yeniOlustur }),
    onSuccess: (o) => {
      setOnizleme(o)
      setBilgi(null)
    },
    onError: hata,
  })
  const uygulaMut = useMutation({
    mutationFn: (o: HamOnizleme) =>
      yaz<{ kayit_id: number; ozet: { guncellenen: number; olusturulan: number } }>("POST", `${TABAN}/uygula`, {
        parti_id: o.parti_id,
        yeni_olustur: o.ozet.yeni_olustur,
        plan_ozeti: o.plan_ozeti,
        onay: true,
      }),
    onSuccess: (s) => {
      setOnizleme(null)
      setBilgi({ ton: "yesil", metin: h.uygulandi(s.ozet.guncellenen, s.ozet.olusturulan) })
      yenile()
    },
    onError: hata,
  })
  const geriAlMut = useMutation({
    mutationFn: (id: number) => yaz<HamGeriAl>("POST", `${TABAN}/aktarimlar/${id}/geri-al`),
    onSuccess: (s) => {
      setOnizleme(null)
      setBilgi({ ton: "yesil", metin: h.geriAlindi(s.geri_alinan_alan, s.silinen_musteri) })
      yenile()
    },
    onError: hata,
  })

  const o = onizleme
  return (
    <div className="grid gap-3 rounded-xl border border-tl-blue/20 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="grid gap-1">
          <span className="flex items-center gap-2 text-sm font-black text-tl-navy">
            <FileSpreadsheet aria-hidden className="size-4" />
            {h.baslik}
          </span>
          <p className="max-w-3xl text-[0.6875rem] font-bold text-slate-500">{h.aciklama}</p>
        </div>
        <span className="flex flex-wrap gap-2">
          <a className={DUGME} href={apiYolu(`${TABAN}/sablon.xlsx`)} download>
            <Download aria-hidden className="size-3.5" />
            {h.bosSablon}
          </a>
          <a className={DUGME} href={apiYolu(`${TABAN}/sablon.xlsx?dolu=true`)} download>
            <Download aria-hidden className="size-3.5" />
            {h.doluSablon}
          </a>
        </span>
      </div>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault()
          setBilgi(null)
          if (dosya) yukleMut.mutate(dosya)
        }}
      >
        <Alan etiket={h.dosya}>
          <input
            ref={girdi}
            type="file"
            accept=".xlsx,.csv,.txt,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
            className={`${GIRDI} max-w-80`}
            onChange={(e) => setDosya(e.target.files?.[0] ?? null)}
          />
        </Alan>
        <button type="submit" className={DUGME_ANA} disabled={!dosya || yukleMut.isPending}>
          <Upload aria-hidden className="size-4" />
          {yukleMut.isPending ? t.yukleniyorDosya : h.yukle}
        </button>
      </form>
      {bilgi ? <Bildirim ton={bilgi.ton}>{bilgi.metin}</Bildirim> : null}
      {yuklenen ? <UyumKarti u={yuklenen.uyum} t={t} /> : null}

      {partiId === null ? (
        <p className="text-xs font-bold text-slate-400">{h.partiYok}</p>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-xs font-black text-slate-500">{h.parti(partiId, yuklenen?.etiket ?? "")}</span>
          <label className="flex cursor-pointer items-center gap-2 text-xs font-bold text-slate-600" title={h.yeniOlusturNot}>
            <input type="checkbox" className="size-4 accent-tl-navy" checked={yeniOlustur} onChange={(e) => setYeniOlustur(e.target.checked)} />
            {h.yeniOlustur}
          </label>
          <button type="button" className={DUGME} disabled={onizleMut.isPending} onClick={() => onizleMut.mutate(partiId)}>
            <Eye aria-hidden className="size-3.5" />
            {onizleMut.isPending ? h.onizleniyor : h.onizle}
          </button>
        </div>
      )}

      {o ? (
        <div className="grid gap-3">
          {!yuklenen ? <UyumKarti u={o.uyum} t={t} /> : null}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {(["guncelle", "yeni", "hata", "degisiklik_yok"] as const).map((k) => (
              <Rozet key={k} ton={DURUM_TON[k]}>
                {h.ozet[k]}: {o.ozet[k]}
              </Rozet>
            ))}
            <button
              type="button"
              className={`${DUGME_SARI} ml-auto`}
              disabled={o.ozet.uygulanacak === 0 || uygulaMut.isPending}
              onClick={() => {
                if (window.confirm(h.uygulaOnay(o.ozet.uygulanacak))) uygulaMut.mutate(o)
              }}
            >
              {h.uygula(o.ozet.uygulanacak)}
            </button>
          </div>
          {o.ozet.tanimsiz_sutunlar.length ? (
            <p className="text-[0.6875rem] text-slate-500">
              <span className="font-bold">{h.tanimsiz}: </span>
              {o.ozet.tanimsiz_sutunlar.join(", ")}
            </p>
          ) : null}
          <VeriTablosu<HamSatir>
            baslik={h.baslik}
            satirlar={o.satirlar}
            anahtar={(s) => `${s.sira}-${s.unvan}`}
            kolonlar={[
              { baslik: h.satirNo, hucre: (s) => s.sira, sinif: "text-right" },
              { baslik: h.unvan, hucre: (s) => <span className="font-black text-tl-navy">{s.unvan || "—"}</span> },
              { baslik: h.durum, hucre: (s) => <Rozet ton={DURUM_TON[s.durum]}>{h.ozet[s.durum]}</Rozet> },
              { baslik: h.degisiklik, hucre: (s) => <Degisiklikler s={s} /> },
            ]}
          />
          {o.kesildi ? <p className="text-[0.6875rem] text-slate-400">{h.kesildi(o.kesildi)}</p> : null}
        </div>
      ) : null}

      <div className="grid gap-2">
        <span className="text-xs font-black text-tl-navy">{h.aktarimlar}</span>
        <VeriTablosu<HamAktarim>
          baslik={h.aktarimlar}
          satirlar={gecmis.data ?? []}
          anahtar={(k) => k.id}
          bos={<p className="text-xs font-bold text-slate-400">{h.aktarimYok}</p>}
          kolonlar={[
            { baslik: h.zaman, hucre: (k) => <span className="whitespace-nowrap">{zaman(k.zaman)}</span> },
            { baslik: h.kullanici, hucre: (k) => k.kullanici },
            { baslik: h.durum, hucre: (k) => h.sonuc(k.guncellenen, k.olusturulan) },
            {
              baslik: "",
              hucre: (k) =>
                k.geri_alinan ? (
                  <Rozet>{h.geriAlinmis}</Rozet>
                ) : (
                  <button
                    type="button"
                    className={DUGME}
                    disabled={geriAlMut.isPending}
                    onClick={() => {
                      if (window.confirm(h.geriAlOnay)) geriAlMut.mutate(k.id)
                    }}
                  >
                    <Undo2 aria-hidden className="size-3.5" />
                    {h.geriAl}
                  </button>
                ),
            },
          ]}
        />
      </div>
    </div>
  )
}
