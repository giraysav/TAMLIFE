# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Kriter VERI KAYNAGI SECIMI: uretim kutucuklar/utilizasyon/kaynak_secimi.py + kutucuklar/veri/kurallar.py, DEV tamponuna uyarlandi.

Bir kriter satirina, Veri Girisi'nde tampona alinmis bir kaynaktan (CSV, Oracle ice alma partisi...) degerin nasil okunacagi secilir;
secim satirin 'kaynak_secimi' alaninda saklanir (UtilCriteriaSet.criteria):
    {'kaynak': 'csv_urun', 'eslesme': [{'sutun': 'Musteri No', 'alan': 'customer_no'}], 'islem': 'say', 'sutun': '',
     'filtreler': [{'sutun': 'Durum', 'islec': 'esit', 'deger': 'Acik'}], 'esleme': [['mpls', 'Data']]}
Skor hesaplanirken (kaynaklar.KriterSecimKaynagi) kaynagin EN SON hazir partisi bu tanimla islenir ve sonuc kriterin metrigi olarak
hesaplanan BUTUN musterilere uygulanir: yeni parti gelince ya da secim degisince skorlar bir sonraki hesapta kendiliginden guncellenir.
Secimi olmayan kriter eski sirayla (DB > Urun-Tutar > Panel) beslenir. Tampon YALNIZ okunur (tampon.depo.satirlari_oku).

DEV farklari: kaynak = tampon source_key (uretimde sabit 3 kaynak: onedesk / onent_ci / musteri_excel); eslesme alanlari Veri
Girisi ile ayni adlarla (customer_no / ncst / name; uretim musteri_no / ncst / unvan) ve ayni anahtar kurallariyla
(tampon.eslestirme.alan_anahtarlari: kartta birden cok numara, NCST/unvan normalize metin); sayi okuma tampon.eslestirme.sayi
(Turkce binlik: '1.234' = 1234; uretim 1.234 okuyordu).
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, IngestBatch
from app.ortak import UygulamaHatasi
from app.skor import motor
from app.tampon import depo
from app.tampon.eslestirme import alan_anahtarlari, sayi

SECIM_ANAHTARI = 'kaynak_secimi'
SERVIS_DAHIL_ANAHTARI = 'servis_dahil'
# Metrik -> deger tipi (uretim veri/hedefler.py HEDEFLER 'tip').
METRIK_TIPI = {'kayit_hacmi': 'sayi', 'lokasyon_sayisi': 'sayi', 'servisler': 'liste', 'baglanti': 'liste', 'segment': 'metin',
               'fatura_bedeli': 'sayi', 'rapor_sayisi': 'sayi'}
ISLEM_TIPI = {'say': 'sayi', 'farkli_say': 'sayi', 'topla': 'sayi', 'ortalama': 'sayi', 'en_buyuk': 'sayi',
              'en_kucuk': 'sayi', 'liste': 'liste', 'esle_liste': 'liste', 'ilk': 'metin', 'en_cok': 'metin'}
ISLEM_ADLARI = {'say': 'SAY', 'farkli_say': 'FARKLI_SAY', 'topla': 'TOPLA', 'ortalama': 'ORTALAMA',
                'en_buyuk': 'EN_BÜYÜK', 'en_kucuk': 'EN_KÜÇÜK', 'liste': 'LİSTE', 'esle_liste': 'EŞLE',
                'ilk': 'İLK', 'en_cok': 'EN_ÇOK'}
ESLESME_ALANLARI = {'customer_no': 'Müşteri No', 'ncst': 'NCST', 'name': 'Müşteri ünvanı'}
ISLECLER = {'esit': '=', 'esit_degil': '≠', 'baslar': 'ile başlar', 'icerir': 'içerir', 'icermez': 'içermez',
            'dolu': 'dolu', 'bos': 'boş', 'buyuk': '>', 'kucuk': '<', 'icinde': 'şunlardan biri'}
