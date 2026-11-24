# Uretimden birebir tasindi: kutucuklar/utilizasyon/skor_motoru.py (2026-10-04; 'X' sabit puan kurali 2026-10-10).
# Hesap kurali degistirilmez; esdegerlik testi tests/test_skor.py.
"""Final skor motoru - sunucu tarafi (2026-09-27). Toplu dinamik atamanin altyapisi.

Sayfadaki (tab_utilizasyon.html) kuralin AYNISI, tek musteriye bagli kalmadan:
  * her kriterde TEK barem: 30 / 50 / 70 / 100 puan (hicbir kural tutmazsa 0)
  * katki = agirlik x (puan / 100)
  * final = YALNIZ cati tablosu, 100 uzerinden: sum(katki) / sum(agirlik) x 100 (en fazla 100)

BAREM HUCRELERI = KURAL (kullanici tanimi 2026-09-27). Otomatik kriterde hucreye
musteri icin "x" konmaz; kosul yazilir ve her musteri kendi verisiyle eslestirilir:
  sayisal   : "1-49", "50-499", "500+", "500 ve uzeri", ">=500", "<50"  (adet)
  kategorik : "SMB" | "MA" | "SA, PA, WHOLESALE"                     (virgul / 've' / 'veya')
Hucrelerde gecerli kural yoksa varsayilan kurallar kullanilir (VARSAYILAN_KURALLAR).
Kriter tablosu degisince tum musteriler bu kurallarla yeniden hesaplanir.

TUM KRITERLER OTOMATIK (kullanici karari 2026-09-27: "utilizasyon modulundeki her alan
otomatik olacak"). Manuel tur / tur secici yok; satirin turu kayitli 'type' otomatik bir
tur degilse BASLIKTAN cikarilir (tur_coz - sayfadaki _turCoz ile ayni).
Kriter turleri (UtilCriteria.criteria_json 'type') ve veri:
  auto_onedesk        sayisal   'kayit_hacmi'    : Kayit Hacmi = bu yil kapanan + su an acik alarm + talep + sikayet (2026-11-24)
  auto_servis_sayisi  sayisal   'lokasyon_sayisi': acik adres + atanmis devre (Urun-Tutar)
  servis_cesitliligi  sayisal   'servisler'      : musterinin servisleri -> satirin servis puanlari toplami
  auto_segment        kategorik 'segment'        : SMB / MA 70, SA / PA 100 (varsayilan, 2026-11-24)
  auto_baglanti       kategorik 'baglanti'       : baglanti tipleri (Urun-Tutar; alanlar sonra)
  auto_sozlesme       alt kriter 'fatura_bedeli' : Fatura (Urun-Tutar fatura bedeli >= 1.000.000 TL) 70 + Kritik Madde 15 + SLA 15
  auto_rapor          sayisal   'rapor_sayisi'   : bu yil aylik rapor hazirlanan ay sayisi (panel)
  auto_kaynaksiz      -         -                : basliktan kaynak cikarilamadi -> hep 'eksik'
Verisi olmayan kriter 'eksik': toplu / otomatik atama o musteriyi atlar, mevcut skor korunur.
Servis Cesitliligi: musterinin servisleri (Urun-Tutar > ONENT) satirin servis_puanlari tablosuyla toplanir, barem uygulanir. Verisi
olmayan musteride servisler Kriter dokumunde isaretlenir; ayni toplam + barem kurali. Servis puanlari YALNIZ kriter tablosunda
degistirilir (2026-11-24 kullanici).
Sozlesme (2026-11-24 kullanici): uc alt kriter dokumde isaretlenir - Fatura 70, Kritik Madde +15, SLA +15 (ucu 100). Fatura, Urun-Tutar
fatura bedeli 1.000.000 TL ve uzeriyse saglanir (veri varsa otomatik, isaret kilitli; yoksa elle). 1 Mio alti fatura saglanmaz.
"""
import re

from app.ortak import normal

PUANLAR = (30, 50, 70, 100)
BAREM_ALANLARI = (('b30', 30), ('b50', 50), ('b70', 70), ('b100', 100))

SAYISAL = {'auto_onedesk': 'kayit_hacmi', 'auto_servis_sayisi': 'lokasyon_sayisi',
           'servis_cesitliligi': 'servisler', 'auto_sozlesme': 'fatura_bedeli', 'auto_rapor': 'rapor_sayisi'}
