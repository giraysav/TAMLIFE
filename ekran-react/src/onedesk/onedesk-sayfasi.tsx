import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { CircleAlert, Inbox, LifeBuoy, MessageSquareWarning, Siren } from "lucide-react"
import { Halka, Lejant, Sutunlar, YatayCubuklar } from "@/components/grafik"
import { GIRDI } from "@/components/kart-ui"
import { Bildirim, BosKutu, HataKutu, Kpi, Panel, SayfaKabi, Sekmeler, Yukleniyor } from "@/components/sayfa-ui"
import { sayi } from "@/lib/bicim"
import { oku } from "@/lib/sorgu"
import { OneriPaneli, RcaPaneli, Top10Paneli } from "@/onedesk/analiz"
import { KaynakPaneli } from "@/onedesk/kaynak"
import { onedeskMetin } from "@/onedesk/onedesk-metin"
import { turSerileri } from "@/onedesk/tipler"
import type { Durum } from "@/onedesk/tipler"
import type { Dil } from "@/shell/metin"

type Kapsam = "acik" | "kapali"

/**
 * Onedesk: iki ana gorunum (Aktif A/T/S, Yil boyu kapatilan) + yil boyu analiz (Top10, RCA ortak noktalari, cozum tavsiyeleri).
 * Veri admin Veri Girisi hattindan beslenir; admin icin kaynak/aktarim paneli en altta.
 */
export function OnedeskSayfasi({ dil, admin }: { dil: Dil; admin: boolean }) {
  const t = onedeskMetin(dil)
  const buYil = new Date().getFullYear()
  const [kapsam, setKapsam] = useState<Kapsam>("acik")
  const [yil, setYil] = useState(buYil)
  const q = useQuery({ queryKey: ["onedesk", "durum", kapsam, yil], queryFn: () => oku<Durum>(`/api/v1/onedesk/durum?kapsam=${kapsam}&yil=${yil}`) })
  const d = q.data
  const seriler = turSerileri(t)
  const sutunlar =
    d?.kapsam === "kapali"
      ? d.grafik.map((g) => ({ etiket: t.aylar[(g.ay ?? 1) - 1] ?? "", degerler: { alarm: g.alarm, talep: g.talep, sikayet: g.sikayet } }))
      : (d?.grafik ?? []).map((g) => ({ etiket: g.etiket ?? "", degerler: { alarm: g.alarm, talep: g.talep, sikayet: g.sikayet } }))

  return (
    <div className="grid grid-cols-1 gap-4">
      <SayfaKabi ikon={LifeBuoy} baslik={t.baslik} aciklama={t.aciklama}>
        <label className="flex items-center gap-2 text-[10px] font-black uppercase tracking-wide text-white/70">
          {t.yil}
          <select className={`${GIRDI} !w-auto !py-2`} value={yil} onChange={(e) => setYil(Number(e.target.value))}>
            {[buYil, buYil - 1, buYil - 2, buYil - 3].map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
      </SayfaKabi>

      <Sekmeler
        etiket={t.sekmeler}
        deger={kapsam}
        onDegis={setKapsam}
        secenekler={[
          { id: "acik", etiket: t.acik, ikon: Siren, sayi: kapsam === "acik" && d ? sayi(d.toplam.hepsi) : undefined },
          { id: "kapali", etiket: t.kapali, ikon: Inbox, sayi: kapsam === "kapali" && d ? sayi(d.toplam.hepsi) : undefined },
        ]}
      />

      {d?.kaynak.ornek ? <Bildirim ton="amber">{t.ornekUyari}</Bildirim> : null}

      {q.isPending ? (
        <Yukleniyor metin="…" />
      ) : q.isError || !d ? (
        <HataKutu metin={t.yuklenemedi} tekrar={() => void q.refetch()} tekrarEtiket={t.tekrar} />
      ) : d.toplam.hepsi === 0 ? (
        <BosKutu ikon={Inbox} baslik={t.veriYok} aciklama={t.veriYokAlt} />
      ) : (
        <>
          <p className="text-xs font-bold text-slate-500">{kapsam === "acik" ? t.acikAlt : t.kapaliAlt(yil)}</p>
          <div className="grid gap-3 sm:grid-cols-3">
            <Kpi etiket={t.alarm} deger={sayi(d.toplam.alarm)} ikon={Siren} ton="kirmizi" />
            <Kpi etiket={t.talep} deger={sayi(d.toplam.talep)} ikon={CircleAlert} ton="mavi" />
            <Kpi etiket={t.sikayet} deger={sayi(d.toplam.sikayet)} ikon={MessageSquareWarning} ton="amber" />
          </div>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
            <Panel baslik={kapsam === "acik" ? t.yaslanma : t.aylik} aciklama={kapsam === "acik" ? t.yaslanmaAlt : t.aylikAlt} sag={<Lejant seriler={seriler} sayilar={d.toplam} />}>
              <div className="flex flex-wrap items-center gap-6">
                <Halka
                  dilimler={seriler.map((s) => ({ anahtar: s.anahtar, ad: s.ad, deger: d.toplam[s.anahtar as "alarm"], renk: s.renk }))}
                  baslik={sayi(d.toplam.hepsi)}
                  alt={t.toplam}
                />
                <div className="min-w-0 flex-1 basis-56">
                  <Sutunlar sutunlar={sutunlar} seriler={seriler} yukseklik={150} />
                </div>
              </div>
            </Panel>
            <Panel baslik={t.musteriKirilimi} aciklama={t.musteriKirilimiAlt(d.musteri_sayisi)}>
              <div className="max-h-[22rem] overflow-y-auto pr-1">
                <YatayCubuklar satirlar={d.musteriler.slice(0, 25).map((m) => ({ anahtar: m.ad, etiket: m.ad, degerler: { alarm: m.alarm, talep: m.talep, sikayet: m.sikayet }, sag: sayi(m.toplam) }))} seriler={seriler} />
              </div>
            </Panel>
          </div>
        </>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Top10Paneli yil={yil} t={t} />
        <RcaPaneli yil={yil} t={t} />
        <OneriPaneli yil={yil} t={t} />
      </div>

      {admin ? <KaynakPaneli t={t} /> : null}
    </div>
  )
}
