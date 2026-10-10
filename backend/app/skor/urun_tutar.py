"""Urun-Tutar Excel ice aktarma: uretim kutucuklar/portfoy/urun_tutar.py (2026-09-27/28) birebir + DEV deposu (urun_tutar_ozet).

Kurumsal "Urun -Tutar Raporu" (sozlesme detayi basina bir satir) okunur ve musteri basina OZET cikarilir; ozet urun_tutar_ozet
tablosunda durur ve Final Skoru'nun otomatik kriterlerine kaynak olur (kaynaklar.UrunTutarExcelKaynagi). Ham satirlar (adres,
devre, numara) SAKLANMAZ.

Satir -> musteri eslestirme: dosya secilen musterinin (ve catiysa istiraklerinin) icindir. Musteri No, sonra NCST, sonra unvan ile
eslesen satir o istirake; eslesmeyen satir secilen musteriye yazilir (onay sorulmaz; dosyadaki unvan ve Musteri No sonucta
gosterilir). Unvan: sirket ekleri (A.S., Tic., Hizmetleri...) yok sayilir ve paneldeki kisa ad dosyadaki tam unvanin BASINDA
geciyorsa eslesir (en uzun ad kazanir).

Ozet (yalniz AKTIF satirlar: durum ACT_*; DEACT_* haric):
  lokasyon_sayisi : devre numarasi atanmis farkli acik adres sayisi
  devre_sayisi    : farkli devre numarasi
  fatura_bedeli   : 'Hesaplanmis Fiyat' toplami (TL)
  servisler       : 'Urun Tipi Grubu Level 3' -> Servis Cesitliligi listesindeki servisler (SERVIS_ESLEME)
  baglanti        : 'Urun Tipi Grubu Level 3' -> baglanti tipleri (BAGLANTI_ESLEME)
Eslesmeyen gruplar ozette 'eslesmeyen_gruplar' olarak doner ve ekranda gosterilir. openpyxl TEMBEL yuklenir (yalniz yuklemede).
"""

from __future__ import annotations

import io
import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, UrunTutarOzet
from app.ortak import UygulamaHatasi, iso, simdi
from app.tampon.eslestirme import musteri_anahtarlari

HEADER_ESLERI = {
    'musteri_adi': ('Müşteri Adı',),
    'durum': ('Sözleşme Detayı Status',),
    'devre': ('Devre Numarası',),
    'adres': ('Tam Adres', 'Hizmet Adresi'),
    'grup': ('Ürün Tipi Grubu Level 3',),
    'musteri_no': ('Müşteri No',),
    'ncst': ('NCST',),
    'fiyat': ('Hesaplanmış Fiyat',),
}
ZORUNLU = ('durum', 'grup', 'fiyat')

# 'Urun Tipi Grubu Level 3' (normalize) icinde gecen ifade -> Servis Cesitliligi servisi (motor.SERVIS_PUANLARI adlariyla AYNI).
SERVIS_ESLEME = (
    ('guvenlik', 'Güvenlik'), ('yuk dengeleme', 'Güvenlik'), ('soc', 'SOC'), ('5651', '5651 Loglama'),
    ('bulut', 'Cloud'), ('cloud', 'Cloud'), ('sistem yonetimi', 'Cloud'), ('it altyapi', 'Cloud'),
    ('dwdm', 'DWDM'), ('sdwan', 'SDWAN'), ('sd-wan', 'SDWAN'), ('yurt disi', 'Yurt Dışı'),
    ('uluslararasi', 'Yurt Dışı'), ('wifi', 'WIFI'), ('wi-fi', 'WIFI'),
    ('veri merkezi', 'Co-Location'), ('colocation', 'Co-Location'), ('co-location', 'Co-Location'),
    ('voip', 'Ses'), ('dakika paketleri', 'Ses'), ('ses', 'Ses'),
    ('mpls', 'Data'), ('metroethernet', 'Data'), ('kurumsal internet', 'Data'), ('kurumsal ip', 'Data'),
    ('kiralik devre', 'Data'), ('vpls', 'Data'), ('fiberinternet', 'Data'), ('static ip', 'Data'),
    ('gshdsl', 'Data'), ('shdsl', 'Data'), ('vdsl', 'Data'), ('adsl', 'Data'), ('dsl', 'Data'),
)
# Baglanti tipi (kriter 'Baglanti Tipi' hucrelerindeki kategoriler).
BAGLANTI_ESLEME = (
    ('metroethernet', 'ME'), ('gshdsl', 'DSL'), ('shdsl', 'DSL'), ('vdsl', 'DSL'), ('adsl', 'DSL'), ('dsl', 'DSL'),
    ('mobile enterprise', 'MOBILE BACKUP'), ('superbox', 'MOBILE BACKUP'), ('fiberinternet', 'FIBER'),
    ('mpls', 'MPLS'), ('vpls', 'MPLS'), ('kiralik devre', 'KIRALIK DEVRE'),
)
# Hic servis sayilmayan gruplar (cihaz, kurulum vb.) 'eslesmeyen' listesine de girmez.
YOK_SAYILAN = ('n/a', 'cihaz', 'kurulum', 'other', 'bilgisayar', 'modem', 'donanim', 'tam destek', 'vas',
               'crm', 'zero infrastructure', 'managed services', 'rl', 'dc')
