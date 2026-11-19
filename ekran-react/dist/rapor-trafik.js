/*
 * TAM Life - Aylik rapor trafik grafikleri (React paketinden AYRI kod).
 * Cizim: Apache ECharts 6.1.0 (echarts-6.1.0.min.js, Apache-2.0; lisans: echarts-6.1.0.LICENSE.txt).
 *
 * Akis: rapor sayfasi window.TamlifeTrafik.gorseller(getir, adres, dil) cagirir -> GET .../rapor/trafik (ReportDB serileri)
 * -> devre basina ECharts grafigi cizilir -> PNG (data URL) olarak doner -> onizlemedeki grafik listesine katilir.
 * PDF (html2canvas + jsPDF) bu gorselleri diger grafikler gibi alir. Veri yoksa ECharts hic yuklenmez.
 *
 * Veri sozlesmesi: backend/app/rapor/trafik.py. Birim bit/sn, zaman epoch ms.
 */
(function () {
  "use strict";

  var ECHARTS = "echarts-6.1.0.min.js";
  var betik = document.currentScript;
  var KOK = betik && betik.src ? new URL(".", betik.src).href : "/";

  // Rapor renkleri (rapor sablonu ile ayni: lacivert #002855, sari #ffc72c)
  var RENK = { lacivert: "#002855", sari: "#ffc72c", turuncu: "#e8a400", gri: "#64748b", cizgi: "#e2e8f0", kapasite: "#be123c" };
  var YAZI = "'Segoe UI', Calibri, Arial, sans-serif";

  // Rapor sayfasindaki gorsel genisligi (~180 mm); 2x piksel yogunlugu PDF'te keskin kalsin diye
  var GENISLIK = 900;
  var YUKSEKLIK = 360;
  var PIKSEL = 2;

  var METIN = {
    tr: { giris: "Giriş", cikis: "Çıkış", p95: "%95", hiz: "Devre hızı", enYuksek: "En yüksek", ortalama: "Ortalama", ay: ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"] },
    en: { giris: "Inbound", cikis: "Outbound", p95: "95th", hiz: "Circuit speed", enYuksek: "Peak", ortalama: "Average", ay: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] }
  };

  var yukleniyor = null;
  function echartsYukle() {
    if (window.echarts) return Promise.resolve(window.echarts);
    if (!yukleniyor) {
      yukleniyor = new Promise(function (tamam, hata) {
        var s = document.createElement("script");
        s.src = KOK + ECHARTS;
        s.async = true;
        s.onload = function () { window.echarts ? tamam(window.echarts) : hata(new Error(ECHARTS)); };
        s.onerror = function () { yukleniyor = null; hata(new Error(ECHARTS)); };
        document.head.appendChild(s);
      });
    }
    return yukleniyor;
  }

  function birim(bps, dil) {
    if (bps == null || !isFinite(bps)) return "—";
    var b = Math.abs(bps), basamak = [[1e9, "Gbps"], [1e6, "Mbps"], [1e3, "Kbps"]];
    for (var i = 0; i < basamak.length; i++) {
      if (b >= basamak[i][0]) return sayi(bps / basamak[i][0], dil) + " " + basamak[i][1];
    }
    return sayi(bps, dil) + " bps";
  }

  function sayi(x, dil) {
    var basamak = Math.abs(x) >= 100 ? 0 : Math.abs(x) >= 10 ? 1 : 2;
    return x.toLocaleString(dil === "en" ? "en-US" : "tr-TR", { maximumFractionDigits: basamak });
  }

  function istatistik(degerler) {
    var d = degerler.filter(function (x) { return x != null && isFinite(x); });
    if (!d.length) return null;
    var toplam = 0, enYuksek = -Infinity;
    d.forEach(function (x) { toplam += x; if (x > enYuksek) enYuksek = x; });
    var sirali = d.slice().sort(function (a, b) { return a - b; });
    return { enYuksek: enYuksek, ortalama: toplam / d.length, p95: sirali[Math.max(0, Math.ceil(sirali.length * 0.95) - 1)] };
  }

  function tarih(ms, dil) {
    var t = new Date(ms);
    return t.getDate() + " " + METIN[dil].ay[t.getMonth()];
  }

  /** Bir devre icin ECharts secenegi (ayri sayfada onizleme / test icin de kullanilir). */
  function secenek(devre, dil) {
    dil = dil === "en" ? "en" : "tr";
    var m = METIN[dil];
    var noktalar = devre.noktalar || [];
    var giris = noktalar.map(function (n) { return [n[0], n[1]]; });
    var cikis = noktalar.map(function (n) { return [n[0], n[2]]; });
    var sg = istatistik(noktalar.map(function (n) { return n[1]; }));
    var sc = istatistik(noktalar.map(function (n) { return n[2]; }));
    var hiz = devre.hiz_bps > 0 ? devre.hiz_bps : null;

    function ozet(ad, s) {
      return s ? ad + "  " + m.enYuksek + " " + birim(s.enYuksek, dil) + " · " + m.ortalama + " " + birim(s.ortalama, dil) + " · " + m.p95 + " " + birim(s.p95, dil) : ad + "  —";
    }

    function p95Cizgisi(s, renk) {
      return s ? { silent: true, symbol: "none", lineStyle: { type: "dashed", width: 1.2, color: renk },
        label: { position: "insideEndTop", color: renk, fontSize: 10, fontWeight: 700, formatter: m.p95 + " " + birim(s.p95, dil),
          backgroundColor: "rgba(255,255,255,0.92)", padding: [2, 5], borderRadius: 3, borderColor: renk, borderWidth: 0.6 },
        data: [{ yAxis: s.p95 }] } : undefined;
    }

    var seriler = [
      { name: m.giris, type: "line", data: giris, showSymbol: false, sampling: "lttb", connectNulls: false,
        lineStyle: { width: 1.6, color: RENK.lacivert }, itemStyle: { color: RENK.lacivert },
        areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: "rgba(0,40,85,0.38)" }, { offset: 1, color: "rgba(0,40,85,0.04)" }] } },
        markLine: p95Cizgisi(sg, RENK.lacivert) },
      { name: m.cikis, type: "line", data: cikis, showSymbol: false, sampling: "lttb", connectNulls: false,
        lineStyle: { width: 1.6, color: RENK.turuncu }, itemStyle: { color: RENK.turuncu },
        areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: "rgba(255,199,44,0.42)" }, { offset: 1, color: "rgba(255,199,44,0.05)" }] } },
        markLine: p95Cizgisi(sc, RENK.turuncu) }
    ];
    if (hiz) {
      seriler.push({ name: m.hiz, type: "line", data: [], silent: true, itemStyle: { color: RENK.kapasite },
        markLine: { silent: true, symbol: "none", lineStyle: { type: "solid", width: 1.2, color: RENK.kapasite },
          label: { position: "insideStartTop", color: RENK.kapasite, fontSize: 10, fontWeight: 700, formatter: m.hiz + " " + birim(hiz, dil),
            backgroundColor: "rgba(255,255,255,0.92)", padding: [2, 5], borderRadius: 3 },
          data: [{ yAxis: hiz }] } });
    }

    var enUst = Math.max(sg ? sg.enYuksek : 0, sc ? sc.enYuksek : 0);
    return {
      animation: false,
      backgroundColor: "#ffffff",
      textStyle: { fontFamily: YAZI, color: RENK.lacivert },
      color: [RENK.lacivert, RENK.turuncu, RENK.kapasite],
      legend: { top: 4, right: 8, icon: "roundRect", itemWidth: 14, itemHeight: 6, textStyle: { fontSize: 11, fontWeight: 700, color: RENK.lacivert } },
      title: { left: 8, bottom: 2, text: "", subtext: ozet(m.giris, sg) + "\n" + ozet(m.cikis, sc), subtextStyle: { fontSize: 10.5, lineHeight: 15, color: RENK.gri, fontWeight: 600 } },
      grid: { left: 64, right: 18, top: 34, bottom: 74 },
      xAxis: { type: "time", boundaryGap: false, axisLine: { lineStyle: { color: RENK.cizgi } }, axisTick: { show: false },
        axisLabel: { color: RENK.gri, fontSize: 10, hideOverlap: true, formatter: function (v) { return tarih(v, dil); } },
        splitLine: { show: false } },
      yAxis: { type: "value", min: 0, max: hiz && hiz > enUst ? Math.ceil(hiz * 1.08) : undefined,
        axisLabel: { color: RENK.gri, fontSize: 10, showMaxLabel: !(hiz && hiz > enUst), formatter: function (v) { return birim(v, dil); } },
        splitLine: { lineStyle: { color: RENK.cizgi, type: "dashed" } } },
      series: seriler
    };
  }

  function ciz(ec, devre, dil) {
    var kutu = document.createElement("div");
    var grafik = ec.init(kutu, null, { renderer: "canvas", width: GENISLIK, height: YUKSEKLIK, devicePixelRatio: PIKSEL });
    try {
      grafik.setOption(secenek(devre, dil));
      return grafik.getDataURL({ type: "png", pixelRatio: PIKSEL, backgroundColor: "#ffffff" });
    } finally {
      grafik.dispose();
    }
  }

  /**
   * Rapor sayfasinin cagirdigi giris noktasi.
   * getir: panelin oturumlu GET yardimcisi (JSON verisini doner); adres: .../rapor/trafik?donem=...; dil: 'tr' | 'en'.
   * Donus: [{anahtar, baslik, gorsel}] - hata ya da veri yoksa bos liste (rapor etkilenmez).
   */
  function gorseller(getir, adres, dil) {
    return Promise.resolve()
      .then(function () { return getir(adres); })
      .then(function (veri) {
        var liste = ((veri && veri.devreler) || []).filter(function (d) { return d && d.noktalar && d.noktalar.length; });
        if (!liste.length) return [];
        return echartsYukle().then(function (ec) {
          return liste.map(function (d, i) {
            return { anahtar: "trafik-" + (d.anahtar || i), baslik: d.baslik || d.ci || "", gorsel: ciz(ec, d, dil) };
          });
        });
      })
      .catch(function (e) {
        if (window.console) console.warn("rapor-trafik:", e && e.message ? e.message : e);
        return [];
      });
  }

  window.TamlifeTrafik = { surum: "1", echarts: "6.1.0", gorseller: gorseller, secenek: secenek, echartsYukle: echartsYukle };
})();
