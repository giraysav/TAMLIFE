# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Musteri karti alani (2026-10-19 kullanici istegi: "Toptan ve Baglantili Araclar Musteri Yonetimi'nin klonu ama baglantilariyla gelmis,
Toptan'dan silince her yerden siliyor; bagimliliklarini kopar").

Ayni musteri ekrani uc modulde acilir ve her modulun kartlari AYRIDIR: customer.modul = musteri | toptan | baglantili.
Istegin alani 'X-Musteri-Alani' basligindan ContextVar'a yazilir (MusteriAlaniAraKatmani; arayuz basligi yalniz Toptan / Baglantili
Araclar ekranindan musteri, topoloji ve rapor gonderim uclarina gonderir). Customer uzerindeki TUM ORM sorgulari (select, update, delete,
iliski yuklemeleri) secili alana suzulur (do_orm_execute + with_loader_criteria); yeni kart secili alanda acilir. Baslik yoksa alan
'musteri'dir: Onedesk, TEMIP eslesmesi, Radar, Ekip Ozeti, skor, sunum, isci ve testler yalniz Musteri Yonetimi kartlarini gorur.
Ham SQL (text) ya da Core tablo sorgusu suzgecten gecmez; customer tablosuna boyle erisen yeni kod alani kendisi suzmeli.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

VARSAYILAN = "musteri"
ALANLAR = (VARSAYILAN, "toptan", "baglantili")
TUMU = "*"  # suzgecsiz: TEMIP / Onedesk / Radar eslesmesi kartin hangi modulde oldugundan bagimsizdir (tum_alanlarda)
# 2026-10-20 kullanici: "segmenti WHOLESALE olan musteri kartlarinin hedef modulu Toptan". Cati kartin segmenti WHOLESALE ise kart
# (istirakleriyle) toptan alanina gecer, WHOLESALE'den cikarsa Musteri Yonetimi'ne doner; istirak her zaman catisinin alanindadir.
# Her yazim yolunda (kart acma, duzenleme, ham musteri yuklemesi) flush kancasi uygular (_segment_alani).
SEGMENT_ALANI = {"WHOLESALE": "toptan", "CONNCAR": "baglantili"}  # 2026-10-20: CONNCAR yalniz Baglantili Araclar'da (ayni kural)
BASLIK = b"x-musteri-alani"
_alan: ContextVar[str] = ContextVar("tamlife_musteri_alani", default=VARSAYILAN)


def secili() -> str:
    """Istegin alani (yeni kart bu alanda acilir). Suzgecsiz baglamda (tum_alanlarda) varsayilan alan."""
    alan = _alan.get()
    return VARSAYILAN if alan == TUMU else alan


def ayarla(alan: str) -> Any:
    """Testler ve isci surecler icin; donen jeton geri_al ile birakilir."""
    return _alan.set(alan if alan in ALANLAR else VARSAYILAN)


def geri_al(jeton: Any) -> None:
    _alan.reset(jeton)


def tum_alanlarda(f: Callable) -> Callable:
    """Fonksiyon boyunca Customer sorgulari alana suzulmez (kart eslesmesi tum modullerde)."""

    @functools.wraps(f)
    def sarmal(*a: Any, **k: Any) -> Any:
        jeton = _alan.set(TUMU)
        try:
            return f(*a, **k)
        finally:
            _alan.reset(jeton)

    return sarmal


class MusteriAlaniAraKatmani:
    """Saf ASGI ara katmani: 'X-Musteri-Alani' basligini okur (yalniz ALANLAR; diger deger varsayilan alandir)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        deger = next((v for k, v in scope.get("headers") or [] if k == BASLIK), b"").decode("latin-1").strip().lower()
        jeton = ayarla(deger)
        try:
            await self.app(scope, receive, send)
        finally:
            geri_al(jeton)


_KURULDU = False


def kur() -> None:
    """Customer sorgularina alan suzgecini baglar (surec basina bir kez; app.db import edilince cagrilir)."""
    global _KURULDU
    if _KURULDU:
        return
    from sqlalchemy import event
    from sqlalchemy.orm import Session, with_loader_criteria

    from app.models import Customer

    @event.listens_for(Session, "do_orm_execute")
    def _suz(durum: Any) -> None:
        if durum.is_column_load or durum.is_relationship_load:
            return  # iliski / sutun yuklemesi ust sorgunun suzgecini tasir
        alan = _alan.get()
        if alan != TUMU and (durum.is_select or durum.is_update or durum.is_delete):
            durum.statement = durum.statement.options(with_loader_criteria(Customer, lambda c: c.modul == alan, include_aliases=True))

    @event.listens_for(Session, "before_flush")
    def _segment_alani(oturum: Any, _baglam: Any, _ornekler: Any) -> None:
        from sqlalchemy import inspect as sa_inspect
        from sqlalchemy import select

        for c in [o for o in (*oturum.new, *oturum.dirty) if isinstance(o, Customer) and o.parent_id is None]:
            gecmis = sa_inspect(c).attrs.segment.history
            if c not in oturum.new and not gecmis.has_changes():
                continue
            hedef = SEGMENT_ALANI.get((c.segment or "").strip().upper())
            if hedef is None:  # WHOLESALE'den cikan kart yalniz kurala gore tasindiysa geri doner
                onceki = next((s for s in gecmis.deleted or () if s), "")
                hedef = VARSAYILAN if c.modul in SEGMENT_ALANI.values() and SEGMENT_ALANI.get(str(onceki).strip().upper()) == c.modul else c.modul
            if hedef == c.modul:
                continue
            c.modul = hedef
            if c.id is not None:  # istirakler catiyi izler (onceki alanda okunur)
                for alt in oturum.scalars(select(Customer).where(Customer.parent_id == c.id).execution_options(autoflush=False)):
                    alt.modul = hedef

    _KURULDU = True
