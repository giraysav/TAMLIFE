# ReportDB tablo keşfi (2026-10-17)

Kaynak `oracle_reportdb` (`REPORTDB_*`), Windows hesabı `TURKCELL\TAMLIFEADLOG`, LADIN01. Keşif yalnız veri sözlüğünü ve toplam sayıları okudu; müşteri satırı listelenmedi. Araç: `python -m araclar.reportdb_kesif [--sahip ŞEMA]` → `backend/var/kesif/oracle_reportdb-<tarih>.{json,md}` (git dışı; sütun listelerinin tamamı oradadır).

## İzinler

Oturum rolü yalnız `CONNECT`; rol üzerinden tablo izni yok. Doğrudan 13 SELECT izni (12'si kullanıcının bildirdiği TEMIP listesi, biri ek):

| Nesne | Satır | Tazelik (2026-10-17 20:45) | Değerlendirme |
|---|---:|---|---|
| `TEMIP.ACTIVEALARMS_5DK_S1` / `_S2` | ~563 bin (anlık) | `INSERT_DATE` 20:42 / 20:39 | **Canlı anlık açık alarm görüntüsü.** İki tablo sırayla 5 dakikada bir yeniden doldurulur (çift tampon). |
| `TEMIP.ACTIVEALARMS_5DK` (eş ad) | — | şu an `_S1`'i gösterir | Mevcut sorgu bunu kullanır. Dolum sırasında yarım tabloyu okumamak için doğrudan S1/S2 yerine **eş ad kullanılmalı**. |
| `TEMIP.VIEW_REPORT_ACTIVE` | ~2,09 milyar (ist. 2026-03) | son 2 günde 3,26 milyon; `INSERT_DATE` 20:40 | **Canlı alarm geçmişi** (kapanan alarmlar dahil). `EVENTTIME` ile bölümlü: her sorgu üst/alt sınırlı `EVENTTIME` filtresi taşımalı. `MAX(EVENTTIME)` saatin ilerisinde (23:58) — ileri tarihli kayıt var. |
| `TEMIP.VIEW_REPORT_ARCHIEVE` | ~459 milyon (ist. 2025-07) | son 400 günde kayıt yok | Eski arşiv; güncel işte kullanılmaz. |
| `TEMIP.VIEW_REPORT_EXPORT` | — | son 2 günde kayıt yok | Boş/ara tablo görünümünde. |
| `TEMIP.ACTIVEALARMS_1SA` | 176.726 | son olay 2017-09 | Kullanılmayan eski tablo. |
| `TEMIP.ALARMS` | 21.715 | son kayıt 2018-12 | Eski tablo. |
| `TEMIP.LOG` | 161.468 | son arama 2021-09 | Eski IVR arama günlüğü; **kişi adı ve telefon numarası içerir — kullanılmamalı.** |
| `TEMIP.TEMIP_SLA` | 8 | 2016–2020 | TEMIP'in kendi entegrasyon KPI'ları (müşteri SLA'sı değil), güncellenmiyor. |
| `TEMIP.TEMIP_UPDATE_TIME` | 1 | 2022-02 | Eski güncelleme işareti; tazelik için güvenilmez (yerine `INSERT_DATE`). |
| `TEMIP.DOMAIN_OC` | 118 | — | Domain → OC eşlemesi (başvuru tablosu). |
| `TEMIP.IE` | 1.831 | — | Tek sütun `WONUM` (iş emri no listesi). |
| `OWB_TEMIP.TEMP_ALARM` | — | — | Kullanıcı listesinde yok, ayrıca verilmiş: kapı açılma / alarm türü geçişleri (`CIID`, `CINAME`, `DOOR_OPENED`). |

İzin listesinde olmayan ama `PUBLIC` üzerinden görünen nesneler: `SOL.SPECTRUM_DAILY_2`, `SOL.SPECTRUM_MODELOUTAGE`, `TCSULAS.ACTIVEALARMS_5DK_S1/_S2`, `TCSULAS.VIEW_REPORT_ACTIVE`, `TCSULAS.VIEW_REPORT_STG`, `TCSULAS.PY_ETL_JOB_LOGS` ve birkaç OWBSYS/ADMIN nesnesi. Bunlar bizim için verilmiş izinler değil; kullanılmaz.

**DBA'ya bildirilecek:** `SOL` ve `TCSULAS` şemalarındaki bu tablolarda `PUBLIC` rolüne INSERT/UPDATE/DELETE/ALTER izni verilmiş; veritabanına bağlanabilen her hesap bu tabloları değiştirebilir. TAMLIFE yalnız SELECT kullanır (`oracle.sorgu_temizle`).

## Canlı alarm tablolarının yapısı

`ACTIVEALARMS_5DK_*` (112 sütun) ve `VIEW_REPORT_ACTIVE` (102 sütun) aynı TeMIP alarm modelidir. Panel için öne çıkan sütunlar:

- **Kimlik / eşleşme:** `IDENTIFIER`, `INFORMATION1` (8 haneli Müşteri No — mevcut sorgunun eşleşme anahtarı), `INFORMATION2` (ünvan), `INFORMATION3`–`INFORMATION10` (anlamı henüz profillenmedi), `CORPARATECIRCUITDETAIL` (kurumsal devre ayrıntısı), `SERVICENAME`, `SERVICEOWNER`.
- **Zaman:** `EVENTTIME` (bölüm anahtarı), `ORIGINALEVENTTIME`, `CREATIONTIMESTAMP`, `ACKNOWLEDGEMENTTIMESTA`, `HANDLETIMESTAMP`, `CLEARANCETIMESTAMP`, `CLOSETIMESTAMP`, `TERMINATIONTIMESTAMP`, `INSERT_DATE` (yükleme zamanı).
- **Sınıflama:** `NETWORK` (anlık görüntüde ACCESS 491 bin, **NOC DESTECH 34.741**, IT, TV+, CORE, BACKBONE…; değerler tırnaklı gelebilir, `REPLACE(NETWORK,'"','')`), `PERCEIVEDSEVERITY`, `ORIGINALSEVERITY`, `PRIORITY`, `ALARMTYPE`, `PROBABLECAUSE`, `SPECIFICPROBLEMS`, `TECHNOLOGYDOMAIN`, `NODETYPE`, `OUTAGEFLAG`, `SERVICEEFFECT`, `PLANNED`.
- **Bilet:** `ALARMOBJECTOPERATORNO` (biletli alarm; mevcut sorgu "biletli" sayısını buradan alır), `TTUNIQUEID`, `TTASSIGNED`, `TTINFORMATION`, `TTRULECODE`, `FAULTBULLETINID`, `COMPLAINTCOUNT`.
- **Yer:** `CITY`, `COUNTY`, `REGIONLOCATION`, `SITEID`, `NODE1`–`NODE3`, `IPADDRESS`.
- `VIEW_REPORT_ACTIVE`'e özgü: `ARCHIVETIMESTAMP`, `CLOSEDBY_1`, `CORRELTAG`, `CORRELGROUP`, `ALARMJOURNAL`.

Mevcut senkron (`tampon/reportdb.py`) zaten doğru iki kaynağı kullanır: açık alarm `TEMIP.ACTIVEALARMS_5DK` (eş ad), kapanan alarm `TEMIP.VIEW_REPORT_ACTIVE` (yıl başından, `EVENTTIME` iki yönlü sınırlı).

## OC domainleri ve kurumsal kayıtlar (2026-10-17, ikinci tur)

Sütun başlıkları ve her tablonun ilk satırı: `backend/var/kesif/ilk-satirlar-20261017.txt` (git dışı; canlı tablolarda örnek kurumsal + Müşteri No'lu alarmdır, `LOG` değerleri yazılmadı).

**OC adlandırması.** Canlı tablolarda `OCNAME` = `fmp_ns:.<p|s>.oc.tcell.<fix|mbl|all>.<ad>_<no>`, `DOMAIN` = `Domain fmp_ns:.<p|s>.DOM.TCELL.…` (aynı adın DOM karşılığı; `.p.` birincil, `.s.` ikincil). Anlık görüntüde 42 OC var, hepsi `.oc.` içerir. `TEMIP.DOMAIN_OC` (118 satır) eski TeMIP adlarını (`.DOM.X → OC.X`, `tcell_ns:` dönemi) tutar; canlı değerlerle eşleşmez, eşleme için kullanılmaz.

**Kurumsal alarmların OC'leri** (anlık görüntü, `NETWORK = NOC DESTECH`):

| OCNAME | Alarm | Biletli | Müşteri No'lu |
|---|---:|---:|---:|
| `fmp_ns:.p.oc.tcell.all.tran_u2000_21` | 15.654 | 2 | 0 |
| **`fmp_ns:.p.oc.tcell.fix.ent_snmp_12`** | 15.557 | 8.390 | **12.188** |
| `fmp_ns:.p.oc.tcell.fix.traf_snmp_22` | 3.040 | 974 | 0 |
| `fmp_ns:.p.oc.tcell.all.ent_sec_snmp_22` | 402 | 402 | 0 |
| diğer 6 OC | 103 | 43 | 0 |

Müşteri No'lu kurumsal alarmların tamamı **`oc.tcell.fix.ent_snmp_12`** (Enterprise SNMP) OC'sindedir; diğer NOC DESTECH OC'leri altyapı (iletim/trafik) alarmıdır. Mevcut senkron müşteri no koşuluyla zaten bu kümeyi sayar.

**Kurumsal alarm satırında anlamı çıkan sütunlar** (örnek satırlardan):

- `INFORMATION1` 8 haneli Müşteri No, `INFORMATION2` ünvan, `INFORMATION3` arayüz (ör. `Virtual-Ethernet3/0/1.3420`), `INFORMATION10` otomatik iş emri senaryosu XML'i (`<scen><vp>AKILLI_OIE_FIX-1.4</vp><p>pb_AKILLI_OIE_aktif|pasif</p><ticket/></scen>`).
- `MANAGEDOBJECT` / `NODE1`: Lookouteyes CI adı (`tcell_lookouteyes fmp_ns:.p.node.loe3 ne "nw_li_cust_tsol_rl_int_<müşteri>_<no>_<ilçe><il>"`), `NODETYPE = LOE`, `SITEID` (KM…), `CITY`/`COUNTY`, `IPADDRESS`/`REMOTEIPADDRESS`.
- `CORPARATECIRCUITDETAIL` hizmet tipi (ör. `TSOL_INTERNETRadioLink`, `TSOL_Wifi_AP1`), `TOPOLOGY` önem + hız (ör. `MAJOR,50Mbps`).
- `ALARMHEADER` (ör. `AVAILABILITY`), `ADDITIONALTEXT` (prob ayrıntısı), `PERCEIVEDSEVERITY`, `STATE` (Outstanding…), `PROBLEMSTATUS` (Handled…), `FILTERNAME`.
- **Bilet:** `ALARMOBJECTOPERATORNO` = 11 haneli bilet no + not (ör. `10134688401 <AD>-ULASILAMADI 1`), `HANDLEDBY` aynı bilet no; `TTASSIGNED` (ör. `TEAM-NOC-OTOTICKET`), `TTINFORMATION` (`CreateTT`), `TTRULECODE` / `CORREL_SETTINGS OIE_CODE` (ör. `ON_400.405`), `TTUNIQUEID`. Arşiv satırlarında `ADDITIONALTEXT` içinde `UpdateOneDeskTicket` geçer: bilet OneDesk biletidir.
- Kapanış: `CLEARANCETIMESTAMP`, `CLOSETIMESTAMP`, `CLOSEUSERIDENTIFIER` (`Auto-Clear` ya da kullanıcı), `TERMINATIONTIMESTAMP`.

**Talep ve şikayet.** İzin verilen tablolar TeMIP **alarm** yönetimidir; müşterinin açtığı talep/şikayet kaydı burada yoktur. Alarmla ilişkili izler: `ALARMOBJECTOPERATORNO` / `HANDLEDBY` (OneDesk bilet no), `TT*` alanları ve `COMPLAINTCOUNT` (alarma bağlı şikayet sayısı; örnek satırlarda boş). Talep/şikayetin kendisi için OneDesk bilet tablolarına erişim gerekir (bu izin kümesinde yok).

## Hedef veri seti: NOC DESTECH son 6 saat (2026-10-17 15:09–21:09)

Kullanıcı kararı: TeMIP'ten alınacak alanlar **müşteri no, ünvan, OneDesk ticket, CI name, ticket durumu**. Çıktı: `backend/var/kesif/nocdestech-6saat-birlesik-*.csv` (git dışı).

- **Kaynak ayrımı:** `VIEW_REPORT_ACTIVE` yalnız **kapanmış** alarmları tutar (her OC'de kapanan = toplam). Açık alarmlar yalnız `ACTIVEALARMS_5DK`'dadır. Tam akış = 5DK (açık) ∪ VIEW_REPORT_ACTIVE (kapalı); `IDENTIFIER` iki tabloda aynı alarmdır (TeMIP alarm nesnesi no; `TTUNIQUEID` içinde `alarm_object <IDENTIFIER>` olarak geçer). Ticket durumu değildir.
- **Sayılar:** 2.249 akış (676 açık, 1.573 kapalı). Müşteri No'lu kurumsal akış 776'nın **tamamı `ent_snmp_12`**; 246 müşteri, 482 CI, 466 ticket. **Her ticket tek akışa bağlı** (kurumsal alarm başına ayrı OneDesk bileti). Ticketlı ama müşteri no'suz akışlar altyapı OC'leridir (bir bilete 3–5 alarm bağlanır).
- **Alanlar:** müşteri no `INFORMATION1`, ünvan `INFORMATION2`, ticket `REGEXP_SUBSTR(ALARMOBJECTOPERATORNO,'^[0-9]+')` (11 hane, `10134…`; ardından operatör notu gelebilir: `FP`, `FAKE`, `GEKESIK`, `ADN-AY`, `INOC`…), CI `REGEXP_SUBSTR(ADDITIONALTEXT,'CIName:[[:space:]]*([^[:space:]]+)',1,1,NULL,1)` (yoksa `NODE1`; ayırıcı boşluk değil, `[[:space:]]` şart). Açık alarmda `HANDLEDBY`, kapalıda `CLOSEDBY_1` ticket no ile aynıdır.
- **Ticket durumu:** OneDesk'in kendi statüsü (açık/çözüldü/kapandı) TeMIP'te **yoktur**. Alarm yaşam döngüsünden türetilebilecek durum:

| Kaynak / STATE / PROBLEMSTATUS | Ticket | Akış (müşteri no'lu) | Türetilmiş anlam |
|---|---|---:|---|
| Açık / Outstanding / Not-Handled | yok | 57 | Alarm açık, ticket henüz açılmadı (5 dk geçici filtre `TRANSIENTFILTRE05DK`) |
| Açık / Outstanding / Handled | var | 93 | Ticket açık, kesinti sürüyor |
| Açık / Acknowledged / Handled | var | 3 | Ticket açık, operatör üstlendi |
| Açık / Terminated / Handled | var | 63 | Alarm temizlendi, ticket kapanışı bekleniyor |
| Kapalı / `CLOSEUSERIDENTIFIER = atm` | var | 298 | Ticket otomasyonla kapatıldı (`CLOSEDBY_1` = ticket) |
| Kapalı / `Auto-Clear` | yok | 262 | Kısa kesinti; ticket açılmadan kendiliğinden temizlendi |

`TTINFORMATION` CreateTT (yeni bilet) / AssociateTT (mevcut bilete bağlama), `TTRULECODE` OIE kural kodu (ON_400.40x, ON_421.x, ON_200.905…), `TTASSIGNED` ekip (TEAM-NOC-OTOTICKET, TEAM-INOC, TEAM-KURUMSAL-UYDU). Gerçek OneDesk statüsü için OneDesk bilet tablosu gerekir.

## Alarm / talep / şikayet hangi tabloda (2026-10-17)

- **TEMIP şemasında görünen nesneler** yalnız izin verilen 12 tablo, indeksleri ve `PERCENT` fonksiyonudur (`ALL_OBJECTS`); başka şemadan TEMIP'e bağımlı görünen nesne yok. Talep/şikayet adlı bir tablo bu hesaba görünmez.
- **Alarm:** `ACTIVEALARMS_5DK` (açık) + `VIEW_REPORT_ACTIVE` (kapalı). Kurumsal müşteri alarmı = `NODETYPE = LOE`, `ALARMHEADER` `AVAILABILITY` (3 günde 16.862 müşteri no'lu) ya da `DELAY` (16), OC `ent_snmp_12`. Diğer NOC DESTECH başlıkları (Link Down, Trafik Seviye QOS, SDWAN ipsec/bgp, DDOS, PLANLI CALISMA ALARMI…) müşteri no taşımaz.
- **Talep:** TEMIP'te yok. `NODETYPE = ONEDESK` (`QualityofServiceAlarm`, 3 günde 1.694) OneDesk'ten gelen **planlı çalışma** alarmıdır, müşteri no taşımaz; talep kaydı değildir.
- **Şikayet:** TEMIP'te kayıt olarak yok. `COMPLAINTCOUNT` yalnız ACCESS (mobil erişim) alarmlarında dolu (canlı 672 alarm, toplam 1.050); NOC DESTECH'te 3 günde hiç dolu değil. "SIKAYET/TALEP/COMPLAINT" metin aramasında kurumsal kayıt çıkmadı.
- Sonuç: kurumsal **talep ve şikayet** kayıtları için OneDesk bilet tablolarına erişim gerekir; TEMIP yalnız alarm ve alarmın OneDesk ticket numarasını verir.

## Panel müşteri kartlarıyla eşleşme (NOC DESTECH son 6 saat)

Kural reportdb senkronuyla aynı: yalnız Müşteri No (`eslestirme.musteri_anahtarlari`), bir numara birden çok karta düşerse belirsiz. Çıktı `backend/var/kesif/nocdestech-6saat-panel-eslesme-*.csv` (TEMIP alanları + panel kart no, panel ünvanı, çatı, sorumlu TAM).

- 776 müşteri no'lu akış, 246 TEMIP müşterisi. **45 müşteri (349 akış, 86'sı ticketlı) panel kartıyla tek eşleşti**; belirsiz eşleşme yok.
- 201 müşteri (427 akış) panelde kartı olmayan kurumsal müşteridir (panel 334 kartlık TAM portföyüdür; ör. Vodafone Net 73 akış, TEB 9 akış). Bunlar panel dışıdır ya da kartında bu Müşteri No yazılı değildir (iştirak numarası eksik olabilir).
- TEMIP ünvanı Türkçe karaktersiz ve kısaltmasızdır; panel ünvanı kısa ad olabilir (ör. `TURKCELL ILETISIM…` ↔ `TİM`). Eşleşme ünvanla değil numarayla yapılmalı.

## Uygulama: TEMIP kayıtları panele (2026-10-17 kullanıcı kararı)

Kural: (1) Müşteri No'su paneldeki bir kartla eşleşen kayıt o karta, yani sorumlu personele atanır; (2) eşleşmeyen kayıt TAM Radar'a düşer; (3) 01.01.2026 00:00'dan itibaren açılan kayıtlar alınır; (4) tür ayrımı: TEMIP yalnız **alarm** verir, talep/şikayet OneDesk'ten gelir (uydurma tür üretilmez).

- **Modül:** `backend/app/tampon/temip_kayit.py`. Kayıt `onedesk_record` (`source='temip'`, `external_key` = TeMIP `IDENTIFIER`, yeni sütunlar `ticket_no`, `customer_no`, `detail`; Alembic `0013_onedesk_temip`). CI → `location`, alarm başlığı → `category`, `detail` = açık alarmda `STATE/PROBLEMSTATUS`, kapalıda `Closed/atm|Auto-Clear|operator` (kapatan kişinin adı alınmaz).
- **Kipler:** `python -m app.isci temip-kayit --kip tam` ilk yükleme (başlangıçtan bugüne ay ay, ~695 bin kayıt; yalnız toplam sorgusu 6 dk sürdü), `artimli` (6 dk görevin her turu: son 1 günde kapananlar + açık anlık görüntü + görüntüden düşen açıkların kapanışı `IDENTIFIER` ile, açılış aralığına sınırlı), `mutabakat` (günde bir kez 02:00'dan sonraki ilk turda son 30 gün). Başlangıç `REPORTDB_KAYIT_BASLANGIC` (varsayılan `2026-01-01`). Kapalı kayıt yeniden açılmaz; yazım idempotenttir (aynı `IDENTIFIER` güncellenir).
- **Atama:** her tur kart bağlantıları Müşteri No'ya göre tazelenir (karta numara eklenince Radar kaydı o karta geçer, numara çıkınca Radar'a döner); bir numara birden çok karta düşerse Radar'da kalır. Kart sayaçları (`alarm_count`, `alarm_closed_count`) kayıtlardan yeniden hesaplanır.
- **Onedesk ekranı** kartsız TEMIP kayıtlarını saymaz (`onedesk/servis._kapsam_kosulu`).
- **TAM Radar** (`GET /api/v1/radar?sayfa&adet&q`, `GET /api/v1/radar/{musteri_no}/kayitlar`): Müşteri No bazında açık/kapalı/ticketlı/son kayıt, arama, sayfalama; aynı ünvan çekirdeğine sahip numarasız kart varsa "kart adayı" rozeti. TEMIP kaydı yoksa eski özet kuralı (ilk 10) çalışır.
- **İşçi:** `python -m app.isci reportdb` alarm kayıtlarını "Kartlara yaz" anahtarından bağımsız her turda yazar; eski "kart başına 500 kayıt, her turda sil-yaz" yolu (`reportdb.kayit_partisi`) kaldırıldı.

## Eşleşme denetimi ve içeri alma komut seti (2026-10-17)

Zincir: TEMIP `INFORMATION1` (Müşteri No) → `INFORMATION2` (ünvan) → kart (`eslestirme.musteri_anahtarlari`, yalnız numara) → sorumlu personel (kart sahibi; iştirakte sahip boşsa çatının sahibi) → açık / kapalı kayıt. Kod: `temip_kayit.Eslesme` (yazımla aynı `_kart()` kuralı), `eslesme_raporu(db)` (paneldeki kayıtlar, **güncel** kart numaralarına göre) ve `onizle(db, kip)` (Oracle'dan aynı sorgular, yazmaz; tam kipte satırlar akarken toplanır).

Durumlar: `kart` (sorumlu TAM), `kart_personelsiz` (karta bağlanır ama sorumlusu `musteri_personeli_mi` değil: hiçbir TAM'in portföyünde görünmez), `radar` (kart yok), `belirsiz` (numara birden çok kartta → Radar). Uyarılar: belirsiz numaralar, personelsiz kartlar, 8 haneden uzun Müşteri No yazılı kartlar (TEMIP numarası 8 hanedir, hiç eşleşmez), kaydı olmayan numaralı kart sayısı, kart bağlantısı güncel olmayan kayıt (`bagli_olmayan`, sonraki turda bağlanır).

Komutlar (`backend`'de, `..\.venv\Scripts\python.exe -m app.isci …`): `temip-kayit --kip <k> --kuru [--csv]` (yazmaz), `temip-kayit --kip tam [--csv]` (ilk yükleme), `temip-eslesme [--csv]` (Oracle'sız). CSV: `backend/var/kesif/temip-eslesme-<zaman>-{musteri,personel}.csv` (git dışı, ünvan içerir).

Sıralı komut seti: `kurulum\temip_kayit_ice_al.ps1 -Adim Durum|Yedek|Sema|Kuru|Yukle|Eslesme|Temizlik|Hepsi` (`TURKCELL\TAMLIFEADLOG` ile). `Hepsi` = Yedek → Sema (`0013_onedesk_temip`) → Kuru → Yukle → Eslesme → Durum. Panelin yeniden başlatılması ve 6 dk görevin etkinleştirilmesi betiğin dışında, kullanıcı kararıdır. `Temizlik` eski numarasız `import` Onedesk kayıtlarını (`gecmis_temizle`) yalnız `-Uygula` ile siler.

İlk kuru deneme (`artimli`, 2026-10-17 23:47): 2.696 kapalı + 12.254 açık satır, 4 sn. 149 müşteri karta (5.787 açık, 1.213 kapalı), 1.764 müşteri TAM Radar'a (6.467 açık), belirsiz ve personelsiz kart yok; 9 kartta 9 haneli Müşteri No yazılı (düzeltilmeden eşleşmez), numaralı 184 kartın son 1 gün + açık görüntüde kaydı yok.

## Sonraki adım (kullanıcı onayıyla)

1. `INFORMATION3`–`INFORMATION10`, `CORPARATECIRCUITDETAIL`, `SERVICENAME`, `TTUNIQUEID` için yalnız NOC DESTECH satırlarında doluluk oranı ve biçim (desen) profili — müşteri değeri listelenmeden.
2. Panelde kullanım adayları: müşteri başına önem derecesi kırılımı, kesinti (`OUTAGEFLAG`) süresi, açılış → kapanış süresi (MTTR), biletli/biletsiz oran, il dağılımı.
