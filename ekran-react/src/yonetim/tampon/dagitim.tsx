import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Eye, Pencil, Plus, Power, Trash2, Undo2 } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Bildirim, Bolum, DUGME, DUGME_ANA, HataKutu, Rozet, VeriTablosu, Yukleniyor } from "@/components/sayfa-ui"
import { ANAHTAR } from "@/yonetim/api"
import { hataMesaji, oku, yaz } from "@/lib/sorgu"
import type { Katalog, Kural, KuralGovdesi, Onizleme, PartiAyrintisi, Uygulama } from "@/yonetim/api"
import { ym } from "@/yonetim/metin"
import { Gosterge } from "@/yonetim/ui"
import { zaman, sayi } from "@/lib/bicim"
import { BOS_KURAL, KuralFormu } from "@/yonetim/tampon/kural-formu"

export type KuralOnerisi = { kolon: string; alan: string; sayac: number }
type FormDurumu = { id: number | null; govde: KuralGovdesi }

function govdeye(k: Kural): KuralGovdesi {
  return {
    name: k.ad,
    source_key: k.kaynak,
    match_field: k.eslesme_alani,
    key_column: k.anahtar_sutunu,
    target: k.hedef,
    operation: k.islem,
    value_column: k.deger_sutunu,
    conditions: k.kosullar,
    zero_unmatched: k.eslesmeyeni_sifirla,
    max_age_minutes: k.en_buyuk_yas_dk,
  }
}

