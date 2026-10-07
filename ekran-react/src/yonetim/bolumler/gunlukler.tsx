import { useState } from "react"
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Download } from "lucide-react"
import { apiYolu } from "@/lib/http"
import type { Dil } from "@/shell/metin"
import { Bolum, DUGME, DUGME_ANA, GIRDI, Rozet } from "@/components/kart-ui"
import { useHashSorgu } from "@/shell/rota"
import { ANAHTAR, hataMesaji, oku, sorguMetni, yaz } from "@/yonetim/api"
import type { GunlukDosyasi, Olay, Oturum, Sayfali } from "@/yonetim/api"
import { useGecikmeli } from "@/yonetim/kanca"
import { ym } from "@/yonetim/metin"
import { Alan, Bilgi, HataKutusu, Sayfalama, VeriTablosu, Yukleniyor, sureYaz, zamanYaz } from "@/yonetim/ui"

const ADET = 25

function Denetim({ dil }: { dil: Dil }) {
  const t = ym(dil)
  const [f, setF] = useState({ olay: "", sonuc: "", kullanici: "", q: "", bas: "", bit: "" })
  const [sayfa, setSayfa] = useState(1)
  const gecikmeli = useGecikmeli(f)
  const sorgu = { ...gecikmeli, sayfa, adet: ADET }
  const q = useQuery({
    queryKey: [...ANAHTAR.gunlukler, sorgu],
    queryFn: () => oku<Sayfali<Olay>>(`/api/v1/yonetim/gunlukler${sorguMetni(sorgu)}`),
    placeholderData: keepPreviousData,
  })
  const ayarla = (alan: keyof typeof f, deger: string) => {
    setF((o) => ({ ...o, [alan]: deger }))
    setSayfa(1)
  }
  const csv = apiYolu(`/api/v1/yonetim/gunlukler.csv${sorguMetni(gecikmeli)}`)

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <Alan etiket={t.olay}>
          <input className={GIRDI} placeholder={t.olayOnEki} value={f.olay} onChange={(e) => ayarla("olay", e.target.value)} />
        </Alan>
        <Alan etiket={t.sonuc}>
          <select className={GIRDI} value={f.sonuc} onChange={(e) => ayarla("sonuc", e.target.value)}>
            <option value="">{t.hepsi}</option>
            <option value="allow">{t.sonucEtiket.allow}</option>
            <option value="deny">{t.sonucEtiket.deny}</option>
          </select>
        </Alan>
        <Alan etiket={t.kullanici}>
          <input className={GIRDI} value={f.kullanici} onChange={(e) => ayarla("kullanici", e.target.value)} />
        </Alan>
        <Alan etiket={t.baslangic}>
          <input type="date" className={GIRDI} value={f.bas} onChange={(e) => ayarla("bas", e.target.value)} />
        </Alan>
        <Alan etiket={t.bitis}>
          <input type="date" className={GIRDI} value={f.bit} onChange={(e) => ayarla("bit", e.target.value)} />
        </Alan>
        <Alan etiket={t.ara} sinif="min-w-48 flex-1">
          <input className={GIRDI} placeholder={t.ayrintidaAra} value={f.q} onChange={(e) => ayarla("q", e.target.value)} />
        </Alan>
        <a className={DUGME} href={csv} download="gunlukler.csv">
          <Download aria-hidden className="size-3.5" />
          {t.csvIndir}
        </a>
      </div>
      {q.isPending ? (
        <Yukleniyor t={t} />
      ) : q.isError ? (
        <HataKutusu t={t} onTekrar={() => void q.refetch()} />
      ) : (
        <div className={`grid gap-3 ${q.isPlaceholderData ? "opacity-70" : ""}`}>
          <VeriTablosu<Olay>
            baslik={t.denetim}
            satirlar={q.data.satirlar}
            anahtar={(o) => o.id}
            bos={<p className="text-xs font-bold text-slate-400">{t.kayitYok}</p>}
            kolonlar={[
              { baslik: t.zaman, hucre: (o) => <span className="whitespace-nowrap">{zamanYaz(o.zaman)}</span> },
              { baslik: t.kullanici, hucre: (o) => o.kullanici },
              { baslik: t.olay, hucre: (o) => <code className="text-[11px]">{o.olay}</code> },
              { baslik: t.sonuc, hucre: (o) => <Rozet ton={o.sonuc === "deny" ? "kirmizi" : "yesil"}>{t.sonucEtiket[o.sonuc] ?? o.sonuc}</Rozet> },
              { baslik: t.modul, hucre: (o) => o.modul || "—" },
              { baslik: t.ayrinti, hucre: (o) => <span className="line-clamp-2 max-w-96 break-words font-normal">{o.ayrinti || "—"}</span> },
            ]}
          />
          <Sayfalama t={t} sayfa={q.data.sayfa} adet={q.data.adet} toplam={q.data.toplam} onSayfa={setSayfa} />
        </div>
      )}
    </div>
  )
}

