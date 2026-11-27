/*! TAMLIFE (c) 2026 Giray Sav - Tum haklari saklidir. Izinsiz kopyalanamaz, dagitilamaz. */
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
  var GENISLIK = 900, YUKSEKLIK = 380, PIKSEL = 3; // 3x: PDF'te ve buyutmede yazilar keskin kalsin
  var METRIKLER = ["erisim", "trafik", "kayip", "jitter", "gecikme"]; // 2026-11-27: erisim de cizgi panel

  var METIN = {
    tr: {
      trafik: "Trafik", giris: "Inbound", cikis: "Outbound", son: "son",
      cozunurluk: function (a) { return "Trafik: " + (a >= 86400 ? "günlük" : a >= 3600 ? (a / 3600) + " saatlik" : (a / 60) + " dakikalık") + " ortalama (LookOutEyes ile aynı çözünürlük)"; }, gecikme: "Delay", jitter: "Jitter", kayip: "Packet Loss", erisim: "Availability",
      ort: "ort.", enYuksek: "en yüksek", p95: "%95", veriler: "Grafikte gösterilecek veriler",
      bolum: "Devre grafikleri", ara: "IMT, açıklama, port ya da CI adı yazın (en az 3 karakter)", ekle: "Ekle", ekli: "Ekli",
      uygula: "Uygula", uygulaNot: "Tarihleri seçip Uygula'ya basın",
      grafikAdi: "Grafik adı", grafikAdiIpucu: "Grafiğe bir ad verin (örn. Merkez internet hattı) — boş bırakılırsa CI adı kullanılır",
      adDegistir: "Adı değiştir", kaydet: "Kaydet", vazgec: "Vazgeç",
      imtOlustur: function (n) { return "Bu IMT ile grafik oluştur (" + n + " devre)"; }, imtEkli: "Bu IMT'nin devreleri ekli", imtNot: "IMT envanterde bulundu; trafik CI adı ve IMT ile eşleştirilir.",
      eslesme: { ci_imt: "trafik: CI adı + IMT eşleşti", ci: "trafik: CI adıyla eşleşti", imt: "trafik: IMT ile eşleşti" },
      kaldir: "Kaldır", secili: "Seçili devreler", seciliYok: "Henüz devre seçilmedi.", sonucYok: "Eşleşen devre bulunamadı.",
      fazla: "ilk 100 sonuç gösteriliyor", toplam: "eşleşme", hazir: "Hazır", bekliyor: "Veri hazırlanıyor (birkaç dakika)",
      veriYok: "Bu dönemde ölçüm yok", kaldirOnay: "Bu devre rapordan kaldırılsın mı?", metrikYok: "Grafik için en az bir veri seçin.",
      noYok: "Kartta Müşteri No olmadığı için devre aranamıyor.", cmdbYok: "Devre listesi henüz hazır değil; arama sonuç vermeyebilir.", olcumHata: "Ölçüm verisi şu an güncellenemiyor; son alınan veri gösteriliyor.",
      salt: "Bu kartta değişiklik yetkiniz yok; ayarlar ve seçili devreler gösteriliyor.", hata: "İşlem yapılamadı",
      trafikYok: "Trafik verisi henüz hazır değil.", aylikLoe: "Dönem", hizmetSaati: "Hizmet saati", tarihAraligi: "Tarih aralığı", raporDonemi: "Rapor dönemi", raporDonemiAcik: "Raporun dönemi kullanılıyor", aralikHata: "Bitiş, başlangıçtan sonra olmalı.", kesinti: "Kesinti",
      kaynak: "Saatlik ölçüm · gri alan hafta sonu",
      ay: ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
    },
    en: {
      trafik: "Traffic", giris: "Inbound", cikis: "Outbound", son: "last",
      cozunurluk: function (a) { return "Traffic: " + (a >= 86400 ? "daily" : a >= 3600 ? (a / 3600) + "-hour" : (a / 60) + "-minute") + " average (same resolution as LookOutEyes)"; }, gecikme: "Delay", jitter: "Jitter", kayip: "Packet Loss", erisim: "Availability",
      ort: "avg", enYuksek: "peak", p95: "95th", veriler: "Data shown on the chart",
      bolum: "Circuit charts", ara: "Type an IMT, description, port or CI name (min. 3 characters)", ekle: "Add", ekli: "Added",
      uygula: "Apply", uygulaNot: "Pick the dates and press Apply",
      grafikAdi: "Chart name", grafikAdiIpucu: "Name the chart (e.g. HQ internet line) — the CI name is used if left empty",
      adDegistir: "Rename", kaydet: "Save", vazgec: "Cancel",
      imtOlustur: function (n) { return "Create chart with this IMT (" + n + " circuit" + (n === 1 ? "" : "s") + ")"; }, imtEkli: "Circuits of this IMT are added", imtNot: "IMT found in inventory; traffic is matched by CI name and IMT.",
      eslesme: { ci_imt: "traffic: CI name + IMT matched", ci: "traffic: matched by CI name", imt: "traffic: matched by IMT" },
      kaldir: "Remove", secili: "Selected circuits", seciliYok: "No circuit selected yet.", sonucYok: "No matching circuit.",
      fazla: "showing first 100 results", toplam: "matches", hazir: "Ready", bekliyor: "Preparing data (a few minutes)",
      veriYok: "No measurement this period", kaldirOnay: "Remove this circuit from the report?", metrikYok: "Select at least one data type for the chart.",
      noYok: "This card has no Customer No, so circuits cannot be searched.", cmdbYok: "Circuit list is not ready yet; search may return no results.", olcumHata: "Measurement data cannot be updated right now; the last received data is shown.",
      salt: "You cannot change this card; settings and selected circuits are shown.", hata: "Action failed",
      trafikYok: "Traffic data is not ready yet.", aylikLoe: "Period", hizmetSaati: "Service hours", tarihAraligi: "Date range", raporDonemi: "Report period", raporDonemiAcik: "Using the report period", aralikHata: "End must be after start.", kesinti: "Outage",
      kaynak: "Hourly measurement · grey area weekend",
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
  function tarih(v, dil) { var t = new Date(v); return t.getDate() + " " + METIN[dil].ay[t.getMonth()]; }
  function zamanMetni(v) { var t = new Date(v + TR_SAAT); return iki(t.getUTCDate()) + "." + iki(t.getUTCMonth() + 1) + "." + t.getUTCFullYear() + " " + iki(t.getUTCHours()) + ":" + iki(t.getUTCMinutes()); }
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
    giris: "#3cc43c", cikis: "#1f3fd1",  // LookOutEyes renkleri: Inbound yesil alan, Outbound mavi cizgi gecikme: "#6250d6", jitter: "#1baf7a", kayip: "#e34948", erisim: "#0f766e",
    metin: "#0b1f3a", ikincil: "#1f2a37", soluk: "#2f3b48", izgara: "#e3e8ee", kutu: "#f4f7fa", haftaSonu: "rgba(100,116,139,0.07)",
    kesinti: "rgba(227,73,72,0.14)"
  };
  var BIRIM = [[1e9, "Gbps"], [1e6, "Mbps"], [1e3, "Kbps"], [1, "bps"]];

  function gunAnahtari(t) { return Math.floor((t + TR_SAAT) / 864e5); }
  function gunOrtasi(g) { return g * 864e5 - TR_SAAT + 432e5; }

  function haftaSonlari(r) {
    var alanlar = [], gun = Math.floor((r[0] + TR_SAAT) / 864e5) * 864e5 - TR_SAAT;
    for (var t = gun; t < r[1]; t += 864e5) {
      var g = new Date(t + TR_SAAT).getUTCDay();
      if (g === 6 || g === 0) alanlar.push([{ xAxis: Math.max(t, r[0]) }, { xAxis: Math.min(t + 864e5, r[1]) }]);
    }
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

  /** Tum veriler ayni bicimde: saatlik, ici dolu alan (cizgi + yukaridan asagi solan dolgu). */
  function alanSerisi(ad, renk, veri, panel) {
    var rgb = [1, 3, 5].map(function (i) { return parseInt(renk.substr(i, 2), 16); }).join(",");
    return { name: ad, type: "line", xAxisIndex: panel, yAxisIndex: panel, data: veri, showSymbol: false, connectNulls: false, sampling: "lttb",
      lineStyle: { width: 1.4, color: renk }, itemStyle: { color: renk },
      areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: "rgba(" + rgb + ",0.32)" }, { offset: 1, color: "rgba(" + rgb + ",0.03)" }] } } };
  }

  function devreSecenek(devre, ar, ayar, dil) {
    dil = dilSec(dil);
    var m = METIN[dil], nk = devre.noktalar || [], o = devre.ozet || {};
    var metrikler = (ayar && ayar.metrikler) || [], saat = [0, 23];
    var r = [ar.bas_ms, ar.bit_ms], gunler = (r[1] - r[0]) / 864e5;
    var paneller = [], seriler = [], kutular = [], lejant = [];
    var golge = haftaSonlari(r), kes = kesintiler(nk);
    function deger(i, carpan) { return nk.filter(function (n) { return saatte(n[0], saat); }).map(function (n) { return n[i] == null ? null : n[i] * carpan; }); }

    if (o.erisilebilirlik != null) kutular.push([m.erisim, yuzde(o.erisilebilirlik, dil, 3), m.aylikLoe]);

    if (metrikler.indexOf("erisim") >= 0) {
      var es = nk.map(function (n) { return [n[0], saatte(n[0], saat) && n[1] != null ? n[1] * 100 : null]; });
      if (es.some(function (x) { return x[1] != null; })) {
        paneller.push({ ad: m.erisim, birim: "%", boy: 80, ondalik: 2, olcekli: true });
        seriler.push(Object.assign(alanSerisi(m.erisim, C.erisim, es, paneller.length - 1), {
          markArea: { silent: true, data: golge.map(function (a) { return [{ xAxis: a[0].xAxis, itemStyle: { color: C.haftaSonu } }, a[1]]; }) } }));
        lejant.push(m.erisim);
      }
    }

    // 2026-11-27 kullanici: "LookOutEyes gosterimi ile ayni veriler" - trafik ayri seride, LookOutEyes'in arsiv cozunurlugunde
    // (sunucu: loe_trafik.cozunurluk / konsolide); Inbound yesil alan, Outbound mavi cizgi; Avg / Max / Last.
    var trafikNotu = "";
    if (metrikler.indexOf("trafik") >= 0 && devre.trafik && devre.trafik.noktalar && devre.trafik.noktalar.length) {
      var tr = devre.trafik, tn = tr.noktalar, sg = tr.giris, sc = tr.cikis;
      var enUst = Math.max(sg ? sg.en_yuksek : 0, sc ? sc.en_yuksek : 0), b = BIRIM[BIRIM.length - 1];
      for (var k = 0; k < BIRIM.length; k++) if (enUst >= BIRIM[k][0]) { b = BIRIM[k]; break; }
      var bol = b[0];
      paneller.push({ ad: m.trafik, birim: b[1], boy: 150, ondalik: enUst / bol < 10 ? 1 : 0 });
      var p = paneller.length - 1;
      seriler.push(Object.assign(alanSerisi(m.giris, C.giris, tn.map(function (n) { return [n[0], n[1] == null ? null : n[1] / bol]; }), p), {
        markArea: { silent: true, data: golge.map(function (a) { return [{ xAxis: a[0].xAxis, itemStyle: { color: C.haftaSonu } }, a[1]]; }) } }));
      seriler.push({ name: m.cikis, type: "line", xAxisIndex: p, yAxisIndex: p, showSymbol: false, connectNulls: false, sampling: "lttb",
        data: tn.map(function (n) { return [n[0], n[2] == null ? null : n[2] / bol]; }), lineStyle: { width: 1.4, color: C.cikis }, itemStyle: { color: C.cikis } });
      lejant.push(m.giris, m.cikis);
      if (sg) kutular.push([m.giris + " " + m.ort, bps(sg.ort, dil), m.son + " " + bps(sg.son, dil) + " · " + m.enYuksek + " " + bps(sg.en_yuksek, dil)]);
      if (sc) kutular.push([m.cikis + " " + m.ort, bps(sc.ort, dil), m.son + " " + bps(sc.son, dil) + " · " + m.enYuksek + " " + bps(sc.en_yuksek, dil)]);
      trafikNotu = m.cozunurluk(tr.adim);
    }

    var gecikmeVar = metrikler.indexOf("gecikme") >= 0, jitterVar = metrikler.indexOf("jitter") >= 0;
    if (gecikmeVar || jitterVar) {
      var saatlik = function (i, carpan) {
        var d = nk.map(function (n) { return [n[0], saatte(n[0], saat) && n[i] != null ? n[i] * carpan : null]; });
        return d.some(function (x) { return x[1] != null; }) ? d : [];
      };
      // olcum saniye cinsinden saklanir (LOE: DELAY_AVG / 1000); ekranda ms (2026-11-27: onceden "0,00 ms" gorunuyordu)
      var gs = gecikmeVar ? saatlik(2, 1000) : [], js = jitterVar ? saatlik(3, 1000) : [];
      if (gs.length || js.length) {
        paneller.push({ ad: gecikmeVar && jitterVar ? m.gecikme + " & " + m.jitter : gecikmeVar ? m.gecikme : m.jitter, birim: "ms", boy: 120, ondalik: 1 });
        var q = paneller.length - 1;
        [[gecikmeVar, gs, m.gecikme, C.gecikme, 2], [jitterVar, js, m.jitter, C.jitter, 3]].forEach(function (t) {
          if (!t[0] || !t[1].length) return;
          var st = istatistik(deger(t[4], 1000));
          seriler.push(alanSerisi(t[2], t[3], t[1], q));
          lejant.push(t[2]);
          if (st) kutular.push([m[t[2] === m.gecikme ? "gecikme" : "jitter"] + " " + m.ort, ms(st.ort, dil), m.enYuksek + " " + ms(st.enYuksek, dil)]);
        });
        seriler.filter(function (s) { return s.xAxisIndex === q; })[0].markArea = { silent: true, data: golge.map(function (a) { return [{ xAxis: a[0].xAxis, itemStyle: { color: C.haftaSonu } }, a[1]]; }) };
      }
    }

    if (metrikler.indexOf("kayip") >= 0) {
      var ks = nk.map(function (n) { return [n[0], saatte(n[0], saat) && n[4] != null ? n[4] * 100 : null]; }), stk = istatistik(deger(4, 100));
      if (stk) {
        paneller.push({ ad: m.kayip, birim: "%", boy: 90, ondalik: 2 });
        var z = paneller.length - 1;
        seriler.push(Object.assign(alanSerisi(m.kayip, C.kayip, ks, z), {
          markArea: { silent: true, data: golge.map(function (a) { return [{ xAxis: a[0].xAxis, itemStyle: { color: C.haftaSonu } }, a[1]]; }) } }));
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
          label: i === 0 ? { show: true, position: "top", distance: 2, formatter: m.kesinti, color: "#9f1c14", fontSize: 10.5, fontWeight: 700 } : { show: false } }, a[1]];
      })) };
    }

    // Yerlesim
    var SOL = 58, SAG = 24, UST_BASLIK = 54, KUTU_Y = UST_BASLIK + 6, KUTU_H = 72, PANEL_BASLIK = 22, ARA = 14;
    var y = KUTU_Y + KUTU_H + 20, grids = [], graphic = [];
    paneller.forEach(function (p, i) {
      graphic.push({ type: "text", left: SOL - 46, top: y, style: { text: p.ad, fill: C.metin, font: "800 13px " + YAZI } });
      graphic.push({ type: "text", right: SAG, top: y + 1, style: { text: p.birim, fill: C.ikincil, font: "700 11.5px " + YAZI, textAlign: "right" } });
      y += PANEL_BASLIK;
      grids.push({ left: SOL, right: SAG, top: y, height: p.boy });
      y += p.boy + (i === paneller.length - 1 ? 0 : ARA + 8);
    });
    var EKSEN_ALT = 22, DIP = 30;
    var yukseklik = y + EKSEN_ALT + DIP;

    // Baslik: devre + donem
    graphic.push({ type: "text", left: 12, top: 12, style: { text: devre.baslik || devre.ci, fill: C.metin, font: "800 15px " + YAZI } });
    graphic.push({ type: "text", left: 12, top: 33, style: {
      text: (devre.baslik ? devre.ci + "   ·   " : "") + zamanMetni(r[0]) + "  –  " + zamanMetni(r[1]),
      fill: C.ikincil, font: "600 11.5px " + YAZI } });

    // Ozet kutucuklari (en fazla 6, esit genislik)
    kutular = kutular.slice(0, 6);
    var kGen = GENISLIK - 24, adet = Math.max(kutular.length, 1), bosluk = 8, w = (kGen - bosluk * (adet - 1)) / adet;
    kutular.forEach(function (k, i) {
      var x = 12 + i * (w + bosluk);
      graphic.push({ type: "rect", left: x, top: KUTU_Y, shape: { width: w, height: KUTU_H, r: 6 }, style: { fill: C.kutu } });
      graphic.push({ type: "text", left: x + 10, top: KUTU_Y + 9, style: { text: k[0], fill: C.metin, font: "700 11px " + YAZI, width: w - 16, overflow: "truncate" } });
      graphic.push({ type: "text", left: x + 10, top: KUTU_Y + 25, style: { text: k[1], fill: C.metin, font: "800 20px " + YAZI } });
      graphic.push({ type: "text", left: x + 10, top: KUTU_Y + 52, style: { text: k[2], fill: C.ikincil, font: "600 11px " + YAZI, width: w - 16, overflow: "truncate" } });
    });

    // Dip notu: tek satir
    graphic.push({ type: "text", left: 12, bottom: 10, style: {
      text: m.kaynak + (trafikNotu ? "   ·   " + trafikNotu : "") + (devre.exchours ? "   ·   " + m.hizmetSaati + " " + devre.exchours : ""), fill: C.ikincil, font: "600 10.5px " + YAZI } });

    var son = paneller.length - 1;
    return {
      _yukseklik: yukseklik,
      animation: false,
      backgroundColor: "#ffffff",
      textStyle: { fontFamily: YAZI, color: C.metin },
      legend: { top: 14, right: SAG, icon: "roundRect", itemWidth: 12, itemHeight: 4, itemGap: 14, data: lejant,
        textStyle: { fontSize: 11.5, fontWeight: 700, color: C.metin } },
      graphic: graphic,
      grid: grids,
      xAxis: paneller.map(function (p, k) {
        return { type: "time", gridIndex: k, min: r[0], max: r[1], boundaryGap: false, axisLine: { lineStyle: { color: "#cfd8e3" } }, axisTick: { show: false },
          axisLabel: { show: k === son, color: C.metin, fontSize: 11, fontWeight: 600, hideOverlap: true, formatter: function (v) {
            var t = new Date(v + TR_SAAT);
            if (gunler <= 3) return tarih(v, dil) + " " + iki(t.getUTCHours()) + ":" + iki(t.getUTCMinutes());
            if (gunler > 200) return METIN[dil].ay[t.getUTCMonth()] + " " + t.getUTCFullYear();
            return tarih(v, dil);
          } },
          splitLine: { show: false } };
      }),
      yAxis: paneller.map(function (p, k) {
        return { type: "value", gridIndex: k, min: p.olcekli ? undefined : 0, scale: !!p.olcekli, splitNumber: p.boy < 100 ? 2 : 3, axisLine: { show: false }, axisTick: { show: false },
          axisLabel: { color: C.ikincil, fontSize: 10.5, fontWeight: 600, formatter: function (v) { return sayi(v, dil, v && v < 1 ? p.ondalik : v % 1 ? 1 : 0); } },
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
        var liste = ((veri && veri.devreler) || []).filter(function (d) { return d && ((d.noktalar && d.noktalar.length) || (d.trafik && d.trafik.noktalar && d.trafik.noktalar.length)); });
        if (!liste.length || !ayar.metrikler.length) return [];
        return echartsYukle().then(function (ec) {
          var cikti = [];
          liste.forEach(function (d) {
            var ar = veri.aralik || { bas_ms: aralik(veri.yil, veri.ay)[0], bit_ms: aralik(veri.yil, veri.ay)[1] };
            var k = [d.id, d.cekildi, dil, ar.bas_ms, ar.bit_ms, ayar.metrikler.join(","), d.noktalar.length, d.trafik ? d.trafik.adim + ":" + d.trafik.noktalar.length : 0, d.baslik || ""].join("|");
            if (!(k in pngOnbellek)) {
              var s = devreSecenek(d, ar, ayar, dil);
              pngOnbellek[k] = s ? ciz(ec, s) : null;
            }
            if (pngOnbellek[k]) {
              var adlar = METRIKLER.filter(function (x) { return ayar.metrikler.indexOf(x) >= 0; }).map(function (x) { return x === "trafik" ? m.giris + " / " + m.cikis : m[x]; });
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
    var saatSatir = el("div", S.saatSatir + ";flex-wrap:wrap");
    saatSatir.appendChild(el("span", "font-size:11.5px;font-weight:800;color:#334155", m.tarihAraligi));
    function zamanGirdisi() {
      var g = el("input", S.secim);
      g.type = "datetime-local";
      g.step = "60";
      // 2026-11-27 kullanici: tarih secimi aninda kaydedilmez; "Uygula" ile sorgulanir
      g.addEventListener("input", function () { durum.tarihKirli = true; uygulaDurum(); });
      g.addEventListener("change", function () { durum.tarihKirli = true; uygulaDurum(); });
      return g;
    }
    var basSec = zamanGirdisi(), bitSec = zamanGirdisi();
    saatSatir.appendChild(basSec);
    saatSatir.appendChild(el("span", "color:#64748b", "–"));
    saatSatir.appendChild(bitSec);
    var uygulaDugme = el("button", S.dugme, m.uygula);
    uygulaDugme.type = "button";
    uygulaDugme.addEventListener("click", function () { aralikKaydet(false); });
    saatSatir.appendChild(uygulaDugme);
    function uygulaDurum() {
      var v = durum.veri, ar = v && v.ayar && v.ayar.aralik;
      var b = basSec.value.slice(0, 16), t = bitSec.value.slice(0, 16);
      var degisti = !!b && !!t && (!ar || ar.bas !== b || ar.bit !== t);
      uygulaDugme.disabled = !degisti || !v || !v.duzenleyebilir || durum.calisiyor;
      uygulaDugme.setAttribute("style", uygulaDugme.disabled ? S.pasif : S.dugme);
      uygulaDugme.title = degisti ? "" : m.uygulaNot;
    }
    var donemDugme = el("button", S.dugme2, m.raporDonemi);
    donemDugme.type = "button";
    donemDugme.addEventListener("click", function () { aralikKaydet(true); });
    saatSatir.appendChild(donemDugme);
    var aralikNot = el("span", S.kucuk + ";margin:0");
    saatSatir.appendChild(aralikNot);
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
    // 2026-11-27 kullanici: grafigin adini kullanici verir (ONENT / CMDB ayrintisi yazilmaz); ekleme isteklerine gider
    var adEtiket = el("label", S.etiket + ";display:block;margin:10px 0 4px", m.grafikAdi);
    var adGirdi = el("input", S.girdi);
    adGirdi.type = "text";
    adGirdi.maxLength = 120;
    adGirdi.placeholder = m.grafikAdiIpucu;
    adGirdi.id = "tl-grafik-adi";
    adEtiket.setAttribute("for", adGirdi.id);
    aramaKap.appendChild(adEtiket);
    aramaKap.appendChild(adGirdi);
    function ekleIstegi(govde) {
      govde.ad = adGirdi.value.trim();
      islem(function () { return durum.p.istek("POST", durum.p.taban + "/devreler", govde); }, function () { adGirdi.value = ""; aramaYenile(); });
    }
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

    function ayarGonder(aralik_) {
      var v = durum.veri;
      if (!v || !v.duzenleyebilir) return;
      var yeni = {
        metrikler: METRIKLER.filter(function (ad) { return kutucuklar[ad].kutu.checked; }),
        bas_zaman: aralik_ ? aralik_.bas : null, bit_zaman: aralik_ ? aralik_.bit : null
      };
      v.ayar = { metrikler: yeni.metrikler, aralik: aralik_ }; // ekranda hemen; sunucu yaniti yenile() ile gelir
      ciz2();
      islem(function () { return durum.p.istek("PUT", durum.p.taban + "/devre-ayar", yeni); });
    }
    function ayarKaydet() { var v = durum.veri; ayarGonder(v && v.ayar ? v.ayar.aralik : null); }
    function aralikKaydet(donem) {
      if (donem) { durum.tarihKirli = false; ayarGonder(null); return; }
      var b = basSec.value, t = bitSec.value;
      if (!b || !t) return;
      if (t <= b) { durum.mesaj = m.aralikHata; ciz2(); return; }
      durum.tarihKirli = false;
      ayarGonder({ bas: b.slice(0, 16), bit: t.slice(0, 16) });
    }

    function ciz2() {
      var v = durum.veri, duz = !v || v.duzenleyebilir;
      kart.style.display = v && typeof v.duzenleyebilir !== "boolean" ? "none" : "";
      uyari.textContent = "";
      if (v && v.kaynak) {
        var c = v.kaynak.cmdb || {}, o = v.kaynak.olcum || {};
        if (!c.son_basari) uyari.appendChild(el("div", S.uyari, m.cmdbYok));
        if (o.hata) uyari.appendChild(el("div", S.uyari, m.olcumHata));
      }
      if (v && !v.duzenleyebilir) uyari.appendChild(el("div", S.uyari, m.salt));
      // ayar denetimleri
      var ayar = (v && v.ayar) || { metrikler: [], aralik: null };
      METRIKLER.forEach(function (ad) {
        var k = kutucuklar[ad], kapali = !duz || !v || (ad === "trafik" && !v.trafik_var);
        k.kutu.checked = ayar.metrikler.indexOf(ad) >= 0;
        k.kutu.disabled = kapali || durum.calisiyor;
        k.etiket.style.opacity = ad === "trafik" && v && !v.trafik_var ? "0.5" : "1";
        k.etiket.title = ad === "trafik" && v && !v.trafik_var ? m.trafikYok : "";
      });
      var etkin = (ayar.aralik) || (v && v.aralik) || null;
      // uygulanmamis secim (Uygula'ya basilmadi) periyodik yenilemede ezilmez
      if (etkin && !durum.tarihKirli && document.activeElement !== basSec) basSec.value = etkin.bas;
      if (etkin && !durum.tarihKirli && document.activeElement !== bitSec) bitSec.value = etkin.bit;
      basSec.disabled = bitSec.disabled = !duz || !v || durum.calisiyor;
      donemDugme.disabled = !duz || !v || durum.calisiyor || !ayar.aralik;
      donemDugme.style.opacity = donemDugme.disabled ? "0.5" : "1";
      aralikNot.textContent = v && !ayar.aralik ? m.raporDonemiAcik : "";
      uygulaDurum();
      metrikUyari.textContent = v && !ayar.metrikler.length ? m.metrikYok : v && !v.trafik_var ? m.trafikYok : "";
      aramaKap.style.display = duz ? "" : "none";
      // secili devreler
      seciliKap.textContent = "";
      var liste = (v && v.devreler) || [];
      if (!liste.length) seciliKap.appendChild(el("div", S.kucuk, m.seciliYok));
      liste.forEach(function (d) {
        var satir = el("div", S.satir), sol = el("div", "min-width:0;flex:1");
        if (durum.adDuzenle === d.id) {
          // satir ici ad duzenleme
          var ag = el("input", S.girdi + ";margin-bottom:6px");
          ag.type = "text";
          ag.maxLength = 120;
          ag.value = durum.adTaslak != null ? durum.adTaslak : (d.baslik || "");
          ag.addEventListener("input", function () { durum.adTaslak = ag.value; });  // periyodik yenilemede yazilan kaybolmaz
          ag.placeholder = m.grafikAdiIpucu;
          ag.setAttribute("aria-label", m.grafikAdi);
          var kd = el("button", S.dugme, m.kaydet), vz = el("button", S.dugme2 + ";margin-left:6px", m.vazgec);
          kd.type = vz.type = "button";
          kd.onclick = function () {
            var yeni = ag.value.trim();
            durum.adDuzenle = null;
            durum.adTaslak = null;
            islem(function () { return durum.p.istek("PATCH", durum.p.taban + "/devreler/" + d.id, { ad: yeni }); });
          };
          vz.onclick = function () { durum.adDuzenle = null; durum.adTaslak = null; ciz2(); };
          ag.addEventListener("keydown", function (e) { if (e.key === "Enter") kd.onclick(); if (e.key === "Escape") vz.onclick(); });
          sol.appendChild(ag);
          var dg = el("div", "");
          dg.appendChild(kd);
          dg.appendChild(vz);
          sol.appendChild(dg);
          setTimeout(function () { ag.focus(); }, 0);
        } else if (d.baslik) {
          sol.appendChild(el("div", S.ci, d.baslik));
          sol.appendChild(el("div", S.kucuk + ";word-break:break-all", d.ci));
        } else {
          sol.appendChild(el("div", S.ci, d.ci));
        }
        var o = d.ozet || {};
        var ozet = d.durum === "hazir"
          ? m.aylikLoe + ": " + m.erisim + " " + yuzde(o.erisilebilirlik, dil, 3) + " · " + m.gecikme + " " + ms(o.gecikme == null ? null : o.gecikme * 1000, dil) + " · " + m.jitter + " " + ms(o.jitter == null ? null : o.jitter * 1000, dil) + " · " + m.kayip + " " + yuzde(o.kayip, dil, 3)
          : "";
        sol.appendChild(el("div", S.kucuk + ";font-weight:700;color:" + (ROZET[d.durum] || RENK.gri),
          (d.durum === "hazir" ? m.hazir : d.durum === "bekliyor" ? m.bekliyor : m.veriYok) + (ozet ? " — " + ozet : "")));
        if (d.trafik_eslesme && m.eslesme[d.trafik_eslesme]) sol.appendChild(el("div", S.kucuk, m.eslesme[d.trafik_eslesme]));
        satir.appendChild(sol);
        if (v.duzenleyebilir && durum.adDuzenle !== d.id) {
          var dugmeler = el("div", "display:flex;flex-direction:column;gap:6px;flex:none");
          var ad = el("button", S.dugme2, m.adDegistir);
          ad.type = "button";
          ad.onclick = function () { durum.adDuzenle = d.id; durum.adTaslak = null; ciz2(); };
          dugmeler.appendChild(ad);
          satir.appendChild(dugmeler);
        }
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
      if (r.imt) {
        // 2026-11-27: yalniz IMT ile grafik - IMT'nin tum envanter devreleri tek tikla, butun veriler secili
        var hepsi = r.sonuclar.every(function (s) { return secili[s.ci] || s.secili; });
        var imtSatir = el("div", S.satir + ";align-items:center"), imtSol = el("div", S.kucuk + ";margin:0", m.imtNot);
        var ib = el("button", hepsi ? S.pasif : S.dugme, hepsi ? m.imtEkli : m.imtOlustur(r.toplam));
        ib.type = "button";
        ib.disabled = hepsi;
        if (!hepsi) ib.onclick = function () { ekleIstegi({ imt: r.imt }); };
        imtSatir.appendChild(imtSol);
        imtSatir.appendChild(ib);
        sonucKap.appendChild(imtSatir);
      }
      r.sonuclar.forEach(function (s) {
        var satir = el("div", S.satir), sol = el("div", "min-width:0");
        sol.appendChild(el("div", S.ci, s.ci));
        if (s.alanlar && s.alanlar.length) sol.appendChild(el("div", S.kucuk, s.alanlar.map(function (a) { return a[0] + ": " + a[1]; }).join(" · ")));
        satir.appendChild(sol);
        var ekli = secili[s.ci] || s.secili;
        var b = el("button", ekli ? S.pasif : S.dugme, ekli ? m.ekli : m.ekle);
        b.type = "button";
        b.disabled = !!ekli;
        if (!ekli) b.onclick = function () { ekleIstegi({ ci: s.ci }); };
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