/** 3. adim: kurallar (sabit hedef katalogu), onizle -> uygula (onayli) -> geri al. Yazan her adim denetim kaydi uretir. */
export function Dagitim({ dil, parti, oneri, kaynakAnahtarlari }: { dil: Dil; parti: PartiAyrintisi | null; oneri: KuralOnerisi | null; kaynakAnahtarlari: string[] }) {
  const t = ym(dil)
  const qc = useQueryClient()
  const kurallar = useQuery({ queryKey: ANAHTAR.kurallar, queryFn: () => oku<Kural[]>("/api/v1/tampon/kurallar") })
  const katalog = useQuery({ queryKey: ANAHTAR.hedefler, queryFn: () => oku<Katalog>("/api/v1/tampon/hedefler"), staleTime: Infinity })
  const gecmis = useQuery({ queryKey: ANAHTAR.uygulamalar, queryFn: () => oku<Uygulama[]>("/api/v1/tampon/uygulamalar") })

  const [form, setForm] = useState<FormDurumu | null>(null)
  const [formHata, setFormHata] = useState("")
  const [onizleme, setOnizleme] = useState<{ kural: Kural; partiId: number; veri: Onizleme } | null>(null)
  const [onay, setOnay] = useState(false)
  const [bilgi, setBilgi] = useState<{ ton: "yesil" | "amber"; metin: string } | null>(null)

  // Analizdeki "bu anahtarla kural olustur" -> form bu anahtarla dolu acilir.
  useEffect(() => {
    if (oneri && parti) {
      setForm({ id: null, govde: { ...BOS_KURAL, source_key: parti.kaynak, match_field: oneri.alan, key_column: oneri.kolon } })
      setFormHata("")
    }
    // yalniz yeni oneri geldiginde (sayac degisince) tetiklenir
  }, [oneri?.sayac]) // eslint-disable-line react-hooks/exhaustive-deps

  // Parti degisince eski onizleme gecersizdir.
  useEffect(() => {
    setOnizleme(null)
    setOnay(false)
  }, [parti?.id])

  const hata = (e: unknown) => setBilgi({ ton: "amber", metin: hataMesaji(e, t.islemBasarisiz) })
  const kuralYenile = () => void qc.invalidateQueries({ queryKey: ANAHTAR.kurallar })

  const kaydet = useMutation({
    mutationFn: (v: { id: number | null; govde: KuralGovdesi }) =>
      v.id === null ? yaz<Kural>("POST", "/api/v1/tampon/kurallar", v.govde) : yaz<Kural>("PUT", `/api/v1/tampon/kurallar/${v.id}`, v.govde),
    onSuccess: () => {
      setForm(null)
      setFormHata("")
      setBilgi({ ton: "yesil", metin: t.kuralKaydedildi })
      kuralYenile()
      void qc.invalidateQueries({ queryKey: ANAHTAR.ozet })
    },
    onError: (e) => setFormHata(hataMesaji(e, t.islemBasarisiz)),
  })
  const etkin = useMutation({
    mutationFn: (v: { id: number; etkin: boolean }) => yaz<Kural>("POST", `/api/v1/tampon/kurallar/${v.id}/etkin`, { etkin: v.etkin }),
    onSuccess: () => {
      kuralYenile()
      void qc.invalidateQueries({ queryKey: ANAHTAR.ozet })
    },
    onError: hata,
  })
  const sil = useMutation({
    mutationFn: (id: number) => yaz<unknown>("DELETE", `/api/v1/tampon/kurallar/${id}`),
    onSuccess: () => {
      kuralYenile()
      setOnizleme(null)
    },
    onError: hata,
  })
  const onizle = useMutation({
    mutationFn: (k: Kural) => yaz<Onizleme>("POST", `/api/v1/tampon/kurallar/${k.id}/onizle`, { parti_id: parti?.id }).then((veri) => ({ kural: k, partiId: parti?.id ?? 0, veri })),
    onSuccess: (s) => {
      setOnizleme(s)
      setOnay(false)
      setBilgi(null)
    },
    onError: (e) => {
      setOnizleme(null)
      hata(e)
    },
  })
  const uygula = useMutation({
    mutationFn: () => yaz<{ yazilan: number }>("POST", `/api/v1/tampon/kurallar/${onizleme?.kural.id}/uygula`, { parti_id: onizleme?.partiId, onay: true }),
    onSuccess: (s) => {
      setBilgi({ ton: "yesil", metin: t.uygulandi(s.yazilan) })
      setOnizleme(null)
      setOnay(false)
      void qc.invalidateQueries({ queryKey: ANAHTAR.uygulamalar })
      void qc.invalidateQueries({ queryKey: ANAHTAR.partiler })
      void qc.invalidateQueries({ queryKey: ANAHTAR.ozet })
    },
    onError: hata,
  })
  const geriAl = useMutation({
    mutationFn: (runId: string) => yaz<{ geri_alinan: number; korunan: number }>("POST", `/api/v1/tampon/uygulamalar/${runId}/geri-al`),
    onSuccess: (s) => {
      setBilgi({ ton: "yesil", metin: t.geriAlindi(s.geri_alinan, s.korunan) })
      void qc.invalidateQueries({ queryKey: ANAHTAR.uygulamalar })
    },
    onError: hata,
  })

  if (kurallar.isPending || katalog.isPending) return <Yukleniyor metin={t.yukleniyor} iskelet />
  if (kurallar.isError || katalog.isError) return <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void kurallar.refetch()} />
  const kat = katalog.data
  // Onizleme anindaki kural kopyasi eskiyebilir (arada etkinlestirilmis olabilir): etkinlik her zaman guncel listeden okunur.
  const onizlemeKuralEtkin = kurallar.data.find((k) => k.id === onizleme?.kural.id)?.etkin ?? false
  const hedefAdi = (anahtar: string) => kat.hedefler.find((h) => h.anahtar === anahtar)?.ad ?? anahtar
  const islemAdi = (anahtar: string) => kat.islemler.find((i) => i.anahtar === anahtar)?.ad ?? anahtar

  function onizlenebilir(k: Kural): string {
    if (!parti) return t.partiSecin
    if (parti.durum !== "ready") return t.partiHazirDegil
    if (parti.kaynak !== k.kaynak) return t.kaynakUyumsuz
    return ""
  }

  return (
    <Bolum anahtar="yonetim-tampon-dagitim" baslik={`${t.adim.dagitim} · ${t.dagitimKurallari}`}>
      <div className="grid gap-4">
        <p className="text-[0.6875rem] font-bold text-slate-400">{t.adimAciklama.dagitim}</p>
        <div>
          <button
            type="button"
            className={DUGME_ANA}
            onClick={() => {
              setFormHata("")
              setForm({ id: null, govde: { ...BOS_KURAL, source_key: parti?.kaynak ?? "" } })
            }}
          >
            <Plus aria-hidden className="size-4" />
            {t.yeniKural}
          </button>
        </div>

        {form ? (
          <KuralFormu
            key={form.id ?? `yeni-${oneri?.sayac ?? 0}-${form.govde.key_column}`}
            dil={dil}
            katalog={kat}
            baslangic={form.govde}
            duzenleme={form.id !== null}
            kaynakAnahtarlari={kaynakAnahtarlari}
            sutunlar={parti && parti.kaynak === form.govde.source_key ? parti.sutunlar : []}
            hata={formHata}
            kaydediliyor={kaydet.isPending}
            onKaydet={(govde) => kaydet.mutate({ id: form.id, govde })}
            onVazgec={() => setForm(null)}
          />
        ) : null}
        {bilgi ? <Bildirim ton={bilgi.ton}>{bilgi.metin}</Bildirim> : null}

        <VeriTablosu<Kural>
          baslik={t.dagitimKurallari}
          satirlar={kurallar.data}
          anahtar={(k) => k.id}
          vurgulu={(k) => k.id === onizleme?.kural.id}
          bos={<p className="text-xs font-bold text-slate-400">{t.kuralYok}</p>}
          kolonlar={[
            { baslik: t.kuralAdi, hucre: (k) => <span className="font-black text-tl-navy">{k.ad}</span> },
            { baslik: t.hedef, hucre: (k) => hedefAdi(k.hedef) },
            { baslik: t.islem, hucre: (k) => islemAdi(k.islem) },
            { baslik: t.anahtarSutunu, hucre: (k) => `${k.anahtar_sutunu} → ${t.alanAdi[k.eslesme_alani] ?? k.eslesme_alani}` },
            { baslik: t.kaynaklar, hucre: (k) => <code className="text-[0.6875rem]">{k.kaynak}</code> },
            {
              baslik: t.durum,
              hucre: (k) => (
                <button
                  type="button"
                  className={DUGME}
                  disabled={etkin.isPending}
                  aria-pressed={k.etkin}
                  onClick={() => {
                    if (!k.etkin && !window.confirm(t.etkinOnay(k.ad))) return
                    etkin.mutate({ id: k.id, etkin: !k.etkin })
                  }}
                >
                  <Power aria-hidden className="size-3.5" />
                  <Rozet ton={k.etkin ? "yesil" : "gri"}>{k.etkin ? t.kuralEtkin : t.kuralKapali}</Rozet>
                </button>
              ),
            },
            {
              baslik: "",
              hucre: (k) => {
                const engel = onizlenebilir(k)
                return (
                  <span className="flex flex-wrap gap-1.5">
                    <button type="button" className={DUGME} disabled={engel !== "" || onizle.isPending} title={engel || undefined} onClick={() => onizle.mutate(k)}>
                      <Eye aria-hidden className="size-3.5" />
                      {onizle.isPending && onizle.variables?.id === k.id ? t.onizleniyor : t.onizle}
                    </button>
                    <button
                      type="button"
                      className={DUGME}
                      aria-label={`${t.duzenle}: ${k.ad}`}
                      onClick={() => {
                        setFormHata("")
                        setForm({ id: k.id, govde: govdeye(k) })
                      }}
                    >
                      <Pencil aria-hidden className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      className={DUGME}
                      aria-label={`${t.sil}: ${k.ad}`}
                      disabled={sil.isPending}
                      onClick={() => {
                        if (window.confirm(t.kuralSilOnay(k.ad))) sil.mutate(k.id)
                      }}
                    >
                      <Trash2 aria-hidden className="size-3.5" />
                    </button>
                  </span>
                )
              },
            },
          ]}
        />

        {onizleme ? (
          <section aria-label={t.onizlemeBaslik} className="grid gap-3 rounded-xl border border-tl-blue/40 bg-white p-4 shadow-sm">
            <h4 className="text-[0.6875rem] font-black uppercase tracking-widest text-tl-navy">
              {t.onizlemeBaslik} · {onizleme.kural.ad} · #{onizleme.partiId}
            </h4>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Gosterge etiket={t.ozetKart.eslesen} deger={sayi(onizleme.veri.eslesen_musteri)} />
              <Gosterge etiket={t.ozetKart.degisecek} deger={sayi(onizleme.veri.degisecek)} ton={onizleme.veri.degisecek > 0 ? "uyari" : "ok"} alt={onizleme.veri.sifirlanacak ? `${t.ozetKart.sifirlanacak}: ${onizleme.veri.sifirlanacak}` : undefined} />
              <Gosterge etiket={t.ozetKart.degismeyen} deger={sayi(onizleme.veri.degismeyen)} />
              <Gosterge etiket={t.ozetKart.eslesmeyen} deger={sayi(onizleme.veri.eslesmeyen_satir)} alt={`${t.ozetKart.belirsiz}: ${onizleme.veri.belirsiz_satir} · ${t.ozetKart.kosulDisi}: ${onizleme.veri.kosul_disi}`} />
            </div>
            {onizleme.veri.uyarilar.map((u) => (
              <Bildirim key={u} ton="amber">
                {u}
              </Bildirim>
            ))}
            <VeriTablosu<Onizleme["ornek"][number]>
              baslik={t.onizlemeBaslik}
              satirlar={onizleme.veri.ornek}
              anahtar={(o) => o.musteri_id}
              bos={<p className="text-xs font-bold text-slate-400">{t.kayitYok}</p>}
              kolonlar={[
                { baslik: t.musteri, hucre: (o) => <span className="font-black text-tl-navy">{o.ad}</span> },
                { baslik: t.eski, hucre: (o) => String(o.eski ?? "—"), sinif: "text-right font-mono" },
                { baslik: t.yeni, hucre: (o) => <span className="font-mono font-black text-tl-blue">{String(o.yeni ?? "—")}</span>, sinif: "text-right" },
                { baslik: "", hucre: (o) => (o.sifirlama ? <Rozet ton="amber">{t.sifirlama}</Rozet> : null) },
              ]}
            />
            {onizleme.veri.degisecek > 0 ? (
              <div className="grid gap-2 border-t border-slate-100 pt-3">
                {!onizlemeKuralEtkin ? <Bildirim ton="amber">{t.kuralKapaliIpucu}</Bildirim> : null}
                <label className="flex items-start gap-2 text-xs font-bold text-slate-700">
                  <input type="checkbox" className="mt-0.5" checked={onay} onChange={(e) => setOnay(e.target.checked)} />
                  {t.uygulamaOnay}
                </label>
                <button type="button" className={`${DUGME_ANA} justify-self-start`} disabled={!onay || !onizlemeKuralEtkin || uygula.isPending} onClick={() => uygula.mutate()}>
                  {uygula.isPending ? t.uygulaniyor : t.uygula}
                </button>
              </div>
            ) : null}
          </section>
        ) : null}

        <div className="grid gap-2">
          <h4 className="text-[0.6875rem] font-black uppercase tracking-widest text-tl-navy">{t.uygulamaGecmisi}</h4>
          {gecmis.isPending ? (
            <Yukleniyor metin={t.yukleniyor} iskelet />
          ) : gecmis.isError ? (
            <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void gecmis.refetch()} />
          ) : (
            <VeriTablosu<Uygulama>
              baslik={t.uygulamaGecmisi}
              satirlar={gecmis.data}
              anahtar={(u) => u.run_id}
              bos={<p className="text-xs font-bold text-slate-400">{t.gecmisYok}</p>}
              kolonlar={[
                { baslik: t.zaman, hucre: (u) => <span className="whitespace-nowrap">{zaman(u.zaman)}</span> },
                { baslik: t.kuralAdi, hucre: (u) => u.kural },
                { baslik: t.hedef, hucre: (u) => u.hedef_adi },
                { baslik: "#", hucre: (u) => `#${u.parti_id}`, sinif: "font-mono" },
                { baslik: t.kullanici, hucre: (u) => u.kullanici },
                { baslik: t.yazilan, hucre: (u) => sayi(u.yazilan), sinif: "text-right font-mono" },
                { baslik: t.geriAlinan, hucre: (u) => sayi(u.geri_alinan), sinif: "text-right font-mono" },
                {
                  baslik: "",
                  hucre: (u) => (
                    <button
                      type="button"
                      className={DUGME}
                      disabled={geriAl.isPending || u.geri_alinan >= u.yazilan}
                      onClick={() => {
                        if (window.confirm(t.geriAlOnay)) geriAl.mutate(u.run_id)
                      }}
                    >
                      <Undo2 aria-hidden className="size-3.5" />
                      {t.geriAl}
                    </button>
                  ),
                },
              ]}
            />
          )}
        </div>
      </div>
    </Bolum>
  )
}