KATEGORIK = {'auto_segment': 'segment', 'auto_baglanti': 'baglanti'}
KAYNAKSIZ = 'auto_kaynaksiz'
# Raporlama satirinda barem hucrelerinden TEK birine 'X' yazilirsa o hucrenin puani TUM musteriler icin sabit puandir (kullanici
# karari 2026-10-08); diger hucreler arayuzde kilitlenir, burada yok sayilir. Sozlesme 2026-11-24'ten beri alt kriterlerle hesaplanir.
SABIT_PUAN_TURLERI = ('auto_rapor',)
# Sozlesme alt kriterleri (2026-11-24 kullanici: "fatura 1 Mio TL ve uzeri, yalniz fatura 70; kritik madde ve SLA +15'er").
SOZLESME_FATURA = 'Fatura'
SOZLESME_ALT_KRITERLER = ((SOZLESME_FATURA, 70), ('Kritik Madde', 15), ('SLA', 15))
FATURA_ESIGI = 1_000_000
SOZLESME_METNI = 'Fatura (Ürün-Tutar, 1.000.000 TL ve üzeri) 70 · Kritik Madde +15 · SLA +15'
# Veri olsa da ELLE secilen turler (2026-11-21 kullanici onayi): Raporlama 'Standart / Ozel' olarak dokumden secilir; rapor ayi
# sayisi puana yansitilmaz (cogu musteride 1 ay -> haksiz 30 puan). Baglanti Tipi (2026-11-24 kullanici): barem Fiber / Karasal /
# Mobil + yedeklilik; urun -> grup eslesme listesi kullanicidan gelene kadar dokumde secilir (veri kurala baglanmaz).
ELLE_SECILEN_TURLER = ('auto_rapor', 'auto_baglanti')
OTOMATIK_TURLER = tuple(SAYISAL) + tuple(KATEGORIK) + (KAYNAKSIZ,)
# Baslik -> tur (normalize baslikta ilk eslesen; sira onemli). Sayfadaki TUR_IPUCLARI ile AYNI.
TUR_IPUCLARI = (('servis cesit', 'servis_cesitliligi'), ('kayit hacmi', 'auto_onedesk'), ('sikayet', 'auto_onedesk'), ('talep', 'auto_onedesk'),
                ('lokasyon', 'auto_servis_sayisi'), ('baglanti', 'auto_baglanti'), ('segment', 'auto_segment'),
                ('sozlesme', 'auto_sozlesme'), ('rapor', 'auto_rapor'))
# Kriter turunun veri kaynagi (Veri Yonlendirici kriter editorunde satirin yaninda gosterilir).
KAYNAK_ADLARI = {
    'auto_onedesk': 'Kayıt hacmi · alarm + talep + şikayet (bu yıl kapanan + açık)', 'servis_cesitliligi': 'Ürün-Tutar / ONENT · servis puanları',
    'auto_servis_sayisi': 'Ürün-Tutar · lokasyon sayısı', 'auto_baglanti': 'Kriter dökümünde seçilir (ürün eşleşmesi bekleniyor)',
    'auto_segment': 'Müşteri kartı · segment', 'auto_sozlesme': 'Ürün-Tutar · fatura bedeli + dökümde Kritik Madde / SLA',
    'auto_rapor': 'Aylık Rapor · rapor ayı sayısı', KAYNAKSIZ: 'Kaynak yok (başlıktan anlaşılamadı)',
}
# Yalniz Servis Cesitliligi sayfa secimini yedek alir (servisler sayfada secilir).

