/* DEMO ornegi: parolasiz misafir oturumu + "demo" seridi + modul aciklama karti. Yalniz dist-demo'da bulunur; gercek panelin dist'inde YOKTUR. */
(function () {
  "use strict";
  function istek(yontem, yol) {
    var x = new XMLHttpRequest();
    x.open(yontem, yol, false); // senkron: uygulama acilmadan once oturum hazir olsun
    try { x.send(null); } catch (e) { return 0; }
    return x.status;
  }
  if (istek("GET", "/api/v1/session/me") === 401) istek("POST", "/api/v1/session/misafir");

  var MODUL = {
    "Genel Bakış": ["Genel Bakış", "Giriş sayfası. Ekibin ve modüllerin güncel özetini tek ekranda gösterir; karta tıklayınca ilgili modül açılır.", ["Ekip ve utilizasyon özeti", "Müşteri, alarm, talep sayıları", "Rapor ve proje durumu"]],
    "Müşteri Yönetimi": ["Müşteri Yönetimi", "Portföydeki müşterilerin, iştiraklerin ve müşteri kartlarının tutulduğu ana modül. Müşteri başına sorumlu TAM, ekip, envanter ve alarm/şikayet/talep sayıları görülür.", ["Müşteri ve iştirak ağacı", "Sorumlu TAM ataması", "Rapor alıcıları ve ekip bilgisi"]],
    "İzin&Takvim Yönetimi": ["İzin&Takvim Yönetimi", "Kişisel iş takvimi ve izin kayıtları. Her gün için çalışma durumu, toplantı sayıları ve yapılan işler girilir.", ["Gün durumu (çalışıyor / izinli)", "Online ve yüz yüze toplantı sayısı", "Günlük iş notları"]],
    "Onedesk": ["Onedesk", "Onedesk'ten gelen alarm, talep ve şikayet kayıtlarının müşteri bazında izlendiği ekran.", ["Açık / kapalı kayıtlar", "Kök neden (RCA) ve çözüm notları", "Müşteriye göre filtre ve süre analizi"]],
    "ICT Sms & Gelir": ["ICT Sms & Gelir", "ICT SMS hizmetlerinden elde edilen aylık üretim ve gelir kayıtları.", ["Müşteri ve ay bazlı gelir", "Proje bilgisi", "Toplam ve dışa aktarım"]],
    "APN Gelir ve Kurulum": ["APN Gelir ve Kurulum", "APN gelirleri, kurulum yüzdesi ve müşteri çalışmaları (toplantı, planlı çalışma tarihleri).", ["Kurulum yüzdesi ve teslim tarihi", "Aylık APN geliri", "Müşteri çalışmaları"]],
    "Bağlantılı Araçlar": ["Bağlantılı Araçlar", "Kurum içi bağlantılı araçlara ait müşteri kartları. Müşteri Yönetimi ile aynı yapıda, ayrı portföy olarak tutulur.", ["Ayrı portföy", "Sorumlu ve sayaçlar"]],
    "Toptan": ["Toptan", "Toptan müşterilerin ayrı bir portföy olarak yönetildiği modül.", ["Toptan müşteri kartları", "Sorumlu atama", "Alarm ve talep sayıları"]],
    "TAM Takvim": ["TAM Takvim", "Yetkiniz kapsamındaki ekibin takvim özeti: kim hangi gün çalışıyor, izinli veya toplantıda.", ["Ekip takvim görünümü", "İzin yoğunluğu", "Toplantı sayıları"]],
    "Gönderilen Aylık Rapor": ["Gönderilen Aylık Rapor", "Müşterilere gönderilen aylık TAM raporlarının hazırlandığı ve takip edildiği modül. Rapor PDF'i ve Outlook taslağı (.eml) üretilir.", ["Aylık rapor taslağı ve alıcılar", "SLA analizi ve grafikler", "Gönderim geçmişi"]],
    "Takip Edilen Projeler": ["Takip Edilen Projeler", "TAM'ın yürüttüğü proje, çalışma, DDoS, DC taşıma ve topoloji işlerinin durum ve aksiyon takibi.", ["Durum ve öncelik", "Aksiyon geçmişi", "Müşteri bazlı çalışma işaretleri"]],
    "Gelir Faydası Sağlanan İşler": ["Gelir Faydası Sağlanan İşler", "Gelir, tasarruf veya verimlilik faydası sağlayan işlerin kaydı ve onay akışı.", ["Fayda türü ve tutar", "İşteki TAM'lar", "Onay durumu"]],
    "Çeyrek Sunum": ["Çeyrek Sunum", "Çeyrek sonu sunumu için modüllerin dondurulmuş görüntülerinin toplandığı ve hazırlandığı ekran.", ["Çeyrek bazlı kaynaklar", "Hazır sunum çıktısı", "Excel dışa aktarım"]],
    "Müşteri Radar": ["Müşteri Radar", "Kartı olmayan müşteri numaralarına ait kayıtlardan çıkan fırsatları ve takip edilecek müşterileri gösterir.", ["Kartsız kayıtlar", "Müşteri fırsatları", "Takip kayıtları"]],
    "TAM Utilizasyon": ["TAM Utilizasyon", "Müşteri bazlı kurumsal skor ve kriter yönetimi. Skorlar kriter tablosundan hesaplanır, değişiklikler onaya gider.", ["Skor ve kriter seti", "Onay talepleri", "Skor geçmişi"]],
    "Rol Yönetimi": ["Rol Yönetimi", "Kullanıcıların rollerinin (Sistem Yöneticisi, MANAGER, MEMBER) ve modül yetkilerinin yönetildiği ekran. Girişte roller Keyflow'daki KTS_ gruplarıyla doğrulanır.", ["Rol atama", "Modül ve ek yetkiler", "Denetim kaydı"]],
    "Geliştirme Talepleri": ["Geliştirme Talepleri", "Panel için geliştirme, iyileştirme ve hata talepleri açılır, durumu ve atananı takip edilir.", ["Talep aç", "Durum ve öncelik", "Değişiklik geçmişi"]]
  };

  var kart, baslikEl, metinEl, listeEl;
  function kartKur() {
    kart = document.createElement("aside");
    kart.className = "demo-kart";
    kart.hidden = true;
    kart.innerHTML = '<button type="button" class="demo-kapat" aria-label="Kapat">×</button><small>Bu modül ne iş yapar?</small><h3></h3><p></p><ul></ul><em>Demo: örnek veriler, gerçek kayıt yok.</em>';
    document.body.appendChild(kart);
    baslikEl = kart.querySelector("h3"); metinEl = kart.querySelector("p"); listeEl = kart.querySelector("ul");
    kart.querySelector(".demo-kapat").addEventListener("click", function () { kart.hidden = true; });
  }
  function goster(k) {
    var b = MODUL[k]; if (!b) return;
    baslikEl.textContent = b[0]; metinEl.textContent = b[1];
    listeEl.innerHTML = ""; b[2].forEach(function (m) { var li = document.createElement("li"); li.textContent = m; listeEl.appendChild(li); });
    kart.hidden = false;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var s = document.createElement("div");
    s.className = "demo-serit";
    s.innerHTML = '<b>DEMO</b> Örnek verilerle salt okunur gösterim · gerçek kayıt içermez ' +
      '<a href="https://' + location.hostname + '/">Gerçek panele git</a>';
    document.body.appendChild(s);
    kartKur();
    var c = document.createElement("style");
    c.textContent = ".demo-serit{position:fixed;left:50%;bottom:10px;transform:translateX(-50%);z-index:99999;background:#ffc900;color:#111;" +
      "padding:.4rem .9rem;border-radius:99px;font:600 12px/1.3 system-ui,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.3);white-space:nowrap}" +
      ".demo-serit a{color:#0b1f4d;margin-left:.6rem;text-decoration:underline}.demo-serit b{background:#0b1f4d;color:#ffc900;padding:.05rem .45rem;border-radius:99px;margin-right:.4rem}" +
      ".demo-kart{position:fixed;right:16px;top:76px;width:min(340px,calc(100vw - 32px));z-index:99998;background:#fff;color:#0f172a;border-radius:14px;padding:14px 16px 12px;" +
      "border-top:4px solid #ffc900;box-shadow:0 12px 36px rgba(11,31,77,.35);font:14px/1.5 system-ui,sans-serif}" +
      ".demo-kart[hidden]{display:none}.demo-kart small{color:#64748b;font-weight:700;letter-spacing:.04em;text-transform:uppercase;font-size:11px}" +
      ".demo-kart h3{margin:2px 0 6px;font-size:17px;color:#0b1f4d}.demo-kart p{margin:0 0 8px}.demo-kart ul{margin:0 0 8px;padding-left:18px}.demo-kart em{color:#64748b;font-size:12px}" +
      ".demo-kapat{position:absolute;right:8px;top:4px;border:0;background:transparent;font-size:22px;cursor:pointer;color:#64748b}" +
      "@media(max-width:640px){.demo-serit{white-space:normal;width:92%;text-align:center;border-radius:12px}.demo-kart{top:auto;bottom:64px}}";
    document.head.appendChild(c);
  });

  // Yan menude bir module tiklaninca aciklama karti: tiklanan ogenin metni modul adiyla eslesirse gosterilir.
  document.addEventListener("click", function (e) {
    if (!kart || !e.target || !e.target.closest) return;
    if (e.target.closest(".demo-kart,.demo-serit")) return;
    var o = e.target.closest("a,button,[role=menuitem],[role=tab],li");
    for (var i = 0; o && i < 3; i++, o = o.parentElement && o.parentElement.closest("a,button,[role=menuitem],[role=tab],li")) {
      var t = (o.textContent || "").replace(/\s+/g, " ").trim();
      if (MODUL[t]) { goster(t); return; }
    }
  }, true);
})();
