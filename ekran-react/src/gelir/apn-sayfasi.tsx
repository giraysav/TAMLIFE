import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CalendarClock, CircleCheck, Hourglass, PackageCheck, Users, Wallet, Wifi } from "lucide-react"
import { DuzenlenebilirTablo } from "@/components/duzenlenebilir-tablo"
import type { Kolon } from "@/components/duzenlenebilir-tablo"
import { BosKutu, GIRDI, HataKutu, Kpi, Rozet, SayfaKabi, Sekmeler, Yukleniyor } from "@/components/sayfa-ui"
import { gelirMetin } from "@/gelir/gelir-metin"
import { bugunYerel, para, tarih } from "@/lib/bicim"
import { oku, sorguMetni, yaz } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"

type Kurulum = { id: number; musteri: string; apn_adi: string; talep_tarihi: string | null; teslim_tarihi: string | null; tutar: number; tam: string }
type KurulumListe = { items: Kurulum[]; toplam: number; teslim_edilen: number; bekleyen: number }
type Calisma = { id: number; musteri: string; toplanti_konusu: string; toplanti_tarihi: string | null; planli_tarih: string | null; apn_adi: string }
type CalismaListe = { items: Calisma[]; yaklasan: number }
type Sekme = "kurulum" | "calisma"

function Kurulumlar({ dil }: { dil: Dil }) {
  const t = gelirMetin(dil)
  const qc = useQueryClient()
  const buYil = new Date().getFullYear()
  const [yil, setYil] = useState("")
  const liste = useQuery({ queryKey: ["gelir", "apn-kurulum", yil], queryFn: () => oku<KurulumListe>(`/api/v1/gelir/apn/kurulum${sorguMetni({ yil })}`) })
  const adlar = useQuery({ queryKey: ["gelir", "musteri-adlari"], queryFn: () => oku<string[]>("/api/v1/gelir/musteri-adlari"), staleTime: 60_000 })
  const yenile = () => qc.invalidateQueries({ queryKey: ["gelir", "apn-kurulum"] })
  const kaydet = useMutation({
    mutationFn: ({ govde, id }: { govde: Record<string, unknown>; id: number | null }) =>
      yaz(id === null ? "POST" : "PUT", id === null ? "/api/v1/gelir/apn/kurulum" : `/api/v1/gelir/apn/kurulum/${id}`, govde),
    onSuccess: yenile,
  })
  const sil = useMutation({ mutationFn: (id: number) => yaz("DELETE", `/api/v1/gelir/apn/kurulum/${id}`), onSuccess: yenile })
  const kolonlar: Kolon[] = [
    { anahtar: "musteri", baslik: t.musteri, tip: "musteri", zorunlu: true },
    { anahtar: "apn_adi", baslik: t.apnAdi, tip: "metin", zorunlu: true },
    { anahtar: "talep_tarihi", baslik: t.talepTarihi, tip: "tarih", zorunlu: true },
    {
      anahtar: "teslim_tarihi",
      baslik: t.teslimTarihi,
      tip: "tarih",
      goster: (s) => (s.teslim_tarihi ? tarih(String(s.teslim_tarihi)) : <Rozet ton="amber">{t.beklemede}</Rozet>),
    },
    { anahtar: "tutar", baslik: t.gelirTl, tip: "tutar", sag: true },
  ]
  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <Kpi etiket={t.kurToplam} deger={liste.data ? para(liste.data.toplam) : "—"} ikon={Wallet} ton="yesil" />
        <Kpi etiket={t.kurTeslim} deger={liste.data?.teslim_edilen ?? "—"} ikon={PackageCheck} ton="mavi" />
        <Kpi etiket={t.kurBekleyen} deger={liste.data?.bekleyen ?? "—"} ikon={Hourglass} ton="amber" />
      </div>
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-end gap-2">
          <label className="flex items-center gap-2 text-[10px] font-black uppercase tracking-wide text-slate-400">
            {t.yil}
            <select className={`${GIRDI} !w-auto`} value={yil} onChange={(e) => setYil(e.target.value)}>
              <option value="">{t.tumYillar}</option>
              {[buYil, buYil - 1, buYil - 2].map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </label>
        </div>
        {liste.isPending ? (
          <Yukleniyor metin="…" />
        ) : liste.isError || !liste.data ? (
          <HataKutu metin={t.yuklenemedi} tekrar={() => void liste.refetch()} tekrarEtiket={t.tekrar} />
        ) : (
          <DuzenlenebilirTablo
            kolonlar={kolonlar}
            satirlar={liste.data.items}
            metin={t.tablo}
            musteriAdlari={adlar.data}
            bosKutu={<BosKutu ikon={Wifi} baslik={t.kurBos} aciklama={t.kurBosAlt} />}
            onKaydet={async (govde, id) => {
              await kaydet.mutateAsync({ govde, id })
            }}
            onSil={async (id) => {
              await sil.mutateAsync(id)
            }}
          />
        )}
      </div>
    </div>
  )
}