# Unvan karsilastirmasinda yok sayilan sirket ekleri (normalize, noktalama silinmis).
SIRKET_EKLERI = frozenset((
    'a', 's', 'as', 'anonim', 'sirketi', 'sirket', 'ltd', 'sti', 'limited', 'tic', 'ticaret', 'san',
    'sanayi', 've', 'hiz', 'hizmetleri', 'hizmet', 'bilisim', 'tas', 'inc', 'co', 'corp', 'gmbh'))


class DosyaHatasi(UygulamaHatasi):
    """Kullaniciya gosterilecek dosya bicimi hatasi (400)."""

    def __init__(self, mesaj: str) -> None:
        super().__init__(400, mesaj)


def _normal(metin):
    """ortak.normal'dan farki: 0 / 0.0 bos sayilmaz (hucre degeri)."""
    tablo = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosuCGIOSU')
    return re.sub(r'\s+', ' ', str(metin if metin is not None else '').translate(tablo).lower()).strip()


def _numara(deger):
    """'0012345' / 12345 / 12345.0 -> '12345' (bastaki sifir ve ondalik farksiz)."""
    if deger is None:
        return ''
    if isinstance(deger, float) and deger.is_integer():
        deger = int(deger)
    return re.sub(r'\D', '', str(deger)).lstrip('0')


def _sayi(deger):
    if isinstance(deger, (int, float)):
        return float(deger)
    temiz = re.sub(r'[^0-9.,-]', '', str(deger or ''))
    if not temiz:
        return 0.0
    if ',' in temiz:                       # Turkce bicim: nokta binlik, virgul ondalik
        temiz = temiz.replace('.', '').replace(',', '.')
    try:
        return float(temiz)
    except ValueError:
        return 0.0


def aktif_mi(durum):
    d = _normal(durum)
    return not d or d.startswith('act')


def _ilk_eslesen(esleme, grup):
    """Ifade grup adinda KELIME olarak gecmeli ('soc' 'social' icinde sayilmaz)."""
    return next((hedef for ipucu, hedef in esleme
                 if re.search(r'(?<![a-z0-9])' + re.escape(ipucu) + r'(?![a-z0-9])', grup)), None)


def _basliklari_bul(ws):
    """(baslik satiri no, {anahtar: sutun}) - ilk 10 satirda aranir."""
    for no, satir in enumerate(ws.iter_rows(min_row=1, max_row=10, values_only=True), 1):
        adlar = {_normal(h): i for i, h in enumerate(satir) if h is not None}
        sutun = {}
        for anahtar, secenekler in HEADER_ESLERI.items():
            for s in secenekler:
                if _normal(s) in adlar:
                    sutun[anahtar] = adlar[_normal(s)]
                    break
        if all(k in sutun for k in ZORUNLU) and ('musteri_no' in sutun or 'musteri_adi' in sutun):
            return no, sutun
    return None, None