DEGERSIZ_ISLECLER = ('dolu', 'bos')
_KAYNAK = re.compile(r'^[A-Za-z0-9_.\-]{1,40}$')
_ONBELLEK: dict[tuple, dict] = {}
_ONBELLEK_AZAMI = 12
_kilit = threading.Lock()


class KuralHatasi(UygulamaHatasi):
    """Kullaniciya gosterilecek tanim hatasi (400)."""

    def __init__(self, mesaj: str) -> None:
        super().__init__(400, mesaj)


def _hucre(v: Any) -> str:
    if v is None or isinstance(v, bool):
        return '' if v is None else str(v)
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _normal(v: Any) -> str:
    tablo = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosuCGIOSU')
    return re.sub(r'\s+', ' ', _hucre(v).translate(tablo).lower()).strip()


def _liste(v: Any) -> list:
    return v if isinstance(v, list) else []


def metrik_anahtari(tur: str) -> str | None:
    return {**motor.SAYISAL, **motor.KATEGORIK}.get(tur)


def tur_islemleri() -> dict[str, list[str]]:
    """Kriter turu -> secilebilir islemler (metrigin tipiyle uyumlu)."""
    return {tur: [i for i, t in ISLEM_TIPI.items() if t == METRIK_TIPI[m]] for tur, m in {**motor.SAYISAL, **motor.KATEGORIK}.items()}


# --- tanim ve dogrulama (uretim kurallar.dogrula + kaynak_secimi.tanim) -------------------------------------------------
def dogrula(tur: str, secim: Any, basliklar: list[str] | None = None) -> dict:
    """Secimi temizler ve dogrular; basliklar verilirse sutunlarin partide olmasi aranir. -> saklanacak secim."""
    metrik = metrik_anahtari(tur)
    if not metrik:
        raise KuralHatasi('Bu kriter için veri kaynağı seçilemez: kriter türü başlıktan anlaşılamadı '
                          '(başlıkta şikayet, talep, servis çeşitliliği, lokasyon, bağlantı, segment, sözleşme ya da rapor geçmeli).')
    if not isinstance(secim, dict):
        raise KuralHatasi('Kaynak seçimi okunamadı.')
    kaynak = _hucre(secim.get('kaynak'))
    if not _KAYNAK.match(kaynak):
        raise KuralHatasi('Geçersiz veri kaynağı.')
    islem = _hucre(secim.get('islem'))
    if islem not in ISLEM_TIPI:
        raise KuralHatasi('Geçersiz işlem.')
    if ISLEM_TIPI[islem] != METRIK_TIPI[metrik]:
        raise KuralHatasi(f"{ISLEM_ADLARI[islem]} işlemi bu kriteri besleyemez (kriter değer tipi: {METRIK_TIPI[metrik]}).")
    t = {'kaynak': kaynak, 'islem': islem, 'sutun': _hucre(secim.get('sutun'))[:160]}
    if islem != 'say' and not t['sutun']:
        raise KuralHatasi('İşlemin sütunu seçilmedi.')
    t['eslesme'] = []
    for e in _liste(secim.get('eslesme'))[:3]:
        if isinstance(e, dict) and _hucre(e.get('sutun')) and _hucre(e.get('alan')) in ESLESME_ALANLARI:
            t['eslesme'].append({'sutun': _hucre(e['sutun'])[:160], 'alan': _hucre(e['alan'])})
    if not t['eslesme']:
        raise KuralHatasi('En az bir müşteri eşleme sütunu seçin.')
    t['filtreler'] = []
    for f in _liste(secim.get('filtreler'))[:10]:
        if not isinstance(f, dict) or not _hucre(f.get('sutun')):
            continue
        islec = _hucre(f.get('islec'))
        if islec not in ISLECLER:
            raise KuralHatasi('Geçersiz koşul işleci.')
        deger = '' if islec in DEGERSIZ_ISLECLER else _hucre(f.get('deger'))[:200]
        if islec in ('buyuk', 'kucuk') and sayi(deger) is None:
            raise KuralHatasi(f"'{_hucre(f['sutun'])}' koşulu için sayı girin.")
        t['filtreler'].append({'sutun': _hucre(f['sutun'])[:160], 'islec': islec, 'deger': deger})
    t['esleme'] = []
    if islem == 'esle_liste':
        for e in _liste(secim.get('esleme'))[:200]:
            if isinstance(e, (list, tuple)) and len(e) == 2 and _hucre(e[0]) and _hucre(e[1]):
                t['esleme'].append([_hucre(e[0])[:100], _hucre(e[1])[:100]])
        if not t['esleme']:
            raise KuralHatasi('Eşleme tablosu boş (her satır: ifade => değer).')
    if basliklar is not None:
        kullanilan = {e['sutun'] for e in t['eslesme']} | {f['sutun'] for f in t['filtreler']} | ({t['sutun']} - {''})
        eksik = sorted(kullanilan - set(basliklar))
        if eksik:
            raise KuralHatasi('Partide olmayan sütun: ' + ', '.join(eksik))
    return {k: t[k] for k in ('kaynak', 'eslesme', 'islem', 'sutun', 'filtreler', 'esleme')}


