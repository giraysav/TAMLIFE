import { useCallback, useEffect, useState } from "react"
import type { FormEvent, ReactNode } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiOku, apiYaz } from "@/lib/api-yaz"
import { AylikRapor } from "@/shell/aylik-rapor"
import type { Dil } from "@/shell/metin"
import { musteriMetin } from "@/shell/musteri-metin"
import { sorguAyarla } from "@/shell/rota"

type Sayilar = { envanter: number; alarm: number; sikayet: number; talep: number; alarm_kapanan: number; sikayet_kapanan: number; talep_kapanan: number }
type Matris = { basliklar: string[]; satirlar: string[][] }
type Gelir = { toplam: Record<string, number>; son: { donem: string; tutar: number; para: string; musteri: string; installation_pct?: number }[] }
type Kart = {
  kimlik: {
    id: number
    unvan: string
    musteri_no: string | null
    ncst: string
    segment: string
    sektor: string | null
    envanter: number
    tam: string | null
    tam_id: number | null
    ayri_rapor: boolean | null
    cati: { id: number; unvan: string } | null
    istirakler: { id: number; unvan: string; ncst: string; tam: string | null }[]
  }
  operasyon: { ft_hacim: string; tam_ft: string; final_skor: number | null; skor_talebi_bekliyor: boolean; kendi: Sayilar; istirak_dahil: Sayilar | null }
  ekip: Matris
  iletisim: Record<string, string>
  kritik_ci: Matris
  izleme: { cacti: string[] }
  raporlar?: { toplam: number; son: { donem: string; gonderildi: boolean; duzenleyen: string | null; tarih: string | null; bayrak: number }[] }
  gelirler?: { ict?: Gelir; apn?: Gelir }
  erisim: { rapor: boolean; gelir: boolean; kimlik_duzenle: boolean; sil: boolean; tam_degistir: boolean; rapor_geri_al: boolean; ayri_rapor_sec: boolean; istirak_ekle: boolean }
  tam_secenekleri?: { id: number; ad: string }[]
}

const SEGMENTLER = ["SMB", "SA", "MA", "PA", "WHOLESALE"]
const ILETISIM = [
  ["sales_manager", "satis"],
  ["presales_manager", "presales"],
  ["tac_name", "tacAd"],
  ["tac_gsm", "tacGsm"],
  ["tac_email", "tacEposta"],
  ["sol_kmt_name", "solAd"],
  ["sol_kmt_gsm", "solGsm"],
  ["sol_kmt_email", "solEposta"],
  ["mobil_kmt_name", "mobilAd"],
  ["mobil_kmt_gsm", "mobilGsm"],
  ["mobil_kmt_email", "mobilEposta"],
  ["mobil_kmt_detail", "mobilNot"],
] as const

function Alan({ id, etiket, children }: { id: string; etiket: string; children: ReactNode }) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{etiket}</Label>
      {children}
    </div>
  )
}

function Bolum({ baslik, children }: { baslik: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{baslik}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">{children}</CardContent>
    </Card>
  )
}

