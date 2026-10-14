import type { ReactNode } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Pencil, Trash2 } from "lucide-react"
import { Cekmece } from "@/components/cekmece"
import { ALT_BASLIK_BANDI, ALT_BASLIK_YAZISI, Bildirim, DUGME, DUGME_ANA, Rozet, Satir } from "@/components/sayfa-ui"
import { para, tarih, zaman } from "@/lib/bicim"
import { hataMesaji, yaz } from "@/lib/sorgu"
import type { Dil } from "@/shell/metin"
import { gelirUretimMetin } from "@/gelir-uretim/gelir-uretim-metin"
import type { Kayit } from "@/gelir-uretim/gelir-uretim-metin"
import { ANAHTAR, DURUM_TON, FaydaRozeti, TABAN, saatMetni, tutarMetni } from "@/gelir-uretim/ortak"

function Grup({ baslik, children }: { baslik: string; children: ReactNode }) {
  return (
    <section className="overflow-hidden rounded-xl border border-slate-200">
      <div className={ALT_BASLIK_BANDI}>
        <span aria-hidden className="h-3.5 w-1 shrink-0 rounded-full bg-tl-yellow" />
        <h4 className={ALT_BASLIK_YAZISI}>{baslik}</h4>
      </div>
      <div className="px-3 py-1.5">{children}</div>
    </section>
  )
}

function Paragraf({ children }: { children: string }) {
  return <p className="whitespace-pre-wrap break-words py-1.5 text-xs font-bold text-slate-700">{children}</p>
}

/** Uzun metin satiri (musteriler, kisiler, notlar): etiket ustte, metin tam genislikte (dar ekranda sag hizali dar sutun okunmaz). */
function UzunSatir({ etiket, children }: { etiket: string; children: string }) {
  return (
    <div className="border-b border-slate-100 py-1.5 text-xs last:border-0">
      <div className="font-bold text-slate-400">{etiket}</div>
      <p className="mt-0.5 whitespace-pre-wrap break-words font-bold text-slate-700">{children}</p>
    </div>
  )
}

/** Kaydi kim ne zaman olusturdu / son guncelledi: "ad · 10.03.2026 14:05"; hicbiri yoksa tire. */
function kimKimde(kim: string, zamanIso: string | null, yok: string): string {
  return [kim, zamanIso ? zaman(zamanIso) : ""].filter(Boolean).join(" · ") || yok
}

/** Is ayrintisi cekmecesi. Yazma yetkisi olanlar (admin) alt cubukta Duzenle ve Sil dugmelerini gorur. */
export function Ayrinti({ k, dil, yazabilir, onKapat, onDuzenle }: { k: Kayit; dil: Dil; yazabilir: boolean; onKapat: () => void; onDuzenle: () => void }) {
  const t = gelirUretimMetin(dil)
  const qc = useQueryClient()
  const sil = useMutation({
    mutationFn: () => yaz("DELETE", `${TABAN}/${k.id}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ANAHTAR })
      onKapat()
    },
  })
  const gelirVar = k.revenue_amount !== null || k.revenue_note !== "" || k.year_revenue !== null
  const eforVar = k.hours_per_month !== null || k.hours_note !== ""
  const tutar = tutarMetni(k, t)

  return (
    <Cekmece
      acik
      genis
      onKapat={onKapat}
      baslik={t.detayBaslik}
      kapatEtiketi={t.kapat}
      alt={
        yazabilir ? (
          <div className="grid gap-2">
            {sil.isError ? <Bildirim ton="kirmizi">{hataMesaji(sil.error, t.silinemedi)}</Bildirim> : null}
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className={`${DUGME} !border-rose-200 !text-rose-600 hover:!bg-rose-50`}
                disabled={sil.isPending}
                onClick={() => {
                  if (window.confirm(t.silOnay(k.title))) sil.mutate()
                }}
              >
                <Trash2 aria-hidden className="size-3.5" />
                {t.sil}
              </button>
              <button type="button" className={`${DUGME_ANA} ml-auto`} onClick={onDuzenle}>
                <Pencil aria-hidden className="size-3.5" />
                {t.duzenle}
              </button>
            </div>
          </div>
        ) : undefined
      }
    >
      <div className="grid gap-4">
        <div className="grid gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <Rozet ton={k.kind === "inisiyatif" ? "sari" : "gri"}>{t.tur_[k.kind]}</Rozet>
            <Rozet ton={DURUM_TON[k.status]}>{t.durum_[k.status]}</Rozet>
            <FaydaRozeti fayda={k.benefit_type} dil={dil} />
          </div>
          <h3 className="break-words text-base font-black leading-snug text-tl-navy">{k.title}</h3>
        </div>

        <Grup baslik={t.grupGenel}>
          <Satir etiket={t.baslangic}>{tarih(k.start_date)}</Satir>
          <Satir etiket={t.bitis}>{k.end_date ? tarih(k.end_date) : k.status === "devam" ? t.devamEdiyor : t.yok}</Satir>
          <UzunSatir etiket={t.musteriler}>{k.customers || t.yok}</UzunSatir>
          <UzunSatir etiket={t.tamKisiler}>{k.people.map((p) => p.name).join(", ") || t.yok}</UzunSatir>
          {k.other_people ? <UzunSatir etiket={t.digerKisiler}>{k.other_people}</UzunSatir> : null}
        </Grup>

        {k.status_note ? (
          <Grup baslik={t.guncelDurum}>
            <Paragraf>{k.status_note}</Paragraf>
          </Grup>
        ) : null}
        {k.description ? (
          <Grup baslik={t.aciklamaAlani}>
            <Paragraf>{k.description}</Paragraf>
          </Grup>
        ) : null}

        {gelirVar ? (
          <Grup baslik={t.gelirBilgisi}>
            {tutar ? <Satir etiket={t.tutar}>{tutar}</Satir> : null}
            {k.revenue_note ? <UzunSatir etiket={t.tutarNotu}>{k.revenue_note}</UzunSatir> : null}
            {k.year_revenue !== null ? <Satir etiket={t.yilIci}>{para(k.year_revenue)}</Satir> : null}
          </Grup>
        ) : null}
        {eforVar ? (
          <Grup baslik={t.verimlilikBilgisi}>
            {k.hours_per_month !== null ? <Satir etiket={t.aylikSaat}>{saatMetni(k.hours_per_month, t)}</Satir> : null}
            {k.hours_note ? <UzunSatir etiket={t.eforNotu}>{k.hours_note}</UzunSatir> : null}
          </Grup>
        ) : null}
        {k.extra_note ? (
          <Grup baslik={t.ekAciklama}>
            <Paragraf>{k.extra_note}</Paragraf>
          </Grup>
        ) : null}

        <Grup baslik={t.grupKayit}>
          <Satir etiket={t.olusturan}>{kimKimde(k.created_by, k.created_at, t.yok)}</Satir>
          <Satir etiket={t.guncelleyen}>{kimKimde(k.updated_by, k.updated_at, t.yok)}</Satir>
        </Grup>
      </div>
    </Cekmece>
  )
}
