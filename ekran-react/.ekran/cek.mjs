// Gelistirme ekran goruntusu: node .ekran/cek.mjs [adim...]  (Edge, 127.0.0.1:5173, admin/0000)
import { chromium } from "@playwright/test"

const KOK = "http://127.0.0.1:5173/"
const adimlar = process.argv.slice(2)
const tarayici = await chromium.launch({ channel: "msedge" })
const sayfa = await tarayici.newPage({ viewport: { width: 1600, height: 900 } })
await sayfa.goto(KOK)
await sayfa.fill("input[autocomplete=username], input[name=username], input[type=text]", "admin")
await sayfa.fill("input[type=password]", "0000")
await sayfa.keyboard.press("Enter")
await sayfa.waitForTimeout(2500)

for (const adim of adimlar.length ? adimlar : ["genel"]) {
  const [ad, dil] = adim.split(":")
  await sayfa.evaluate((d) => localStorage.setItem("tamlife.dil", d), dil ?? "tr")
  const yol = { genel: "#/", takvim: "#/takvim_ozet", musteri: "#/musteri", yonetim: "#/yonetim/durum", sms: "#/tamsms", apn: "#/tamapn", izin: "#/takvim", onedesk: "#/onedesk", sunum: "#/sunum", roller: "#/roller", profil: "#/profil" }[ad] ?? `#/${ad}`
  await sayfa.goto(KOK + yol)
  await sayfa.reload()
  await sayfa.waitForTimeout(2500)
  if (ad === "takvim") {
    const ok = sayfa.locator("table tbody tr button").first()
    if (await ok.count()) {
      await ok.click()
      await sayfa.waitForTimeout(1500)
    }
  }
  await sayfa.screenshot({ path: `.ekran/${ad}-${dil ?? "tr"}.png`, fullPage: true })
  console.log("cekildi", ad, dil ?? "tr")
}
await tarayici.close()