def son_parti(db: Session, kaynak: str) -> IngestBatch | None:
    """Kaynagin en son HAZIR partisi (yoksa None)."""
    return db.scalars(
        select(IngestBatch).where(IngestBatch.source_key == kaynak, IngestBatch.status == 'ready').order_by(IngestBatch.id.desc()).limit(1)
    ).first()


def satirlari_temizle(db: Session, satirlar: list[dict]) -> list[dict]:
    """Kriter kaydi: 'kaynak_secimi' dogrulanir (bos secim kaldirilir; parti varsa sutunlarin ORADA olmasi aranir) ve 'servis_dahil'
    (metin listesi) denetlenir. Hata: KuralHatasi / UygulamaHatasi (400)."""
    for s in satirlar:
        baslik = str(s.get('title') or '').strip()
        secim = s.get(SECIM_ANAHTARI)
        if not secim:
            s.pop(SECIM_ANAHTARI, None)
        else:
            parti = son_parti(db, _hucre(secim.get('kaynak'))) if isinstance(secim, dict) else None
            try:
                s[SECIM_ANAHTARI] = dogrula(motor.tur_coz(s), secim, list(parti.columns) if parti else None)
            except KuralHatasi as e:
                raise KuralHatasi(f'Kriter "{baslik or "?"}" veri kaynağı: {e.mesaj}') from e
        dahil = s.get(SERVIS_DAHIL_ANAHTARI)
        if dahil is None:
            s.pop(SERVIS_DAHIL_ANAHTARI, None)
        elif not isinstance(dahil, list) or len(dahil) > 200 or not all(isinstance(x, str) and len(x) <= 80 for x in dahil):
            raise UygulamaHatasi(400, f'Kriter "{baslik or "?"}" servis seçimi: metin listesi olmalı.')
    return satirlar


def secimli_kriterler(kriterler: list[dict] | None) -> list[tuple[str, str, dict, str]]:
    """[(tur, metrik, secim, baslik)] - secimi olan ve turu bilinen kriterler."""
    sonuc = []
    for k in kriterler or []:
        secim = (k or {}).get(SECIM_ANAHTARI)
        if not secim:
            continue
        tur = motor.tur_coz(k)
        metrik = metrik_anahtari(tur)
        if metrik:
            sonuc.append((tur, metrik, secim, str(k.get('title') or '').strip()))
    return sonuc


