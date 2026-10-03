"""Panel catalog. Display names only; no customer rows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Module:
    key: str
    title: str
    kind: str
    admin_only: bool = False
    public: bool = False
    in_nav: bool = True
    permission: str | None = None


@dataclass(frozen=True)
class HomeCard:
    key: str
    title: str
    i18n: str
    card_id: str


MODULES: tuple[Module, ...] = (
    Module("musteri", "Müşteri Yönetimi", "module"),
    Module("takvim", "İzin ve Takvim Yönetimi", "module"),
    Module("takvim_ozet", "TAM Takvim", "card"),
    Module("onedesk", "OneDesk", "module"),
    Module("utilizasyon", "TAM Utilizasyon", "module", admin_only=True, in_nav=False),
    Module("roller", "Rol Yönetimi", "module", admin_only=True, in_nav=False),
    Module("talep", "Geliştirme Talepleri", "module", public=True, in_nav=False),
    Module("ekip", "TAM Özet", "card"),
    Module("rapor", "Gönderilen Aylık Rapor", "card"),
    Module("proje", "Takip Edilen Projeler", "card"),
    Module("tamsms", "TAM SMS", "card"),
    Module("tamapn", "TAM APN", "card"),
    Module("gelir_uretim", "TAM GELIR&URETIM", "card"),
    Module("toptan", "TAM Toptan", "card"),
    Module("sunum", "TAM Sunum", "card"),
    Module("radar", "Müşteri Radar", "card"),
    Module("baglantili", "Bağlantılı Araçlar", "card"),
    Module("topoloji", "TopoMaker", "module", in_nav=False, permission="musteri"),
)

BY_KEY = {item.key: item for item in MODULES}

HOME_CARDS: tuple[HomeCard, ...] = (
    HomeCard("ekip", "TAM Özet", "card.ekip.title", "dash-card-ekip"),
    HomeCard("takvim_ozet", "TAM Takvim", "card.takvim.title", "dash-card-takvim"),
    HomeCard("sunum", "TAM Sunum", "card.sunum.title", "dash-card-sunum"),
    HomeCard("radar", "Müşteri Radar", "card.radar.title", "dash-card-radar"),
    HomeCard("musteri", "Müşteri Yönetimi", "musteri.tamPortfoy", "dash-card-modul-portfoy"),
    HomeCard("rapor", "Gönderilen Aylık Rapor", "card.rapor.title", "dash-card-rapor"),
    HomeCard("proje", "Takip Edilen Projeler", "card.proje.title", "dash-card-proje"),
    HomeCard("onedesk", "OneDesk", "card.ats.title", "dash-card-onedesk"),
    HomeCard("toptan", "TAM Toptan", "card.toptan.title", "dash-card-toptan"),
    HomeCard("tamsms", "TAM SMS", "card.tamSms.title", "dash-card-tamsms"),
    HomeCard("tamapn", "TAM APN", "card.tamApn.title", "dash-card-tamapn"),
    HomeCard("gelir_uretim", "TAM GELIR&URETIM", "card.gelirUretim.title", "dash-card-gelir-uretim"),
    HomeCard("takvim", "İzin ve Takvim Yönetimi", "tab.takvim", "dash-card-modul-takvim"),
    HomeCard("baglantili", "Bağlantılı Araçlar", "card.placeholder.title", "dash-card-baglantili"),
)


def get(key: str) -> Module:
    return BY_KEY[key]
