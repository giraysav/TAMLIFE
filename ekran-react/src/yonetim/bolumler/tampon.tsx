import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Database, Diff, FileUp, Link2, Upload, Workflow } from "lucide-react"
import type { Dil } from "@/shell/metin"
import { Bildirim, Bolum, DUGME, HataKutu, Panel, Sekmeler } from "@/components/sayfa-ui"
import type { SekmeSecenegi } from "@/components/sayfa-ui"
import { sorguAyarla, useHashSorgu } from "@/shell/rota"
import { ANAHTAR } from "@/yonetim/api"
import { oku } from "@/lib/sorgu"
import type { Kaynak, PartiAyrintisi } from "@/yonetim/api"
import { IceAktar } from "@/gelir-uretim/ice-aktar"
import { gelirUretimMetin } from "@/gelir-uretim/gelir-uretim-metin"
import { UrunTutarYukleme } from "@/yonetim/utilizasyon/urun-tutar"
import { Analiz } from "@/yonetim/tampon/analiz"
import { GenelCsvYukle } from "@/yonetim/tampon/csv-yukle"
import { Dagitim } from "@/yonetim/tampon/dagitim"
import type { KuralOnerisi } from "@/yonetim/tampon/dagitim"
import { MusteriEslesmesiPanosu } from "@/yonetim/tampon/eslesme"
import { FarkAlani } from "@/yonetim/tampon/fark"
import { VeriAkislariPaneli, useVeriAkislari } from "@/yonetim/tampon/akislar"
import { ReportdbKatalogu } from "@/yonetim/tampon/katalog"
import { Kaynaklar, OracleKaynakKarti } from "@/yonetim/tampon/kaynaklar"
import { HamMusteriBolumu } from "@/yonetim/tampon/musteri-ham"
import { Partiler } from "@/yonetim/tampon/partiler"
import { PgKataloglari } from "@/yonetim/tampon/pg-katalog"
import { Rehber } from "@/yonetim/tampon/rehber"
import { TemipEslesmesi } from "@/yonetim/tampon/temip"
import { tm } from "@/yonetim/tampon/metin"

const YOL = "yonetim/tampon"
const SEKMELER = ["canli", "akis", "import", "eslesme", "fark"] as const
const DBLER = ["reportdb", "onedesk", "onent", "galapagos"] as const
type Sekme = (typeof SEKMELER)[number]
type Db = (typeof DBLER)[number]

/** Veri Girisi (2026-10-24 yeniden duzen, kullanici: "cok karisik ve yonetilmesi zor"). Bes sekme, secim adreste
 *  (#/yonetim/tampon?sekme=akis&parti=12): Canli DB (ReportDB / ONEDESKDB / ONENTDB / GALAPAGOSDB: baglanti + katalog) ·
 *  Veri Akisi (tek hat: kaynaklar -> tampon partiler -> analiz -> TEMIP eslesmesi -> dagitim) · Import (panelin TEK Excel/CSV
 *  giris noktasi; aylik rapor SLA/grafik ekleri simdilik istisna) · Musteri Eslesmesi (her veri TAM'a atanmis karta baglanmali) ·
 *  Fark (eslesmeyen numaralar: tek tek / toplu personele atama). */
export default function Tampon({ dil }: { dil: Dil }) {
  const t = tm(dil)
  const y = t.yapi
  const sorgu = useHashSorgu()
  const seciliId = Number(sorgu.get("parti")) || null
  const ham = sorgu.get("sekme") ?? ""
  const sekme: Sekme = (SEKMELER as readonly string[]).includes(ham) ? (ham as Sekme) : seciliId ? "akis" : "canli"
  const dbHam = sorgu.get("db") ?? ""
  const db: Db = (DBLER as readonly string[]).includes(dbHam) ? (dbHam as Db) : "reportdb"
  const git = (s: Sekme, ek: Record<string, string | null> = {}) => sorguAyarla(YOL, { sekme: s, ...ek })

  const secenekler: SekmeSecenegi<Sekme>[] = [
    { id: "canli", etiket: y.sekme.canli, ikon: Database },
    { id: "akis", etiket: y.sekme.akis, ikon: Workflow },
    { id: "import", etiket: y.sekme.import, ikon: FileUp },
    { id: "eslesme", etiket: y.sekme.eslesme, ikon: Link2 },
    { id: "fark", etiket: y.sekme.fark, ikon: Diff },
  ]
  return (
    <div className="grid gap-4">
      <Sekmeler etiket={y.nav} secenekler={secenekler} deger={sekme} onDegis={(s) => git(s, s === "akis" ? { parti: seciliId ? String(seciliId) : null } : {})} />
      {sekme === "canli" ? (
        <CanliDb dil={dil} db={db} onDb={(d) => git("canli", { db: d })} />
      ) : sekme === "akis" ? (
        <VeriAkisi dil={dil} seciliId={seciliId} onSec={(id) => git("akis", { parti: id ? String(id) : null })} />
      ) : sekme === "import" ? (
        <Import dil={dil} onYeniParti={(id) => git("akis", { parti: String(id) })} />
      ) : sekme === "eslesme" ? (
        <MusteriEslesmesiPanosu dil={dil} />
      ) : (
        <FarkAlani dil={dil} />
      )}
    </div>
  )
}