# --- calistirma (uretim kurallar._Isleyici / _Birikim) -------------------------------------------------------------------
def _kosul_islevi(f: dict):
    islec, beklenen = f['islec'], _normal(f['deger'])
    if islec == 'dolu':
        return lambda v: bool(_hucre(v))
    if islec == 'bos':
        return lambda v: not _hucre(v)
    if islec == 'esit':
        return lambda v: _normal(v) == beklenen
    if islec == 'esit_degil':
        return lambda v: _normal(v) != beklenen
    if islec == 'baslar':
        return lambda v: _normal(v).startswith(beklenen)
    if islec == 'icerir':
        return lambda v: beklenen in _normal(v)
    if islec == 'icermez':
        return lambda v: beklenen not in _normal(v)
    if islec == 'icinde':
        kume = {_normal(x) for x in re.split(r'[,;|]', f['deger']) if x.strip()}
        return lambda v: _normal(v) in kume
    esik, buyuk = sayi(f['deger']), islec == 'buyuk'

    def karsilastir(v):
        s = sayi(v)
        if s is None or esik is None:
            return False
        return s > esik if buyuk else s < esik
    return karsilastir


def _esle_islevi(esleme: list[list[str]]):
    """Esleme tablosu -> deger alip hedefi (ya da None) donen islev: ifade degerde KELIME olarak gecmeli; ilk eslesen."""
    desenler = [(re.compile(r'(?<![a-z0-9])' + re.escape(_normal(ifade)) + r'(?![a-z0-9])'), hedef) for ifade, hedef in esleme]

    def esle(deger):
        d = _normal(deger)
        return next((hedef for desen, hedef in desenler if desen.search(d)), None)
    return esle


class _Birikim:
    """Musteri basina islem sonucu; degerler listede tutulmaz, yol ustunde birikir."""

    def __init__(self, t: dict, esle) -> None:
        self.islem, self.esle, self.n = t['islem'], esle, 0
        self.kume: dict[str, str] = {}
        self.toplam, self.sayili, self.enb, self.enk = 0.0, 0, None, None
        self.sayac: Counter[str] = Counter()
        self.ilk: str | None = None

    def ekle(self, v: Any) -> None:
        self.n += 1
        islem = self.islem
        if islem == 'say' or not _hucre(v):
            return
        if islem in ('farkli_say', 'liste'):
            self.kume.setdefault(_normal(v), _hucre(v))
        elif islem in ('topla', 'ortalama', 'en_buyuk', 'en_kucuk'):
            s = sayi(v)
            if s is not None:
                self.sayili += 1
                self.toplam += s
                self.enb = s if self.enb is None else max(self.enb, s)
                self.enk = s if self.enk is None else min(self.enk, s)
        elif islem == 'esle_liste':
            h = self.esle(v)
            if h:
                self.kume[h] = h
        elif islem == 'ilk':
            if self.ilk is None:
                self.ilk = _hucre(v)
        elif islem == 'en_cok':
            self.sayac[_hucre(v)] += 1

    def sonuc(self) -> Any:
        islem = self.islem
        if islem == 'say':
            return self.n
        if islem == 'farkli_say':
            return len(self.kume)
        if islem == 'topla':
            return round(self.toplam, 2)
        if islem in ('ortalama', 'en_buyuk', 'en_kucuk'):
            if not self.sayili:
                return None
            return round({'ortalama': self.toplam / self.sayili, 'en_buyuk': self.enb, 'en_kucuk': self.enk}[islem], 2)
        if islem in ('liste', 'esle_liste'):
            return sorted(self.kume.values())
        if islem == 'ilk':
            return self.ilk
        return self.sayac.most_common(1)[0][0] if self.sayac else None


def musteri_dizini(musteriler: list[Customer]) -> dict[str, dict[str, int]]:
    """{alan: {anahtar: customer_id}} - verilen musteriler icinde; ayni anahtar iki kartta varsa ilk gelen (uretim setdefault)."""
    dizin: dict[str, dict[str, int]] = {alan: {} for alan in ESLESME_ALANLARI}
    for c in musteriler:
        for alan, deger in (('customer_no', c.customer_no), ('ncst', c.ncst), ('name', c.name)):
            for k in alan_anahtarlari(alan, deger):
                dizin[alan].setdefault(k, c.id)
    return dizin


