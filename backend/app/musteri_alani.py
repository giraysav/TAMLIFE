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

from contextvars import ContextVar
from typing import Any

VARSAYILAN = "musteri"
ALANLAR = (VARSAYILAN, "toptan", "baglantili")
BASLIK = b"x-musteri-alani"
_alan: ContextVar[str] = ContextVar("tamlife_musteri_alani", default=VARSAYILAN)


def secili() -> str:
    return _alan.get()


def ayarla(alan: str) -> Any:
    """Testler ve isci surecler icin; donen jeton geri_al ile birakilir."""
    return _alan.set(alan if alan in ALANLAR else VARSAYILAN)


def geri_al(jeton: Any) -> None:
    _alan.reset(jeton)


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
        if durum.is_select or durum.is_update or durum.is_delete:
            alan = _alan.get()
            durum.statement = durum.statement.options(with_loader_criteria(Customer, lambda c: c.modul == alan, include_aliases=True))

    _KURULDU = True
