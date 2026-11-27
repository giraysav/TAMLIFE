/*
 * TAM Life - TopoMaker cografi harita (React paketinden AYRI kod).
 * 2026-11-24 kullanici: "cografi haritayi Turkiye haritasina yerlestir; zeminde iller olsun ve hangi ilde ne kadar servis varsa
 * uzerinde pinli gostersin; daha dinamik, gorunumu profesyonel".
 *
 * Cizim: Apache ECharts 6.1.0 (echarts-6.1.0.min.js, yerel). Il sinirlari: tr-iller.json (GeoJSON, dist kokunde; sunucu internete
 * cikmadigi icin elle konur). Dosya yoksa ciz() false doner, ekran eski basit haritayi gosterir.
 *   - Iller servis sayisina gore renklenir (koyu = cok); il merkezinde sayili pin; secili il vurgulanir.
 *   - Yakinlastirma / kaydirma; ile tiklaninca (envanter ciziminde) o il secilir.
 *
 * Giris: window.TamlifeHarita.ciz(kap, {sehirler:[{il, adet, enlem, boylam}], agac, secili, dil, birim, onIl}) -> Promise<bool>
 *        window.TamlifeHarita.birak(kap)
 */
(function () {
  "use strict";

  var betik = document.currentScript;
  var KOK = betik && betik.src ? new URL(".", betik.src).href : "/";
  var ECHARTS = "echarts-6.1.0.min.js";
  var GEO = "tr-iller.json";
  var HARITA = "turkiye-iller";
  var YAZI = "'Segoe UI', Calibri, Arial, sans-serif";
  var RENK = { lacivert: "#0A1628", mavi: "#1A5276", sari: "#FFD100", turuncu: "#F39C12", zemin: "#F1F5F9", sinir: "#CBD5E1" };

  var ILLER = ["Adana", "Adıyaman", "Afyonkarahisar", "Ağrı", "Amasya", "Ankara", "Antalya", "Artvin", "Aydın", "Balıkesir", "Bilecik",
    "Bingöl", "Bitlis", "Bolu", "Burdur", "Bursa", "Çanakkale", "Çankırı", "Çorum", "Denizli", "Diyarbakır", "Edirne", "Elazığ",
    "Erzincan", "Erzurum", "Eskişehir", "Gaziantep", "Giresun", "Gümüşhane", "Hakkari", "Hatay", "Isparta", "Mersin", "İstanbul",
    "İzmir", "Kars", "Kastamonu", "Kayseri", "Kırklareli", "Kırşehir", "Kocaeli", "Konya", "Kütahya", "Malatya", "Manisa",
    "Kahramanmaraş", "Mardin", "Muğla", "Muş", "Nevşehir", "Niğde", "Ordu", "Rize", "Sakarya", "Samsun", "Siirt", "Sinop", "Sivas",
    "Tekirdağ", "Tokat", "Trabzon", "Tunceli", "Şanlıurfa", "Uşak", "Van", "Yozgat", "Zonguldak", "Aksaray", "Bayburt", "Karaman",
    "Kırıkkale", "Batman", "Şırnak", "Bartın", "Ardahan", "Iğdır", "Yalova", "Karabük", "Kilis", "Osmaniye", "Düzce"];
  var ES = { ICEL: "MERSIN", AFYON: "AFYONKARAHISAR", MARAS: "KAHRAMANMARAS", KMARAS: "KAHRAMANMARAS", URFA: "SANLIURFA", ANTEP: "GAZIANTEP" };

  var METIN = {
    tr: { baslik: "Coğrafi dağılım", ozet: function (i, n, b) { return i + " ilde " + n + " " + b; }, bin: "B", servis: "servis", cihaz: "cihaz",
          cok: "Çok", az: "Az", yok: "Kayıt yok", tikla: "İli seçmek için tıklayın", ilceler: "İlçeler", diger: "diğer" },
    en: { baslik: "Geographic distribution", ozet: function (i, n, b) { return n + " " + b + " in " + i + " provinces"; }, bin: "K", servis: "services",
          cihaz: "devices", cok: "More", az: "Less", yok: "No records", tikla: "Click to select the province", ilceler: "Districts", diger: "other" }
  };

  function katla(s) {
    var b = String(s || "").replace(/i/g, "İ").replace(/ı/g, "I").toUpperCase();
    b = b.replace(/İ/g, "I").replace(/Ş/g, "S").replace(/Ğ/g, "G").replace(/Ü/g, "U").replace(/Ö/g, "O").replace(/Ç/g, "C");
    b = b.replace(/[^A-Z]/g, "");
    return ES[b] || b;
  }
  var AD = {};
  ILLER.forEach(function (ad) { AD[katla(ad)] = ad; });

  function yukle(src) {
    return new Promise(function (tamam, hata) {
      var s = document.createElement("script");
      s.src = KOK + src;
      s.async = true;
      s.onload = function () { window.echarts ? tamam(window.echarts) : hata(new Error(src)); };
      s.onerror = function () { hata(new Error(src)); };
      document.head.appendChild(s);
    });
  }
  var ec = null;
  function echartsYukle() {
    if (window.echarts) return Promise.resolve(window.echarts);
    if (!ec) ec = yukle(ECHARTS).catch(function (e) { ec = null; throw e; });
    return ec;
  }

  // GeoJSON: her il ozelliklerindeki ad (name / NAME_1 / il_adi ...) kanonik il adina cevrilir. Dosya yoksa null.
  var geo = null;
  function geoYukle(echarts) {
    if (!geo) {
      geo = fetch(KOK + GEO, { credentials: "same-origin" }).then(function (r) {
        if (!r.ok) return null;
        return r.json().then(function (j) {
          var ozellikler = j && (j.features || (j.type === "Topology" ? null : []));
          if (!ozellikler || !ozellikler.length) return null;
          var bulunan = 0;
          ozellikler.forEach(function (f) {
            var p = f.properties || (f.properties = {});
            var ad = null;
            Object.keys(p).some(function (k) { var a = AD[katla(p[k])]; if (typeof p[k] === "string" && a) { ad = a; return true; } return false; });
            if (ad) { p.name = ad; bulunan++; }
          });
          if (bulunan < 70) return null;  // il dosyasi degil
          echarts.registerMap(HARITA, j);
          return true;
        });
      }).catch(function () { return null; });
      geo.then(function (ok) { if (!ok) geo = null; });
    }
    return geo;
  }

  var grafikler = new WeakMap();

  function ciz(kap, ayar) {
    ayar = ayar || {};
    var m = METIN[ayar.dil === "en" ? "en" : "tr"];
    return echartsYukle().then(function (echarts) {
      return geoYukle(echarts).then(function (ok) {
        if (!ok || !kap.isConnected) return false;
        var veri = {};
        (ayar.sehirler || []).forEach(function (s) {
          var ad = AD[katla(s.il)];
          if (ad) veri[ad] = { adet: (veri[ad] ? veri[ad].adet : 0) + (s.adet || 0), enlem: s.enlem, boylam: s.boylam };
        });
        var agac = {};
        (ayar.agac || []).forEach(function (x) { var ad = AD[katla(x.il)]; if (ad) agac[ad] = x.ilceler || []; });
        var secili = AD[katla(ayar.secili)] || "";
        var adlar = Object.keys(veri);
        var toplam = adlar.reduce(function (t, k) { return t + veri[k].adet; }, 0);
        var enCok = adlar.reduce(function (t, k) { return Math.max(t, veri[k].adet); }, 1);
        var birim = ayar.birim === "cihaz" ? m.cihaz : m.servis;
        var pinBoy = function (n) { return 26 + 22 * Math.sqrt(n / enCok); };

        var g = grafikler.get(kap);
        if (!g) {
          g = echarts.init(kap, null, { renderer: "canvas" });
          grafikler.set(kap, g);
          var izle = new ResizeObserver(function () { g.resize(); });
          izle.observe(kap);
          g.__izle = izle;
        }
        g.off("click");
        if (ayar.onIl) {
          g.on("click", function (p) { var ad = p && p.name && AD[katla(p.name)]; if (ad && veri[ad]) ayar.onIl(ad); });
        }

        function ipucu(p) {
          var ad = p.name, v = veri[ad];
          var s = "<b style='font-size:13px'>" + ad + "</b><br/>";
          if (!v) return s + "<span style='color:#94a3b8'>" + m.yok + "</span>";
          s += "<span style='color:#0A1628;font-weight:700'>" + v.adet.toLocaleString("tr-TR") + "</span> " + birim;
          var ilceler = agac[ad] || [];
          if (ilceler.length) {
            s += "<div style='margin-top:6px;color:#64748b;font-size:11px'>" + m.ilceler + "</div>";
            ilceler.slice(0, 6).forEach(function (c) { s += "<div style='font-size:11px'>" + c.ilce + ": <b>" + c.ci + "</b></div>"; });
            if (ilceler.length > 6) s += "<div style='font-size:11px;color:#94a3b8'>+" + (ilceler.length - 6) + " " + m.diger + "</div>";
          }
          if (ayar.onIl) s += "<div style='margin-top:6px;font-size:10px;color:#94a3b8'>" + m.tikla + "</div>";
          return s;
        }

        g.setOption({
          textStyle: { fontFamily: YAZI },
          title: { text: m.baslik, subtext: m.ozet(adlar.length, toplam.toLocaleString("tr-TR"), birim), left: 16, top: 12,
                   textStyle: { fontSize: 14, fontWeight: 800, color: RENK.lacivert }, subtextStyle: { fontSize: 12, color: "#64748b" } },
          tooltip: { trigger: "item", formatter: ipucu, backgroundColor: "#ffffff", borderColor: "#e2e8f0", padding: [8, 10],
                     extraCssText: "box-shadow:0 6px 18px rgba(15,23,42,.12);border-radius:10px;" },
          visualMap: { type: "continuous", min: 0, max: enCok, seriesIndex: 0, left: 16, bottom: 16, itemHeight: 110, calculable: false,
                       text: [m.cok, m.az], textStyle: { color: "#64748b", fontSize: 11 }, inRange: { color: ["#E0ECF8", "#7FA7D4", "#1A5276"] },
                       show: toplam > 0 },
          geo: { map: HARITA, roam: true, aspectScale: 0.78, layoutCenter: ["50%", "54%"], layoutSize: "118%", scaleLimit: { min: 0.8, max: 8 },
                 itemStyle: { areaColor: RENK.zemin, borderColor: "#ffffff", borderWidth: 0.8 },
                 emphasis: { itemStyle: { areaColor: "#FFE680" }, label: { show: true, color: RENK.lacivert, fontWeight: 700, fontSize: 11 } },
                 select: { disabled: true }, label: { show: false } },
          series: [
            { type: "map", geoIndex: 0, name: m.baslik,
              data: ILLER.map(function (ad) {
                var v = veri[ad];
                return { name: ad, value: v ? v.adet : null,
                         itemStyle: ad === secili ? { borderColor: RENK.turuncu, borderWidth: 2.5 } : (v ? undefined : { areaColor: RENK.zemin }) };
              }) },
            { type: "scatter", coordinateSystem: "geo", symbol: "pin", zlevel: 2,
              data: adlar.filter(function (k) { return veri[k].boylam != null; }).map(function (k) {
                var v = veri[k];
                return { name: k, value: [v.boylam, v.enlem, v.adet], symbolSize: pinBoy(v.adet),
                         itemStyle: { color: k === secili ? RENK.turuncu : RENK.sari } };
              }),
              itemStyle: { borderColor: RENK.lacivert, borderWidth: 1, shadowBlur: 6, shadowColor: "rgba(10,22,40,.35)" },
              label: { show: true, formatter: function (p) { var n = p.value[2]; return n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 0 : 1) + m.bin : String(n); },
                       color: RENK.lacivert, fontSize: 10, fontWeight: 800, offset: [0, -3] },
              emphasis: { scale: 1.15, label: { fontSize: 11 } } },
            { type: "effectScatter", coordinateSystem: "geo", zlevel: 1, rippleEffect: { brushType: "stroke", scale: 3, period: 3 },
              data: secili && veri[secili] && veri[secili].boylam != null ? [{ name: secili, value: [veri[secili].boylam, veri[secili].enlem] }] : [],
              symbolSize: 14, itemStyle: { color: RENK.turuncu }, silent: true }
          ],
          animationDuration: 600
        }, true);
        return true;
      });
    }).catch(function (e) {
      if (window.console) console.warn("topo-harita:", e && e.message ? e.message : e);
      return false;
    });
  }

  function birak(kap) {
    var g = grafikler.get(kap);
    if (g) {
      if (g.__izle) g.__izle.disconnect();
      g.dispose();
      grafikler.delete(kap);
    }
  }

  window.TamlifeHarita = { ciz: ciz, birak: birak };
})();
