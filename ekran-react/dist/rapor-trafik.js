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
      trafikYok: "ReportDB'de trafik sütunu henüz tanımlı değil (tablo yetkisi bekleniyor).", aylikLoe: "LOE aylık",
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
      trafikYok: "Traffic column is not defined in ReportDB yet (awaiting table access).", aylikLoe: "LOE monthly",
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

  // --- Tek grafik --------------------------------------------------------------------------------------------------------
  /**
   * Devrenin secili verilerini tek grafikte (tek PNG) cizer: birim grubu basina alt alta serit, ortak tarih ekseni.
   * Gruplar: trafik (bps), gecikme + jitter (ms), paket kaybi (%); yukseklik secilen gruplara gore. Saat araligi disindaki saatler bos (cizgi kesilir). Donus: null = cizilecek veri yok.
   */
  function devreSecenek(devre, yil, ay, ayar, dil) {
    dil = dilSec(dil);
    var m = METIN[dil], nk = devre.noktalar || [];
    var metrikler = (ayar && ayar.metrikler) || [], saat = (ayar && ayar.saat) || [0, 23];
    function seri(i, carpan) {
      return nk.map(function (n) { return [n[0], saatte(n[0], saat) && n[i] != null ? n[i] * carpan : null]; });
    }
    function degerler(s) { return s.map(function (n) { return n[1]; }); }
    var gruplar = [], seriler = [], ozet = [];
    function grup(ad) { var i = gruplar.indexOf(ad); if (i < 0) { gruplar.push(ad); i = gruplar.length - 1; } return i; }

    if (metrikler.indexOf("trafik") >= 0) {
      var gi = seri(6, 1), ci = seri(7, 1), sg = istatistik(degerler(gi)), sc = istatistik(degerler(ci));
      if (sg || sc) {
        var ax = grup("bps");
        seriler.push({ name: m.giris, type: "line", yAxisIndex: ax, data: gi, showSymbol: false, connectNulls: false, sampling: "lttb",
          lineStyle: { width: 1.4, color: RENK.lacivert }, itemStyle: { color: RENK.lacivert },
          areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: "rgba(0,40,85,0.32)" }, { offset: 1, color: "rgba(0,40,85,0.03)" }] } } });
        seriler.push({ name: m.cikis, type: "line", yAxisIndex: ax, data: ci, showSymbol: false, connectNulls: false, sampling: "lttb",
          lineStyle: { width: 1.4, color: RENK.sari }, itemStyle: { color: RENK.sari },
          areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: "rgba(232,164,0,0.30)" }, { offset: 1, color: "rgba(232,164,0,0.03)" }] } } });
        [[m.giris, sg], [m.cikis, sc]].forEach(function (x) {
          if (x[1]) ozet.push(x[0] + " " + m.ort + " " + bps(x[1].ort, dil) + ", " + m.enYuksek + " " + bps(x[1].enYuksek, dil) + ", " + m.p95 + " " + bps(x[1].p95, dil));
        });
      }
    }
    [["gecikme", 2, RENK.mavi], ["jitter", 3, RENK.mor]].forEach(function (t) {
      if (metrikler.indexOf(t[0]) < 0) return;
      var s = seri(t[1], 1), st = istatistik(degerler(s));
      if (!st) return;
      seriler.push({ name: m[t[0]], type: "line", yAxisIndex: grup("ms"), data: s, showSymbol: false, connectNulls: false, sampling: "lttb",
        lineStyle: { width: 1.3, color: t[2] }, itemStyle: { color: t[2] } });
      ozet.push(m[t[0]] + " " + m.ort + " " + ms(st.ort, dil) + ", " + m.enYuksek + " " + ms(st.enYuksek, dil));
    });
    if (metrikler.indexOf("kayip") >= 0) {
      var sk = seri(4, 100), stk = istatistik(degerler(sk));
      if (stk) {
        seriler.push({ name: m.kayip, type: "line", yAxisIndex: grup("yuzde"), data: sk, showSymbol: false, connectNulls: false, step: "end",
          lineStyle: { width: 1.1, color: RENK.kirmizi }, itemStyle: { color: RENK.kirmizi }, areaStyle: { color: "rgba(190,18,60,0.12)" } });
        ozet.push(m.kayip + " " + m.ort + " " + yuzde(stk.ort / 100, dil, 3) + ", " + m.enYuksek + " " + yuzde(stk.enYuksek / 100, dil, 2));
      }
    }
    if (!seriler.length) return null;

    var BICIM = {
      bps: function (v) { return bps(v, dil); },
      ms: function (v) { return sayi(v, dil, v && v < 10 && v % 1 ? 1 : 0) + " ms"; },
      yuzde: function (v) { return "%" + sayi(v, dil, v && v < 1 ? 2 : 0); }
    };
    var EKSEN_RENK = { bps: RENK.gri, ms: RENK.mavi, yuzde: RENK.kirmizi };
    // Panel yukseklikleri: birim grubu basina bir serit (ust uste binmesin); paket kaybi daha alcak
    var BOY = { bps: 150, ms: 130, yuzde: 90 };
    var r = aralik(yil, ay);
    var altSatirlar = [];
    for (var i = 0; i < ozet.length; i += 2) altSatirlar.push(ozet.slice(i, i + 2).join("   ·   "));
    altSatirlar.push(METIN[dil].saatAraligi + " " + saatMetni(saat) + (devre.exchours ? "   ·   EXCHOURS " + devre.exchours : ""));
    var ust = 34, ara = 18, grids = [], y = ust;
    gruplar.forEach(function (g) {
      var h = gruplar.length === 1 ? 240 : BOY[g]; // tek grup: tam boy grafik
      grids.push({ left: 70, right: 18, top: y, height: h });
      y += h + ara;
    });
    var yukseklik = y - ara + 26 + altSatirlar.length * 15 + 10;
    var son = gruplar.length - 1;
    return {
      _yukseklik: yukseklik,
      animation: false,
      backgroundColor: "#ffffff",
      textStyle: { fontFamily: YAZI, color: RENK.lacivert },
      legend: { top: 4, right: 8, icon: "roundRect", itemWidth: 14, itemHeight: 6, textStyle: { fontSize: 11, fontWeight: 700, color: RENK.lacivert } },
      title: { left: 8, bottom: 4, text: "", subtext: altSatirlar.join(String.fromCharCode(10)), subtextStyle: { fontSize: 10.5, lineHeight: 15, color: RENK.gri, fontWeight: 600 } },
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      grid: grids,
      xAxis: gruplar.map(function (g, k) {
        return { type: "time", gridIndex: k, min: r[0], max: r[1], boundaryGap: false, axisLine: { lineStyle: { color: RENK.cizgi } }, axisTick: { show: false },
          axisLabel: { show: k === son, color: RENK.gri, fontSize: 10, hideOverlap: true, formatter: function (v) { return tarih(v, dil); } },
          splitLine: { show: true, lineStyle: { color: "#f1f5f9" } } };
      }),
      yAxis: gruplar.map(function (g, k) {
        return { type: "value", gridIndex: k, min: 0, splitNumber: g === "yuzde" ? 2 : 3,
          axisLabel: { color: EKSEN_RENK[g], fontSize: 10, formatter: BICIM[g] },
          splitLine: { lineStyle: { color: RENK.cizgi, type: "dashed" } } };
      }),
      series: seriler.map(function (x) { x.xAxisIndex = x.yAxisIndex; return x; })
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