class _Isleyici:
    """Tek tanimin satir isleyicisi; ayni partiye uygulanacak tanimlar satirlari TEK okumada isler."""

    def __init__(self, t: dict, basliklar: list[str], dizin: dict[str, dict[str, int]]) -> None:
        ix = {b: i for i, b in enumerate(basliklar)}
        self.t = t
        self.esle = _esle_islevi(t.get('esleme') or [])
        self.kosullar = [(ix.get(f['sutun']), _kosul_islevi(f)) for f in t['filtreler']]
        self.eslesme = [(ix.get(e['sutun']), e['alan'], dizin[e['alan']]) for e in t['eslesme']]
        self.sutun_ix = ix.get(t['sutun']) if t['sutun'] else None
        self.birikimler: dict[int, _Birikim] = {}
        self.filtrelenen = 0
        self.eslesmeyen: Counter[str] = Counter()

    @staticmethod
    def _al(r: list, i: int | None) -> Any:
        return r[i] if i is not None and i < len(r) else None

    def isle(self, r: list) -> None:
        al = self._al
        if not all(kosul(al(r, i)) for i, kosul in self.kosullar):
            return
        self.filtrelenen += 1
        hedef = None
        for i, alan, sozluk in self.eslesme:
            hedef = next((sozluk[k] for k in alan_anahtarlari(alan, al(r, i)) if k in sozluk), None)
            if hedef is not None:
                break
        if hedef is None:
            ornek = next((_hucre(al(r, i)) for i, _, _ in self.eslesme if _hucre(al(r, i))), '(boş)')
            self.eslesmeyen[ornek] += 1
            return
        b = self.birikimler.get(hedef)
        if b is None:
            b = self.birikimler[hedef] = _Birikim(self.t, self.esle)
        b.ekle(al(r, self.sutun_ix))

    def sonuc(self) -> dict:
        sonuclar = {cid: b.sonuc() for cid, b in self.birikimler.items()}
        return {'sonuclar': {cid: d for cid, d in sonuclar.items() if d is not None},
                'satir': {cid: b.n for cid, b in self.birikimler.items()}, 'filtrelenen': self.filtrelenen,
                'eslesmeyen': sum(self.eslesmeyen.values()), 'eslesmeyen_ornek': self.eslesmeyen.most_common(15)}


def calistir_coklu(db: Session, tanimlar: list[dict], parti: IngestBatch, musteriler: list[Customer]) -> list[dict]:
    """Ayni partiye uygulanacak tanimlari tek okumada calistirir (YAZMAZ); sonuclar tanim sirasiyla."""
    dizin = musteri_dizini(musteriler)
    isleyiciler = [_Isleyici(t, list(parti.columns), dizin) for t in tanimlar]
    for r in depo.satirlari_oku(db, parti.id):
        for isleyici in isleyiciler:
            isleyici.isle(r)
    return [i.sonuc() for i in isleyiciler]


def _parmak_izi(musteriler: list[Customer]) -> str:
    """Esleme sonucunu etkileyen musteri alanlari (kimlik / no / ad / NCST) - onbellek anahtari."""
    h = hashlib.sha1()
    for c in musteriler:
        h.update(f'{c.id}|{c.customer_no}|{c.name}|{c.ncst}\n'.encode('utf-8', 'replace'))
    return h.hexdigest()