function Tablo({ veri, bos }: { veri: Matris; bos: string }) {
  if (veri.satirlar.length === 0) return <p className="text-sm text-muted-foreground">{bos}</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            {veri.basliklar.map((b, i) => (
              <th key={i} scope="col" className="px-2 py-2 font-medium">
                {b}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {veri.satirlar.map((s, i) => (
            <tr key={i} className="border-b last:border-0">
              {s.map((h, j) => (
                <td key={j} className="px-2 py-2">
                  {h}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Sayim({ baslik, s, t }: { baslik: string; s: Sayilar; t: ReturnType<typeof musteriMetin> }) {
  return (
    <div className="grid gap-1 text-sm">
      <p className="text-xs font-medium text-muted-foreground">{baslik}</p>
      <p className="tabular-nums">
        {t.envanter}: {s.envanter} · {t.alarm}: {s.alarm} ({s.alarm_kapanan} {t.kapanan}) · {t.sikayet}: {s.sikayet} ({s.sikayet_kapanan} {t.kapanan}) · {t.talep}: {s.talep} ({s.talep_kapanan}{" "}
        {t.kapanan})
      </p>
    </div>
  )
}

function GelirListe({ baslik, g, t, apn }: { baslik: string; g: Gelir; t: ReturnType<typeof musteriMetin>; apn?: boolean }) {
  return (
    <div className="grid gap-1 text-sm">
      <p className="text-xs font-medium text-muted-foreground">
        {baslik} ·{" "}
        {Object.entries(g.toplam)
          .map(([p, v]) => `${v.toLocaleString("tr-TR")} ${p}`)
          .join(" · ") || "—"}
      </p>
      {g.son.length === 0 ? <p className="text-muted-foreground">{t.sonucYok}</p> : null}
      <ul className="grid gap-0.5">
        {g.son.map((k, i) => (
          <li key={i} className="flex justify-between gap-2 tabular-nums">
            <span>{k.donem}</span>
            <span>
              {k.tutar.toLocaleString("tr-TR")} {k.para}
              {apn && k.installation_pct !== undefined ? ` · %${k.installation_pct} ${t.kurulum}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function MusteriKarti({ id, dil }: { id: number; dil: Dil }) {
  const t = musteriMetin(dil)
  const [kart, setKart] = useState<Kart | null | undefined>(undefined)
  const [durum, setDurum] = useState(0)
  const [sekme, setSekme] = useState<"kart" | "rapor">("kart")
  const [kim, setKim] = useState<Record<string, string>>({})
  const [ilet, setIlet] = useState<Record<string, string>>({})
  const [tam, setTam] = useState("")
  const [mesaj, setMesaj] = useState<Record<string, string>>({})

  const yukle = useCallback(async () => {
    const sonuc = await apiOku<Kart>(`/api/v1/musteri/${id}`)
    setDurum(sonuc.durum)
    const k = sonuc.ok ? sonuc.veri : null
    setKart(k)
    if (k) {
      setKim({
        name: k.kimlik.unvan,
        customer_no: k.kimlik.musteri_no ?? "",
        ncst: k.kimlik.ncst,
        segment: k.kimlik.segment,
        sector: k.kimlik.sektor ?? "",
        ft_volume: k.operasyon.ft_hacim,
        tam_ft: k.operasyon.tam_ft,
        inventory: String(k.kimlik.envanter),
      })
      setIlet({ ...k.iletisim })
      setTam(k.kimlik.tam_id ? String(k.kimlik.tam_id) : "")
    }
  }, [id])

  useEffect(() => {
    setKart(undefined)
    setSekme("kart")
    void yukle()
  }, [yukle])

  function bildir(anahtar: string, metin: string) {
    setMesaj((m) => ({ ...m, [anahtar]: metin }))
  }

  async function kimligiKaydet(olay: FormEvent) {
    olay.preventDefault()
    const sonuc = await apiYaz("PUT", `/api/v1/musteri/${id}/kimlik`, { ...kim, inventory: kim.inventory === "" ? 0 : Number(kim.inventory) })
    bildir("kimlik", sonuc.ok ? t.kaydedildi : `${t.kaydedilemedi}: ${sonuc.hata}`)
    if (sonuc.ok) await yukle()
  }

  async function iletisimiKaydet(olay: FormEvent) {
    olay.preventDefault()
    const sonuc = await apiYaz("PUT", `/api/v1/musteri/${id}/iletisim`, ilet)
    bildir("iletisim", sonuc.ok ? t.kaydedildi : `${t.kaydedilemedi}: ${sonuc.hata}`)
    if (sonuc.ok) await yukle()
  }

  async function sorumluKaydet() {
    const sonuc = await apiYaz("PUT", `/api/v1/musteri/${id}/sorumlu`, { owner_id: Number(tam) })
    bildir("tam", sonuc.ok ? t.kaydedildi : `${t.kaydedilemedi}: ${sonuc.hata}`)
    if (sonuc.ok) await yukle()
  }

  async function ayriRapor(deger: boolean) {
    const sonuc = await apiYaz("PUT", `/api/v1/musteri/${id}/ayri-rapor`, { ayri_rapor: deger })
    if (sonuc.ok) await yukle()
    else bildir("ayri", `${t.kaydedilemedi}: ${sonuc.hata}`)
  }

  async function sil() {
    if (!window.confirm(t.silOnay)) return
    const sonuc = await apiYaz("DELETE", `/api/v1/musteri/${id}`)
    if (sonuc.ok) sorguAyarla("musteri", {})
    else bildir("sil", `${t.kaydedilemedi}: ${sonuc.hata}`)
  }

  if (kart === undefined) return <p className="text-sm text-muted-foreground">…</p>
  if (kart === null) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {durum === 404 || durum === 403 ? t.bulunamadi : t.yuklenemedi}
      </p>
    )
  }
  const e = kart.erisim
  const duzenle = e.kimlik_duzenle
  const girdi = (anahtar: string, onChange: (v: string) => void, deger: string, uzun = 150, disabled = !duzenle) => (
    <Input id={`k-${anahtar}`} value={deger} maxLength={uzun} disabled={disabled} onChange={(ev) => onChange(ev.target.value)} />
  )

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-xl font-semibold">{kart.kimlik.unvan}</h2>
        {kart.kimlik.segment ? <Badge variant="secondary">{kart.kimlik.segment}</Badge> : null}
        {kart.kimlik.cati ? <Badge variant="outline">{t.istirak}</Badge> : null}
        <div className="ml-auto flex items-center gap-2" role="tablist" aria-label={kart.kimlik.unvan}>
          {(["kart", "rapor"] as const).map((s) => (
            <Button key={s} type="button" role="tab" aria-selected={sekme === s} size="sm" variant={sekme === s ? "default" : "outline"} onClick={() => setSekme(s)}>
              {s === "kart" ? t.sekmeKart : t.sekmeRapor}
            </Button>
          ))}
          {e.sil ? (
            <Button type="button" size="sm" variant="outline" className="text-destructive" onClick={() => void sil()}>
              {t.sil}
            </Button>
          ) : null}
        </div>
      </div>
      {mesaj.sil ? (
        <p role="alert" className="text-sm text-destructive">
          {mesaj.sil}
        </p>
      ) : null}

      {sekme === "rapor" ? (
        <AylikRapor musteriId={id} dil={dil} geriAlabilir={e.rapor_geri_al} />
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          <Bolum baslik={t.kimlik}>
            <form onSubmit={kimligiKaydet} className="grid gap-3 sm:grid-cols-2" aria-label={t.kimlik}>
              <Alan id="k-name" etiket={t.unvan}>
                {girdi("name", (v) => setKim({ ...kim, name: v }), kim.name ?? "")}
              </Alan>
              <Alan id="k-segment" etiket={t.segment}>
                <select id="k-segment" disabled={!duzenle} value={kim.segment ?? ""} onChange={(ev) => setKim({ ...kim, segment: ev.target.value })} className="h-9 rounded-md border bg-background px-2 text-sm">
                  <option value="">{t.seciniz}</option>
                  {[...new Set([...SEGMENTLER, kim.segment ?? ""])]
                    .filter(Boolean)
                    .map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                </select>
              </Alan>
              <Alan id="k-customer_no" etiket={t.musteriNo}>
                {girdi("customer_no", (v) => setKim({ ...kim, customer_no: v }), kim.customer_no ?? "", 50)}
              </Alan>
              <Alan id="k-ncst" etiket={t.ncst}>
                {girdi("ncst", (v) => setKim({ ...kim, ncst: v }), kim.ncst ?? "", 50)}
              </Alan>
              <Alan id="k-sector" etiket={t.sektor}>
                {girdi("sector", (v) => setKim({ ...kim, sector: v }), kim.sector ?? "", 100)}
              </Alan>
              <Alan id="k-inventory" etiket={t.envanter}>
                {girdi("inventory", (v) => setKim({ ...kim, inventory: v.replace(/\D/g, "") }), kim.inventory ?? "", 12)}
              </Alan>
              <Alan id="k-ft_volume" etiket={t.ftHacim}>
                {girdi("ft_volume", (v) => setKim({ ...kim, ft_volume: v }), kim.ft_volume ?? "", 100)}
              </Alan>
              <Alan id="k-tam_ft" etiket={t.tamFt}>
                {girdi("tam_ft", (v) => setKim({ ...kim, tam_ft: v }), kim.tam_ft ?? "", 100)}
              </Alan>
              {duzenle ? (
                <div className="flex items-center gap-3 sm:col-span-2">
                  <Button type="submit">{t.kaydet}</Button>
                  {mesaj.kimlik ? <span role="status" className="text-sm text-muted-foreground">{mesaj.kimlik}</span> : null}
                </div>
              ) : null}
            </form>
            <dl className="grid gap-1 text-sm sm:grid-cols-[10rem_1fr]">
              <dt className="text-muted-foreground">{t.sorumlu}</dt>
              <dd>
                {e.tam_degistir && kart.tam_secenekleri ? (
                  <span className="flex items-center gap-2">
                    <select aria-label={t.sorumlu} value={tam} onChange={(ev) => setTam(ev.target.value)} className="h-9 rounded-md border bg-background px-2 text-sm">
                      {kart.tam_secenekleri.map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.ad}
                        </option>
                      ))}
                    </select>
                    <Button type="button" size="sm" variant="outline" onClick={() => void sorumluKaydet()}>
                      {t.sorumluDegistir}
                    </Button>
                    {mesaj.tam ? <span role="status" className="text-muted-foreground">{mesaj.tam}</span> : null}
                  </span>
                ) : (
                  (kart.kimlik.tam ?? "—")
                )}
              </dd>
              {kart.kimlik.cati ? (
                <>
                  <dt className="text-muted-foreground">{t.cati}</dt>
                  <dd>
                    <a className="underline-offset-4 hover:underline" href={`#/musteri?m=${kart.kimlik.cati.id}`}>
                      {kart.kimlik.cati.unvan}
                    </a>
                  </dd>
                </>
              ) : null}
              {kart.kimlik.istirakler.length > 0 ? (
                <>
                  <dt className="text-muted-foreground">{t.istirakler}</dt>
                  <dd className="grid gap-0.5">
                    {kart.kimlik.istirakler.map((i) => (
                      <a key={i.id} className="underline-offset-4 hover:underline" href={`#/musteri?m=${i.id}`}>
                        {i.unvan}
                        {i.ncst ? ` · ${i.ncst}` : ""}
                      </a>
                    ))}
                  </dd>
                </>
              ) : null}
            </dl>
            {e.ayri_rapor_sec ? (
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-1" checked={!!kart.kimlik.ayri_rapor} onChange={(ev) => void ayriRapor(ev.target.checked)} />
                <span>
                  {t.ayriRapor}
                  <span className="block text-xs text-muted-foreground">{t.ayriRaporAciklama}</span>
                </span>
              </label>
            ) : null}
            {mesaj.ayri ? <p role="alert" className="text-sm text-destructive">{mesaj.ayri}</p> : null}
          </Bolum>

          <Bolum baslik={t.operasyon}>
            <p className="text-sm">
              {t.finalSkor}: <strong>{kart.operasyon.final_skor ?? "—"}</strong>
              {kart.operasyon.skor_talebi_bekliyor ? <Badge variant="secondary" className="ml-2">{t.skorBekliyor}</Badge> : null}
            </p>
            <Sayim baslik={t.kendi} s={kart.operasyon.kendi} t={t} />
            {kart.operasyon.istirak_dahil ? <Sayim baslik={t.istirakDahil} s={kart.operasyon.istirak_dahil} t={t} /> : null}
          </Bolum>

          <Bolum baslik={t.iletisim}>
            <form onSubmit={iletisimiKaydet} className="grid gap-3 sm:grid-cols-2" aria-label={t.iletisim}>
              {ILETISIM.map(([alan, anahtar]) => (
                <Alan key={alan} id={`i-${alan}`} etiket={t[anahtar]}>
                  <Input id={`i-${alan}`} value={ilet[alan] ?? ""} maxLength={alan === "mobil_kmt_detail" ? 2000 : 100} onChange={(ev) => setIlet({ ...ilet, [alan]: ev.target.value })} />
                </Alan>
              ))}
              <div className="flex items-center gap-3 sm:col-span-2">
                <Button type="submit">{t.kaydet}</Button>
                {mesaj.iletisim ? <span role="status" className="text-sm text-muted-foreground">{mesaj.iletisim}</span> : null}
              </div>
            </form>
          </Bolum>

          <Bolum baslik={t.ekip}>
            <Tablo veri={kart.ekip} bos={t.satirYok} />
          </Bolum>
          <Bolum baslik={t.kritikCi}>
            <Tablo veri={kart.kritik_ci} bos={t.satirYok} />
          </Bolum>

          {kart.gelirler ? (
            <Bolum baslik={t.gelirler}>
              {kart.gelirler.ict ? <GelirListe baslik={t.ictGelir} g={kart.gelirler.ict} t={t} /> : null}
              {kart.gelirler.apn ? <GelirListe baslik={t.apnGelir} g={kart.gelirler.apn} t={t} apn /> : null}
            </Bolum>
          ) : null}

          {kart.raporlar ? (
            <Bolum baslik={`${t.raporlar} (${kart.raporlar.toplam})`}>
              {kart.raporlar.son.length === 0 ? <p className="text-sm text-muted-foreground">{t.sonucYok}</p> : null}
              <ul className="grid gap-1 text-sm">
                {kart.raporlar.son.map((r, i) => (
                  <li key={i} className="flex justify-between gap-2">
                    <span>{r.donem}</span>
                    <span className="text-muted-foreground">
                      {r.gonderildi ? t.gonderildi : t.taslak}
                      {r.duzenleyen ? ` · ${r.duzenleyen}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </Bolum>
          ) : null}

          <Bolum baslik={t.izleme}>
            {kart.izleme.cacti.length === 0 ? <p className="text-sm text-muted-foreground">{t.izlemeYok}</p> : null}
            <ul className="grid gap-1 text-sm">
              {kart.izleme.cacti.map((u) => (
                <li key={u} className="break-all">
                  {u}
                </li>
              ))}
            </ul>
          </Bolum>
        </div>
      )}
    </div>
  )
}