# Hucrelerde gecerli kural yoksa (eski "x" isaretli tablo) kullanilan varsayilanlar;
# sayfadaki eski sabit esiklerle ayni.
VARSAYILAN_KURALLAR = {
    'auto_onedesk': {'b30': '1-49', 'b50': '50-199', 'b70': '200-499', 'b100': '500+'},
    'auto_servis_sayisi': {'b30': '1-19', 'b50': '20-59', 'b70': '60-99', 'b100': '100+'},  # 2026-11-24 kullanici
    'servis_cesitliligi': {'b30': '1-19', 'b50': '20-29', 'b70': '30-39', 'b100': '40+'},
    'auto_segment': {'b70': 'SMB, MA', 'b100': 'SA, PA'},  # 2026-11-24 kullanici
    'auto_rapor': {'b30': '1-3', 'b50': '4-6', 'b70': '7-9', 'b100': '10+'},
}
# Kategori es anlamlilari (normalize edilmis).
ES_ANLAM = {'ws': 'wholesale', 'toptan': 'wholesale'}
# Servis cesitliligi puanlari - sayfadaki UTIL_SERVICE_LIST ile AYNI (satirda
# 'servis_puanlari' kayitliysa o kullanilir).
SERVIS_PUANLARI = {
    'Güvenlik': 10, 'Cloud': 10, 'Data': 8, 'DWDM': 8, 'SDWAN': 8, 'SOC': 8, 'Yurt Dışı': 8,
    'WIFI': 7, 'Ses': 5, 'Co-Location': 5, '5651 Loglama': 3,
}
# Kriter tablosu hic kaydedilmemisse (cati ve istirak) kullanilan resmi Excel modeli: 7 kriter, agirliklar 20/20/5/5/15/20/15.
# Uretim kutucuklar/utilizasyon/servis.py _default_util_criteria ile birebir.
VARSAYILAN_KRITERLER = (
    {'type': 'auto_onedesk', 'title': '1. Kayıt Hacmi', 'metric': 'Bu yıl kapanan + açıkta bekleyen alarm, talep ve şikayet toplamı', 'b30': '1-49', 'b50': '50-199', 'b70': '200-499', 'b100': '500+', 'weight': 20},
    {'type': 'servis_cesitliligi', 'title': '2. Servis Çeşitliliği', 'metric': 'Servis puanları toplamı (Ürün-Tutar)', 'b30': '1-19', 'b50': '20-29', 'b70': '30-39', 'b100': '40+', 'weight': 20},
    {'type': 'auto_servis_sayisi', 'title': '3. Lokasyon Sayısı', 'metric': 'Açık adres + atanmış devre (Ürün-Tutar)', 'b30': '1-19', 'b50': '20-59', 'b70': '60-99', 'b100': '100+', 'weight': 5},
    {'type': 'auto_baglanti', 'title': '4. Bağlantı Tipi', 'metric': 'Fiber / Karasal / Mobil + yedeklilik (ürün eşleşmesi bekleniyor; şimdilik dökümde seçilir)', 'b30': 'Yalnız DSL / Mobil (yedeksiz)', 'b50': 'Karasal + Yedek', 'b70': 'Yedeksiz Fiber', 'b100': 'Fiber + Yedek', 'weight': 5},
    {'type': 'auto_segment', 'title': '5. Segment', 'metric': 'SMB / MA 70 · SA / PA 100', 'b30': '', 'b50': '', 'b70': 'SMB, MA', 'b100': 'SA, PA', 'weight': 15},
    {'type': 'auto_sozlesme', 'title': '6. Sözleşme', 'metric': SOZLESME_METNI, 'b30': '', 'b50': '', 'b70': 'Yalnız Fatura (1.000.000 TL+)', 'b100': 'Fatura + Kritik Madde + SLA', 'weight': 20},
    {'type': 'auto_rapor', 'title': '7. Raporlama', 'metric': 'Bu yıl aylık rapor hazırlanan ay sayısı', 'b30': '1-3', 'b50': '4-6', 'b70': '7-9', 'b100': '10+', 'weight': 15},
)  # fmt: skip


def varsayilan_kriterler():
    """VARSAYILAN_KRITERLER'in degistirilebilir kopyasi."""
    return [dict(k) for k in VARSAYILAN_KRITERLER]


def tur_coz(kriter):
    """Satirin otomatik turu: kayitli tur otomatikse o, degilse basliktan (eski 'manual' satirlar)."""
    tur = (kriter or {}).get('type')
    if tur in OTOMATIK_TURLER and tur != KAYNAKSIZ:
        return tur
    baslik = normal((kriter or {}).get('title'))
    return next((t for ipucu, t in TUR_IPUCLARI if ipucu in baslik), KAYNAKSIZ)


