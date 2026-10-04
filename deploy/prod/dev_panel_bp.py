"""Yeni panel (TAMLIFE v3.5) /admin/dev altinda: yalniz yonetici, ayri surece ters vekil.

Yeni panel ayri bir surecte (uvicorn) yalniz 127.0.0.1 uzerinde calisir; bu modul onu
uretim panelinin arkasina baglar. Disaridan dogrudan erisim yoktur.

- Yetki: uretim paneli oturumu + yonetici (security.admin_required). Yonetici olmayan erisemez.
- Giris: yonetici ikinci kez giris yapmaz; vekil X-TAM-* basliklariyla kimligi iletir (SSO).
- Cerezler: tarayicidan yalniz yeni panelin kendi cerezleri iletilir; uretim oturum cerezi
  yeni panele GITMEZ. X-TAM-* basliklari istemciden gelirse atilir, vekil kendisi yazar.
- Yapilandirma (.env): DEV_PANEL_SECRET (en az 32 karakter; yeni panelin TAMLIFE_SSO_SECRET
  degeriyle ayni), DEV_PANEL_PORT (varsayilan 8117). Sir yoksa 503 doner (kapali basarisizlik).
- Yeni panel kapaliysa 503 sayfasi doner; uretim paneli etkilenmez.
- Yalniz standart kutuphane (http.client). Ana makine sabit 127.0.0.1: hedef degistirilemez.

Kurulum: backend/app/__init__.py icinde blueprint kaydi, bkz. deploy/prod/README.md.
"""
from __future__ import annotations

import http.client
import os
import re
from urllib.parse import quote

from flask import Blueprint, Response, current_app, g, jsonify, request, session

from backend.app.security import _istek_ip, admin_required

dev_panel_bp = Blueprint('dev_panel', __name__)

ON_EK = '/admin/dev'
HEDEF_ANA_MAKINE = '127.0.0.1'
VARSAYILAN_PORT = 8117
ZAMAN_ASIMI_SN = 60

ISTEK_BASLIKLARI = ('content-type', 'accept', 'accept-language', 'origin', 'referer', 'user-agent',
                    'x-csrf-token', 'if-none-match', 'if-modified-since')
CEVAP_BASLIKLARI = ('content-type', 'content-disposition', 'cache-control', 'content-security-policy',
                    'retry-after', 'etag', 'last-modified', 'x-content-type-options', 'referrer-policy',
                    'permissions-policy')
IZINLI_CEREZLER = ('tamlife_session', 'tamlife_csrf')
# Arayuz CSP'si ve onbellek basliklari uretim panelinin genel basliklarina ezilmesin (bkz. kur).
KORUNAN_BASLIKLAR = ('Content-Security-Policy', 'Cache-Control')

_CEREZ_ADI = re.compile(r'^([^=;\s]+)=')


def _port():
    ham = os.environ.get('DEV_PANEL_PORT', '').strip()
    return int(ham) if ham.isdigit() and 1024 <= int(ham) <= 65535 else VARSAYILAN_PORT


def _sir():
    sir = os.environ.get('DEV_PANEL_SECRET', '').strip()
    return sir if len(sir) >= 32 else ''


def _api_mi():
    return request.path.startswith(ON_EK + '/api/')


def _hata(mesaj, kod):
    if _api_mi():
        return jsonify(status='error', message=mesaj), kod
    govde = (f'<!doctype html><meta charset="utf-8"><title>Yeni panel</title>'
             f'<h3>{mesaj}</h3><p><a href="/">Ana sayfa</a></p>')
    return Response(govde, status=kod, mimetype='text/html')


def _cerezler():
    """Tarayici cerezlerinden yalniz yeni panelin kendilerini ilet."""
    parcalar = [f'{ad}={deger}' for ad, deger in request.cookies.items() if ad in IZINLI_CEREZLER]
    return '; '.join(parcalar)


def _istek_basliklari(sir):
    basliklar = {ad: request.headers[ad] for ad in ISTEK_BASLIKLARI if request.headers.get(ad)}
    basliklar['Host'] = request.headers.get('Host', '')
    basliklar['Accept-Encoding'] = 'identity'
    basliklar['Connection'] = 'close'
    basliklar['X-Forwarded-For'] = _istek_ip()
    basliklar['X-Forwarded-Proto'] = 'https' if request.is_secure else 'http'
    cerez = _cerezler()
    if cerez:
        basliklar['Cookie'] = cerez
    basliklar['X-TAM-User'] = g.current_user.username
    basliklar['X-TAM-Role'] = 'admin'
    basliklar['X-TAM-Proxy-Secret'] = sir
    return basliklar


def _cevap(yanit):
    govde = yanit.read()
    cevap = Response(govde, status=yanit.status)
    for ad, deger in yanit.getheaders():
        kucuk = ad.lower()
        if kucuk in CEVAP_BASLIKLARI:
            cevap.headers[ad] = deger
        elif kucuk == 'set-cookie':
            eslesme = _CEREZ_ADI.match(deger)
            if eslesme and eslesme.group(1) in IZINLI_CEREZLER:
                cevap.headers.add('Set-Cookie', deger)
    g.dev_panel_basliklari = {ad: cevap.headers[ad] for ad in KORUNAN_BASLIKLAR if ad in cevap.headers}
    return cevap


@admin_required
def _yonetici_vekili(yol):
    sir = _sir()
    if not sir:
        return _hata('Yeni panel yapılandırılmadı (DEV_PANEL_SECRET).', 503)
    hedef = '/' + quote(yol, safe="/:@!$&'()*+,;=~-._")
    if request.query_string:
        hedef += '?' + request.query_string.decode('latin-1')
    govde = request.get_data() if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') else None
    try:
        baglanti = http.client.HTTPConnection(HEDEF_ANA_MAKINE, _port(), timeout=ZAMAN_ASIMI_SN)
        try:
            baglanti.request(request.method, hedef, body=govde, headers=_istek_basliklari(sir))
            return _cevap(baglanti.getresponse())
        finally:
            baglanti.close()
    except ValueError:
        return _hata('Geçersiz istek yolu.', 400)
    except OSError:
        current_app.logger.warning('Yeni panel (dev) %s:%s yanit vermedi.', HEDEF_ANA_MAKINE, _port())
        return _hata('Yeni panel şu an çalışmıyor. Yöneticiye bildirin.', 503)


@dev_panel_bp.route(ON_EK + '/', defaults={'yol': ''}, methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
@dev_panel_bp.route(ON_EK + '/<path:yol>', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def vekil(yol):
    # Oturumsuz ya da yonetici olmayan API cagrisina yonlendirme yerine JSON (uretim paneli
    # /api/ disindaki yollarda login'e yonlendirir). Asil yetki denetimi admin_required'dadir.
    if _api_mi() and not (getattr(g, 'current_user', None) and session.get('is_admin')):
        return jsonify(status='error', message='Oturum bulunamadı ya da yönetici yetkisi yok.'), 401
    return _yonetici_vekili(yol)


def _basliklari_geri_yukle(response):
    for ad, deger in (getattr(g, 'dev_panel_basliklari', None) or {}).items():
        response.headers[ad] = deger
    return response


def kur(app):
    """Blueprint'i kaydeder. security_headers'tan ONCE cagrilmali: after_request ters sirada
    calistigindan bu kanca en sonda calisir ve arayuzun CSP'sini geri yukler."""
    app.register_blueprint(dev_panel_bp)
    app.after_request(_basliklari_geri_yukle)
