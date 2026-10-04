"""dev_panel_bp yalitilmis test: uretim uygulamasi ve veritabani gerekmez.

Uretimin backend.app.security modulu yerine ayni anlamli kucuk bir taklit yuklenir
(admin_required: g.current_user + session['is_admin']); yeni panel yerine yerel sahte bir
HTTP sunucusu kullanilir. Calistirma (yeni panel deposunun kokunden):

    PYTHONPATH=<uretim>/.venv/Lib/site-packages .venv/Scripts/python.exe -m pytest deploy/prod/test_dev_panel_bp.py

Sunucuda uretim venv'inde: python -m pytest <bu dosya>
"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
import types
from functools import wraps
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from flask import Flask, g, jsonify, redirect, request, session

SIR = 's' * 40
KAYIT: list[dict] = []
YANIT: dict = {}


class SahteYeniPanel(BaseHTTPRequestHandler):
    def _ver(self):
        uzunluk = int(self.headers.get('Content-Length') or 0)
        govde = self.rfile.read(uzunluk) if uzunluk else b''
        KAYIT.append({'yontem': self.command, 'yol': self.path, 'baslik': {k.lower(): v for k, v in self.headers.items()},
                      'govde': govde})
        ayar = YANIT.get(self.path.split('?')[0], YANIT['*'])
        self.send_response(ayar.get('durum', 200))
        for ad, deger in ayar.get('baslik', []):
            self.send_header(ad, deger)
        icerik = ayar.get('govde', b'tamam')
        self.send_header('Content-Length', str(len(icerik)))
        self.end_headers()
        self.wfile.write(icerik)

    do_GET = do_POST = do_PUT = do_DELETE = _ver

    def log_message(self, *_):
        pass


def _modulu_yukle():
    """Sahte backend.app.security ile dev_panel_bp.py dosyasini yukler."""
    paket = types.ModuleType('backend')
    uygulama = types.ModuleType('backend.app')
    guvenlik = types.ModuleType('backend.app.security')

    def admin_required(f):
        @wraps(f)
        def sarmal(*a, **k):
            if not getattr(g, 'current_user', None):
                return redirect('/login')
            if not session.get('is_admin'):
                return redirect('/')
            return f(*a, **k)
        return sarmal

    guvenlik.admin_required = admin_required
    guvenlik._istek_ip = lambda: request.remote_addr or ''
    for ad, mod in (('backend', paket), ('backend.app', uygulama), ('backend.app.security', guvenlik)):
        sys.modules[ad] = mod
    yol = Path(__file__).with_name('dev_panel_bp.py')
    belirtim = importlib.util.spec_from_file_location('dev_panel_bp_test', yol)
    modul = importlib.util.module_from_spec(belirtim)
    belirtim.loader.exec_module(modul)
    return modul


@pytest.fixture
def sahte_panel(monkeypatch):
    sunucu = ThreadingHTTPServer(('127.0.0.1', 0), SahteYeniPanel)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    KAYIT.clear()
    YANIT.clear()
    YANIT['*'] = {'baslik': [('Content-Type', 'text/plain')]}
    monkeypatch.setenv('DEV_PANEL_PORT', str(sunucu.server_address[1]))
    monkeypatch.setenv('DEV_PANEL_SECRET', SIR)
    yield sunucu
    sunucu.shutdown()


def _uygulama(modul, yonetici=True, giris=True):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'x'

    @app.before_request
    def kullanici():
        g.current_user = types.SimpleNamespace(username='ayse.yilmaz') if giris and 'user_id' in session else None

    modul.kur(app)  # uretimdeki gibi security_headers'tan once

    @app.after_request
    def security_headers(response):
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        return response

    @app.route('/giris')
    def giris_yap():
        session['user_id'] = 1
        session['is_admin'] = yonetici
        return 'ok'

    return app


@pytest.fixture
def modul():
    return _modulu_yukle()


@pytest.fixture
def yonetici(modul, sahte_panel):
    c = _uygulama(modul, yonetici=True).test_client()
    c.get('/giris')
    return c


def test_yonetici_olmayan_sayfada_yonlenir_apide_401_ve_yeni_panele_gitmez(modul, sahte_panel):
    c = _uygulama(modul, yonetici=False).test_client()
    c.get('/giris')
    assert c.get('/admin/dev/').status_code == 302
    r = c.get('/admin/dev/api/v1/session/me')
    assert r.status_code == 401 and r.get_json()['status'] == 'error'
    assert KAYIT == []


def test_oturumsuz_erisim_reddedilir(modul, sahte_panel):
    c = _uygulama(modul).test_client()
    assert c.get('/admin/dev/').status_code == 302
    assert c.post('/admin/dev/api/v1/session/sso').status_code == 401
    assert KAYIT == []


def test_slashsiz_adres_slasha_yonlenir(yonetici):
    r = yonetici.get('/admin/dev')
    assert r.status_code in (301, 308) and r.headers['Location'].endswith('/admin/dev/')


def test_yonetici_kimligi_ve_sir_eklenir_istemci_basliklari_ve_uretim_cerezi_atilir(yonetici):
    sunucu = 'http://tamlife'
    yonetici.get('/giris', base_url=sunucu)
    for ad, deger in (('tamlife_session', 'abc'), ('tamlife_csrf', 'xyz'), ('baska', 'gizli')):
        yonetici.set_cookie(ad, deger, domain='tamlife', path='/')
    r = yonetici.get('/admin/dev/assets/a.js?v=1', base_url=sunucu, headers={
        'X-TAM-User': 'saldirgan', 'X-TAM-Role': 'admin', 'X-TAM-Proxy-Secret': 'tahmin',
        'Authorization': 'Bearer x'})
    assert r.status_code == 200 and r.data == b'tamam'
    gelen = KAYIT[-1]
    assert gelen['yol'] == '/assets/a.js?v=1'
    b = gelen['baslik']
    assert b['x-tam-user'] == 'ayse.yilmaz' and b['x-tam-role'] == 'admin' and b['x-tam-proxy-secret'] == SIR
    assert b['host'] == 'tamlife' and b['accept-encoding'] == 'identity'
    assert 'authorization' not in b
    cerez = b['cookie']
    assert 'tamlife_session=abc' in cerez and 'tamlife_csrf=xyz' in cerez
    assert 'baska' not in cerez and 'session=' not in cerez.replace('tamlife_session=', '')


def test_govde_ve_csrf_basligi_iletilir_ve_cevap_aynen_doner(yonetici):
    YANIT['/api/v1/musteri'] = {'durum': 201, 'baslik': [('Content-Type', 'application/json')],
                                'govde': json.dumps({'status': 'success'}).encode()}
    r = yonetici.post('/admin/dev/api/v1/musteri', json={'name': 'Test'}, headers={'X-CSRF-Token': 't1'})
    assert r.status_code == 201 and r.get_json() == {'status': 'success'}
    gelen = KAYIT[-1]
    assert gelen['yontem'] == 'POST' and json.loads(gelen['govde']) == {'name': 'Test'}
    assert gelen['baslik']['x-csrf-token'] == 't1'
    assert gelen['baslik']['content-type'].startswith('application/json')


def test_sadece_yeni_panel_cerezleri_tarayiciya_gecer(yonetici):
    YANIT['/api/v1/session/sso'] = {'baslik': [
        ('Content-Type', 'application/json'),
        ('Set-Cookie', 'tamlife_session=tok; HttpOnly; Path=/admin/dev; SameSite=strict'),
        ('Set-Cookie', 'tamlife_csrf=cs; Path=/admin/dev; SameSite=strict'),
        ('Set-Cookie', 'session=ele-gecirme; Path=/'),
        ('Set-Cookie', 'baska=1; Path=/'),
    ]}
    r = yonetici.post('/admin/dev/api/v1/session/sso')
    gelen = r.headers.getlist('Set-Cookie')
    assert len(gelen) == 2 and all(h.startswith(('tamlife_session=', 'tamlife_csrf=')) for h in gelen)


def test_arayuz_csp_ve_onbellek_basligi_uretimin_genel_basligina_ezilmez(yonetici):
    yonetici.get('/admin/dev/')  # varsayilan cevap
    YANIT['/'] = {'baslik': [('Content-Type', 'text/html'),
                             ('Content-Security-Policy', "default-src 'self'; script-src 'self'"),
                             ('Cache-Control', 'no-store')]}
    r = yonetici.get('/admin/dev/')
    assert r.headers['Content-Security-Policy'] == "default-src 'self'; script-src 'self'"
    # vekil olmayan yollarda uretimin basligi degismez
    assert yonetici.get('/giris').headers['Content-Security-Policy'] == "frame-ancestors 'self'"


def test_yeni_panel_kapaliysa_503(modul, monkeypatch):
    monkeypatch.setenv('DEV_PANEL_SECRET', SIR)
    monkeypatch.setenv('DEV_PANEL_PORT', '1999')  # dinleyen yok
    c = _uygulama(modul).test_client()
    c.get('/giris')
    sayfa = c.get('/admin/dev/')
    assert sayfa.status_code == 503 and 'çalışmıyor' in sayfa.get_data(as_text=True)
    api = c.get('/admin/dev/api/v1/health')
    assert api.status_code == 503 and api.get_json()['status'] == 'error'


@pytest.mark.parametrize('sir', ['', 'kisa'])
def test_sir_yoksa_ya_da_kisaysa_kapali_basarisizlik(modul, sahte_panel, monkeypatch, sir):
    monkeypatch.setenv('DEV_PANEL_SECRET', sir)
    c = _uygulama(modul).test_client()
    c.get('/giris')
    assert c.get('/admin/dev/').status_code == 503
    assert KAYIT == []


def test_hedef_ana_makine_sabit_ve_yol_bozulmaz(yonetici):
    assert yonetici.get('/admin/dev/a%20b/%C3%A7.js').status_code == 200
    assert KAYIT[-1]['yol'] == '/a%20b/%C3%A7.js'
