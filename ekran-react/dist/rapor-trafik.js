/*
 * TAM Life - Aylik rapor devre grafikleri (React paketinden AYRI kod).
 * Cizim: Apache ECharts 6.1.0 (echarts-6.1.0.min.js, Apache-2.0; lisans: echarts-6.1.0.LICENSE.txt).
 *
 * Veri ReportDB'den (backend/app/rapor/loe.py, LOE sorgusu): devre basina saatlik gecikme, jitter, paket kaybi (+ trafik, kaynak
 * sutunu tanimlaninca). Tarih araligi raporun donemi; saat araligi ve gosterilecek veriler (Trafik, Paket kaybi, Jitter, Gecikme)
 * kutudan secilir, musteriye kalicidir. Secilen veriler her devre icin TEK grafikte cizilir; devre sayisinda sinir yok.
 *
 * Iki giris noktasi (ikisini de rapor sayfasi cagirir):
 *  - gorseller(getir, adres, dil): GET .../rapor/trafik?donem= -> devre basina 1 grafik (PNG data URL) -> onizlemedeki grafik
 *    listesine katilir; PDF (html2canvas + jsPDF) bunlari diger grafikler gibi alir. Veri yoksa ECharts hic yuklenmez.
 *  - devreKutusu(kap, {taban, adres, dil, getir, istek, yenile}): "Devre grafikleri" bolumu (veri secimi, saat araligi, arama,
 *    secili devreler). Arama ReportDB CMDB kopyasinda (CI adi, aciklama, port ...).
 */
