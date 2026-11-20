/*
 * TAM Life - Aylik rapor devre grafikleri (React paketinden AYRI kod).
 * Cizim: Apache ECharts 6.1.0 (echarts-6.1.0.min.js, Apache-2.0; lisans: echarts-6.1.0.LICENSE.txt).
 *
 * 2026-11-20: veri ReportDB LOE sorgusundan (backend/app/rapor/loe.py): devre basina saatlik erisilebilirlik, gecikme, jitter,
 * paket kaybi. Grafik araligi raporun donemi (ay basi - sonraki ay basi); secilen devre sayisinda sinir yok.
 *
 * Iki giris noktasi (ikisini de rapor sayfasi cagirir):
 *  - gorseller(getir, adres, dil): GET .../rapor/trafik?donem= -> devre basina 2 grafik (PNG data URL) -> onizlemedeki grafik
 *    listesine katilir; PDF (html2canvas + jsPDF) bunlari diger grafikler gibi alir. Veri yoksa ECharts hic yuklenmez.
 *  - devreKutusu(kap, {taban, adres, dil, getir, istek, yenile}): "Devre grafikleri" bolumu (arama + secili devreler). Arama
 *    ReportDB CMDB kopyasinda (CI adi, aciklama, port ...); secim musteriye kalicidir, kaldirilana kadar her ay cizilir.
 */
