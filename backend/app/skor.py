# Uretimden birebir tasindi: kutucuklar/utilizasyon/skor_motoru.py (2026-10-04).
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
  auto_onedesk        sayisal   'sikayet_talep'  : yil boyu acik + kapanan sikayet/talep (OneDesk)
  auto_servis_sayisi  sayisal   'lokasyon_sayisi': acik adres + atanmis devre (Urun-Tutar)
  servis_cesitliligi  sayisal   'servisler'      : musterinin servisleri -> satirin servis puanlari toplami
  auto_segment        kategorik 'segment'        : SMB 50, MA 70, SA/PA/WHOLESALE 100 (varsayilan)
  auto_baglanti       kategorik 'baglanti'       : baglanti tipleri (Urun-Tutar; alanlar sonra)
  auto_sozlesme       sayisal   'fatura_bedeli'  : fatura bedeli TL (Urun-Tutar; yedek kart FT Hacim)
  auto_rapor          sayisal   'rapor_sayisi'   : bu yil aylik rapor hazirlanan ay sayisi (panel)
  auto_kaynaksiz      -         -                : basliktan kaynak cikarilamadi -> hep 'eksik'
Verisi olmayan kriter 'eksik': toplu / otomatik atama o musteriyi atlar, mevcut skor korunur.
Tek istisna Servis Cesitliligi: Urun-Tutar gelene kadar servisler sayfadaki acilir listeden
secilir; musteriye sayfadan son atanan puani yedektir.
"""
import re

PUANLAR = (30, 50, 70, 100)
BAREM_ALANLARI = (('b30', 30), ('b50', 50), ('b70', 70), ('b100', 100))

SAYISAL = {'auto_onedesk': 'sikayet_talep', 'auto_servis_sayisi': 'lokasyon_sayisi',
           'servis_cesitliligi': 'servisler', 'auto_sozlesme': 'fatura_bedeli', 'auto_rapor': 'rapor_sayisi'}
KATEGORIK = {'auto_segment': 'segment', 'auto_baglanti': 'baglanti'}
KAYNAKSIZ = 'auto_kaynaksiz'
OTOMATIK_TURLER = tuple(SAYISAL) + tuple(KATEGORIK) + (KAYNAKSIZ,)
# Baslik -> tur (normalize baslikta ilk eslesen; sira onemli). Sayfadaki TUR_IPUCLARI ile AYNI.
TUR_IPUCLARI = (('servis cesit', 'servis_cesitliligi'), ('sikayet', 'auto_onedesk'), ('talep', 'auto_onedesk'),
                ('lokasyon', 'auto_servis_sayisi'), ('baglanti', 'auto_baglanti'), ('segment', 'auto_segment'),
                ('sozlesme', 'auto_sozlesme'), ('rapor', 'auto_rapor'))
# Kriter turunun veri kaynagi (Veri Yonlendirici kriter editorunde satirin yaninda gosterilir).
KAYNAK_ADLARI = {
    'auto_onedesk': 'OneDesk · şikayet + talep sayısı', 'servis_cesitliligi': 'Ürün-Tutar · servis puanları',
    'auto_servis_sayisi': 'Ürün-Tutar · lokasyon sayısı', 'auto_baglanti': 'Ürün-Tutar · bağlantı tipi',
    'auto_segment': 'Müşteri kartı · segment', 'auto_sozlesme': 'Ürün-Tutar · fatura bedeli (TL)',
    'auto_rapor': 'Aylık Rapor · rapor ayı sayısı', KAYNAKSIZ: 'Kaynak yok (başlıktan anlaşılamadı)',
}
# Yalniz Servis Cesitliligi sayfa secimini yedek alir (servisler sayfada secilir).
SAYFA_YEDEKLI = ('servis_cesitliligi',)

# Hucrelerde gecerli kural yoksa (eski "x" isaretli tablo) kullanilan varsayilanlar;
# sayfadaki eski sabit esiklerle ayni.
VARSAYILAN_KURALLAR = {
    'auto_onedesk': {'b30': '1-49', 'b50': '50-199', 'b70': '200-499', 'b100': '500+'},
    'auto_servis_sayisi': {'b30': '1-19', 'b50': '20-99', 'b70': '100-299', 'b100': '300+'},
    'servis_cesitliligi': {'b30': '1-19', 'b50': '20-29', 'b70': '30-39', 'b100': '40+'},
    'auto_segment': {'b50': 'SMB', 'b70': 'MA', 'b100': 'SA, PA, WHOLESALE'},
    'auto_sozlesme': {'b30': '1-49.999', 'b50': '50.000-249.999', 'b70': '250.000-999.999', 'b100': '1.000.000+'},
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


def normal(metin):
    tablo = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosuCGIOSU')
    return re.sub(r'\s+', ' ', str(metin or '').translate(tablo).lower()).strip()


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


def kural_puani(kriter, deger):
    """Musterinin degeri -> (puan, eslesen_kural_puani|None). Tutmayan kural = 0 puan."""
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


def kriter_degerlendir(kriter, metrikler, manuel=None):
    """Tek kriter -> {baslik, tur, agirlik, puan, katki, durum, kaynak, deger, varsayilan_kural}.
    durum: 'otomatik' | 'manuel' (yalniz Servis Cesitliligi sayfa secimi) | 'eksik'."""
    tur = tur_coz(kriter)
    baslik = str(kriter.get('title') or '').strip()
    try:
        agirlik = float(kriter.get('weight') or 0)
    except (TypeError, ValueError):
        agirlik = 0.0
    sonuc = {'baslik': baslik, 'tur': tur, 'agirlik': agirlik, 'puan': 0, 'katki': 0.0,
             'durum': 'eksik', 'kaynak': None, 'deger': None, 'varsayilan_kural': False}
    anahtar = SAYISAL.get(tur) or KATEGORIK.get(tur)
    metrik = (metrikler or {}).get(anahtar) if anahtar else None
    if metrik is not None:
        puan, deger = kural_puani(kriter, metrik['deger'])
        sonuc.update(deger=deger, kaynak=metrik['kaynak'], durum='otomatik', puan=puan,
                     varsayilan_kural=kurallar(kriter)[1])
    elif tur in SAYFA_YEDEKLI:
        # Servis Cesitliligi: Urun-Tutar gelene kadar servisler sayfada secilir; musteriye
        # sayfadan son atanan puan yedektir. Diger kriterlerde veri yoksa 'eksik'.
        secim = (manuel or {}).get(normal(baslik))
        if secim is not None and int(secim) in (0,) + PUANLAR:
            sonuc.update(puan=int(secim), durum='manuel', kaynak='sayfa (son atama)')
    sonuc['katki'] = round(agirlik * (sonuc['puan'] / 100), 4)
    return sonuc


def musteri_skoru(kriterler, metrikler, manuel=None):
    """Tum kriterler -> {'skor', 'kriterler', 'eksik', 'tamam'} (sayfayla ayni normalizasyon)."""
    satirlar = [kriter_degerlendir(k, metrikler, manuel) for k in (kriterler or [])]
    agirlik = sum(s['agirlik'] for s in satirlar)
    toplam = sum(s['katki'] for s in satirlar)
    skor = min(100.0, toplam / agirlik * 100) if agirlik > 0 else 0.0
    eksik = [s['baslik'] for s in satirlar if s['durum'] == 'eksik']
    return {'skor': round(skor, 1), 'kriterler': satirlar, 'eksik': eksik, 'tamam': not eksik and bool(satirlar),
            'agirlik_toplami': round(agirlik, 2)}


def manuel_secimler(detay):
    """Kaydedilmis skor dokumu -> {normal(baslik): puan}. Tum satirlar: otomatik kriterde
    kaynak hazirsa metrik oncelikli, degilse bu secim yedek olarak kullanilir."""
    sonuc = {}
    for satir in (detay or []):
        if not isinstance(satir, dict):
            continue
        try:
            sonuc[normal(satir.get('baslik'))] = int(float(satir.get('puan') or 0))
        except (TypeError, ValueError):
            continue
    return sonuc