def turleri_duzelt(satirlar):
    """Kaydedilen kriter satirlari: her satirin 'type'i otomatik tura cevrilir (manuel yok)."""
    for s in satirlar or []:
        if isinstance(s, dict):
            s['type'] = tur_coz(s)
    return satirlar


def _sayi(metin):
    return int(metin.replace('.', '').replace(',', ''))


def aralik_ayikla(metin):
    """Barem hucresi -> (alt, ust) dahil; ust None = ust sinirsiz. Kural yoksa None.
    "(30p)" / "30 puan" gibi puan ekleri yok sayilir."""
    m = normal(metin)
    m = re.sub(r'\(\s*\d+\s*p(uan)?\s*\)', ' ', m)
    m = re.sub(r'\b\d+\s*puan\b', ' ', m).strip()
    sayi = r'\d{1,3}(?:[.,]\d{3})+|\d+'
    if r := re.search(rf'({sayi})\s*(?:-|–|ile)\s*({sayi})', m):
        alt, ust = _sayi(r.group(1)), _sayi(r.group(2))
        return (min(alt, ust), max(alt, ust))
    if r := re.search(rf'(?:>=|≥|en az)\s*({sayi})|({sayi})\s*(?:\+|ve uzeri|ve ustu|uzeri|ustu)', m):
        return (_sayi(r.group(1) or r.group(2)), None)
    if r := re.search(rf'>\s*({sayi})', m):
        return (_sayi(r.group(1)) + 1, None)
    if r := re.search(rf'(?:<=|≤|en fazla)\s*({sayi})', m):
        return (0, _sayi(r.group(1)))
    if r := re.search(rf'<\s*({sayi})', m):
        return (0, _sayi(r.group(1)) - 1)
    if r := re.fullmatch(rf'({sayi})(?:\s*adet)?', m):
        return (_sayi(r.group(1)), _sayi(r.group(1)))
    return None


def kategori_tokenlari(metin):
    """"SA, PA ve WHOLESALE" -> {'sa', 'pa', 'wholesale'}. Puan ekleri yok sayilir."""
    m = re.sub(r'\(\s*\d+\s*p(uan)?\s*\)', ' ', normal(metin))
    parcalar = re.split(r'\s*(?:,|;|/|\bve\b|\bveya\b|\|)\s*', m)
    return {ES_ANLAM.get(p.strip(), p.strip()) for p in parcalar if p.strip() and p.strip() != 'x'}


def kurallar(kriter):
    """Kriterin gecerli kurallari [(puan, kural)] + 'varsayilan' bayragi."""
    tur = tur_coz(kriter)
    ayikla = aralik_ayikla if tur in SAYISAL else kategori_tokenlari
    liste = []
    for alan, puan in BAREM_ALANLARI:
        kural = ayikla(kriter.get(alan) or '')
        if kural:
            liste.append((puan, kural))
    if not liste and tur in VARSAYILAN_KURALLAR:
        return [(p, ayikla(VARSAYILAN_KURALLAR[tur].get(a, ''))) for a, p in BAREM_ALANLARI
                if VARSAYILAN_KURALLAR[tur].get(a)], True
    return liste, False


def servis_puani(kriter, servisler):
    """Musterinin servisleri -> puan toplami (satirin servis_puanlari ya da varsayilan).
    2026-09-30: satirda 'servis_dahil' (isaretli servis adlari) varsa YALNIZ onlar sayilir; yoksa hepsi."""
    tablo = kriter.get('servis_puanlari') if isinstance(kriter.get('servis_puanlari'), dict) else SERVIS_PUANLARI
    puanlar = {normal(k): v for k, v in tablo.items()}
    dahil = kriter.get('servis_dahil')
    if isinstance(dahil, list):
        dahil = {normal(x) for x in dahil}
        puanlar = {k: v for k, v in puanlar.items() if k in dahil}
    toplam = 0.0
    for s in {normal(x) for x in (servisler or [])}:
        try:
            toplam += float(puanlar.get(s, 0))
        except (TypeError, ValueError):
            continue
    return toplam