(function () {
  "use strict";

  var ECHARTS = "echarts-6.1.0.min.js";
  var betik = document.currentScript;
  var KOK = betik && betik.src ? new URL(".", betik.src).href : "/";
  var TR_SAAT = 3 * 3600 * 1000; // ReportDB zamanlari Turkiye saati

  var RENK = { lacivert: "#002855", sari: "#e8a400", mavi: "#0284c7", mor: "#7c3aed", kirmizi: "#be123c", gri: "#64748b", cizgi: "#e2e8f0" };
  var YAZI = "'Segoe UI', Calibri, Arial, sans-serif";
  var GENISLIK = 900, YUKSEKLIK = 380, PIKSEL = 2;
  var METRIKLER = ["trafik", "kayip", "jitter", "gecikme"];

  var METIN = {
    tr: {
      trafik: "Trafik", giris: "Giriş", cikis: "Çıkış", gecikme: "Gecikme", jitter: "Jitter", kayip: "Paket kaybı", erisim: "Erişilebilirlik",
      ort: "ort.", enYuksek: "en yüksek", p95: "%95", saatAraligi: "Saat aralığı", veriler: "Grafikte gösterilecek veriler",
      bolum: "Devre grafikleri (ReportDB)", ara: "Açıklama, port ya da CI adı yazın (en az 3 karakter)", ekle: "Ekle", ekli: "Ekli",
      kaldir: "Kaldır", secili: "Seçili devreler", seciliYok: "Henüz devre seçilmedi.", sonucYok: "Eşleşen devre bulunamadı.",
      fazla: "ilk 100 sonuç gösteriliyor", toplam: "eşleşme", hazir: "Hazır", bekliyor: "Veri hazırlanıyor (birkaç dakika)",
      veriYok: "Bu dönemde ölçüm yok", kaldirOnay: "Bu devre rapordan kaldırılsın mı?", metrikYok: "Grafik için en az bir veri seçin.",
      noYok: "Kartta Müşteri No olmadığı için devre aranamıyor.", cmdbYok: "ReportDB CMDB verisi henüz alınamadı", olcumHata: "Son ölçüm çekimi başarısız",
      salt: "Bu kartta değişiklik yetkiniz yok; ayarlar ve seçili devreler gösteriliyor.", hata: "İşlem yapılamadı",
      trafikYok: "ReportDB'de trafik sütunu henüz tanımlı değil (tablo yetkisi bekleniyor).", aylikLoe: "LOE aylık", kesinti: "Kesinti",
      kaynak: "Kaynak: ReportDB · saatlik ölçüm · gecikme, jitter ve paket kaybı günlük ortalama · gri alan hafta sonu",
      ay: ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
    },
    en: {
      trafik: "Traffic", giris: "Inbound", cikis: "Outbound", gecikme: "Delay", jitter: "Jitter", kayip: "Packet loss", erisim: "Availability",
      ort: "avg", enYuksek: "peak", p95: "95th", saatAraligi: "Hour range", veriler: "Data shown on the chart",
      bolum: "Circuit charts (ReportDB)", ara: "Type a description, port or CI name (min. 3 characters)", ekle: "Add", ekli: "Added",
      kaldir: "Remove", secili: "Selected circuits", seciliYok: "No circuit selected yet.", sonucYok: "No matching circuit.",
      fazla: "showing first 100 results", toplam: "matches", hazir: "Ready", bekliyor: "Preparing data (a few minutes)",
      veriYok: "No measurement this period", kaldirOnay: "Remove this circuit from the report?", metrikYok: "Select at least one data type for the chart.",
      noYok: "This card has no Customer No, so circuits cannot be searched.", cmdbYok: "ReportDB CMDB data not received yet", olcumHata: "Last measurement fetch failed",
      salt: "You cannot change this card; settings and selected circuits are shown.", hata: "Action failed",
      trafikYok: "Traffic column is not defined in ReportDB yet (awaiting table access).", aylikLoe: "LOE monthly", kesinti: "Outage",
      kaynak: "Source: ReportDB · hourly measurement · delay, jitter and packet loss as daily average · grey area weekend",
      ay: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    }
  };
  function dilSec(d) { return d === "en" ? "en" : "tr"; }

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

  // --- Bicimler ----------------------------------------------------------------------------------------------------------
  function sayi(x, dil, basamak) {
    return x.toLocaleString(dil === "en" ? "en-US" : "tr-TR", { minimumFractionDigits: basamak, maximumFractionDigits: basamak });
  }
  function serbest(x, dil) { return sayi(x, dil, Math.abs(x) >= 100 ? 0 : Math.abs(x) >= 10 ? 1 : 2); }
  function yuzde(x, dil, basamak) { return x == null || !isFinite(x) ? "—" : "%" + sayi(x * 100, dil, basamak); }
  function ms(x, dil) { return x == null || !isFinite(x) ? "—" : serbest(x, dil) + " ms"; }
  function bps(x, dil) {
    if (x == null || !isFinite(x)) return "—";
    var b = Math.abs(x), k = [[1e9, "Gbps"], [1e6, "Mbps"], [1e3, "Kbps"]];
    for (var i = 0; i < k.length; i++) if (b >= k[i][0]) return serbest(x / k[i][0], dil) + " " + k[i][1];
    return serbest(x, dil) + " bps";
  }
  function iki(n) { return (n < 10 ? "0" : "") + n; }
  function saatMetni(saat) { return iki(saat[0]) + ":00–" + iki(saat[1]) + ":59"; }
  function tarih(v, dil) { var t = new Date(v); return t.getDate() + " " + METIN[dil].ay[t.getMonth()]; }
  function aralik(yil, ay) { return [Date.UTC(yil, ay - 1, 1) - TR_SAAT, Date.UTC(ay === 12 ? yil + 1 : yil, ay % 12, 1) - TR_SAAT]; }

  function saatte(t, saat) {
    var h = new Date(t + TR_SAAT).getUTCHours();
    return saat[0] <= saat[1] ? h >= saat[0] && h <= saat[1] : h >= saat[0] || h <= saat[1];
  }

  function istatistik(d) {
    d = d.filter(function (x) { return x != null && isFinite(x); });
    if (!d.length) return null;
    var t = 0, e = -Infinity;
    d.forEach(function (x) { t += x; if (x > e) e = x; });
    var s = d.slice().sort(function (a, b) { return a - b; });
    return { ort: t / d.length, enYuksek: e, p95: s[Math.max(0, Math.ceil(s.length * 0.95) - 1)] };
  }

  // --- Tek grafik (rapor gorseli) -----------------------------------------------------------------------------------------
  // Okuyucu: musteri yoneticileri. Ust kisim bir bakista ozet (devre, donem, ozet kutucuklari); altta birim basina bir panel,
  // her panel tek eksen. Trafik saatlik (gunluk desen gorunsun), kalite verileri gunluk ortalama (saatlik gurultu yerine egilim).
  // Hafta sonlari hafif gri, kesintiler kirmizi bant. Renkler dataviz dogrulayicisindan gecti (panel ici ciftler, acik zemin).
  var C = {
    giris: "#2a78d6", cikis: "#eb6834", gecikme: "#6250d6", jitter: "#1baf7a", kayip: "#e34948",
    metin: "#0b1f3a", ikincil: "#52606d", soluk: "#8a96a3", izgara: "#e8edf2", kutu: "#f4f7fa", haftaSonu: "rgba(100,116,139,0.07)",
    kesinti: "rgba(227,73,72,0.14)"
  };
  var BIRIM = [[1e9, "Gbps"], [1e6, "Mbps"], [1e3, "Kbps"], [1, "bps"]];

  function gunAnahtari(t) { return Math.floor((t + TR_SAAT) / 864e5); }
  function gunOrtasi(g) { return g * 864e5 - TR_SAAT + 432e5; }

  /** Saat araligindaki noktalarin gunluk ortalamasi: [[gun ortasi ms, ortalama], ...] */
  function gunlukOrtalama(nk, i, carpan, saat) {
    var gun = {};
    nk.forEach(function (n) {
      if (n[i] == null || !saatte(n[0], saat)) return;
      var k = gunAnahtari(n[0]), g = gun[k] || (gun[k] = [0, 0]);
      g[0] += n[i] * carpan;
      g[1] += 1;
    });
    return Object.keys(gun).sort().map(function (k) { return [gunOrtasi(Number(k)), gun[k][0] / gun[k][1]]; });
  }

  function haftaSonlari(yil, ay) {
    var r = aralik(yil, ay), alanlar = [];
    for (var t = r[0]; t < r[1]; t += 864e5) {
      var g = new Date(t + TR_SAAT).getUTCDay();
      if (g === 6) alanlar.push([{ xAxis: t }, { xAxis: Math.min(t + 2 * 864e5, r[1]) }]);
    }
    if (new Date(r[0] + TR_SAAT).getUTCDay() === 0) alanlar.unshift([{ xAxis: r[0] }, { xAxis: r[0] + 864e5 }]);
    return alanlar;
  }

  function kesintiler(nk) {
    var alanlar = [], bas = null;
    nk.forEach(function (n, i) {
      var yok = n[1] != null && n[1] < 0.5;
      if (yok && bas === null) bas = n[0];
      if ((!yok || i === nk.length - 1) && bas !== null) {
        alanlar.push([{ xAxis: bas }, { xAxis: yok ? n[0] + 3600e3 : n[0] }]);
        bas = null;
      }
    });
    return alanlar;
  }

  function devreSecenek(devre, yil, ay, ayar, dil) {
    dil = dilSec(dil);
    var m = METIN[dil], nk = devre.noktalar || [], o = devre.ozet || {};
    var metrikler = (ayar && ayar.metrikler) || [], saat = (ayar && ayar.saat) || [0, 23];
    var r = aralik(yil, ay);
    var paneller = [], seriler = [], kutular = [], lejant = [];
    var golge = haftaSonlari(yil, ay), kes = kesintiler(nk);
    function deger(i, carpan) { return nk.filter(function (n) { return saatte(n[0], saat); }).map(function (n) { return n[i] == null ? null : n[i] * carpan; }); }

    if (o.erisilebilirlik != null) kutular.push([m.erisim, yuzde(o.erisilebilirlik, dil, 3), m.aylikLoe]);

    if (metrikler.indexOf("trafik") >= 0) {
      var sg = istatistik(deger(6, 1)), sc = istatistik(deger(7, 1));
      if (sg || sc) {
        var enUst = Math.max(sg ? sg.enYuksek : 0, sc ? sc.enYuksek : 0), b = BIRIM[BIRIM.length - 1];
        for (var k = 0; k < BIRIM.length; k++) if (enUst >= BIRIM[k][0]) { b = BIRIM[k]; break; }
        var bol = b[0];
        var veri = function (i) { return nk.map(function (n) { return [n[0], saatte(n[0], saat) && n[i] != null ? n[i] / bol : null]; }); };
        paneller.push({ ad: m.trafik, birim: b[1], boy: 150, ondalik: enUst / bol < 10 ? 1 : 0 });
        var p = paneller.length - 1;
        seriler.push({ name: m.giris, type: "line", xAxisIndex: p, yAxisIndex: p, data: veri(6), showSymbol: false, connectNulls: false, sampling: "lttb",
          lineStyle: { width: 1.5, color: C.giris }, itemStyle: { color: C.giris },
          areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: "rgba(42,120,214,0.30)" }, { offset: 1, color: "rgba(42,120,214,0.02)" }] } },
          markArea: { silent: true, data: golge.map(function (a) { return [{ xAxis: a[0].xAxis, itemStyle: { color: C.haftaSonu } }, a[1]]; }) },
          markLine: sg ? { silent: true, symbol: "none", lineStyle: { type: "dashed", width: 1, color: C.giris },
            label: { position: "insideEndTop", formatter: m.p95 + " " + m.giris.toLowerCase() + "  " + bps(sg.p95, dil), color: C.metin, fontSize: 10, fontWeight: 700,
              backgroundColor: "rgba(255,255,255,0.9)", padding: [1, 4], borderRadius: 3 },
            data: [{ yAxis: sg.p95 / bol }] } : undefined });
        seriler.push({ name: m.cikis, type: "line", xAxisIndex: p, yAxisIndex: p, data: veri(7), showSymbol: false, connectNulls: false, sampling: "lttb",
          lineStyle: { width: 1.5, color: C.cikis }, itemStyle: { color: C.cikis } });
        lejant.push(m.giris, m.cikis);
        if (sg) kutular.push([m.trafik + " " + m.giris.toLowerCase() + " " + m.p95, bps(sg.p95, dil), m.ort + " " + bps(sg.ort, dil)]);
        if (sc) kutular.push([m.trafik + " " + m.cikis.toLowerCase() + " " + m.p95, bps(sc.p95, dil), m.ort + " " + bps(sc.ort, dil)]);
      }
    }

    var gecikmeVar = metrikler.indexOf("gecikme") >= 0, jitterVar = metrikler.indexOf("jitter") >= 0;
    if (gecikmeVar || jitterVar) {
      var gs = gecikmeVar ? gunlukOrtalama(nk, 2, 1, saat) : [], js = jitterVar ? gunlukOrtalama(nk, 3, 1, saat) : [];
      if (gs.length || js.length) {
        paneller.push({ olcekli: true, ad: gecikmeVar && jitterVar ? m.gecikme + (dil === "en" ? " and " : " ve ") + m.jitter.toLowerCase() : gecikmeVar ? m.gecikme : m.jitter, birim: "ms", boy: 120, ondalik: 1 });
        var q = paneller.length - 1;
        [[gecikmeVar, gs, m.gecikme, C.gecikme, 2], [jitterVar, js, m.jitter, C.jitter, 3]].forEach(function (t) {
          if (!t[0] || !t[1].length) return;
          var st = istatistik(deger(t[4], 1));
          seriler.push({ name: t[2], type: "line", xAxisIndex: q, yAxisIndex: q, data: t[1], smooth: 0.3, symbol: "circle", symbolSize: 4, showSymbol: true,
            lineStyle: { width: 2, color: t[3] }, itemStyle: { color: t[3], borderColor: "#fff", borderWidth: 1 } });
          lejant.push(t[2]);
          if (st) kutular.push([m[t[2] === m.gecikme ? "gecikme" : "jitter"] + " " + m.ort, ms(st.ort, dil), m.enYuksek + " " + ms(st.enYuksek, dil)]);
        });
        seriler.filter(function (s) { return s.xAxisIndex === q; })[0].markArea = { silent: true, data: golge.map(function (a) { return [{ xAxis: a[0].xAxis, itemStyle: { color: C.haftaSonu } }, a[1]]; }) };
      }
    }

    if (metrikler.indexOf("kayip") >= 0) {
      var ks = gunlukOrtalama(nk, 4, 100, saat), stk = istatistik(deger(4, 100));
      if (ks.length) {
        paneller.push({ ad: m.kayip, birim: "%", boy: 82, ondalik: 2 });
        var z = paneller.length - 1;
        seriler.push({ name: m.kayip, type: "bar", xAxisIndex: z, yAxisIndex: z, data: ks, barWidth: "58%",
          itemStyle: { color: C.kayip, borderRadius: [3, 3, 0, 0] },
          markArea: { silent: true, data: golge.map(function (a) { return [{ xAxis: a[0].xAxis, itemStyle: { color: C.haftaSonu } }, a[1]]; }) } });
        lejant.push(m.kayip);
        if (stk) kutular.push([m.kayip + " " + m.ort, yuzde(stk.ort / 100, dil, 3), m.enYuksek + " " + yuzde(stk.enYuksek / 100, dil, 2)]);
      }
    }
    if (!paneller.length) return null;

    // Kesinti bantlari: ilk panelin ilk serisine
    if (kes.length) {
      var ilk = seriler[0], eski = (ilk.markArea && ilk.markArea.data) || [];
      ilk.markArea = { silent: true, data: eski.concat(kes.map(function (a, i) {
        return [{ xAxis: a[0].xAxis, itemStyle: { color: C.kesinti },
          label: i === 0 ? { show: true, position: "top", distance: 2, formatter: m.kesinti, color: "#b42318", fontSize: 9.5, fontWeight: 700 } : { show: false } }, a[1]];
      })) };
    }

    // Yerlesim
    var SOL = 58, SAG = 24, UST_BASLIK = 54, KUTU_Y = UST_BASLIK + 6, KUTU_H = 58, PANEL_BASLIK = 22, ARA = 14;
    var y = KUTU_Y + KUTU_H + 20, grids = [], graphic = [];
    paneller.forEach(function (p, i) {
      graphic.push({ type: "text", left: SOL - 46, top: y, style: { text: p.ad, fill: C.metin, font: "700 12px " + YAZI } });
      graphic.push({ type: "text", right: SAG, top: y + 1, style: { text: p.birim, fill: C.soluk, font: "600 10.5px " + YAZI, textAlign: "right" } });
      y += PANEL_BASLIK;
      grids.push({ left: SOL, right: SAG, top: y, height: p.boy });
      y += p.boy + (i === paneller.length - 1 ? 0 : ARA + 8);
    });
    var EKSEN_ALT = 22, DIP = 30;
    var yukseklik = y + EKSEN_ALT + DIP;

    // Baslik: devre + donem
    var ayAdi = (dil === "en"
      ? ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
      : ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"])[ay - 1];
    graphic.push({ type: "text", left: 12, top: 12, style: { text: devre.baslik || devre.ci, fill: C.metin, font: "800 15px " + YAZI } });
    graphic.push({ type: "text", left: 12, top: 33, style: {
      text: (devre.baslik ? devre.ci + "   ·   " : "") + ayAdi + " " + yil + "   ·   " + m.saatAraligi + " " + saatMetni(saat),
      fill: C.ikincil, font: "600 10.5px " + YAZI } });

    // Ozet kutucuklari (en fazla 6, esit genislik)
    kutular = kutular.slice(0, 6);
    var kGen = GENISLIK - 24, adet = Math.max(kutular.length, 1), bosluk = 8, w = (kGen - bosluk * (adet - 1)) / adet;
    kutular.forEach(function (k, i) {
      var x = 12 + i * (w + bosluk);
      graphic.push({ type: "rect", left: x, top: KUTU_Y, shape: { width: w, height: KUTU_H, r: 6 }, style: { fill: C.kutu } });
      graphic.push({ type: "text", left: x + 10, top: KUTU_Y + 8, style: { text: k[0], fill: C.ikincil, font: "700 9.5px " + YAZI, width: w - 16, overflow: "truncate" } });
      graphic.push({ type: "text", left: x + 10, top: KUTU_Y + 21, style: { text: k[1], fill: C.metin, font: "800 17px " + YAZI } });
      graphic.push({ type: "text", left: x + 10, top: KUTU_Y + 42, style: { text: k[2], fill: C.soluk, font: "600 9.5px " + YAZI, width: w - 16, overflow: "truncate" } });
    });

    // Dip notu: tek satir
    graphic.push({ type: "text", left: 12, bottom: 10, style: {
      text: m.kaynak + (devre.exchours ? "   ·   EXCHOURS " + devre.exchours : ""), fill: C.soluk, font: "600 9.5px " + YAZI } });

    var son = paneller.length - 1;
    return {
      _yukseklik: yukseklik,
      animation: false,
      backgroundColor: "#ffffff",
      textStyle: { fontFamily: YAZI, color: C.metin },
      legend: { top: 14, right: SAG, icon: "roundRect", itemWidth: 12, itemHeight: 4, itemGap: 14, data: lejant,
        textStyle: { fontSize: 10.5, fontWeight: 700, color: C.ikincil } },
      graphic: graphic,
      grid: grids,
      xAxis: paneller.map(function (p, k) {
        return { type: "time", gridIndex: k, min: r[0], max: r[1], boundaryGap: false, axisLine: { lineStyle: { color: "#cfd8e3" } }, axisTick: { show: false },
          axisLabel: { show: k === son, color: C.ikincil, fontSize: 10, hideOverlap: true, formatter: function (v) { return tarih(v, dil); } },
          splitLine: { show: false } };
      }),
      yAxis: paneller.map(function (p, k) {
        return { type: "value", gridIndex: k, min: p.olcekli ? undefined : 0, scale: !!p.olcekli, splitNumber: p.boy < 100 ? 2 : 3, axisLine: { show: false }, axisTick: { show: false },
          axisLabel: { color: C.soluk, fontSize: 9.5, formatter: function (v) { return sayi(v, dil, v && v < 1 ? p.ondalik : v % 1 ? 1 : 0); } },
          splitLine: { lineStyle: { color: C.izgara } } };
      }),
      series: seriler
    };
  }

  function ciz(ec, secenek) {
    var kutu = document.createElement("div");
    var grafik = ec.init(kutu, null, { renderer: "canvas", width: GENISLIK, height: secenek._yukseklik || YUKSEKLIK, devicePixelRatio: PIKSEL });
    try {
      grafik.setOption(secenek);
      return grafik.getDataURL({ type: "png", pixelRatio: PIKSEL, backgroundColor: "#ffffff" });
    } finally {
      grafik.dispose();
    }
  }

  // --- Veri paylasimi: gorseller() son veriyi saklar, devre kutusu dinler -------------------------------------------------
  var sonVeri = {};
  var dinleyiciler = [];
  var pngOnbellek = {};
  function veriYayinla(adres, veri) {
    sonVeri[adres] = veri;
    dinleyiciler.slice().forEach(function (f) { try { f(adres, veri); } catch (e) { /* kutu kapanmis olabilir */ } });
  }
  function bekliyor(adres) { var v = sonVeri[adres]; return !!(v && v.bekliyor); }

  /** Rapor sayfasinin grafik girisi. Donus: [{anahtar, baslik, gorsel}] - hata ya da veri yoksa bos liste (rapor etkilenmez). */
  function gorseller(getir, adres, dil) {
    dil = dilSec(dil);
    var m = METIN[dil];
    return Promise.resolve()
      .then(function () { return getir(adres); })
      .then(function (veri) {
        veriYayinla(adres, veri);
        var ayar = (veri && veri.ayar) || { metrikler: [], saat: [0, 23] };
        var liste = ((veri && veri.devreler) || []).filter(function (d) { return d && d.noktalar && d.noktalar.length; });
        if (!liste.length || !ayar.metrikler.length) return [];
        return echartsYukle().then(function (ec) {
          var cikti = [];
          liste.forEach(function (d) {
            var k = [d.id, d.cekildi, dil, veri.yil, veri.ay, ayar.metrikler.join(","), ayar.saat.join("-")].join("|");
            if (!(k in pngOnbellek)) {
              var s = devreSecenek(d, veri.yil, veri.ay, ayar, dil);
              pngOnbellek[k] = s ? ciz(ec, s) : null;
            }
            if (pngOnbellek[k]) {
              var adlar = METRIKLER.filter(function (x) { return ayar.metrikler.indexOf(x) >= 0; }).map(function (x) { return m[x].toLowerCase(); });
              cikti.push({ anahtar: "devre-" + d.id, baslik: d.ci + (d.baslik ? " · " + d.baslik : "") + " — " + adlar.join(", "), gorsel: pngOnbellek[k] });
            }
          });
          return cikti;
        });
      })
      .catch(function (e) {
        if (window.console) console.warn("rapor-trafik:", e && e.message ? e.message : e);
        return [];
      });
  }

  // --- Devre kutusu ------------------------------------------------------------------------------------------------------
  function el(etiket, stil, metin) {
    var e = document.createElement(etiket);
    if (stil) e.setAttribute("style", stil);
    if (metin != null) e.textContent = metin;
    return e;
  }
  var S = {
    kart: "margin-top:16px;border:1px solid #e2e8f0;border-radius:12px;background:#fff;padding:16px;font-family:" + YAZI + ";color:#002855;text-transform:none;letter-spacing:normal",
    baslik: "font-size:14px;font-weight:800;margin:0 0 12px;text-transform:uppercase",
    etiket: "font-size:11.5px;font-weight:800;color:#334155;margin:0 0 6px",
    secenekler: "display:flex;flex-wrap:wrap;gap:6px 16px;margin-bottom:12px",
    kutucuk: "display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:600;color:#0f172a;cursor:pointer",
    saatSatir: "display:flex;align-items:center;gap:8px;margin-bottom:12px;font-size:13px;color:#0f172a",
    secim: "border:1px solid #cbd5e1;border-radius:8px;padding:5px 8px;font-size:13px;color:#0f172a;background:#fff",
    girdi: "width:100%;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:8px;padding:8px 10px;font-size:13px;color:#0f172a;background:#fff",
    satir: "display:flex;align-items:flex-start;gap:10px;justify-content:space-between;padding:8px 0;border-top:1px solid #f1f5f9",
    ci: "font-size:13px;font-weight:700;word-break:break-all",
    kucuk: "font-size:11.5px;color:#64748b;margin-top:2px;word-break:break-word",
    dugme: "flex:none;border:1px solid #002855;background:#002855;color:#fff;border-radius:8px;padding:5px 12px;font-size:12px;font-weight:700;cursor:pointer",
    dugme2: "flex:none;border:1px solid #cbd5e1;background:#fff;color:#334155;border-radius:8px;padding:5px 12px;font-size:12px;font-weight:700;cursor:pointer",
    pasif: "flex:none;border:1px solid #e2e8f0;background:#f8fafc;color:#94a3b8;border-radius:8px;padding:5px 12px;font-size:12px;font-weight:700",
    uyari: "font-size:12px;color:#92400e;background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:6px 10px;margin:0 0 10px",
    hata: "font-size:12px;color:#be123c;margin-top:6px",
    altBaslik: "font-size:11.5px;font-weight:800;color:#334155;margin:14px 0 2px"
  };
  var ROZET = { hazir: "#15803d", bekliyor: "#b45309", veri_yok: "#64748b" };

  function devreKutusu(kap, p) {
    if (!kap) return;
    var dil = dilSec(p.dil);
    var imza = [p.taban, p.adres, dil].join("|");
    if (kap._tl && kap._tl.imza === imza) { kap._tl.p = p; return; }
    if (kap._tl) kap._tl.kapat();
    var m = METIN[dil];
    var durum = { p: p, imza: imza, veri: sonVeri[p.adres] || null, sonuc: null, aranan: "", mesaj: "", calisiyor: false };
    kap.textContent = "";
    var kart = el("section", S.kart);
    kart.setAttribute("lang", dil);
    kart.appendChild(el("h3", S.baslik, m.bolum));
    var uyari = el("div", "");
    kart.appendChild(uyari);

    // Veri secimi (Trafik, Paket kaybi, Jitter, Gecikme) ve saat araligi
    kart.appendChild(el("div", S.etiket, m.veriler));
    var secenekKap = el("div", S.secenekler);
    var kutucuklar = {};
    METRIKLER.forEach(function (ad) {
      var l = el("label", S.kutucuk), c = el("input", "width:15px;height:15px;accent-color:#002855;cursor:pointer");
      c.type = "checkbox";
      c.addEventListener("change", ayarKaydet);
      l.appendChild(c);
      l.appendChild(document.createTextNode(m[ad]));
      kutucuklar[ad] = { kutu: c, etiket: l };
      secenekKap.appendChild(l);
    });
    kart.appendChild(secenekKap);
    var saatSatir = el("div", S.saatSatir);
    saatSatir.appendChild(el("span", "font-size:11.5px;font-weight:800;color:#334155", m.saatAraligi));
    function saatSecimi(son) {
      var s = el("select", S.secim);
      for (var h = 0; h < 24; h++) {
        var o = el("option", "", iki(h) + (son ? ":59" : ":00"));
        o.value = String(h);
        s.appendChild(o);
      }
      s.addEventListener("change", ayarKaydet);
      return s;
    }
    var basSec = saatSecimi(false), bitSec = saatSecimi(true);
    saatSatir.appendChild(basSec);
    saatSatir.appendChild(el("span", "color:#64748b", "–"));
    saatSatir.appendChild(bitSec);
    kart.appendChild(saatSatir);
    var metrikUyari = el("div", S.kucuk + ";margin:-6px 0 10px;color:#b45309");
    kart.appendChild(metrikUyari);

    var aramaKap = el("div", "");
    var girdi = el("input", S.girdi);
    girdi.type = "search";
    girdi.placeholder = m.ara;
    girdi.maxLength = 200;
    girdi.setAttribute("aria-label", m.ara);
    aramaKap.appendChild(girdi);
    var sonucKap = el("div", "");
    aramaKap.appendChild(sonucKap);
    kart.appendChild(aramaKap);
    kart.appendChild(el("div", S.altBaslik, m.secili));
    var seciliKap = el("div", "");
    kart.appendChild(seciliKap);
    var mesaj = el("div", S.hata);
    kart.appendChild(mesaj);
    kap.appendChild(kart);

    function hataMetni(e) { return (e && e.message) || m.hata; }
    function islem(f, sonra) {
      if (durum.calisiyor) return;
      durum.calisiyor = true;
      durum.mesaj = "";
      Promise.resolve().then(f).catch(function (e) { durum.mesaj = hataMetni(e); }).then(function () {
        durum.calisiyor = false;
        ciz2();
        if (durum.p.yenile) durum.p.yenile();
        if (sonra) sonra();
      });
    }

    function ayarKaydet() {
      var v = durum.veri;
      if (!v || !v.duzenleyebilir) return;
      var yeni = {
        metrikler: METRIKLER.filter(function (ad) { return kutucuklar[ad].kutu.checked; }),
        bas: Number(basSec.value), bit: Number(bitSec.value)
      };
      v.ayar = { metrikler: yeni.metrikler, saat: [yeni.bas, yeni.bit] }; // ekranda hemen; sunucu yaniti yenile() ile gelir
      ciz2();
      islem(function () { return durum.p.istek("PUT", durum.p.taban + "/devre-ayar", yeni); });
    }

    function ciz2() {
      var v = durum.veri, duz = !v || v.duzenleyebilir;
      kart.style.display = v && typeof v.duzenleyebilir !== "boolean" ? "none" : "";
      uyari.textContent = "";
      if (v && v.kaynak) {
        var c = v.kaynak.cmdb || {}, o = v.kaynak.olcum || {};
        if (!c.son_basari) uyari.appendChild(el("div", S.uyari, m.cmdbYok + (c.hata ? ": " + c.hata : ".")));
        if (o.hata) uyari.appendChild(el("div", S.uyari, m.olcumHata + ": " + o.hata));
      }
      if (v && !v.duzenleyebilir) uyari.appendChild(el("div", S.uyari, m.salt));
      // ayar denetimleri
      var ayar = (v && v.ayar) || { metrikler: [], saat: [0, 23] };
      METRIKLER.forEach(function (ad) {
        var k = kutucuklar[ad], kapali = !duz || !v || (ad === "trafik" && !v.trafik_var);
        k.kutu.checked = ayar.metrikler.indexOf(ad) >= 0;
        k.kutu.disabled = kapali || durum.calisiyor;
        k.etiket.style.opacity = ad === "trafik" && v && !v.trafik_var ? "0.5" : "1";
        k.etiket.title = ad === "trafik" && v && !v.trafik_var ? m.trafikYok : "";
      });
      basSec.value = String(ayar.saat[0]);
      bitSec.value = String(ayar.saat[1]);
      basSec.disabled = bitSec.disabled = !duz || !v || durum.calisiyor;
      metrikUyari.textContent = v && !ayar.metrikler.length ? m.metrikYok : v && !v.trafik_var ? m.trafikYok : "";
      aramaKap.style.display = duz ? "" : "none";
      // secili devreler
      seciliKap.textContent = "";
      var liste = (v && v.devreler) || [];
      if (!liste.length) seciliKap.appendChild(el("div", S.kucuk, m.seciliYok));
      liste.forEach(function (d) {
        var satir = el("div", S.satir), sol = el("div", "min-width:0");
        sol.appendChild(el("div", S.ci, d.ci));
        if (d.baslik) sol.appendChild(el("div", S.kucuk, d.baslik));
        var o = d.ozet || {};
        var ozet = d.durum === "hazir"
          ? m.aylikLoe + ": " + m.erisim + " " + yuzde(o.erisilebilirlik, dil, 3) + " · " + m.gecikme + " " + ms(o.gecikme, dil) + " · " + m.jitter + " " + ms(o.jitter, dil) + " · " + m.kayip + " " + yuzde(o.kayip, dil, 3)
          : "";
        sol.appendChild(el("div", S.kucuk + ";font-weight:700;color:" + (ROZET[d.durum] || RENK.gri),
          (d.durum === "hazir" ? m.hazir : d.durum === "bekliyor" ? m.bekliyor : m.veriYok) + (ozet ? " — " + ozet : "")));
        satir.appendChild(sol);
        if (v.duzenleyebilir) {
          var b = el("button", S.dugme2, m.kaldir);
          b.type = "button";
          b.onclick = function () {
            if (!window.confirm(m.kaldirOnay + "\n" + d.ci)) return;
            islem(function () { return durum.p.istek("DELETE", durum.p.taban + "/devreler/" + d.id); }, aramaYenile);
          };
          satir.appendChild(b);
        }
        seciliKap.appendChild(satir);
      });
      mesaj.textContent = durum.mesaj;
      cizSonuc();
    }

    function cizSonuc() {
      sonucKap.textContent = "";
      var r = durum.sonuc;
      if (!r || !durum.aranan) return;
      if (!r.musteri_no_var) { sonucKap.appendChild(el("div", S.uyari + ";margin-top:8px", m.noYok)); return; }
      if (!r.sonuclar.length) { sonucKap.appendChild(el("div", S.kucuk + ";padding:8px 0", m.sonucYok)); return; }
      sonucKap.appendChild(el("div", S.kucuk + ";padding-top:8px", r.toplam + " " + m.toplam + (r.toplam > r.sonuclar.length ? " · " + m.fazla : "")));
      var secili = {};
      ((durum.veri && durum.veri.devreler) || []).forEach(function (d) { secili[d.ci] = true; });
      r.sonuclar.forEach(function (s) {
        var satir = el("div", S.satir), sol = el("div", "min-width:0");
        sol.appendChild(el("div", S.ci, s.ci));
        if (s.alanlar && s.alanlar.length) sol.appendChild(el("div", S.kucuk, s.alanlar.map(function (a) { return a[0] + ": " + a[1]; }).join(" · ")));
        satir.appendChild(sol);
        var ekli = secili[s.ci] || s.secili;
        var b = el("button", ekli ? S.pasif : S.dugme, ekli ? m.ekli : m.ekle);
        b.type = "button";
        b.disabled = !!ekli;
        if (!ekli) b.onclick = function () { islem(function () { return durum.p.istek("POST", durum.p.taban + "/devreler", { ci: s.ci }); }, aramaYenile); };
        satir.appendChild(b);
        sonucKap.appendChild(satir);
      });
    }

    var zamanlayici = null, sira = 0;
    function ara(q, hemen) {
      q = (q || "").trim();
      durum.aranan = q;
      clearTimeout(zamanlayici);
      if (q.length < 3) { durum.sonuc = null; cizSonuc(); return; }
      zamanlayici = setTimeout(function () {
        var no = ++sira;
        durum.p.getir(durum.p.taban + "/devre-ara?q=" + encodeURIComponent(q)).then(function (r) {
          if (no !== sira) return;
          durum.sonuc = r;
          cizSonuc();
        }).catch(function (e) { if (no === sira) { durum.mesaj = hataMetni(e); ciz2(); } });
      }, hemen ? 0 : 300);
    }
    function aramaYenile() { if (durum.aranan) ara(durum.aranan, true); }
    girdi.addEventListener("input", function () { ara(girdi.value); });

    function dinle(adres, veri) { if (adres === durum.p.adres) { durum.veri = veri; ciz2(); } }
    dinleyiciler.push(dinle);
    durum.kapat = function () {
      clearTimeout(zamanlayici);
      var i = dinleyiciler.indexOf(dinle);
      if (i >= 0) dinleyiciler.splice(i, 1);
    };
    kap._tl = durum;
    ciz2();
    if (!durum.veri && p.getir) {
      // Grafik sorgusu onbellekten geldiyse yayin olmaz: secili devre listesi icin veriyi kutu kendisi ister
      Promise.resolve().then(function () { return p.getir(p.adres); })
        .then(function (v) { if (!sonVeri[p.adres]) veriYayinla(p.adres, v); })
        .catch(function (e) { durum.mesaj = hataMetni(e); ciz2(); });
    }
  }

  window.TamlifeTrafik = {
    surum: "3", echarts: "6.1.0", gorseller: gorseller, devreKutusu: devreKutusu, bekliyor: bekliyor,
    devreSecenek: devreSecenek, echartsYukle: echartsYukle
  };
})();
