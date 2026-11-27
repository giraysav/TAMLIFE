/* Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz. */
// rapor-trafik.js'i Node'da yukler; verilen /rapor/trafik verisiyle devreSecenek + gorseller akisini calistirir (echarts sahte).
// Cikti (JSON): {"paneller": [...], "seri": n, "gorsel": n, "hata": "..."}
const fs = require("fs");
const vm = require("vm");
const [, , betikYolu, veriYolu] = process.argv;
const veri = JSON.parse(fs.readFileSync(veriYolu, "utf8"));
const window = {};
const document = { currentScript: { src: "http://x/rapor-trafik.js" }, createElement: () => ({ style: {}, appendChild() {}, setAttribute() {} }), head: { appendChild() {} } };
const ctx = { window, document, console, URL, Promise, setTimeout, clearTimeout, Math, Date, JSON, Object, Array, isFinite, Number, String };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(betikYolu, "utf8"), ctx);
const T = window.TamlifeTrafik;
const sonuc = { paneller: [], seri: 0, gorsel: 0, hata: "" };
try {
  const s = T.devreSecenek(veri.devreler[0], veri.aralik, veri.ayar, "tr");
  if (s) {
    sonuc.seri = s.series.length;
    sonuc.paneller = s.graphic.filter((g) => g.style && g.style.font && g.style.font.startsWith("800 13px")).map((g) => g.style.text);
  }
} catch (e) {
  sonuc.hata = String(e && e.message ? e.message : e);
}
window.echarts = { init: () => ({ setOption() {}, getDataURL: () => "data:image/png;base64,AAA", dispose() {} }) };
T.gorseller(async () => veri, "/x", "tr").then((r) => {
  sonuc.gorsel = r.length;
  process.stdout.write(JSON.stringify(sonuc));
});