def servis_listesi(kriter):
    """Satirin puanlanan servisleri [{ad, puan}] (servis_puanlari ya da varsayilan; 'servis_dahil' varsa yalniz onlar)."""
    tablo = kriter.get('servis_puanlari') if isinstance(kriter.get('servis_puanlari'), dict) else SERVIS_PUANLARI
    dahil = kriter.get('servis_dahil')
    dahil = {normal(x) for x in dahil} if isinstance(dahil, list) else None
    liste = []
    for ad, puan in tablo.items():
        if dahil is not None and normal(ad) not in dahil:
            continue
        try:
            liste.append({'ad': ad, 'puan': float(puan)})
        except (TypeError, ValueError):
            continue
    return liste


def servis_secim_puani(kriter, secilen):
    """Dokumde elle isaretlenen servisler -> (kriter puani, alinan adlar). 2026-11-24 kullanici karari: otomatik veriyle AYNI kural -
    alinan servislerin puanlari toplanir, satirin 30/50/70/100 baremine gore puanlanir (eski oran kurali kaldirildi)."""
    secili = {normal(x) for x in secilen}
    alinan = [s['ad'] for s in servis_listesi(kriter) if normal(s['ad']) in secili]
    return kural_puani(kriter, alinan)[0], alinan


def servis_kurallari(kriter):
    """Dokum onizlemesi icin satirin barem kurallari [{puan, alt, ust}] (ust None = sinirsiz)."""
    return [{'puan': p, 'alt': a, 'ust': u} for p, (a, u) in kurallar(kriter)[0]]


def sozlesme_degerlendir(metrik, secim):
    """Sozlesme alt kriterleri -> (puan, alt kriter listesi, saglanan adlar). metrik: Urun-Tutar fatura bedeli {'deger', 'kaynak'} ya da
    None; secim: dokumde isaretlenen adlar. Fatura verisi varsa fatura isareti veriden gelir (secimdeki yok sayilir)."""
    secili = {normal(x) for x in (secim or [])}
    fatura = float(metrik['deger']) if metrik is not None else None
    alt, saglanan = [], []
    for ad, puan in SOZLESME_ALT_KRITERLER:
        oto = ad == SOZLESME_FATURA and fatura is not None
        tamam = fatura >= FATURA_ESIGI if oto else normal(ad) in secili
        satir = {'ad': ad, 'puan': puan, 'oto': oto, 'saglandi': tamam}
        if ad == SOZLESME_FATURA:
            satir['fatura_bedeli'] = fatura
        alt.append(satir)
        if tamam:
            saglanan.append(ad)
    return min(100, sum(p for ad, p in SOZLESME_ALT_KRITERLER if ad in saglanan)), alt, saglanan


def sabit_puan(kriter):
    """Sozlesme / Raporlama satirinda tam bir barem hucresinde 'X' varsa o hucrenin puani (30/50/70/100), yoksa None.
    Birden fazla X belirsizdir (arayuz buna izin vermez): kural gecerli sayilmaz, satir normal kuralla hesaplanir."""
    if tur_coz(kriter) not in SABIT_PUAN_TURLERI:
        return None
    isaretli = [puan for alan, puan in BAREM_ALANLARI if normal((kriter or {}).get(alan)) == 'x']
    return isaretli[0] if len(isaretli) == 1 else None


def kural_puani(kriter, deger):
    """Musterinin degeri -> (puan, eslesen_kural_puani|None). Tutmayan kural = 0 puan."""
    sabit = sabit_puan(kriter)
    if sabit is not None:
        return sabit, deger
    tur = tur_coz(kriter)
    liste, _ = kurallar(kriter)
    if tur in SAYISAL:
        if tur == 'servis_cesitliligi':
            deger = servis_puani(kriter, deger)
        for puan, (alt, ust) in sorted(liste, key=lambda x: -x[0]):
            if deger >= alt and (ust is None or deger <= ust):
                return puan, deger
        return 0, deger
    degerler = {ES_ANLAM.get(normal(v), normal(v)) for v in (deger if isinstance(deger, (list, tuple, set)) else [deger]) if v}
    for puan, tokenlar in sorted(liste, key=lambda x: -x[0]):
        if degerler & tokenlar:
            return puan, deger
    return 0, deger


MANUEL_KAYNAK = 'Manuel seçim (kriter dökümü)'


