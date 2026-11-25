import { ORTAK } from "@/shell/metin"
import type { Dil } from "@/shell/metin"

const TR = {
  ...ORTAK.tr,
  baslik: "Ekip Özeti",
  baslikKendi: "Özetim",
  aciklama: "Ekip ve modül özetleri; karoya tıklayınca modül açılır.",
  aciklamaKendi: "Size ait veriler ve modül özetleri; karoya tıklayınca modül açılır.",
  kisiAlt: "ekipteki personel",
  kutularEtiket: "Özet karoları",
  kisi: "TAM",
  skorRiskAlt: (u: string, oran: number, acik: number) => `utilizasyon ${u} · risk %${oran} · ${acik} açık kayıt`,
  formul: (e: number) =>
    `Riskli utilizasyon = U × (1 + p). U: ağırlık puanı (0-100). p = R / (R + ${e}), R = Σ (açık alarm + açık şikayet) × müşteri skoru/100 (skorsuz müşteride 1). Risk = olasılık × etki (ISO 31000, NIST SP 800-30). Risk yoksa değer utilizasyona eşit, en fazla 2 katı.`,
  kolSkorRisk: "Riskli utilizasyon",
  riskVeriYok: "Alarm verisi yok",
}

const EN: typeof TR = {
  ...ORTAK.en,
  baslik: "Team overview",
  baslikKendi: "My overview",
  aciklama: "The team and module summaries; click a tile to open the module.",
  aciklamaKendi: "Your data and module summaries; click a tile to open the module.",
  kisiAlt: "staff in the team",
  kutularEtiket: "Summary tiles",
  kisi: "TAM",
  skorRiskAlt: (u: string, oran: number, acik: number) => `utilization ${u} · risk ${oran}% · ${acik} open records`,
  formul: (e: number) =>
    `Risk-weighted utilization = U × (1 + p). U: weight score (0-100). p = R / (R + ${e}), R = Σ (open alarms + open complaints) × customer score/100 (1 for unscored customers). Risk = likelihood × impact (ISO 31000, NIST SP 800-30). Without risk the value equals utilization, at most twice it.`,
  kolSkorRisk: "Risk-weighted utilization",
  riskVeriYok: "No alarm data",
}

export const ekipMetin = (dil: Dil) => (dil === "en" ? EN : TR)