(function () {
  "use strict";

  var ECHARTS = "echarts-6.1.0.min.js";
  var betik = document.currentScript;
  var KOK = betik && betik.src ? new URL(".", betik.src).href : "/";
  var TR_SAAT = 3 * 3600 * 1000; // ReportDB zamanlari Turkiye saati

  var RENK = { lacivert: "#002855", sari: "#ffc72c", turuncu: "#e8a400", gri: "#64748b", cizgi: "#e2e8f0", kirmizi: "#be123c", yesil: "#15803d", mor: "#7c3aed" };
  var YAZI = "'Segoe UI', Calibri, Arial, sans-serif";
  var GENISLIK = 900, YUKSEKLIK = 360, PIKSEL = 2;

  var METIN = {
    tr: {
      erisim: "Erişilebilirlik", gecikme: "Gecikme", jitter: "Jitter", kayip: "Paket kaybı", aylik: "Aylık", pencere: "Ölçüm penceresi",
      saat: "saat", olcumYok: "Pencere içinde ölçüm yok", grafikErisim: "erişilebilirlik", grafikKalite: "gecikme, jitter, paket kaybı",
      bolum: "Devre grafikleri (ReportDB)", aciklama: "Seçilen devrelerin grafikleri her ay raporun dönemine göre kendiliğinden çizilir; kaldırılana kadar seçili kalır.",
      ara: "Açıklama, port ya da CI adı yazın (en az 3 karakter)", ekle: "Ekle", ekli: "Ekli", kaldir: "Kaldır", secili: "Seçili devreler",
      seciliYok: "Henüz devre seçilmedi.", sonucYok: "Eşleşen devre bulunamadı.", fazla: "ilk 100 sonuç gösteriliyor", toplam: "eşleşme",
      hazir: "Hazır", bekliyor: "Veri hazırlanıyor (birkaç dakika)", veriYok: "Bu dönemde ölçüm yok", kaldirOnay: "Bu devre rapordan kaldırılsın mı?",
      noYok: "Kartta Müşteri No olmadığı için devre aranamıyor.", cmdbYok: "ReportDB CMDB verisi henüz alınamadı", olcumHata: "Son ölçüm çekimi başarısız",
      salt: "Bu kartta değişiklik yetkiniz yok; seçili devreler gösteriliyor.", hata: "İşlem yapılamadı",
      ay: ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
    },
    en: {
      erisim: "Availability", gecikme: "Delay", jitter: "Jitter", kayip: "Packet loss", aylik: "Monthly", pencere: "Measurement window",
      saat: "hours", olcumYok: "No measurement in window", grafikErisim: "availability", grafikKalite: "delay, jitter, packet loss",
      bolum: "Circuit charts (ReportDB)", aciklama: "Charts of selected circuits are drawn every month for the report period; circuits stay selected until removed.",
      ara: "Type a description, port or CI name (min. 3 characters)", ekle: "Add", ekli: "Added", kaldir: "Remove", secili: "Selected circuits",
      seciliYok: "No circuit selected yet.", sonucYok: "No matching circuit.", fazla: "showing first 100 results", toplam: "matches",
      hazir: "Ready", bekliyor: "Preparing data (a few minutes)", veriYok: "No measurement this period", kaldirOnay: "Remove this circuit from the report?",
      noYok: "This card has no Customer No, so circuits cannot be searched.", cmdbYok: "ReportDB CMDB data not received yet", olcumHata: "Last measurement fetch failed",
      salt: "You cannot change this card; selected circuits are shown.", hata: "Action failed",
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

  function sayi(x, dil, basamak) {
    return x.toLocaleString(dil === "en" ? "en-US" : "tr-TR", { minimumFractionDigits: basamak, maximumFractionDigits: basamak });
  }
  function yuzde(x, dil, basamak) { return x == null || !isFinite(x) ? "—" : "%" + sayi(x * 100, dil, basamak); }
  function ms(x, dil) { return x == null || !isFinite(x) ? "—" : sayi(x, dil, x >= 100 ? 0 : x >= 10 ? 1 : 2) + " ms"; }
  function tarih(v, dil) { var t = new Date(v); return t.getDate() + " " + METIN[dil].ay[t.getMonth()]; }

  function aralik(yil, ay) {
    return [Date.UTC(yil, ay - 1, 1) - TR_SAAT, Date.UTC(ay === 12 ? yil + 1 : yil, ay % 12, 1) - TR_SAAT];
  }

  function ortak(dil, yil, ay, altMetin) {
    var r = aralik(yil, ay);
    return {
      animation: false,
      backgroundColor: "#ffffff",
      textStyle: { fontFamily: YAZI, color: RENK.lacivert },
      legend: { top: 4, right: 8, icon: "roundRect", itemWidth: 14, itemHeight: 6, textStyle: { fontSize: 11, fontWeight: 700, color: RENK.lacivert } },
      title: { left: 8, bottom: 2, text: "", subtext: altMetin, subtextStyle: { fontSize: 10.5, lineHeight: 15, color: RENK.gri, fontWeight: 600 } },
      grid: { left: 64, right: 56, top: 34, bottom: 64 },
      xAxis: { type: "time", min: r[0], max: r[1], boundaryGap: false, axisLine: { lineStyle: { color: RENK.cizgi } }, axisTick: { show: false },
        axisLabel: { color: RENK.gri, fontSize: 10, hideOverlap: true, formatter: function (v) { return tarih(v, dil); } }, splitLine: { show: false } }
    };
  }

  function pencereli(noktalar, i, carpan) {
    return noktalar.map(function (n) { return [n[0], n[5] && n[i] != null ? n[i] * carpan : null]; });
  }

  /** Gunluk erisilebilirlik (pencere icindeki saatlerin ortalamasi); gun ortasina yerlesir. */
  function gunluk(noktalar) {
    var gunler = {};
    noktalar.forEach(function (n) {
      if (!n[5] || n[1] == null) return;
      var g = Math.floor((n[0] + TR_SAAT) / 864e5);
      var k = gunler[g] || (gunler[g] = { t: 0, n: 0 });
      k.t += n[1];
      k.n += 1;
    });
    return Object.keys(gunler).sort().map(function (g) {
      return [Number(g) * 864e5 - TR_SAAT + 432e5, (gunler[g].t / gunler[g].n) * 100];
    });
  }

  /** Erisilebilirlik grafigi: gunluk cubuklar (yalniz olcum penceresindeki saatler) + aylik deger cizgisi. */
  function erisimSecenek(devre, yil, ay, dil) {
    dil = dilSec(dil);
    var m = METIN[dil], o = devre.ozet || {}, nk = devre.noktalar || [];
    var veri = gunluk(nk);
    var enAz = 100;
    veri.forEach(function (n) { if (n[1] < enAz) enAz = n[1]; });
    var alt = enAz >= 99.9 ? 99 : enAz >= 99 ? 98 : Math.max(0, Math.floor((enAz - 2) / 5) * 5);
    var renkli = veri.map(function (n) {
      return { value: n, itemStyle: { color: n[1] >= 99.9 ? RENK.lacivert : n[1] >= 99 ? RENK.turuncu : RENK.kirmizi, borderRadius: [2, 2, 0, 0] } };
    });
    var ust = m.aylik + " " + m.erisim.toLowerCase() + " " + yuzde(o.erisilebilirlik, dil, 3) + "  ·  " + m.pencere + ": " + (devre.exchours || "—") +
      "  ·  " + (o.pencere_saat || 0) + " " + m.saat;
    var s = ortak(dil, yil, ay, o.pencere_saat ? ust : ust + "  ·  " + m.olcumYok);
    s.color = [RENK.lacivert];
    s.yAxis = { type: "value", min: alt, max: 100, interval: (100 - alt) / 5, axisLabel: { color: RENK.gri, fontSize: 10, formatter: function (v) { return "%" + sayi(v, dil, v % 1 ? 1 : 0); } },
      splitLine: { lineStyle: { color: RENK.cizgi, type: "dashed" } } };
    s.legend.show = false;
    s.series = [{
      name: m.erisim, type: "bar", data: renkli, barMaxWidth: 16, barCategoryGap: "30%", itemStyle: { color: RENK.lacivert },
      label: { show: true, position: "top", fontSize: 9, color: RENK.kirmizi, fontWeight: 700,
        formatter: function (x) { var v = x.value[1]; return v < 99 ? "%" + sayi(v, dil, 1) : ""; } },
      markLine: o.erisilebilirlik == null ? undefined : { silent: true, symbol: "none", lineStyle: { type: "dashed", width: 1.2, color: RENK.gri },
        label: { position: "insideStartTop", color: RENK.lacivert, fontSize: 10, fontWeight: 700, formatter: m.aylik + " " + yuzde(o.erisilebilirlik, dil, 3),
          backgroundColor: "rgba(255,255,255,0.92)", padding: [2, 5], borderRadius: 3 },
        data: [{ yAxis: o.erisilebilirlik * 100 }] }
    }];
    return s;
  }

  /** Gecikme + jitter (ms, sol eksen) ve paket kaybi (%, sag eksen); yalniz olcum penceresindeki saatler. */
  function kaliteSecenek(devre, yil, ay, dil) {
    dil = dilSec(dil);
    var m = METIN[dil], o = devre.ozet || {}, nk = devre.noktalar || [];
    var ust = m.aylik + ": " + m.gecikme + " " + ms(o.gecikme, dil) + "  ·  " + m.jitter + " " + ms(o.jitter, dil) + "  ·  " + m.kayip + " " + yuzde(o.kayip, dil, 3);
    var s = ortak(dil, yil, ay, ust);
    s.color = [RENK.lacivert, RENK.turuncu, RENK.kirmizi];
    s.yAxis = [
      { type: "value", min: 0, axisLabel: { color: RENK.gri, fontSize: 10, formatter: function (v) { return sayi(v, dil, 0) + " ms"; } },
        splitLine: { lineStyle: { color: RENK.cizgi, type: "dashed" } } },
      { type: "value", min: 0, axisLabel: { color: RENK.kirmizi, fontSize: 10, formatter: function (v) { return "%" + sayi(v, dil, v && v < 1 ? 2 : 0); } },
        splitLine: { show: false } }
    ];
    s.series = [
      { name: m.gecikme, type: "line", data: pencereli(nk, 2, 1), showSymbol: false, connectNulls: false, sampling: "lttb",
        lineStyle: { width: 1.4, color: RENK.lacivert }, itemStyle: { color: RENK.lacivert } },
      { name: m.jitter, type: "line", data: pencereli(nk, 3, 1), showSymbol: false, connectNulls: false, sampling: "lttb",
        lineStyle: { width: 1.2, color: RENK.turuncu }, itemStyle: { color: RENK.turuncu } },
      { name: m.kayip, type: "line", yAxisIndex: 1, data: pencereli(nk, 4, 100), showSymbol: false, connectNulls: false, step: "end",
        lineStyle: { width: 1, color: RENK.kirmizi }, itemStyle: { color: RENK.kirmizi },
        areaStyle: { color: "rgba(190,18,60,0.12)" } }
    ];
    return s;
  }

  function ciz(ec, secenek) {
    var kutu = document.createElement("div");
    var grafik = ec.init(kutu, null, { renderer: "canvas", width: GENISLIK, height: YUKSEKLIK, devicePixelRatio: PIKSEL });
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

  /**
   * Rapor sayfasinin grafik girisi. Donus: [{anahtar, baslik, gorsel}] - hata ya da veri yoksa bos liste (rapor etkilenmez).
   */
  function gorseller(getir, adres, dil) {
    dil = dilSec(dil);
    var m = METIN[dil];
    return Promise.resolve()
      .then(function () { return getir(adres); })
      .then(function (veri) {
        veriYayinla(adres, veri);
        var liste = ((veri && veri.devreler) || []).filter(function (d) { return d && d.noktalar && d.noktalar.length; });
        if (!liste.length) return [];
        return echartsYukle().then(function (ec) {
          var cikti = [];
          liste.forEach(function (d) {
            var ad = d.ci + (d.baslik ? " · " + d.baslik : "");
            [["erisim", erisimSecenek, m.grafikErisim], ["kalite", kaliteSecenek, m.grafikKalite]].forEach(function (t) {
              var k = [d.id, t[0], d.cekildi, dil, veri.yil, veri.ay].join("|");
              if (!pngOnbellek[k]) pngOnbellek[k] = ciz(ec, t[1](d, veri.yil, veri.ay, dil));
              cikti.push({ anahtar: "devre-" + d.id + "-" + t[0], baslik: ad + " — " + t[2], gorsel: pngOnbellek[k] });
            });
          });
          return cikti;
        });
      })
      .catch(function (e) {
        if (window.console) console.warn("rapor-trafik:", e && e.message ? e.message : e);
        return [];
      });
  }

  // --- Devre kutusu (arama + secili devreler) ---------------------------------------------------------------------------
  function el(etiket, stil, metin) {
    var e = document.createElement(etiket);
    if (stil) e.setAttribute("style", stil);
    if (metin != null) e.textContent = metin;
    return e;
  }
  var S = {
    kart: "margin-top:16px;border:1px solid #e2e8f0;border-radius:12px;background:#fff;padding:16px;font-family:" + YAZI + ";color:#002855",
    baslik: "font-size:14px;font-weight:800;margin:0",
    aciklama: "font-size:12px;color:#64748b;margin:4px 0 12px",
    girdi: "width:100%;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:8px;padding:8px 10px;font-size:13px;color:#0f172a;background:#fff",
    satir: "display:flex;align-items:flex-start;gap:10px;justify-content:space-between;padding:8px 0;border-top:1px solid #f1f5f9",
    ci: "font-size:13px;font-weight:700;word-break:break-all",
    kucuk: "font-size:11.5px;color:#64748b;margin-top:2px;word-break:break-word",
    dugme: "flex:none;border:1px solid #002855;background:#002855;color:#fff;border-radius:8px;padding:5px 12px;font-size:12px;font-weight:700;cursor:pointer",
    dugme2: "flex:none;border:1px solid #cbd5e1;background:#fff;color:#334155;border-radius:8px;padding:5px 12px;font-size:12px;font-weight:700;cursor:pointer",
    pasif: "flex:none;border:1px solid #e2e8f0;background:#f8fafc;color:#94a3b8;border-radius:8px;padding:5px 12px;font-size:12px;font-weight:700",
    uyari: "font-size:12px;color:#92400e;background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:6px 10px;margin:8px 0",
    hata: "font-size:12px;color:#be123c;margin-top:6px",
    altBaslik: "font-size:12px;font-weight:800;color:#334155;margin:14px 0 2px;text-transform:uppercase;letter-spacing:.03em"
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
    kart.appendChild(el("h3", S.baslik, m.bolum));
    kart.appendChild(el("p", S.aciklama, m.aciklama));
    var uyari = el("div", "");
    var aramaKap = el("div", "");
    var girdi = el("input", S.girdi);
    girdi.type = "search";
    girdi.placeholder = m.ara;
    girdi.maxLength = 200;
    girdi.setAttribute("aria-label", m.ara);
    aramaKap.appendChild(girdi);
    var sonucKap = el("div", "");
    aramaKap.appendChild(sonucKap);
    var seciliBaslik = el("div", S.altBaslik, m.secili);
    var seciliKap = el("div", "");
    var mesaj = el("div", S.hata);
    kart.appendChild(uyari);
    kart.appendChild(aramaKap);
    kart.appendChild(seciliBaslik);
    kart.appendChild(seciliKap);
    kart.appendChild(mesaj);
    kap.appendChild(kart);

    function hataMetni(e) { return (e && e.message) || m.hata; }
    function islem(f) {
      if (durum.calisiyor) return;
      durum.calisiyor = true;
      durum.mesaj = "";
      Promise.resolve().then(f).catch(function (e) { durum.mesaj = hataMetni(e); }).then(function () {
        durum.calisiyor = false;
        ciz2();
        if (durum.p.yenile) durum.p.yenile();
        if (durum.aranan) ara(durum.aranan, true);
      });
    }

    function ciz2() {
      var v = durum.veri, duz = !v || v.duzenleyebilir;
      // Sunucu yeni sozlesmeyi (duzenleyebilir alani) dondurene kadar bolum gizli: panel yeniden baslatilmadan once ya da veri gelmeden
      kart.style.display = v && typeof v.duzenleyebilir === "boolean" ? "" : "none";
      uyari.textContent = "";
      if (v && v.kaynak) {
        var c = v.kaynak.cmdb || {}, o = v.kaynak.olcum || {};
        if (!c.son_basari) {
          uyari.appendChild(el("div", S.uyari, m.cmdbYok + (c.hata ? ": " + c.hata : ".")));
        }
        if (o.hata) uyari.appendChild(el("div", S.uyari, m.olcumHata + ": " + o.hata));
      }
      if (v && !v.duzenleyebilir) uyari.appendChild(el("div", S.uyari, m.salt));
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
          ? m.erisim + " " + yuzde(o.erisilebilirlik, dil, 3) + " · " + m.gecikme + " " + ms(o.gecikme, dil) + " · " + m.jitter + " " + ms(o.jitter, dil) + " · " + m.kayip + " " + yuzde(o.kayip, dil, 3)
          : "";
        var rozet = el("div", S.kucuk + ";font-weight:700;color:" + (ROZET[d.durum] || RENK.gri),
          (d.durum === "hazir" ? m.hazir : d.durum === "bekliyor" ? m.bekliyor : m.veriYok) + (ozet ? " — " + ozet : ""));
        sol.appendChild(rozet);
        satir.appendChild(sol);
        if (v.duzenleyebilir) {
          var b = el("button", S.dugme2, m.kaldir);
          b.type = "button";
          b.onclick = function () {
            if (!window.confirm(m.kaldirOnay + "\n" + d.ci)) return;
            islem(function () { return durum.p.istek("DELETE", durum.p.taban + "/devreler/" + d.id); });
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
      if (!r.musteri_no_var) { sonucKap.appendChild(el("div", S.uyari, m.noYok)); return; }
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
        if (!ekli) b.onclick = function () { islem(function () { return durum.p.istek("POST", durum.p.taban + "/devreler", { ci: s.ci }); }); };
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
  }

  window.TamlifeTrafik = {
    surum: "2", echarts: "6.1.0", gorseller: gorseller, devreKutusu: devreKutusu, bekliyor: bekliyor,
    erisimSecenek: erisimSecenek, kaliteSecenek: kaliteSecenek, echartsYukle: echartsYukle
  };
})();
