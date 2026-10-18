import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check, RefreshCw } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Alan, Bildirim, Bolum, DUGME, DUGME_ANA, GIRDI, HataKutu, Panel, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import type { AtamaSonucu, SkorAgaci, SkorMusterisi, SkorOnizleme } from "@/yonetim/api"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import { adaGoreSirala, zaman } from "@/lib/bicim"
import { AGAC_YOLU, KaynakListesi, KriterDokumu, TamamRozeti, skorYaz } from "@/yonetim/utilizasyon/ortak"
import { uym } from "@/yonetim/utilizasyon/metin"

/** Toplu atama (uretim skor_toplu onizleme / uygula): sunucu yeniden hesaplar, onizleme yazmaz; uygula yalniz TAMAM olanlara yazar. */
export function TopluAtama({ dil }: { dil: Dil }) {
  const t = uym(dil)
  const u = t.util
  const qc = useQueryClient()
  const [tamId, setTamId] = useState("")
  const [secili, setSecili] = useState<Set<number>>(new Set())
  const [dokum, setDokum] = useState<number | null>(null)
  const [bilgi, setBilgi] = useState<{ ton: "yesil" | "amber"; metin: string } | null>(null)
  const agac = useQuery({ queryKey: ANAHTAR.skorAgac, queryFn: () => oku<SkorAgaci>(AGAC_YOLU) })
  const on = useQuery({
    queryKey: ["skor", "onizleme", tamId],
    queryFn: () => yaz<SkorOnizleme>("POST", "/api/v1/skor/toplu/onizleme", { tam_id: tamId ? Number(tamId) : null }),
  })
  const uygula = useMutation({
    mutationFn: (kimlikler: number[]) => yaz<AtamaSonucu>("POST", "/api/v1/skor/toplu/uygula", { customer_ids: kimlikler }),
    onSuccess: (s) => {
      setSecili(new Set())
      const atlanan = s.atlanan.slice(0, 5).map((a) => `${a.ad || `#${a.id}`}: ${a.neden}`)
      setBilgi({ ton: "yesil", metin: [u.uygulandi(s.uygulanan.length, s.atlanan.length), ...atlanan].join(" · ") })
      for (const anahtar of [["skor", "onizleme"], ANAHTAR.skorAgac, ANAHTAR.skorSiralama, ANAHTAR.skorTalepler]) void qc.invalidateQueries({ queryKey: anahtar })
    },
    onError: (e) => setBilgi({ ton: "amber", metin: hataMesaji(e, t.islemBasarisiz) }),
  })

  const personel = adaGoreSirala(agac.data?.tum_personel ?? [], (p) => p.ad)
  const veri = on.data
  const tamamlar = (veri?.musteriler ?? []).filter((m) => m.tamam).map((m) => m.id)
  const acik = veri?.musteriler.find((m) => m.id === dokum) ?? null
  const sec = (id: number, evet: boolean) =>
    setSecili((once) => {
      const yeni = new Set(once)
      if (evet) yeni.add(id)
      else yeni.delete(id)
      return yeni
    })

  return (
    <div className="grid gap-4">
      <Panel baslik={u.sekme.atama} aciklama={veri ? u.hazirOzet(veri.ozet.hazir, veri.ozet.toplam) : undefined}>
        <div className="grid gap-3">
          <div className="flex flex-wrap items-end gap-2">
            <Alan etiket={u.personel}>
              <select
                className={`${GIRDI} !w-56`}
                value={tamId}
                onChange={(e) => {
                  setTamId(e.target.value)
                  setSecili(new Set())
                  setDokum(null)
                }}
              >
                <option value="">{u.tumPersonel}</option>
                {personel.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.ad}
                  </option>
                ))}
              </select>
            </Alan>
            <button type="button" className={DUGME} onClick={() => void on.refetch()} disabled={on.isFetching}>
              <RefreshCw aria-hidden className={`size-3.5 ${on.isFetching ? "animate-spin motion-reduce:animate-none" : ""}`} />
              {u.hesapla}
            </button>
            <button type="button" className={DUGME} disabled={!tamamlar.length} onClick={() => setSecili(new Set(tamamlar))}>
              <Check aria-hidden className="size-3.5" />
              {u.tamamlariSec}
            </button>
            {secili.size > 0 ? (
              <button type="button" className={DUGME} onClick={() => setSecili(new Set())}>
                {u.secimiTemizle}
              </button>
            ) : null}
            <button
              type="button"
              className={`${DUGME_ANA} ml-auto`}
              disabled={secili.size === 0 || uygula.isPending}
              onClick={() => {
                if (window.confirm(u.uygulaOnay(secili.size))) uygula.mutate([...secili])
              }}
            >
              {u.seciliUygula(secili.size)}
            </button>
          </div>
          {bilgi ? <Bildirim ton={bilgi.ton}>{bilgi.metin}</Bildirim> : null}

          {on.isPending ? (
            <Yukleniyor metin={t.yukleniyor} iskelet />
          ) : on.isError ? (
            <HataKutu metin={hataMesaji(on.error, t.yuklenemedi)} tekrarEtiket={t.tekrar} tekrar={() => void on.refetch()} />
          ) : (
            <VeriTablosu<SkorMusterisi>
              baslik={u.sekme.atama}
              satirlar={on.data.musteriler}
              anahtar={(m) => m.id}
              vurgulu={(m) => m.id === dokum}
              bos={<p className="text-xs font-bold text-slate-400">{u.musteriYok}</p>}
              kolonlar={[
                {
                  baslik: "",
                  // Eksik kriterli satir da secilebilir (eskiden disabled'di: DEV'de hic musteri "Tamam" olmadigindan hicbiri secilemiyordu);
                  // sunucu eksik kriterliyi yazmaz, nedeniyle "atlandi" doner.
                  hucre: (m) => (
                    <input
                      type="checkbox"
                      className="size-4 cursor-pointer accent-tl-navy"
                      aria-label={u.secMusteri(m.ad)}
                      checked={secili.has(m.id)}
                      onChange={(e) => sec(m.id, e.target.checked)}
                    />
                  ),
                  sinif: "w-8",
                },
                {
                  baslik: u.musteri,
                  hucre: (m) => (
                    <button type="button" className="text-left font-black text-tl-navy underline-offset-2 hover:underline" aria-expanded={dokum === m.id} onClick={() => setDokum(dokum === m.id ? null : m.id)}>
                      {m.ad}
                    </button>
                  ),
                },
                { baslik: u.personel, hucre: (m) => m.tam || "—" },
                { baslik: u.mevcut, hucre: (m) => skorYaz(m.mevcut), sinif: "text-right font-mono" },
                { baslik: u.yeni, hucre: (m) => <span className="font-black text-tl-navy">{skorYaz(m.yeni)}</span>, sinif: "text-right font-mono" },
                {
                  baslik: u.fark,
                  hucre: (m) =>
                    m.fark === null ? "—" : <span className={m.fark > 0 ? "text-emerald-600" : m.fark < 0 ? "text-rose-600" : "text-slate-400"}>{m.fark > 0 ? `+${m.fark.toFixed(1)}` : m.fark.toFixed(1)}</span>,
                  sinif: "text-right font-mono",
                },
                { baslik: u.durum, hucre: (m) => <TamamRozeti tamam={m.tamam} eksik={m.eksik} t={t} /> },
                {
                  baslik: u.sonAtama,
                  hucre: (m) =>
                    m.son_atama ? (
                      <span className="text-[0.6875rem] text-slate-500">
                        {u.kaynakAdi[m.son_atama.kaynak] ?? m.son_atama.kaynak} · {m.son_atama.atayan || "—"} · {zaman(m.son_atama.zaman)}
                      </span>
                    ) : (
                      "—"
                    ),
                },
              ]}
            />
          )}
        </div>
      </Panel>

      {acik ? (
        <Panel baslik={u.dokum(acik.ad)}>
          <KriterDokumu kriterler={acik.kriterler} t={t} />
        </Panel>
      ) : null}

      {veri ? (
        <Bolum anahtar="yonetim-util-atama-kaynak" baslik={u.kaynaklar} varsayilanAcik={veri.uyarilar.length > 0}>
          <KaynakListesi kaynaklar={veri.kaynaklar} uyarilar={veri.uyarilar} t={t} />
        </Bolum>
      ) : null}
    </div>
  )
}
