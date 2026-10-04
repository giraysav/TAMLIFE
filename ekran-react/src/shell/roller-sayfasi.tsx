import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { apiGet } from "@/lib/oturum"
import { csrfBasliklari } from "@/lib/http"
import { metin } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

type Rol = { role: string; label: string; editable: boolean; modules: string[]; landing: string; saved: boolean }
type Katalog = { id: string; label: string; admin_only: boolean; children: { id: string; label: string }[] }
type Veri = { roles: Rol[]; catalog: Katalog[] }

/** Rol Yonetimi: admin her rolun gorecegi sayfalari ve giris sayfasini belirler. Sunucu da ayni kurali zorlar. */
export function RollerSayfasi({ dil }: { dil: Dil }) {
  const t = metin(dil)
  const [veri, setVeri] = useState<Veri | null | undefined>(undefined)
  const [taslak, setTaslak] = useState<Record<string, { modules: Set<string>; landing: string }>>({})
  const [bilgi, setBilgi] = useState<Record<string, string>>({})

  const yukle = useCallback(async () => {
    const govde = await apiGet<Veri>("/api/v1/roller")
    setVeri(govde)
    if (govde) {
      setTaslak(Object.fromEntries(govde.roles.map((r) => [r.role, { modules: new Set(r.modules), landing: r.landing }])))
    }
  }, [])

  useEffect(() => {
    void yukle()
  }, [yukle])

  if (veri === undefined) return <p className="text-sm text-muted-foreground">{t.yukleniyor}</p>
  if (veri === null) return <p role="alert" className="text-sm text-destructive">{t.yuklenemedi}</p>

  function degistir(rol: string, kimlik: string, acik: boolean) {
    setTaslak((onceki) => {
      const mevcut = onceki[rol]
      const kume = new Set(mevcut.modules)
      if (acik) kume.add(kimlik)
      else kume.delete(kimlik)
      const landing = mevcut.landing !== "ozet" && !kume.has(mevcut.landing) ? "ozet" : mevcut.landing
      return { ...onceki, [rol]: { modules: kume, landing } }
    })
  }

  async function kaydet(rol: string) {
    const t1 = taslak[rol]
    setBilgi((b) => ({ ...b, [rol]: "" }))
    try {
      const cevap = await fetch(`/api/v1/roller/${rol}`, {
        method: "PUT",
        credentials: "same-origin",
        headers: csrfBasliklari({ "Content-Type": "application/json" }),
        body: JSON.stringify({ modules: [...t1.modules], landing: t1.landing }),
      })
      setBilgi((b) => ({ ...b, [rol]: cevap.ok ? t.rolKaydedildi : t.rolKaydedilemedi }))
      if (cevap.ok) await yukle()
    } catch {
      setBilgi((b) => ({ ...b, [rol]: t.rolKaydedilemedi }))
    }
  }

  const kimlikler = veri.catalog.flatMap((m) => [m.id, ...m.children.map((c) => c.id)])
  const etiket = (kimlik: string) => {
    for (const m of veri.catalog) {
      if (m.id === kimlik) return m.label
      const c = m.children.find((x) => x.id === kimlik)
      if (c) return `${m.label} › ${c.label}`
    }
    return kimlik
  }

  return (
    <div className="grid gap-4">
      <p className="text-sm text-muted-foreground">{t.rolAciklama}</p>
      <div className="grid gap-4 lg:grid-cols-3">
        {veri.roles.map((r) => {
          const tas = taslak[r.role]
          const secili = kimlikler.filter((k) => tas?.modules.has(k))
          return (
            <Card key={r.role}>
              <CardHeader>
                <CardTitle className="text-base">{r.label}</CardTitle>
                <CardDescription>{r.editable ? (r.saved ? t.rolKayitli : t.rolVarsayilan) : t.rolAdminSabit}</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3">
                {r.editable ? (
                  <>
                    <fieldset className="grid gap-1.5">
                      <legend className="mb-1 text-xs font-medium text-muted-foreground">{t.rolGorecegiSayfalar}</legend>
                      {veri.catalog.map((m) => (
                        <div key={m.id} className="grid gap-1">
                          <label className={`flex items-center gap-2 text-sm ${m.admin_only ? "text-muted-foreground" : ""}`}>
                            <input
                              type="checkbox"
                              disabled={m.admin_only}
                              checked={!m.admin_only && !!tas?.modules.has(m.id)}
                              onChange={(e) => degistir(r.role, m.id, e.target.checked)}
                            />
                            {m.label}
                            {m.admin_only ? <span className="text-xs">({t.yalnizAdmin})</span> : null}
                          </label>
                          {m.children.map((c) => (
                            <label key={c.id} className="ml-6 flex items-center gap-2 text-sm">
                              <input
                                type="checkbox"
                                checked={!!tas?.modules.has(c.id)}
                                onChange={(e) => degistir(r.role, c.id, e.target.checked)}
                              />
                              {c.label}
                            </label>
                          ))}
                        </div>
                      ))}
                    </fieldset>
                    <label className="grid gap-1 text-sm">
                      <span className="text-xs font-medium text-muted-foreground">{t.rolGirisSayfasi}</span>
                      <select
                        className="h-9 rounded-md border bg-background px-2"
                        value={tas?.landing ?? "ozet"}
                        onChange={(e) => setTaslak((o) => ({ ...o, [r.role]: { ...o[r.role], landing: e.target.value } }))}
                      >
                        <option value="ozet">{t.genelBakis}</option>
                        {secili.map((k) => (
                          <option key={k} value={k}>
                            {etiket(k)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="flex items-center gap-3">
                      <Button type="button" size="sm" onClick={() => void kaydet(r.role)}>
                        {t.kaydet}
                      </Button>
                      {bilgi[r.role] ? (
                        <span role="status" className="text-sm text-muted-foreground">
                          {bilgi[r.role]}
                        </span>
                      ) : null}
                    </div>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">{t.rolAdminAciklama}</p>
                )}
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
