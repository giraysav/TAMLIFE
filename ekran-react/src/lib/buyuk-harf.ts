/**
 * Panel yazim kurali (2026-10-15 kullanici karari): yan menu disinda ekrandaki her yazi BUYUK HARF ve Turkce karaktersizdir
 * ("Giray Sav" / "GİRAY SAV" -> "GIRAY SAV"). Veritabanindaki deger degismez; donusum yalniz gosterimdedir, bu yuzden geri
 * donusu tek satirdir (main.tsx'teki buyukHarfIzle cagrisi). Disarida kalanlar: yan menu (`data-yan-menu`), yazi giris alanlari
 * (input/textarea degeri metin dugumu degildir, kullanicinin yazdigi aynen kalir), `data-harf-koru` isaretli ogeler.
 */

const KORU = "[data-yan-menu],[data-harf-koru],script,style,textarea,[contenteditable='true']"
const ISARET = /[̀-ͯ]/g // NFD'de ayrilan aksan isaretleri: İ, Ş, Ç, Ğ, Ü, Ö, Â ...

/** Buyuk harf + Turkce/aksanli harfleri duz Latin harfe indirir: "Çağrı Şık İş" -> "CAGRI SIK IS". */
export function buyukHarf(metin: string): string {
  return metin.toUpperCase().normalize("NFD").replace(ISARET, "").normalize("NFC")
}

function korunur(dugum: Node): boolean {
  const ust = dugum.parentElement
  return ust === null || ust.closest(KORU) !== null
}

function cevir(dugum: Text): void {
  const eski = dugum.nodeValue
  if (!eski || korunur(dugum)) return
  const yeni = buyukHarf(eski)
  if (yeni !== eski) dugum.nodeValue = yeni // ayni degeri yazmamak gozlemciyi donguye sokmaz
}

function agaci_cevir(kok: Node): void {
  if (kok.nodeType === Node.TEXT_NODE) {
    cevir(kok as Text)
    return
  }
  if (kok.nodeType !== Node.ELEMENT_NODE || (kok as Element).closest(KORU)) return
  const gezgin = document.createTreeWalker(kok, NodeFilter.SHOW_TEXT)
  for (let d = gezgin.nextNode(); d; d = gezgin.nextNode()) cevir(d as Text)
}

/**
 * `kok` altindaki metni ceviren ve sonradan eklenen / degisen metni (React guncellemesi, acilan pencere, bildirim) aninda ceviren
 * gozlemciyi kurar. Gozlemci mikro gorevde calistigi icin donusmemis metin ekrana hic cizilmez. Donus: gozlemciyi kaldirir.
 */
export function buyukHarfIzle(kok: HTMLElement = document.body): () => void {
  agaci_cevir(kok)
  const gozlemci = new MutationObserver((kayitlar) => {
    for (const k of kayitlar) {
      if (k.type === "characterData") cevir(k.target as Text)
      else k.addedNodes.forEach(agaci_cevir)
    }
  })
  gozlemci.observe(kok, { subtree: true, childList: true, characterData: true })
  return () => gozlemci.disconnect()
}