function Oturumlar({ dil }: { dil: Dil }) {
  const t = ym(dil)
  const qc = useQueryClient()
  const [bilgi, setBilgi] = useState<string | null>(null)
  const q = useQuery({
    queryKey: ANAHTAR.oturumlar,
    queryFn: () => oku<{ oturumlar: Oturum[]; siz: string }>("/api/v1/yonetim/oturumlar"),
    refetchInterval: 15_000,
  })
  const kapat = useMutation({
    mutationFn: (kullanici: string) => yaz<{ kapatilan: number }>("POST", `/api/v1/yonetim/oturumlar/${encodeURIComponent(kullanici)}/kapat`),
    onSuccess: (s) => {
      setBilgi(t.oturumKapandi(s.kapatilan))
      void qc.invalidateQueries({ queryKey: ANAHTAR.oturumlar })
      void qc.invalidateQueries({ queryKey: ANAHTAR.ozet })
    },
    onError: (e) => setBilgi(hataMesaji(e, t.islemBasarisiz)),
  })
  if (q.isPending) return <Yukleniyor t={t} />
  if (q.isError) return <HataKutusu t={t} onTekrar={() => void q.refetch()} />
  return (
    <div className="grid gap-3">
      <VeriTablosu<Oturum>
        baslik={t.aktifOturumlar}
        satirlar={q.data.oturumlar}
        anahtar={(o) => `${o.username}-${o.age_s}`}
        bos={<p className="text-xs font-bold text-slate-400">{t.kayitYok}</p>}
        kolonlar={[
          {
            baslik: t.kullanici,
            hucre: (o) => (
              <span>
                {o.username}
                {o.username === q.data.siz ? <span className="ml-1 text-slate-400">({t.siz})</span> : null}
              </span>
            ),
          },
          { baslik: t.rol, hucre: (o) => o.role },
          { baslik: t.oturumSuresi, hucre: (o) => sureYaz(o.age_s) },
          { baslik: t.bosta, hucre: (o) => sureYaz(o.idle_s) },
          {
            baslik: "",
            hucre: (o) => (
              <button
                type="button"
                className={DUGME}
                disabled={kapat.isPending}
                onClick={() => {
                  if (window.confirm(t.oturumKapatOnay(o.username))) kapat.mutate(o.username)
                }}
              >
                {t.oturumuKapat}
              </button>
            ),
          },
        ]}
      />
      {bilgi ? <Bilgi>{bilgi}</Bilgi> : null}
    </div>
  )
}

function UygulamaGunlugu({ dil, baslangic }: { dil: Dil; baslangic: string | null }) {
  const t = ym(dil)
  const [giris, setGiris] = useState(baslangic ?? "")
  const [aranan, setAranan] = useState<string | null>(baslangic)
  const q = useQuery({
    queryKey: [...ANAHTAR.uygulamaGunlugu, aranan],
    queryFn: () => oku<GunlukDosyasi>(`/api/v1/yonetim/uygulama-gunlugu${sorguMetni({ kayit: aranan })}`),
    enabled: aranan !== null,
  })
  return (
    <div className="grid gap-3">
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault()
          setAranan(giris.trim().toLowerCase())
        }}
      >
        <Alan etiket={t.kayitNoGetir}>
          <input className={`${GIRDI} font-mono`} maxLength={8} pattern="[0-9a-fA-F]{0,8}" value={giris} onChange={(e) => setGiris(e.target.value)} placeholder="3f9a1c2b" />
        </Alan>
        <button type="submit" className={DUGME_ANA}>
          {t.getir}
        </button>
      </form>
      {q.isFetching ? <Yukleniyor t={t} /> : null}
      {q.isError ? <HataKutusu t={t} onTekrar={() => void q.refetch()} /> : null}
      {q.data && !q.isFetching ? (
        !q.data.var ? (
          <Bilgi>{t.gunlukYok}</Bilgi>
        ) : q.data.satirlar.length === 0 ? (
          <Bilgi>{t.kayitBulunamadi}</Bilgi>
        ) : (
          <pre tabIndex={0} aria-label={t.uygulamaGunlugu} className="max-h-96 overflow-auto rounded-xl border border-slate-200 bg-slate-900 p-3 font-mono text-[11px] leading-relaxed text-slate-100">
            {q.data.satirlar.join("\n")}
          </pre>
        )
      ) : null}
    </div>
  )
}

/** Gunlukler: denetim olaylari (suz / sayfala / CSV), aktif oturumlar (kapat), uygulama gunlugu (kayit numarasiyla yigin izi). */
export default function Gunlukler({ dil }: { dil: Dil }) {
  const t = ym(dil)
  const kayit = useHashSorgu().get("kayit")
  return (
    <div className="grid gap-4">
      <Bolum anahtar="yonetim-gunluk-denetim" baslik={t.denetim}>
        <Denetim dil={dil} />
      </Bolum>
      <Bolum anahtar="yonetim-gunluk-oturum" baslik={t.aktifOturumlar}>
        <Oturumlar dil={dil} />
      </Bolum>
      <Bolum anahtar={kayit ? "yonetim-gunluk-uygulama-kayit" : "yonetim-gunluk-uygulama"} baslik={t.uygulamaGunlugu} varsayilanAcik={!!kayit}>
        <UygulamaGunlugu dil={dil} baslangic={kayit} />
      </Bolum>
    </div>
  )
}