def hesapla(db: Session, secimli: list[tuple[str, str, dict, str]], musteriler: list[Customer]) -> tuple[dict[int, dict], list[str]]:
    """-> ({musteri_id: {metrik: (deger, kaynak_adi)}}, [uyari]). Ayni kaynagin kriterleri partiyi TEK okumada isler; sonuc
    (parti, secim, musteriler) anahtariyla onbellekte: yeni parti ya da secim / musteri degisikligi onbellegi gecersiz kilar."""
    izi = _parmak_izi(musteriler)
    sonuc: dict[int, dict] = {}
    uyarilar: list[str] = []
    gruplar: dict[str, list] = {}
    for tur, metrik, secim, baslik in secimli:
        gruplar.setdefault(_hucre((secim or {}).get('kaynak')) if isinstance(secim, dict) else '', []).append((tur, metrik, secim, baslik))
    for kaynak, liste in gruplar.items():
        parti = son_parti(db, kaynak) if kaynak else None
        if parti is None:
            uyarilar.append(f'{kaynak or "?"}: hazır parti yok (kriter: {", ".join(b or t for t, _, _, b in liste)}).')
            continue
        hesaplanacak, sonuclar = [], {}
        for sira, (tur, _metrik, secim, baslik) in enumerate(liste):
            try:
                t = dogrula(tur, secim, list(parti.columns))
            except KuralHatasi as e:
                uyarilar.append(f'{baslik or tur}: {e.mesaj}')
                continue
            anahtar = (parti.id, json.dumps(t, sort_keys=True, ensure_ascii=False), izi)
            with _kilit:
                onbellekte = _ONBELLEK.get(anahtar)
            if onbellekte is not None:
                sonuclar[sira] = onbellekte
            else:
                hesaplanacak.append((sira, anahtar, t))
        if hesaplanacak:
            for (sira, anahtar, _), r in zip(hesaplanacak, calistir_coklu(db, [t for _, _, t in hesaplanacak], parti, musteriler), strict=True):
                sonuclar[sira] = r['sonuclar']
                with _kilit:
                    if len(_ONBELLEK) >= _ONBELLEK_AZAMI:
                        _ONBELLEK.pop(next(iter(_ONBELLEK)))
                    _ONBELLEK[anahtar] = r['sonuclar']
        kaynak_adi = f'{kaynak} #{parti.id}'
        for sira, degerler in sonuclar.items():
            metrik = liste[sira][1]
            for cid, d in degerler.items():
                sonuc.setdefault(cid, {})[metrik] = (d, kaynak_adi)
    return sonuc, uyarilar


def onizle(db: Session, satir: Any) -> dict:
    """Kriter satirindaki secimi KAYDETMEDEN dener (uretim veri_bp.kaynak_onizle): kac musteriyle eslesir, ilk sonuclar. YAZMAZ."""
    if not isinstance(satir, dict):
        raise KuralHatasi('Kriter satırı okunamadı.')
    tur = motor.tur_coz({'title': str(satir.get('title') or '')[:120], 'type': satir.get('type')})
    secim = satir.get(SECIM_ANAHTARI)
    parti = son_parti(db, _hucre(secim.get('kaynak'))) if isinstance(secim, dict) else None
    if parti is None:
        raise KuralHatasi('Bu kaynakta hazır parti yok; önce veriyi Veri Girişi\'nden tampona alın.')
    t = dogrula(tur, secim, list(parti.columns))
    musteriler = list(db.scalars(select(Customer).order_by(Customer.name, Customer.id)))
    r = calistir_coklu(db, [t], parti, musteriler)[0]
    ad = {c.id: c for c in musteriler}
    ornek = sorted(({'ad': ad[cid].name, 'cati': ad[cid].parent_id is None, 'deger': d, 'satir': r['satir'].get(cid, 0)}
                    for cid, d in r['sonuclar'].items()), key=lambda x: _normal(x['ad']))
    return {'parti': parti.id, 'toplam_satir': parti.row_count, 'filtrelenen': r['filtrelenen'], 'musteri': len(r['sonuclar']),
            'eslesmeyen': r['eslesmeyen'], 'eslesmeyen_ornek': r['eslesmeyen_ornek'][:8], 'ornek': ornek[:8]}