function CanliDb({ dil, db, onDb }: { dil: Dil; db: Db; onDb: (d: Db) => void }) {
  const y = tm(dil).yapi
  return (
    <div className="grid gap-4">
      <p className="max-w-4xl text-[0.6875rem] font-bold text-slate-500">{y.canliAciklama}</p>
      <Sekmeler etiket={y.canliNav} secenekler={DBLER.map((d) => ({ id: d, etiket: y.db[d] }))} deger={db} onDegis={onDb} />
      {db === "reportdb" ? (
        <>
          <OracleKaynakKarti dil={dil} anahtar="oracle_reportdb" baslik={y.db.reportdb} yokMetni={y.kaynakYok(y.db.reportdb)} />
          <ReportdbKatalogu dil={dil} />
        </>
      ) : db === "galapagos" ? (
        <OracleKaynakKarti dil={dil} anahtar="oracle_galapagos" baslik={y.galapagos} yokMetni={y.kaynakYok(y.db.galapagos)} />
      ) : (
        <PgKataloglari dil={dil} kaynak={db === "onedesk" ? "pg_onedesk" : "pg_onent"} />
      )}
    </div>
  )
}

/** Tek hat: akis ozeti (bayatlik) -> 1 kaynaklar -> 2 tampon partiler -> 3 analiz -> 4 TEMIP eslesmesi -> 5 dagitim; rehber en sonda. */
function VeriAkisi({ dil, seciliId, onSec }: { dil: Dil; seciliId: number | null; onSec: (id: number | null) => void }) {
  const t = tm(dil)
  const y = t.yapi
  const [oneri, setOneri] = useState<KuralOnerisi | null>(null)
  const detay = useQuery({
    queryKey: [...ANAHTAR.parti, seciliId],
    queryFn: () => oku<PartiAyrintisi>(`/api/v1/tampon/partiler/${seciliId}`),
    enabled: seciliId !== null,
    retry: false,
  })
  const kaynaklar = useQuery({ queryKey: ANAHTAR.kaynaklar, queryFn: () => oku<Kaynak[]>("/api/v1/tampon/kaynaklar") })
  const kaynakAnahtarlari = (kaynaklar.data ?? []).filter((k) => k.tur !== "oracle" && k.tur !== "postgres").map((k) => k.anahtar)
  const dagitimOzeti = useVeriAkislari().data?.dagitim
  return (
    <div className="grid gap-4">
      <ol aria-label={y.sekme.akis} className="flex flex-wrap items-center gap-2 text-[0.6875rem] font-black text-tl-navy">
        {y.adimlar.map((a, i) => (
          <li key={a} className="flex items-center gap-2">
            <span className="rounded-lg border border-slate-200 bg-white px-2 py-1 shadow-sm">
              {i + 1} · {a}
            </span>
            {i < y.adimlar.length - 1 ? <span aria-hidden className="text-slate-300">→</span> : null}
          </li>
        ))}
      </ol>
      <p className="max-w-4xl text-[0.6875rem] font-bold text-slate-500">{y.akisAciklama}</p>
      <VeriAkislariPaneli dil={dil} />
      <Kaynaklar dil={dil} />
      <Partiler dil={dil} seciliId={seciliId} onSec={onSec} />
      {seciliId === null ? (
        <Bildirim>{t.partiSecin}</Bildirim>
      ) : detay.isPending ? (
        <Bolum anahtar="yonetim-tampon-analiz" baslik={t.adim.analiz}>
          <p className="text-xs font-bold text-slate-400">{t.yukleniyor}</p>
        </Bolum>
      ) : detay.isError ? (
        <HataKutu metin={t.yuklenemedi} tekrarEtiket={t.tekrar} tekrar={() => void detay.refetch()} />
      ) : (
        <Analiz dil={dil} parti={detay.data} onKuralOner={(o) => setOneri({ ...o, sayac: (oneri?.sayac ?? 0) + 1 })} onSilindi={() => onSec(null)} />
      )}
      <TemipEslesmesi dil={dil} />
      <Dagitim dil={dil} parti={detay.data ?? null} oneri={oneri} kaynakAnahtarlari={kaynakAnahtarlari} kural={dagitimOzeti?.kural} etkin={dagitimOzeti?.etkin} />
      <Rehber dil={dil} />
    </div>
  )
}

/** Panelin TEK Excel/CSV giris noktasi (2026-10-24). Parti olusturan yuklemeler Veri Akisi sekmesine o partiyle gecer. */
function Import({ dil, onYeniParti }: { dil: Dil; onYeniParti: (id: number) => void }) {
  const y = tm(dil).yapi
  const g = gelirUretimMetin(dil)
  const [gelirAcik, setGelirAcik] = useState(false)
  return (
    <div className="grid gap-4">
      <Bildirim>{y.importAciklama}</Bildirim>
      <HamMusteriBolumu dil={dil} onYeniParti={(p) => onYeniParti(p.id)} />
      <GenelCsvYukle dil={dil} onYeniParti={onYeniParti} />
      <Panel baslik={y.gelirFaydasi} aciklama={y.gelirFaydasiAciklama}>
        <button type="button" className={DUGME} onClick={() => setGelirAcik(true)}>
          <Upload aria-hidden className="size-4" />
          {g.excelIceAktar}
        </button>
      </Panel>
      <UrunTutarYukleme dil={dil} baslik={y.urunTutar} />
      {gelirAcik ? <IceAktar dil={dil} onKapat={() => setGelirAcik(false)} /> : null}
    </div>
  )
}
