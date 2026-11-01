import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Upload } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Alan, Bildirim, Bos, DUGME_ANA, GIRDI, HataKutu, Panel, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import type { SkorAgaci, UrunTutarKaydi, UrunTutarOzeti, UrunTutarYukleme } from "@/yonetim/api"
import { hataMesaji, oku, sorguMetni, yukle } from "@/lib/sorgu"
import { para, zaman } from "@/lib/bicim"
import { AGAC_YOLU, tumCatilar } from "@/yonetim/utilizasyon/ortak"
import { uym } from "@/yonetim/utilizasyon/metin"
import type { UYM } from "@/yonetim/utilizasyon/metin"

const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

/** Ozet sutunlari (yukleme sonucu ve kayitli ozetler ayni bicimde). */
function ozetKolonlari<T extends UrunTutarOzeti & { ad: string }>(t: UYM) {
  const u = t.util
  return [
    { baslik: u.musteri, hucre: (o: T) => <span className="font-black text-tl-navy">{o.ad}</span> },
    { baslik: u.aktifSatir, hucre: (o: T) => `${o.aktif_satir} / ${o.satir}`, sinif: "text-right font-mono" },
    { baslik: u.lokasyon, hucre: (o: T) => o.lokasyon_sayisi, sinif: "text-right font-mono" },
    { baslik: u.devre, hucre: (o: T) => o.devre_sayisi, sinif: "text-right font-mono" },
    { baslik: u.fatura, hucre: (o: T) => para(o.fatura_bedeli), sinif: "whitespace-nowrap text-right font-mono" },
    { baslik: u.servisler, hucre: (o: T) => o.servisler.join(", ") || "—" },
    { baslik: u.baglanti, hucre: (o: T) => o.baglanti.join(", ") || "—" },
    { baslik: u.eslesmeyen, hucre: (o: T) => <span className="text-amber-700">{o.eslesmeyen_gruplar.join(", ") || "—"}</span> },
  ]
}

/** Urun-Tutar Excel yukleme (uretim Musteri Karti > Veri Al > Urun-Tutar): secilen musterinin ailesine eslenir, ozet skora kaynak olur.
 *  2026-10-24: yalniz Veri Girisi > Import'ta (panelin tek Excel giris noktasi); Utilizasyon sekmesi kayitli ozetleri listeler. */
export function UrunTutarYukleme({ dil, baslik }: { dil: Dil; baslik?: string }) {
  const t = uym(dil)
  const u = t.util
  const qc = useQueryClient()
  const girdi = useRef<HTMLInputElement>(null)
  const [musteri, setMusteri] = useState("")
  const [dosya, setDosya] = useState<File | null>(null)
  const [sonuc, setSonuc] = useState<UrunTutarYukleme | null>(null)
  const [hata, setHata] = useState("")
  const agac = useQuery({ queryKey: ANAHTAR.skorAgac, queryFn: () => oku<SkorAgaci>(AGAC_YOLU) })
  const gonder = useMutation({
    mutationFn: (v: { id: string; dosya: File }) => yukle<UrunTutarYukleme>(`/api/v1/skor/urun-tutar/${v.id}${sorguMetni({ dosya: v.dosya.name })}`, v.dosya, XLSX),
    onSuccess: (s) => {
      setSonuc(s)
      setHata("")
      setDosya(null)
      if (girdi.current) girdi.current.value = ""
      for (const anahtar of [ANAHTAR.skorUrunTutar, ANAHTAR.skorAgac, ANAHTAR.iceAktarmalar, ["skor", "onizleme"]]) void qc.invalidateQueries({ queryKey: anahtar })
    },
    onError: (e) => {
      setSonuc(null)
      setHata(hataMesaji(e, t.islemBasarisiz))
    },
  })
  const catilar = agac.data ? tumCatilar(agac.data) : []

  return (
    <Panel baslik={baslik ?? u.sekme.veri} aciklama={u.urunTutarAciklama}>
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            if (musteri && dosya) gonder.mutate({ id: musteri, dosya })
          }}
        >
          <Alan etiket={u.musteriSec}>
            <select className={`${GIRDI} !w-72`} value={musteri} onChange={(e) => setMusteri(e.target.value)} required>
              <option value="">{t.secin}</option>
              {catilar.map((c) => [
                <option key={c.id} value={c.id}>
                  {c.ad}
                </option>,
                ...c.istirakler.map((i) => (
                  <option key={i.id} value={i.id}>
                    {`  — ${i.ad}`}
                  </option>
                )),
              ])}
            </select>
          </Alan>
          <Alan etiket={u.excelDosyasi}>
            <input
              ref={girdi}
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              className={`${GIRDI} max-w-72`}
              onChange={(e) => setDosya(e.target.files?.[0] ?? null)}
            />
          </Alan>
          <button type="submit" className={DUGME_ANA} disabled={!musteri || !dosya || gonder.isPending}>
            <Upload aria-hidden className="size-4" />
            {gonder.isPending ? u.yukleniyorDosya : u.yukle}
          </button>
        </form>
        {hata ? (
          <div className="mt-3">
            <Bildirim ton="amber">{hata}</Bildirim>
          </div>
        ) : null}
        {sonuc ? (
          <div className="mt-3 grid gap-3">
            <Bildirim ton="yesil">{u.yuklendi(sonuc.eslesen, sonuc.kart_musterisine)}</Bildirim>
            <p className="text-[0.6875rem] font-bold text-slate-500">
              {u.kartNo(sonuc.kart_musteri_no)} · {u.dosyadaki(sonuc.dosyadaki_adet)}: {sonuc.dosyadaki.map((d) => `${d.ad || "—"} (${d.musteri_no || "—"}, ${d.satir})`).join(" · ")}
            </p>
            <VeriTablosu baslik={u.yuklenenler} satirlar={sonuc.musteriler} anahtar={(o) => o.id} kolonlar={ozetKolonlari(t)} />
          </div>
        ) : null}
    </Panel>
  )
}

/** Utilizasyon > Urun-Tutar: kayitli ozetler. Yukleme Veri Girisi > Import'a tasindi (2026-10-24); buradan oraya baglanti. */
export function UrunTutar({ dil }: { dil: Dil }) {
  const t = uym(dil)
  const u = t.util
  const liste = useQuery({ queryKey: ANAHTAR.skorUrunTutar, queryFn: () => oku<UrunTutarKaydi[]>("/api/v1/skor/urun-tutar") })
  return (
    <div className="grid gap-4">
      <Bildirim>
        {u.yuklemeTasindi}{" "}
        <a href="#/yonetim/tampon?sekme=import" className="font-black text-tl-blue underline-offset-2 hover:underline">
          {u.importaGit}
        </a>
      </Bildirim>
      <Panel baslik={u.yuklenenler}>
        {liste.isPending ? (
          <Yukleniyor metin={t.yukleniyor} />
        ) : liste.isError ? (
          <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void liste.refetch()} />
        ) : (
          <VeriTablosu<UrunTutarKaydi>
            baslik={u.yuklenenler}
            satirlar={liste.data}
            anahtar={(o) => o.id}
            bos={<Bos>{u.yuklenenYok}</Bos>}
            kolonlar={[
              ...ozetKolonlari<UrunTutarKaydi>(t),
              { baslik: u.dosya, hucre: (o) => o.dosya || "—" },
              { baslik: u.yukleyen, hucre: (o) => o.yukleyen || "—" },
              { baslik: t.zaman, hucre: (o) => zaman(o.zaman) },
            ]}
          />
        )}
      </Panel>
    </div>
  )
}