function Calismalar({ dil }: { dil: Dil }) {
  const t = gelirMetin(dil)
  const qc = useQueryClient()
  const liste = useQuery({ queryKey: ["gelir", "apn-calisma"], queryFn: () => oku<CalismaListe>("/api/v1/gelir/apn/calisma") })
  const adlar = useQuery({ queryKey: ["gelir", "musteri-adlari"], queryFn: () => oku<string[]>("/api/v1/gelir/musteri-adlari"), staleTime: 60_000 })
  const yenile = () => qc.invalidateQueries({ queryKey: ["gelir", "apn-calisma"] })
  const kaydet = useMutation({
    mutationFn: ({ govde, id }: { govde: Record<string, unknown>; id: number | null }) =>
      yaz(id === null ? "POST" : "PUT", id === null ? "/api/v1/gelir/apn/calisma" : `/api/v1/gelir/apn/calisma/${id}`, govde),
    onSuccess: yenile,
  })
  const sil = useMutation({ mutationFn: (id: number) => yaz("DELETE", `/api/v1/gelir/apn/calisma/${id}`), onSuccess: yenile })
  const bugun = bugunYerel()
  const kolonlar: Kolon[] = [
    { anahtar: "toplanti_konusu", baslik: t.toplantiKonusu, tip: "metin", zorunlu: true, azami: 300 },
    { anahtar: "toplanti_tarihi", baslik: t.toplantiTarihi, tip: "tarih", zorunlu: true },
    {
      anahtar: "planli_tarih",
      baslik: t.planliTarih,
      tip: "tarih",
      goster: (s) => {
        const d = s.planli_tarih ? String(s.planli_tarih) : null
        if (!d) return "—"
        const ton = d < bugun ? "gri" : d === bugun ? "sari" : "yesil"
        return (
          <Rozet ton={ton}>
            {tarih(d)}
            {d < bugun ? ` · ${t.gecmis}` : d === bugun ? ` · ${t.bugun}` : ""}
          </Rozet>
        )
      },
    },
    { anahtar: "apn_adi", baslik: t.apnAdi, tip: "metin" },
    { anahtar: "musteri", baslik: t.musteriKisa, tip: "musteri", zorunlu: true },
  ]
  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Kpi etiket={t.calYaklasan} deger={liste.data?.yaklasan ?? "—"} ikon={CalendarClock} ton="sari" />
        <Kpi etiket={t.calToplam} deger={liste.data?.items.length ?? "—"} ikon={Users} ton="mavi" />
      </div>
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        {liste.isPending ? (
          <Yukleniyor metin="…" />
        ) : liste.isError || !liste.data ? (
          <HataKutu metin={t.yuklenemedi} tekrar={() => void liste.refetch()} tekrarEtiket={t.tekrar} />
        ) : (
          <DuzenlenebilirTablo
            kolonlar={kolonlar}
            satirlar={liste.data.items}
            metin={t.tablo}
            musteriAdlari={adlar.data}
            bosKutu={<BosKutu ikon={CircleCheck} baslik={t.calBos} aciklama={t.calBosAlt} />}
            onKaydet={async (govde, id) => {
              await kaydet.mutateAsync({ govde, id })
            }}
            onSil={async (id) => {
              await sil.mutateAsync(id)
            }}
          />
        )}
      </div>
    </div>
  )
}

/** APN Gelir ve Kurulum: iki ana baslik (Kurulum, Musteri Calismalari) dugme olarak. */
export function ApnSayfasi({ dil }: { dil: Dil }) {
  const t = gelirMetin(dil)
  const [sekme, setSekme] = useState<Sekme>("kurulum")
  return (
    <div className="grid grid-cols-1 gap-4">
      <SayfaKabi ikon={Wifi} baslik={t.apnBaslik} aciklama={t.apnAciklama} />
      <Sekmeler
        etiket={t.sekmeler}
        deger={sekme}
        onDegis={setSekme}
        secenekler={[
          { id: "kurulum", etiket: t.kurulum, ikon: PackageCheck },
          { id: "calisma", etiket: t.calismalar, ikon: Users },
        ]}
      />
      {sekme === "kurulum" ? <Kurulumlar dil={dil} /> : <Calismalar dil={dil} />}
    </div>
  )
}