def satirlari_oku(icerik: bytes) -> list[dict]:
    """Excel baytlari -> [{anahtar: deger}] (yalniz gerekli sutunlar)."""
    import zipfile

    import openpyxl
    from openpyxl.utils.exceptions import InvalidFileException

    try:
        wb = openpyxl.load_workbook(io.BytesIO(icerik), read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as e:
        raise DosyaHatasi('Dosya okunamadı: .xlsx biçiminde bir Ürün-Tutar raporu seçin.') from e
    try:
        for ws in wb.worksheets:
            no, sutun = _basliklari_bul(ws)
            if not no:
                continue
            satirlar = []
            for r in ws.iter_rows(min_row=no + 1, values_only=True):
                if not any(v is not None and str(v).strip() for v in r):
                    continue
                satirlar.append({k: (r[i] if i < len(r) else None) for k, i in sutun.items()})
            return satirlar
    finally:
        wb.close()
    raise DosyaHatasi('Ürün-Tutar sütunları bulunamadı (Müşteri No / Müşteri Adı, Sözleşme Detayı Status, '
                      'Ürün Tipi Grubu Level 3, Hesaplanmış Fiyat).')


def ozetle(satirlar):
    """Bir musterinin satirlari -> ozet (bkz. modul aciklamasi)."""
    aktif = [s for s in satirlar if aktif_mi(s.get('durum'))]
    adresler, devreler, gruplar = set(), set(), Counter()
    servisler, baglanti, eslesmeyen = set(), set(), set()
    fatura = 0.0
    for s in aktif:
        fatura += _sayi(s.get('fiyat'))
        devre = str(s.get('devre') or '').strip()
        if devre:
            devreler.add(devre)
            adres = _normal(s.get('adres'))
            if adres:
                adresler.add(adres)
        grup = _normal(s.get('grup'))
        if not grup:
            continue
        gruplar[str(s.get('grup')).strip()] += 1
        servis = _ilk_eslesen(SERVIS_ESLEME, grup)
        tip = _ilk_eslesen(BAGLANTI_ESLEME, grup)
        if servis:
            servisler.add(servis)
        if tip:
            baglanti.add(tip)
        if not servis and not tip and not _ilk_eslesen([(y, y) for y in YOK_SAYILAN], grup):
            eslesmeyen.add(str(s.get('grup')).strip())
    return {'satir': len(satirlar), 'aktif_satir': len(aktif), 'lokasyon_sayisi': len(adresler),
            'devre_sayisi': len(devreler), 'fatura_bedeli': round(fatura, 2), 'servisler': sorted(servisler),
            'baglanti': sorted(baglanti), 'gruplar': dict(gruplar.most_common(40)),
            'eslesmeyen_gruplar': sorted(eslesmeyen)}


def _cekirdek(ad):
    """'DOGUS Teknoloji Hiz. ve Tic. A.S.' -> 'dogus teknoloji'."""
    kelimeler = re.sub(r'[^a-z0-9]+', ' ', _normal(ad)).split()
    return ' '.join(k for k in kelimeler if k not in SIRKET_EKLERI)


def _ad_eslestirici(aile):
    """Dosyadaki unvan -> aileden musteri: cekirdek ayni ya da paneldeki cekirdek (>= 4 harf) dosyadakinin basinda KELIME
    olarak geciyor. Birden cok aday varsa en uzun ad kazanir (cati 'Dogus' ile istirak 'Dogus Teknoloji' ayrilir)."""
    adaylar = sorted(((_cekirdek(c.name), c) for c in aile if _cekirdek(c.name)), key=lambda a: len(a[0]), reverse=True)
    ayni = {}
    for k, c in reversed(adaylar):          # ayni cekirdek iki kez varsa secilen musteri kalir
        ayni[k] = c
    onbellek = {}

    def bul(ad):
        cek = _cekirdek(ad)
        if cek not in onbellek:
            onbellek[cek] = (ayni.get(cek) or next(
                (c for k, c in adaylar if len(k) >= 4 and cek.startswith(k + ' ')), None)) if cek else None
        return onbellek[cek]
    return bul


def ice_aktar(db: Session, musteri: Customer, icerik: bytes) -> dict:
    """Dosyayi okur, musterinin ailesine esler, ozetleri doner (YAZMAZ).
    Donus: {'ozetler': {customer_id: ozet}, 'eslesen': n, 'kart_musterisine': n,
            'dosyadaki': [{'ad', 'musteri_no', 'satir'}] (en cok satirli 5 unvan), 'dosyadaki_adet': n}."""
    satirlar = satirlari_oku(icerik)
    if not satirlar:
        raise DosyaHatasi('Dosyada veri satırı yok.')
    aile = [musteri]
    if musteri.parent_id is None:
        aile += list(db.scalars(select(Customer).where(Customer.parent_id == musteri.id).order_by(Customer.id)))
    no_ile = {k: c for c in aile for k in musteri_anahtarlari(c.customer_no)}   # birden cok numara: her biri karta isaret eder
    ncst_ile = {_numara(c.ncst): c for c in aile if _numara(c.ncst)}
    ad_ile = _ad_eslestirici(aile)
    dagitim, eslesen = {}, 0
    unvanlar = Counter()
    for s in satirlar:
        hedef = (no_ile.get(_numara(s.get('musteri_no'))) or ncst_ile.get(_numara(s.get('ncst')))
                 or ad_ile(s.get('musteri_adi')))
        if hedef:
            eslesen += 1
        dagitim.setdefault((hedef or musteri).id, []).append(s)
        unvanlar[(str(s.get('musteri_adi') or '').strip(), _numara(s.get('musteri_no')))] += 1
    return {'ozetler': {cid: ozetle(liste) for cid, liste in dagitim.items()}, 'eslesen': eslesen,
            'kart_musterisine': len(dagitim.get(musteri.id, [])),
            'dosyadaki': [{'ad': ad, 'musteri_no': no, 'satir': n} for (ad, no), n in unvanlar.most_common(5)],
            'dosyadaki_adet': len(unvanlar)}


# --- depo (uretim sla_deposu.urun_tutar_kaydet / urun_tutar_hepsi) ------------------------------------------------------
def kaydet(db: Session, ozetler: dict[int, dict], dosya: str, yukleyen: str) -> None:
    """Musteri basina son yukleme degistirir (commit cagiranda)."""
    zaman = simdi()
    for cid, ozet in ozetler.items():
        satir = db.get(UrunTutarOzet, int(cid))
        if satir is None:
            db.add(UrunTutarOzet(customer_id=int(cid), summary=ozet, file_name=dosya[:200], uploaded_by=yukleyen[:120], uploaded_at=zaman))
        else:
            satir.summary, satir.file_name, satir.uploaded_by, satir.uploaded_at = ozet, dosya[:200], yukleyen[:120], zaman
    db.flush()


def hepsi(db: Session, musteri_idleri: list[int] | None = None) -> dict[int, dict]:
    """{customer_id: {'ozet', 'dosya', 'yukleyen', 'zaman'}} - tek sorgu; None = tumu."""
    sorgu = select(UrunTutarOzet)
    if musteri_idleri is not None:
        if not musteri_idleri:
            return {}
        sorgu = sorgu.where(UrunTutarOzet.customer_id.in_(musteri_idleri))
    return {
        s.customer_id: {'ozet': s.summary or {}, 'dosya': s.file_name, 'yukleyen': s.uploaded_by, 'zaman': iso(s.uploaded_at)}
        for s in db.scalars(sorgu)
    }


def yukle(db: Session, musteri_id: int, icerik: bytes, dosya: str, yukleyen: str) -> dict:
    """Yukleme ucu (uretim customer_bp.urun_tutar_yukle): oku -> esle -> kaydet. Donus uretimle ayni alanlar."""
    musteri = db.get(Customer, musteri_id)
    if musteri is None:
        raise UygulamaHatasi(404, 'Müşteri bulunamadı.')
    if not icerik:
        raise DosyaHatasi('Excel dosyası seçilmedi.')
    sonuc = ice_aktar(db, musteri, icerik)
    kaydet(db, sonuc['ozetler'], dosya, yukleyen)
    ad = dict(db.execute(select(Customer.id, Customer.name).where(Customer.id.in_(list(sonuc['ozetler'])))).all())
    return {'eslesen': sonuc['eslesen'], 'kart_musterisine': sonuc['kart_musterisine'], 'dosyadaki': sonuc['dosyadaki'],
            'dosyadaki_adet': sonuc['dosyadaki_adet'], 'kart_musteri_no': musteri.customer_no or '',
            'musteriler': [{'id': cid, 'ad': ad.get(cid, ''), **o} for cid, o in sonuc['ozetler'].items()]}
