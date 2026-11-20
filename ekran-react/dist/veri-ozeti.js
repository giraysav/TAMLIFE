/* Yonetim > Veri Ozeti (2026-11-21): ReportDB / OneDesk / ONENT verisinin tek ekranda konsolide gorunumu + gunluk utilizasyon turu.
   React'tan bagimsiz; yonetim-sayfasi "veri" sekmesi window.TamlifeVeriOzeti.kur(el, {dil}) ile baglar. Yalniz admin ucu okur:
   GET /api/v1/yonetim/veri-ozeti, POST /api/v1/yonetim/veri-ozeti/calistir (CSRF cerezli). */
(function () {
  "use strict";
  var C = { navy: "#002855", metin: "#0f172a", ikincil: "#475569", cizgi: "#e2e8f0", zemin: "#f8fafc", yesil: "#047857", yesilZ: "#ecfdf5",
    amber: "#b45309", amberZ: "#fffbeb", kirmizi: "#b91c1c", kirmiziZ: "#fef2f2", mavi: "#1d4ed8" };
  var M = {
    tr: {
      tur: "Günlük utilizasyon turu", turAcik: "Her gün 06:00'da çalışır: bu yılın kapanmış kayıtlarını ve envanteri toplar, final skorları yeniden hesaplar.",
      sonCalisma: "Son çalışma", sure: "Süre", skor: "Skor", calistir: "Şimdi çalıştır", calisiyor: "Çalışıyor…", hicCalismadi: "Henüz çalışmadı",
      skorOzet: function (s) { return s ? s.uygulanan + " güncellendi · " + s.degismeyen + " değişmedi · " + s.atlanan + " eksik kriterli" : "Skor yazılmadı"; },
      kaynaklar: "Veri kaynakları", siklik: "Sıklık", sonBasari: "Son başarılı", durumOk: "Güncel", durumHata: "Hata", durumBekle: "Bekleniyor", durumEski: "Gecikmiş",
      toplam: "Toplam (çatı müşteriler)", alarm: "Kapanan alarm", sikayet: "Kapanan şikayet", talep: "Kapanan talep", ci: "Aktif CI", lokasyon: "Lokasyon",
      musteriler: "Müşteriler", ara: "Müşteri, TAM ya da müşteri no ara", hepsi: "Tümü", eksik: "Verisi eksik", skorsuz: "Skoru yok",
      musteri: "Müşteri", tam: "TAM", no: "Müşteri No", finalSkor: "Final skor", guncelleme: "Skor güncellemesi", csv: "CSV indir",
      yil: function (y) { return y + " yılı, kapanan kayıtlar"; }, istirak: function (n) { return "+" + n + " iştirak"; },
      kayit: function (n, t) { return n + " / " + t + " müşteri"; }, yukleniyor: "Yükleniyor…", yuklenemedi: "Veri alınamadı.", tekrar: "Tekrar dene",
      baslatildi: "Tur başlatıldı; birkaç dakika içinde tamamlanır.", kaynakSkor: { gunluk: "Günlük tur", toplu: "Toplu atama", sayfa: "Sayfa", kriter_degisikligi: "Kriter değişikliği" },
      bos: "Eşleşen müşteri yok.", once: function (dk) { return dk < 1 ? "az önce" : dk < 60 ? dk + " dk önce" : dk < 1440 ? Math.floor(dk / 60) + " sa önce" : Math.floor(dk / 1440) + " gün önce"; }
    },
    en: {
      tur: "Daily utilization run", turAcik: "Runs every day at 06:00: collects this year's closed records and the inventory, recalculates final scores.",
      sonCalisma: "Last run", sure: "Duration", skor: "Score", calistir: "Run now", calisiyor: "Running…", hicCalismadi: "Not run yet",
      skorOzet: function (s) { return s ? s.uygulanan + " updated · " + s.degismeyen + " unchanged · " + s.atlanan + " missing criteria" : "No score written"; },
      kaynaklar: "Data sources", siklik: "Frequency", sonBasari: "Last success", durumOk: "Up to date", durumHata: "Error", durumBekle: "Pending", durumEski: "Delayed",
      toplam: "Total (parent customers)", alarm: "Closed alarms", sikayet: "Closed complaints", talep: "Closed requests", ci: "Active CIs", lokasyon: "Locations",
      musteriler: "Customers", ara: "Search customer, TAM or customer no", hepsi: "All", eksik: "Missing data", skorsuz: "No score",
      musteri: "Customer", tam: "TAM", no: "Customer No", finalSkor: "Final score", guncelleme: "Score updated", csv: "Download CSV",
      yil: function (y) { return "Year " + y + ", closed records"; }, istirak: function (n) { return "+" + n + " affiliates"; },
      kayit: function (n, t) { return n + " / " + t + " customers"; }, yukleniyor: "Loading…", yuklenemedi: "Could not load data.", tekrar: "Retry",
      baslatildi: "Run started; it completes in a few minutes.", kaynakSkor: { gunluk: "Daily run", toplu: "Bulk assignment", sayfa: "Page", kriter_degisikligi: "Criteria change" },
      bos: "No matching customers.", once: function (dk) { return dk < 1 ? "just now" : dk < 60 ? dk + " min ago" : dk < 1440 ? Math.floor(dk / 60) + " h ago" : Math.floor(dk / 1440) + " d ago"; }
    }
  };
  var SUTUNLAR = ["ad", "tam", "musteri_no", "alarm", "sikayet", "talep", "ci", "lokasyon", "skor", "skor_zaman"];
  var SAYISAL = { alarm: 1, sikayet: 1, talep: 1, ci: 1, lokasyon: 1, skor: 1 };

  function el(etiket, stil, metin) { var e = document.createElement(etiket); if (stil) e.style.cssText = stil; if (metin != null) e.textContent = metin; return e; }
  function sayi(v, dil) { return v == null ? "—" : Number(v).toLocaleString(dil === "en" ? "en-US" : "tr-TR"); }
  function zaman(v) {
    if (!v) return "—";
    var t = new Date(v); if (isNaN(t)) return "—";
    var p = function (n) { return (n < 10 ? "0" : "") + n; };
    return p(t.getDate()) + "." + p(t.getMonth() + 1) + "." + t.getFullYear() + " " + p(t.getHours()) + ":" + p(t.getMinutes());
  }
  function dakika(v) { var t = new Date(v); return isNaN(t) ? null : Math.max(0, Math.round((Date.now() - t) / 60000)); }
  function csrf() { var m = document.cookie.match(/(?:^|;\s*)tamlife_csrf=([^;]+)/); return m ? decodeURIComponent(m[1]) : ""; }
  function istek(yontem, url) {
    var h = { Accept: "application/json" }; if (yontem !== "GET") h["X-CSRF-Token"] = csrf();
    return fetch(url, { method: yontem, credentials: "same-origin", headers: h }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) { var e = new Error((j && (j.detail && (j.detail.mesaj || j.detail)) || j.mesaj) || ("HTTP " + r.status)); e.kod = r.status; throw e; }
        return j && j.data !== undefined ? j.data : j;
      });
    });
  }
  var ROZET = {
    ok: [C.yesil, C.yesilZ], hata: [C.kirmizi, C.kirmiziZ], bekle: [C.ikincil, C.zemin], eski: [C.amber, C.amberZ]
  };
  function rozet(tur, metin) { var r = ROZET[tur]; return el("span", "display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:800;color:" + r[0] + ";background:" + r[1] + ";border:1px solid " + r[0] + "33", metin); }
  var KART = "background:#fff;border:1px solid " + C.cizgi + ";border-radius:12px;padding:14px 16px;min-width:0";
  var DUGME = "display:inline-flex;align-items:center;gap:6px;min-height:34px;padding:0 14px;border-radius:8px;border:1px solid " + C.navy + ";background:" + C.navy + ";color:#fff;font-size:12px;font-weight:800;cursor:pointer";
  var DUGME2 = "display:inline-flex;align-items:center;min-height:30px;padding:0 10px;border-radius:8px;border:1px solid " + C.cizgi + ";background:#fff;color:" + C.navy + ";font-size:12px;font-weight:800;cursor:pointer";

  function kur(kok, ayar) {
    var dil = ayar && ayar.dil === "en" ? "en" : "tr", m = M[dil];
    var durum = { veri: null, hata: null, ara: "", filtre: "hepsi", sira: "ad", artan: true, mesaj: "", zamanlayici: null, bitti: false };
    kok.textContent = "";
    var sayfa = el("div", "display:grid;gap:14px;font-family:inherit;color:" + C.metin);
    kok.appendChild(sayfa);

    function yukle() {
      return istek("GET", "/api/v1/yonetim/veri-ozeti").then(function (v) { durum.veri = v; durum.hata = null; ciz(); planla(); })
        .catch(function (e) { durum.hata = e.message || m.yuklenemedi; ciz(); });
    }
    function planla() {
      clearTimeout(durum.zamanlayici);
      if (durum.bitti) return;
      var cal = durum.veri && durum.veri.tur && durum.veri.tur.calisiyor;
      durum.zamanlayici = setTimeout(yukle, cal ? 8000 : 120000);
    }
    function calistir() {
      durum.mesaj = "";
      istek("POST", "/api/v1/yonetim/veri-ozeti/calistir").then(function () { durum.mesaj = m.baslatildi; return yukle(); })
        .catch(function (e) { durum.mesaj = e.message; ciz(); });
    }

    function turKarti(v) {
      var t = v.tur || {}, k = el("section", KART + ";display:flex;flex-wrap:wrap;gap:14px;align-items:center;justify-content:space-between");
      var sol = el("div", "min-width:0;flex:1 1 380px");
      var bas = el("div", "display:flex;align-items:center;gap:8px;flex-wrap:wrap");
      bas.appendChild(el("h3", "margin:0;font-size:14px;font-weight:900;color:" + C.navy, m.tur));
      var hataVar = Object.keys(t.kaynaklar || {}).some(function (a) { return (t.kaynaklar[a] || {}).durum === "hata"; });
      bas.appendChild(t.calisiyor ? rozet("bekle", m.calisiyor) : !t.zaman ? rozet("bekle", m.hicCalismadi) : hataVar ? rozet("hata", m.durumHata) : (dakika(t.zaman) > 1560 ? rozet("eski", m.durumEski) : rozet("ok", m.durumOk)));
      sol.appendChild(bas);
      sol.appendChild(el("p", "margin:4px 0 0;font-size:12px;font-weight:600;color:" + C.ikincil, m.turAcik + (t.yil ? " " + m.yil(t.yil) + "." : "")));
      var dl = el("div", "display:flex;flex-wrap:wrap;gap:6px 22px;margin-top:10px;font-size:12px");
      [[m.sonCalisma, t.zaman ? zaman(t.zaman) + " (" + m.once(dakika(t.zaman)) + ")" : "—"], [m.sure, t.sure_sn != null ? t.sure_sn + " sn" : "—"], [m.skor, t.zaman ? m.skorOzet(t.skor) : "—"]]
        .forEach(function (x) { var d = el("div"); d.appendChild(el("span", "font-weight:700;color:" + C.ikincil, x[0] + ": ")); d.appendChild(el("span", "font-weight:800", x[1])); dl.appendChild(d); });
      sol.appendChild(dl);
      k.appendChild(sol);
      var sag = el("div", "display:grid;gap:6px;justify-items:end");
      var b = el("button", DUGME, t.calisiyor ? m.calisiyor : m.calistir); b.type = "button"; b.disabled = !!t.calisiyor;
      if (b.disabled) b.style.opacity = "0.6";
      b.addEventListener("click", calistir);
      sag.appendChild(b);
      if (durum.mesaj) sag.appendChild(el("span", "font-size:11.5px;font-weight:700;color:" + C.ikincil + ";max-width:280px;text-align:right", durum.mesaj));
      k.appendChild(sag);
      return k;
    }

    function kaynakKartlari(v) {
      var sar = el("section", "display:grid;gap:8px");
      sar.appendChild(el("h3", "margin:0;font-size:12px;font-weight:900;letter-spacing:.04em;text-transform:uppercase;color:" + C.ikincil, m.kaynaklar));
      var izg = el("div", "display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))");
      (v.kaynaklar || []).forEach(function (k) {
        var kart = el("div", KART + ";display:grid;gap:8px");
        var ust = el("div", "display:flex;justify-content:space-between;gap:8px;align-items:flex-start");
        var ad = el("div", "min-width:0");
        ad.appendChild(el("div", "font-size:14px;font-weight:900;color:" + C.navy, k.ad));
        ad.appendChild(el("div", "font-size:12px;font-weight:700;color:" + C.ikincil, k.icerik));
        ust.appendChild(ad);
        var dk = k.son_basari ? dakika(k.son_basari) : null;
        ust.appendChild(k.hata ? rozet("hata", m.durumHata) : dk == null ? rozet("bekle", m.durumBekle) : dk > (k.anahtar === "reportdb" ? 60 : k.anahtar === "onent" ? 600 : 1560) ? rozet("eski", m.durumEski) : rozet("ok", m.durumOk));
        kart.appendChild(ust);
        var tablo = el("div", "display:grid;grid-template-columns:1fr auto;gap:3px 12px;font-size:12px");
        (k.hacim || []).concat([[m.siklik, k.siklik], [m.sonBasari, k.son_basari ? zaman(k.son_basari) + " · " + m.once(dk) : "—"]]).forEach(function (x) {
          tablo.appendChild(el("span", "font-weight:700;color:" + C.ikincil, x[0]));
          tablo.appendChild(el("span", "font-weight:800;text-align:right;font-variant-numeric:tabular-nums", typeof x[1] === "number" || x[1] == null ? sayi(x[1], dil) : x[1]));
        });
        kart.appendChild(tablo);
        if (k.hata) kart.appendChild(el("div", "font-size:11.5px;font-weight:700;color:" + C.kirmizi + ";background:" + C.kirmiziZ + ";border-radius:8px;padding:6px 8px;word-break:break-word", k.hata));
        izg.appendChild(kart);
      });
      sar.appendChild(izg);
      return sar;
    }

    function toplamlar(v) {
      var t = v.toplam || {}, izg = el("section", "display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))");
      ["alarm", "sikayet", "talep", "ci", "lokasyon"].forEach(function (a) {
        var k = el("div", KART + ";padding:12px 14px");
        k.appendChild(el("div", "font-size:12px;font-weight:800;color:" + C.ikincil, m[a]));
        k.appendChild(el("div", "font-size:22px;font-weight:900;color:" + C.navy + ";font-variant-numeric:tabular-nums;margin-top:2px", sayi(t[a], dil)));
        izg.appendChild(k);
      });
      return izg;
    }

    function eksikMi(s) { return s.sikayet == null || s.talep == null || !s.ci || !s.musteri_no; }
    function satirlar(v) {
      var q = durum.ara.trim().toLocaleLowerCase("tr");
      var l = (v.musteriler || []).filter(function (s) {
        if (durum.filtre === "eksik" && !eksikMi(s)) return false;
        if (durum.filtre === "skorsuz" && s.skor != null) return false;
        return !q || [s.ad, s.tam, s.musteri_no].join(" ").toLocaleLowerCase("tr").indexOf(q) >= 0;
      });
      var a = durum.sira, yon = durum.artan ? 1 : -1;
      l.sort(function (x, y) {
        var p = x[a], r = y[a];
        if (p == null && r == null) return 0; if (p == null) return 1; if (r == null) return -1;
        return (SAYISAL[a] ? p - r : String(p).localeCompare(String(r), "tr")) * yon;
      });
      return l;
    }
    function csvIndir(l) {
      var bas = [m.musteri, m.tam, m.no, m.alarm, m.sikayet, m.talep, m.ci, m.lokasyon, m.finalSkor, m.guncelleme];
      var hucre = function (x) { x = x == null ? "" : String(x); return /[";\n]/.test(x) ? '"' + x.replace(/"/g, '""') + '"' : x; };
      var metin = [bas].concat(l.map(function (s) { return SUTUNLAR.map(function (a) { return a === "skor_zaman" ? zaman(s[a]) : s[a]; }); }))
        .map(function (r) { return r.map(hucre).join(";"); }).join("\r\n");
      var u = URL.createObjectURL(new Blob(["﻿" + metin], { type: "text/csv;charset=utf-8" }));
      var a = el("a"); a.href = u; a.download = "veri-ozeti.csv"; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(u); }, 1000);
    }

    var tabloKutu = null;
    function musteriTablosu(v) {
      var sar = el("section", KART + ";display:grid;gap:10px;padding:14px");
      var ust = el("div", "display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between");
      ust.appendChild(el("h3", "margin:0;font-size:14px;font-weight:900;color:" + C.navy, m.musteriler));
      var araclar = el("div", "display:flex;flex-wrap:wrap;gap:6px;align-items:center");
      var ara = el("input", "min-height:32px;width:260px;max-width:100%;border:1px solid " + C.cizgi + ";border-radius:8px;padding:0 10px;font-size:12px;font-weight:600;color:" + C.metin);
      ara.placeholder = m.ara; ara.value = durum.ara; ara.setAttribute("aria-label", m.ara);
      ara.addEventListener("input", function () { durum.ara = ara.value; govde(); });
      araclar.appendChild(ara);
      [["hepsi", m.hepsi], ["eksik", m.eksik], ["skorsuz", m.skorsuz]].forEach(function (f) {
        var b = el("button", DUGME2, f[1]); b.type = "button";
        if (durum.filtre === f[0]) { b.style.background = C.navy; b.style.color = "#fff"; b.style.borderColor = C.navy; }
        b.addEventListener("click", function () { durum.filtre = f[0]; ciz(); });
        araclar.appendChild(b);
      });
      var csv = el("button", DUGME2, m.csv); csv.type = "button"; csv.addEventListener("click", function () { csvIndir(satirlar(v)); });
      araclar.appendChild(csv);
      ust.appendChild(araclar);
      sar.appendChild(ust);
      var sayac = el("div", "font-size:11.5px;font-weight:700;color:" + C.ikincil);
      sar.appendChild(sayac);
      tabloKutu = el("div", "overflow:auto;max-height:620px;border:1px solid " + C.cizgi + ";border-radius:10px");
      sar.appendChild(tabloKutu);
      function govde() {
        var l = satirlar(v);
        sayac.textContent = m.kayit(l.length, (v.musteriler || []).length);
        tabloKutu.textContent = "";
        var t = el("table", "width:100%;border-collapse:collapse;font-size:12px");
        var th = el("thead"), tr = el("tr");
        [["ad", m.musteri], ["tam", m.tam], ["musteri_no", m.no], ["alarm", m.alarm], ["sikayet", m.sikayet], ["talep", m.talep], ["ci", m.ci], ["lokasyon", m.lokasyon], ["skor", m.finalSkor], ["skor_zaman", m.guncelleme]].forEach(function (c) {
          var h = el("th", "position:sticky;top:0;z-index:1;background:" + C.zemin + ";border-bottom:1px solid " + C.cizgi + ";padding:8px 10px;font-size:11.5px;font-weight:900;color:" + C.navy + ";cursor:pointer;white-space:nowrap;text-align:" + (SAYISAL[c[0]] ? "right" : "left"),
            c[1] + (durum.sira === c[0] ? (durum.artan ? " ▲" : " ▼") : ""));
          h.setAttribute("aria-sort", durum.sira === c[0] ? (durum.artan ? "ascending" : "descending") : "none");
          h.addEventListener("click", function () { if (durum.sira === c[0]) durum.artan = !durum.artan; else { durum.sira = c[0]; durum.artan = !SAYISAL[c[0]]; } govde(); });
          tr.appendChild(h);
        });
        th.appendChild(tr); t.appendChild(th);
        var tb = el("tbody");
        if (!l.length) { var b = el("tr"), d = el("td", "padding:18px;text-align:center;font-weight:700;color:" + C.ikincil, m.bos); d.colSpan = 10; b.appendChild(d); tb.appendChild(b); }
        l.forEach(function (s, i) {
          var r = el("tr", "background:" + (i % 2 ? C.zemin : "#fff"));
          var ad = el("td", "padding:7px 10px;border-bottom:1px solid " + C.cizgi + ";font-weight:800;min-width:200px");
          var link = el("a", "color:" + C.navy + ";text-decoration:none", s.ad); link.href = "#/musteri?m=" + s.id;
          ad.appendChild(link);
          if (s.istirak) ad.appendChild(el("span", "margin-left:6px;font-size:10.5px;font-weight:800;color:" + C.ikincil, m.istirak(s.istirak)));
          r.appendChild(ad);
          r.appendChild(el("td", "padding:7px 10px;border-bottom:1px solid " + C.cizgi + ";font-weight:600;white-space:nowrap", s.tam || "—"));
          r.appendChild(el("td", "padding:7px 10px;border-bottom:1px solid " + C.cizgi + ";font-weight:600;font-variant-numeric:tabular-nums;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap", s.musteri_no || "—"));
          ["alarm", "sikayet", "talep", "ci", "lokasyon"].forEach(function (a) {
            r.appendChild(el("td", "padding:7px 10px;border-bottom:1px solid " + C.cizgi + ";text-align:right;font-weight:700;font-variant-numeric:tabular-nums;color:" + (s[a] == null ? C.amber : C.metin), sayi(s[a], dil)));
          });
          var sk = el("td", "padding:7px 10px;border-bottom:1px solid " + C.cizgi + ";text-align:right;font-weight:900;font-variant-numeric:tabular-nums;color:" + (s.skor == null ? C.ikincil : C.navy), s.skor == null ? "—" : s.skor.toFixed(1));
          r.appendChild(sk);
          var z = el("td", "padding:7px 10px;border-bottom:1px solid " + C.cizgi + ";white-space:nowrap;font-weight:600;color:" + C.ikincil, s.skor_zaman ? zaman(s.skor_zaman) + (s.skor_kaynak ? " · " + (m.kaynakSkor[s.skor_kaynak] || s.skor_kaynak) : "") : "—");
          r.appendChild(z);
          tb.appendChild(r);
        });
        t.appendChild(tb);
        tabloKutu.appendChild(t);
      }
      govde();
      return sar;
    }

    function ciz() {
      var kaydir = tabloKutu ? tabloKutu.scrollTop : 0, odak = document.activeElement && document.activeElement.tagName === "INPUT" && sayfa.contains(document.activeElement);
      sayfa.textContent = "";
      if (durum.hata && !durum.veri) {
        var k = el("div", KART + ";display:flex;gap:10px;align-items:center");
        k.appendChild(el("span", "font-weight:800;color:" + C.kirmizi, durum.hata));
        var b = el("button", DUGME2, m.tekrar); b.type = "button"; b.addEventListener("click", yukle); k.appendChild(b);
        sayfa.appendChild(k); return;
      }
      if (!durum.veri) { sayfa.appendChild(el("div", KART + ";font-weight:700;color:" + C.ikincil, m.yukleniyor)); return; }
      var v = durum.veri;
      sayfa.appendChild(turKarti(v));
      sayfa.appendChild(kaynakKartlari(v));
      var t = el("div", "display:grid;gap:8px");
      t.appendChild(el("h3", "margin:0;font-size:12px;font-weight:900;letter-spacing:.04em;text-transform:uppercase;color:" + C.ikincil, m.toplam));
      t.appendChild(toplamlar(v));
      sayfa.appendChild(t);
      sayfa.appendChild(musteriTablosu(v));
      if (tabloKutu) tabloKutu.scrollTop = kaydir;
      if (odak) { var g = sayfa.querySelector("input"); if (g) { g.focus(); g.setSelectionRange(g.value.length, g.value.length); } }
    }

    ciz();
    yukle();
    kok.__veriOzetiKapat = function () { durum.bitti = true; clearTimeout(durum.zamanlayici); };
  }

  function kaldir(kok) { if (kok && kok.__veriOzetiKapat) kok.__veriOzetiKapat(); if (kok) kok.textContent = ""; }
  window.TamlifeVeriOzeti = { kur: kur, kaldir: kaldir };
})();