def secenekler(kriter):
    """Manuel secim listesi: [{puan, etiket}] - Kriterler tablosundaki barem hucresinin kural metni (bossa varsayilan kural) etiket olur.
    0 puan secenegi yok (2026-10-20 kullanici). Kurali olan barem varsa yalniz onlar listelenir (orn. Segment'te bos 30 hucresi
    secilemez); hicbir baremde kural yoksa dort puan da secilebilir."""
    varsayilan = VARSAYILAN_KURALLAR.get(tur_coz(kriter), {})
    liste = []
    for alan, puan in BAREM_ALANLARI:
        metin = str((kriter or {}).get(alan) or '').strip()
        liste.append({'puan': puan, 'etiket': metin if metin and normal(metin) != 'x' else varsayilan.get(alan, '')})
    return [s for s in liste if s['etiket']] or liste


def kriter_degerlendir(kriter, metrikler, manuel=None, otomatik=True):
    """Tek kriter -> {baslik, tur, agirlik, puan, katki, durum, kaynak, deger, varsayilan_kural}.
    durum: 'otomatik' | 'manuel' (yalniz Servis Cesitliligi sayfa secimi) | 'eksik'.
    otomatik=False (2026-10-20 kullanici: "db kaynaklarindan otomatik puanlama simdilik manuel"): veri kaynagi okunmaz; her kriterin
    puani Toplu atama > Kriter dokumunde yapilan secimdir (manuel: {normal(baslik): puan}), secilmemis kriter 'eksik'. X sabit puani
    veri degil tablo kuralidir, gecerli kalir. Sonuca 'secenekler' eklenir (dokumdeki secim listesi)."""
    tur = tur_coz(kriter)
    baslik = str(kriter.get('title') or '').strip()
    try:
        agirlik = float(kriter.get('weight') or 0)
    except (TypeError, ValueError):
        agirlik = 0.0
    sonuc = {'baslik': baslik, 'tur': tur, 'agirlik': agirlik, 'puan': 0, 'katki': 0.0,
             'durum': 'eksik', 'kaynak': None, 'deger': None, 'varsayilan_kural': False}
    sabit = sabit_puan(kriter)
    if sabit is not None:       # X isareti: veri gerekmez, her musteri ayni puani alir
        sonuc.update(puan=sabit, durum='otomatik', kaynak='Sabit puan (X işareti)', deger='X')
        sonuc['katki'] = round(agirlik * (sabit / 100), 4)
        return sonuc
    if tur == 'auto_sozlesme':
        # Alt kriterler: Fatura (Urun-Tutar verisi varsa otomatik) + dokumde Kritik Madde / SLA. Veri de secim de yoksa 'eksik'.
        metrik = (metrikler or {}).get('fatura_bedeli') if otomatik else None
        secim = (manuel or {}).get(normal(baslik))
        secim = [str(x) for x in secim] if isinstance(secim, (list, tuple)) else None
        puan, alt, saglanan = sozlesme_degerlendir(metrik, secim)
        sonuc.update(alt_kriterler=alt, secim=secim)
        if metrik is not None:
            kaynak = metrik['kaynak'] + (' + ' + MANUEL_KAYNAK if secim else '')
            sonuc.update(puan=puan, durum='otomatik', kaynak=kaynak, deger=saglanan)
        elif secim is not None:
            sonuc.update(puan=puan, durum='manuel', kaynak=MANUEL_KAYNAK, deger=saglanan)
        sonuc['katki'] = round(agirlik * (sonuc['puan'] / 100), 4)
        return sonuc
    if not otomatik and tur == 'servis_cesitliligi':
        # Alt kriter: dokumde alinan servisler isaretlenir (bos liste = hic servis yok, 0 puan); secim yoksa 'eksik'.
        sonuc['servisler'], sonuc['kurallar'] = servis_listesi(kriter), servis_kurallari(kriter)
        secim = (manuel or {}).get(normal(baslik))
        if isinstance(secim, (list, tuple)):
            puan, adlar = servis_secim_puani(kriter, secim)
            sonuc.update(puan=puan, durum='manuel', kaynak=MANUEL_KAYNAK, deger=adlar, secim=adlar)
        sonuc['katki'] = round(agirlik * (sonuc['puan'] / 100), 4)
        return sonuc
    if not otomatik:
        sonuc['secenekler'] = secenekler(kriter)
        secim = (manuel or {}).get(normal(baslik))
        if isinstance(secim, (list, tuple)):
            secim = None
        if secim is not None and int(secim) in {s['puan'] for s in sonuc['secenekler']}:
            sonuc.update(puan=int(secim), durum='manuel', kaynak=MANUEL_KAYNAK)
        sonuc['katki'] = round(agirlik * (sonuc['puan'] / 100), 4)
        return sonuc
    anahtar = SAYISAL.get(tur) or KATEGORIK.get(tur)
    metrik = (metrikler or {}).get(anahtar) if anahtar and tur not in ELLE_SECILEN_TURLER else None
    if metrik is not None and tur in KATEGORIK and not kurallar(kriter)[0]:
        # Kategorik kriterde hicbir barem hucresi dolu degil (orn. Baglanti Tipi): veri her musteride 0 puan verirdi -> kayitli secime duser.
        metrik = None
    if metrik is not None:
        puan, deger = kural_puani(kriter, metrik['deger'])
        sonuc.update(deger=deger, kaynak=metrik['kaynak'], durum='otomatik', puan=puan,
                     varsayilan_kural=kurallar(kriter)[1])
        sonuc['katki'] = round(agirlik * (sonuc['puan'] / 100), 4)
        return sonuc
    # KARMA (2026-11-21 kullanici: gunluk isci skoru gunceller): verisi olmayan kriter, Kriter dokumunde kayitli secime duser
    # (manuel kipteki kuralla ayni; dokumde yalniz bu kriterler secilir). Secim de yoksa 'eksik'.
    return kriter_degerlendir(kriter, metrikler, manuel, otomatik=False)


