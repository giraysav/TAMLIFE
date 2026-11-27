/* Utilizasyon > Puanlama (2026-11-21 sadelestirme): "Toplu atama", "Skor agaci" ve "Musteri Listesi" sekmelerinin yerine tek ekran.
   Personele gore gruplu tek musteri listesi; musteriye tiklayinca kriter dokumu acilir. Otomatik kriterler salt okunur, yalniz verisi
   olmayan (elle girilecek) kriterler secilir ve kaydedilir. Istirak "finale dahil" ve "puanlamaya girecek personel" ayarlari da burada.
   React'tan bagimsiz; utilizasyon sayfasi window.TamlifeUtilPuanlama.kur(el, {dil}) ile baglar.
   Uclar: GET /api/v1/skor/agac, PUT /api/v1/skor/toplu/manuel/{id}, PUT /api/v1/skor/istirak/{id}/final-dahil,
   PUT /api/v1/skor/puanlama-disi, POST /api/v1/yonetim/veri-ozeti/calistir (yalniz admin). */
(function () {
  "use strict";
  var C = { navy: "#002855", metin: "#0f172a", ikincil: "#475569", soluk: "#94a3b8", cizgi: "#e2e8f0", zemin: "#f8fafc", yesil: "#047857",
    yesilZ: "#ecfdf5", amber: "#b45309", amberZ: "#fffbeb", kirmizi: "#b91c1c", kirmiziZ: "#fef2f2" };
  var M = {
    tr: {
      baslik: "Puanlama", aciklama: "Skorlar her sabah 06:00'da otomatik güncellenir. Verisi olmayan kriterleri müşterinin dökümünden seçin; eksik kriterli müşterinin skoru dolu kriterlerle orantılı hesaplanır.",
      ara: "Müşteri ya da personel ara…", tumPersonel: "Tüm personel", hepsi: "Tümü", eksikli: "Eksik kriterli", skorsuz: "Skoru yok",
      ozet: function (m, t, e) { return m + " çatı müşteri · " + t + " tamam · " + e + " eksik kriterli"; },
      yenidenHesapla: "Şimdi yeniden hesapla", basladi: "Hesaplama başlatıldı; birkaç dakika içinde skorlar güncellenir.",
      yetkiYok: "Yeniden hesaplamayı yalnız yönetici başlatabilir; skorlar her sabah 06:00'da güncellenir.",
      musteri: "müşteri", skorlu: "skorlu", agirlik: "Ağırlık", atanmamis: "Atanmamış / puanlama dışı",
      mevcut: "Skor", yeni: "Hesaplanan", tamam: "Tamam", eksik: function (n) { return n + " kriter eksik"; }, istirak: function (n) { return "+" + n + " iştirak"; },
      kriter: "Kriter", agirlikKol: "Ağırlık", durum: "Durum", deger: "Değer", puan: "Puan",
      otomatik: "Otomatik", elle: "Elle seçildi", secilmedi: "Seçilmedi", sec: "Seçin", kaydet: "Kaydet", kaydediliyor: "Kaydediliyor…",
      kaydedildi: function (s) { return "Kaydedildi. Yeni skor: " + s; }, degisiklikYok: "Seçim yapılmadı.",
      istirakler: "İştirakler", finaleDahil: "Finale dahil", istirakNot: "Finale dahil edilen iştirake çatı kuralları uygulanır (skor yalnız gösterilir).",
      ayarlar: "Puanlamaya girecek personel", ayarNot: "İşareti kaldırılan personel sıralamaya ve ağırlık hesabına girmez; müşterileri 'Atanmamış' grubunda görünür.",
      ayarKaydet: "Personel seçimini kaydet", ayarKaydedildi: "Personel seçimi kaydedildi.",
      musteriYok: "Eşleşen müşteri yok.", yukleniyor: "Yükleniyor…", yuklenemedi: "Puanlama verisi yüklenemedi.", tekrar: "Tekrar dene",
      kart: "Müşteri kartı"
    },
    en: {
      baslik: "Scoring", aciklama: "Scores update automatically every morning at 06:00. Choose criteria without data in the customer's breakdown; a customer with missing criteria is scored proportionally on the filled ones.",
      ara: "Search customer or staff…", tumPersonel: "All staff", hepsi: "All", eksikli: "Missing criteria", skorsuz: "No score",
      ozet: function (m, t, e) { return m + " parent customers · " + t + " complete · " + e + " with missing criteria"; },
      yenidenHesapla: "Recalculate now", basladi: "Recalculation started; scores update within a few minutes.",
      yetkiYok: "Only an administrator can start a recalculation; scores update every morning at 06:00.",
      musteri: "customers", skorlu: "scored", agirlik: "Weight", atanmamis: "Unassigned / not scored",
      mevcut: "Score", yeni: "Calculated", tamam: "Complete", eksik: function (n) { return n + " criteria missing"; }, istirak: function (n) { return "+" + n + " affiliates"; },
      kriter: "Criterion", agirlikKol: "Weight", durum: "Status", deger: "Value", puan: "Points",
      otomatik: "Automatic", elle: "Chosen", secilmedi: "Not chosen", sec: "Choose", kaydet: "Save", kaydediliyor: "Saving…",
      kaydedildi: function (s) { return "Saved. New score: " + s; }, degisiklikYok: "Nothing chosen.",
      istirakler: "Affiliates", finaleDahil: "Include in final", istirakNot: "Parent rules apply to an included affiliate (score is display-only).",
      ayarlar: "Staff included in scoring", ayarNot: "Unchecked staff are left out of the ranking and weight calculation; their customers appear under 'Unassigned'.",
      ayarKaydet: "Save staff selection", ayarKaydedildi: "Staff selection saved.",
      musteriYok: "No matching customers.", yukleniyor: "Loading…", yuklenemedi: "Scoring data could not be loaded.", tekrar: "Retry",
      kart: "Customer card"
    }
  };

  function el(etiket, stil, metin) { var e = document.createElement(etiket); if (stil) e.style.cssText = stil; if (metin != null) e.textContent = metin; return e; }
  function normal(s) { return String(s || "").toLocaleLowerCase("tr-TR").replace(/[çğıöşü]/g, function (c) { return { "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u" }[c]; }); }
  function puanMetni(v, dil) { return v == null ? "—" : Number(v).toLocaleString(dil === "en" ? "en-US" : "tr-TR", { maximumFractionDigits: 1 }); }
  function csrf() { var m = document.cookie.match(/(?:^|;\s*)tamlife_csrf=([^;]+)/); return m ? decodeURIComponent(m[1]) : ""; }
  function istek(yontem, url, govde) {
    var h = { Accept: "application/json" };
    if (yontem !== "GET") h["X-CSRF-Token"] = csrf();
    if (govde !== undefined) h["Content-Type"] = "application/json";
    return fetch(url, { method: yontem, credentials: "same-origin", headers: h, body: govde === undefined ? undefined : JSON.stringify(govde) }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) {
          var d = j && j.detail, msg = (d && (d.mesaj || (typeof d === "string" ? d : null))) || (j && (j.mesaj || (j.error && j.error.message))) || ("HTTP " + r.status);
          var e = new Error(msg); e.kod = r.status; throw e;
        }
        return j && j.data !== undefined ? j.data : j;
      });
    });
  }
  function rozet(renk, zemin, metin) { return el("span", "display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:800;white-space:nowrap;color:" + renk + ";background:" + zemin + ";border:1px solid " + renk + "33", metin); }
  var KART = "background:#fff;border:1px solid " + C.cizgi + ";border-radius:12px;min-width:0";
  var DUGME = "display:inline-flex;align-items:center;gap:6px;min-height:34px;padding:0 14px;border-radius:8px;border:1px solid " + C.navy + ";background:" + C.navy + ";color:#fff;font-size:12px;font-weight:800;cursor:pointer";
  var DUGME2 = "display:inline-flex;align-items:center;min-height:32px;padding:0 12px;border-radius:8px;border:1px solid " + C.cizgi + ";background:#fff;color:" + C.navy + ";font-size:12px;font-weight:800;cursor:pointer";
  var GIRDI = "min-height:34px;padding:0 10px;border-radius:8px;border:1px solid " + C.cizgi + ";background:#fff;color:" + C.metin + ";font-size:13px";

  function degerMetni(k, dil) {
    var v = k.deger;
    if (v == null || v === "") return "—";
    if (Array.isArray(v)) return v.length ? v.join(", ") : "—";
    if (typeof v === "number") return puanMetni(v, dil);
    return String(v);
  }

  function kur(kok, ayar) {
    var dil = ayar && ayar.dil === "en" ? "en" : "tr", m = M[dil];
    var d = { veri: null, hata: null, ara: "", personel: "", filtre: "hepsi", acik: {}, kapaliGrup: {}, secim: {}, mesaj: {}, genelMesaj: "", ayarAcik: false, kapandi: false };
    kok.textContent = "";
    var sayfa = el("div", "display:grid;gap:14px;font-family:inherit;color:" + C.metin);
    kok.appendChild(sayfa);

    function yukle() {
      return istek("GET", "/api/v1/skor/agac").then(function (v) { if (d.kapandi) return; d.veri = v; d.hata = null; ciz(); })
        .catch(function (e) { if (d.kapandi) return; d.hata = e.message || m.yuklenemedi; ciz(); });
    }
    kok.__puanlamaYenile = yukle;

    function eslesir(c, p) {
      if (d.personel && String(d.personel) !== String(p ? p.id : "atanmamis")) return false;
      if (d.filtre === "eksikli" && !(c.eksik && c.eksik.length)) return false;
      if (d.filtre === "skorsuz" && c.mevcut != null) return false;
      if (!d.ara) return true;
      var a = normal(d.ara);
      return normal(c.ad).indexOf(a) >= 0 || (p && normal(p.ad).indexOf(a) >= 0);
    }

    function ustBolum(v) {
      var k = el("section", KART + ";padding:14px 16px;display:grid;gap:10px");
      var ust = el("div", "display:flex;flex-wrap:wrap;gap:10px;align-items:flex-start;justify-content:space-between");
      var sol = el("div", "min-width:0;flex:1 1 320px");
      sol.appendChild(el("h2", "margin:0;font-size:16px;font-weight:900;color:" + C.navy, m.baslik));
      sol.appendChild(el("p", "margin:4px 0 0;font-size:12px;font-weight:600;color:" + C.ikincil, m.aciklama));
      ust.appendChild(sol);
      var b = el("button", DUGME, m.yenidenHesapla); b.type = "button";
      b.onclick = function () {
        b.disabled = true;
        istek("POST", "/api/v1/yonetim/veri-ozeti/calistir").then(function () { d.genelMesaj = m.basladi; setTimeout(yukle, 45000); ciz(); })
          .catch(function (e) { d.genelMesaj = e.kod === 403 ? m.yetkiYok : e.message; ciz(); });
      };
      ust.appendChild(b);
      k.appendChild(ust);

      var arac = el("div", "display:flex;flex-wrap:wrap;gap:8px;align-items:center");
      var ara = el("input", GIRDI + ";flex:1 1 220px;min-width:0"); ara.type = "search"; ara.placeholder = m.ara; ara.value = d.ara; ara.setAttribute("aria-label", m.ara);
      ara.oninput = function () { d.ara = ara.value; listeyiCiz(); };
      arac.appendChild(ara);
      var ps = el("select", GIRDI); ps.setAttribute("aria-label", m.tumPersonel);
      ps.appendChild(new Option(m.tumPersonel, ""));
      (v.personel || []).forEach(function (p) { ps.appendChild(new Option(p.ad, String(p.id))); });
      if ((v.atanmamis || []).length) ps.appendChild(new Option(m.atanmamis, "atanmamis"));
      ps.value = d.personel; ps.onchange = function () { d.personel = ps.value; listeyiCiz(); };
      arac.appendChild(ps);
      [["hepsi", m.hepsi], ["eksikli", m.eksikli], ["skorsuz", m.skorsuz]].forEach(function (f) {
        var fb = el("button", DUGME2 + (d.filtre === f[0] ? ";background:" + C.navy + ";color:#fff;border-color:" + C.navy : ""), f[1]); fb.type = "button";
        fb.setAttribute("aria-pressed", d.filtre === f[0] ? "true" : "false");
        fb.onclick = function () { d.filtre = f[0]; ciz(); };
        arac.appendChild(fb);
      });
      k.appendChild(arac);
      var tum = [].concat.apply([], (v.personel || []).map(function (p) { return p.musteriler || []; })).concat(v.atanmamis || []);
      var tamamSay = tum.filter(function (c) { return c.tamam; }).length, eksikSay = tum.filter(function (c) { return c.eksik && c.eksik.length; }).length;
      k.appendChild(el("div", "font-size:12px;font-weight:700;color:" + C.ikincil, m.ozet(tum.length, tamamSay, eksikSay)));
      if (d.genelMesaj) k.appendChild(el("div", "font-size:12px;font-weight:700;color:" + C.amber, d.genelMesaj));
      return k;
    }

    function dokum(c) {
      var kutu = el("div", "padding:12px 14px 14px;background:" + C.zemin + ";border-top:1px solid " + C.cizgi + ";display:grid;gap:10px");
      var tablo = el("div", "overflow-x:auto");
      var t = el("table", "width:100%;border-collapse:collapse;font-size:12px;min-width:560px");
      var bas = el("tr");
      [m.kriter, m.agirlikKol, m.durum, m.deger, m.puan].forEach(function (h, i) { bas.appendChild(el("th", "text-align:" + (i === 1 || i === 4 ? "right" : "left") + ";padding:6px 8px;font-weight:800;color:" + C.ikincil + ";border-bottom:1px solid " + C.cizgi, h)); });
      t.appendChild(bas);
      var secim = d.secim[c.id] || (d.secim[c.id] = {});
      (c.kriterler || []).forEach(function (k) {
        var tr = el("tr");
        tr.appendChild(el("td", "padding:6px 8px;font-weight:800;color:" + C.navy, k.baslik));
        tr.appendChild(el("td", "padding:6px 8px;text-align:right;font-family:monospace", "%" + puanMetni(k.agirlik, dil)));
        var dz = el("td", "padding:6px 8px");
        dz.appendChild(k.durum === "otomatik" ? rozet(C.yesil, C.yesilZ, m.otomatik) : k.durum === "manuel" ? rozet(C.navy, "#eff6ff", m.elle) : rozet(C.amber, C.amberZ, m.secilmedi));
        tr.appendChild(dz);
        var deg = el("td", "padding:6px 8px;color:" + C.ikincil + ";max-width:320px");
        var pz = el("td", "padding:6px 8px;text-align:right");
        if (Array.isArray(k.servisler)) {
          // Elle girilen Servis Cesitliligi: alinan servisler isaretlenir.
          if (secim[k.baslik] === undefined) secim[k.baslik] = k.durum === "manuel" && Array.isArray(k.deger) ? k.deger.slice() : null;
          var liste = el("div", "display:flex;flex-wrap:wrap;gap:6px 12px");
          k.servisler.forEach(function (s) {
            var et = el("label", "display:inline-flex;gap:4px;align-items:center;font-weight:700;color:" + C.metin);
            var cb = el("input"); cb.type = "checkbox"; cb.checked = (secim[k.baslik] || []).indexOf(s.ad) >= 0;
            cb.onchange = function () {
              var mevcut = (secim[k.baslik] || []).filter(function (x) { return x !== s.ad; });
              if (cb.checked) mevcut.push(s.ad);
              secim[k.baslik] = mevcut;
            };
            et.appendChild(cb); et.appendChild(document.createTextNode(s.ad));
            liste.appendChild(et);
          });
          deg.appendChild(liste);
          pz.textContent = k.durum === "eksik" ? "—" : puanMetni(k.puan, dil);
        } else if (Array.isArray(k.secenekler) && k.secenekler.length) {
          deg.textContent = degerMetni(k, dil);
          if (secim[k.baslik] === undefined) secim[k.baslik] = k.durum === "manuel" ? k.puan : null;
          var sel = el("select", GIRDI + ";min-height:30px"); sel.setAttribute("aria-label", k.baslik);
          sel.appendChild(new Option(m.sec, ""));
          k.secenekler.forEach(function (o) { sel.appendChild(new Option(o.puan + (o.etiket ? " · " + o.etiket : ""), String(o.puan))); });
          sel.value = secim[k.baslik] == null ? "" : String(secim[k.baslik]);
          sel.onchange = function () { secim[k.baslik] = sel.value === "" ? null : Number(sel.value); };
          pz.appendChild(sel);
        } else {
          deg.textContent = degerMetni(k, dil);
          pz.style.fontFamily = "monospace"; pz.style.fontWeight = "800";
          pz.textContent = puanMetni(k.puan, dil);
        }
        tr.appendChild(deg); tr.appendChild(pz);
        t.appendChild(tr);
      });
      tablo.appendChild(t);
      kutu.appendChild(tablo);

      var elle = (c.kriterler || []).some(function (k) { return Array.isArray(k.servisler) || (Array.isArray(k.secenekler) && k.secenekler.length); });
      var alt = el("div", "display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:flex-end");
      if (d.mesaj[c.id]) alt.appendChild(el("span", "font-size:12px;font-weight:700;color:" + (d.mesaj[c.id].hata ? C.kirmizi : C.yesil), d.mesaj[c.id].metin));
      var kartLink = el("a", DUGME2 + ";text-decoration:none", m.kart); kartLink.href = "#/musteri?m=" + encodeURIComponent(c.id);
      alt.appendChild(kartLink);
      if (elle) {
        var kb = el("button", DUGME, m.kaydet); kb.type = "button";
        kb.onclick = function () {
          var govde = {};
          Object.keys(secim).forEach(function (b) { if (secim[b] != null) govde[b] = secim[b]; });
          if (!Object.keys(govde).length) { d.mesaj[c.id] = { metin: m.degisiklikYok, hata: true }; ciz(); return; }
          kb.disabled = true; kb.textContent = m.kaydediliyor;
          istek("PUT", "/api/v1/skor/toplu/manuel/" + encodeURIComponent(c.id), { secimler: govde }).then(function (r) {
            d.mesaj[c.id] = { metin: m.kaydedildi(puanMetni(r && r.yeni, dil)), hata: false }; delete d.secim[c.id]; return yukle();
          }).catch(function (e) { d.mesaj[c.id] = { metin: e.message, hata: true }; ciz(); });
        };
        alt.appendChild(kb);
      }
      kutu.appendChild(alt);

      if ((c.istirakler || []).length) {
        var ib = el("div", "display:grid;gap:6px;border-top:1px dashed " + C.cizgi + ";padding-top:10px");
        ib.appendChild(el("div", "font-size:12px;font-weight:900;color:" + C.navy, m.istirakler));
        ib.appendChild(el("div", "font-size:11px;font-weight:600;color:" + C.ikincil, m.istirakNot));
        c.istirakler.forEach(function (i) {
          var s = el("label", "display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:12px;font-weight:700");
          var cb = el("input"); cb.type = "checkbox"; cb.checked = !!i.dahil; cb.setAttribute("aria-label", m.finaleDahil + ": " + i.ad);
          cb.onchange = function () {
            cb.disabled = true;
            istek("PUT", "/api/v1/skor/istirak/" + encodeURIComponent(i.id) + "/final-dahil", { dahil: cb.checked }).then(yukle)
              .catch(function (e) { d.mesaj[c.id] = { metin: e.message, hata: true }; cb.checked = !cb.checked; cb.disabled = false; ciz(); });
          };
          s.appendChild(cb);
          s.appendChild(el("span", "color:" + C.metin, i.ad));
          s.appendChild(el("span", "color:" + C.ikincil, m.finaleDahil));
          if (i.dahil && i.yeni != null) s.appendChild(el("span", "margin-left:auto;font-family:monospace;font-weight:800;color:" + C.navy, puanMetni(i.yeni, dil)));
          ib.appendChild(s);
        });
        kutu.appendChild(ib);
      }
      return kutu;
    }

    function musteriSatiri(c) {
      var sar = el("div", "border-top:1px solid " + C.cizgi);
      // Musteri satiri: icerden baslar, normal harf ve koyu gri (personel basligindan ayrilir).
      var satir = el("button", "all:unset;box-sizing:border-box;width:100%;display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;padding:9px 16px 9px 30px;cursor:pointer;background:#fff;text-transform:none");
      satir.type = "button"; satir.setAttribute("aria-expanded", d.acik[c.id] ? "true" : "false");
      satir.onmouseenter = function () { satir.style.background = C.zemin; };
      satir.onmouseleave = function () { satir.style.background = "#fff"; };
      satir.appendChild(el("span", "font-size:12px;color:" + C.soluk + ";width:10px", d.acik[c.id] ? "▾" : "▸"));
      satir.appendChild(el("span", "font-size:13px;font-weight:600;color:#334155;text-transform:none;flex:1 1 220px;min-width:0;overflow-wrap:anywhere", c.ad));
      if ((c.istirakler || []).length) satir.appendChild(el("span", "font-size:11px;font-weight:700;color:" + C.ikincil, m.istirak(c.istirakler.length)));
      satir.appendChild(c.eksik && c.eksik.length ? rozet(C.amber, C.amberZ, m.eksik(c.eksik.length)) : rozet(C.yesil, C.yesilZ, m.tamam));
      var skor = el("span", "min-width:110px;text-align:right;font-family:monospace;font-size:13px");
      skor.appendChild(el("b", "color:" + C.navy, puanMetni(c.mevcut, dil)));
      if (c.yeni != null && (c.mevcut == null || Math.abs(c.yeni - c.mevcut) >= 0.1)) skor.appendChild(el("span", "color:" + C.amber + ";margin-left:6px", "→ " + puanMetni(c.yeni, dil)));
      satir.appendChild(skor);
      satir.title = c.eksik && c.eksik.length ? c.eksik.join(", ") : "";
      satir.onclick = function () { d.acik[c.id] = !d.acik[c.id]; listeyiCiz(); };
      sar.appendChild(satir);
      if (d.acik[c.id]) sar.appendChild(dokum(c));
      return sar;
    }

    function grup(baslik, ek, musteriler, anahtar) {
      var g = el("section", KART + ";overflow:hidden");
      // Personel basligi: lacivert serit + bas harf rozeti (musteri satirlarindan acikca ayrilsin; 2026-11-21 kullanici geri bildirimi).
      var h = el("button", "all:unset;box-sizing:border-box;width:100%;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;padding:12px 16px;cursor:pointer;background:" + C.navy + ";color:#fff");
      h.type = "button"; var kapali = !!d.kapaliGrup[anahtar]; h.setAttribute("aria-expanded", kapali ? "false" : "true");
      h.appendChild(el("span", "font-size:12px;color:#cbd5e1;width:10px", kapali ? "▸" : "▾"));
      var harf = String(baslik || "?").trim().split(/\s+/).slice(0, 2).map(function (x) { return x.charAt(0); }).join("");
      h.appendChild(el("span", "display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:999px;background:#ffc72c;color:" + C.navy + ";font-size:11px;font-weight:900;flex:none", harf));
      h.appendChild(el("span", "font-size:15px;font-weight:900;color:#fff;flex:1 1 200px;letter-spacing:.02em", baslik));
      h.appendChild(el("span", "font-size:12px;font-weight:700;color:#e2e8f0", ek));
      h.onclick = function () { d.kapaliGrup[anahtar] = !d.kapaliGrup[anahtar]; listeyiCiz(); };
      g.appendChild(h);
      if (!kapali) musteriler.forEach(function (c) { g.appendChild(musteriSatiri(c)); });
      return g;
    }

    var liste = el("div", "display:grid;gap:10px");
    function listeyiCiz() {
      liste.textContent = "";
      var v = d.veri, adet = 0;
      (v.personel || []).forEach(function (p) {
        var ms = (p.musteriler || []).filter(function (c) { return eslesir(c, p); });
        if (!ms.length) return;
        adet += ms.length;
        var ek = p.musteri_sayisi + " " + m.musteri + " · " + p.skorlu_musteri + " " + m.skorlu + " · " + m.agirlik + " " + puanMetni(p.agirlik_puani, dil);
        liste.appendChild(grup(p.ad, ek, ms, "p" + p.id));
      });
      var at = (v.atanmamis || []).filter(function (c) { return eslesir(c, null); });
      if (at.length) { adet += at.length; liste.appendChild(grup(m.atanmamis, at.length + " " + m.musteri, at, "atanmamis")); }
      if (!adet) liste.appendChild(el("div", KART + ";padding:16px;font-size:13px;font-weight:700;color:" + C.ikincil, m.musteriYok));
    }

    function ayarBolumu(v) {
      var k = el("details", KART + ";padding:12px 16px");
      if (d.ayarAcik) k.open = true;
      k.ontoggle = function () { d.ayarAcik = k.open; };
      k.appendChild(el("summary", "cursor:pointer;font-size:13px;font-weight:900;color:" + C.navy, m.ayarlar));
      k.appendChild(el("p", "margin:8px 0;font-size:12px;font-weight:600;color:" + C.ikincil, m.ayarNot));
      var izgara = el("div", "display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:6px 14px");
      var kutular = [];
      (v.tum_personel || []).forEach(function (p) {
        var et = el("label", "display:flex;gap:6px;align-items:center;font-size:12px;font-weight:700");
        var cb = el("input"); cb.type = "checkbox"; cb.checked = !!p.dahil; cb.value = String(p.id);
        kutular.push(cb);
        et.appendChild(cb); et.appendChild(document.createTextNode(p.ad + " (" + p.musteri_sayisi + ")"));
        izgara.appendChild(et);
      });
      k.appendChild(izgara);
      var alt = el("div", "display:flex;gap:10px;align-items:center;justify-content:flex-end;margin-top:10px");
      var not = el("span", "font-size:12px;font-weight:700");
      var b = el("button", DUGME, m.ayarKaydet); b.type = "button";
      b.onclick = function () {
        b.disabled = true;
        var disi = kutular.filter(function (x) { return !x.checked; }).map(function (x) { return Number(x.value); });
        istek("PUT", "/api/v1/skor/puanlama-disi", { disi: disi }).then(function () { not.style.color = C.yesil; not.textContent = m.ayarKaydedildi; return yukle(); })
          .catch(function (e) { not.style.color = C.kirmizi; not.textContent = e.message; b.disabled = false; });
      };
      alt.appendChild(not); alt.appendChild(b);
      k.appendChild(alt);
      return k;
    }

    function ciz() {
      sayfa.textContent = "";
      if (d.hata && !d.veri) {
        var h = el("div", KART + ";padding:16px;display:flex;gap:10px;align-items:center;color:" + C.kirmizi + ";font-weight:700;font-size:13px", d.hata);
        var tb = el("button", DUGME2, m.tekrar); tb.type = "button"; tb.onclick = yukle; h.appendChild(tb);
        sayfa.appendChild(h); return;
      }
      if (!d.veri) { sayfa.appendChild(el("div", "font-size:13px;color:" + C.ikincil, m.yukleniyor)); return; }
      sayfa.appendChild(ustBolum(d.veri));
      sayfa.appendChild(liste);
      listeyiCiz();
      sayfa.appendChild(ayarBolumu(d.veri));
    }

    kok.__puanlamaKapat = function () { d.kapandi = true; };
    ciz();
    yukle();
  }
  function kaldir(kok) { if (kok && kok.__puanlamaKapat) kok.__puanlamaKapat(); if (kok) kok.textContent = ""; }
  function yenile(kok) { if (kok && kok.__puanlamaYenile) kok.__puanlamaYenile(); }
  window.TamlifeUtilPuanlama = { kur: kur, kaldir: kaldir, yenile: yenile };
})();