def musteri_skoru(kriterler, metrikler, manuel=None, otomatik=True):
    """Tum kriterler -> {'skor', 'kriterler', 'eksik', 'tamam', 'yazilabilir'}.
    2026-11-21 kullanici karari ("dolu kriterlerle orantili"): skor YALNIZ dolu (eksik olmayan) kriterlerin agirligiyla 100 uzerinden
    hesaplanir; elle girilecek kriter (Sozlesme, Raporlama) secildikce hesaba girer. tamam = hic eksik yok; yazilabilir = en az bir
    kriter dolu (ara skor yazilir, ekranda 'eksik' etiketi kalir)."""
    satirlar = [kriter_degerlendir(k, metrikler, manuel, otomatik) for k in (kriterler or [])]
    dolu = [s for s in satirlar if s['durum'] != 'eksik']
    agirlik = sum(s['agirlik'] for s in dolu)
    toplam = sum(s['katki'] for s in dolu)
    skor = min(100.0, toplam / agirlik * 100) if agirlik > 0 else 0.0
    eksik = [s['baslik'] for s in satirlar if s['durum'] == 'eksik']
    return {'skor': round(skor, 1), 'kriterler': satirlar, 'eksik': eksik, 'tamam': not eksik and bool(satirlar),
            'yazilabilir': agirlik > 0, 'agirlik_toplami': round(sum(s['agirlik'] for s in satirlar), 2),
            'dolu_agirlik': round(agirlik, 2)}


def manuel_secimler(detay):
    """Kaydedilmis skor dokumu -> {normal(baslik): puan}. Tum satirlar: otomatik kriterde
    kaynak hazirsa metrik oncelikli, degilse bu secim yedek olarak kullanilir. Manuel Servis Cesitliligi satirinda deger
    alinan servis listesidir ({baslik: [servis, ...]}); Sozlesme satirinda dokumde isaretlenen alt kriterler ('secim')."""
    sonuc = {}
    for satir in (detay or []):
        if not isinstance(satir, dict):
            continue
        if satir.get('tur') == 'auto_sozlesme':
            if isinstance(satir.get('secim'), list):
                sonuc[normal(satir.get('baslik'))] = [str(x) for x in satir['secim']]
            continue
        if satir.get('tur') == 'servis_cesitliligi' and satir.get('kaynak') == MANUEL_KAYNAK and isinstance(satir.get('deger'), list):
            sonuc[normal(satir.get('baslik'))] = [str(x) for x in satir['deger']]
            continue
        try:
            sonuc[normal(satir.get('baslik'))] = int(float(satir.get('puan') or 0))
        except (TypeError, ValueError):
            continue
    return sonuc
