"""Tek modul listesi. Uretim MODULLER, ANA_SAYFA_KUTUCUKLARI ve kutucuk kaydindan.

Eski uygulamada her kutu ayri klasordeydi. Burada klasor yok; kimlik, ad ve
bayrak ayni kaynaktan tek listede durur. Musteri satiri yok.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubModule:
    """Ana modulun alt modulu (sol menude modulun altinda acilan fonksiyon penceresi).

    Kimlik `<modul>/<alt>` bicimindedir; ornek `musteri/liste`. Alt moduller ayrintilari
    verildikce `Module.children` icine eklenir; su an hicbir modulde tanimli degildir.
    """

    key: str
    title: str
    description: str = ""
    ready: bool = False
    title_en: str = ""
    description_en: str = ""


@dataclass(frozen=True)
class Module:
    key: str
    title: str
    kind: str
    title_en: str = ""  # arayuz dili English iken gosterilen ad
    admin_only: bool = False
    personel_only: bool = False  # yalniz TeamMember kendi kaydini tutar; admin ve TeamMngr bu modulde yer almaz (2026-10-13)
    public: bool = False
    in_nav: bool = True
    permission: str | None = None
    i18n: str = ""
    card_id: str = ""
    box_id: str = ""
    permission_group: str = ""
    note: str = ""
    ready: bool = True
    registry_id: str = ""
    registry_status: str = ""
    modal_id: str = ""
    table: str = ""
    children: tuple[SubModule, ...] = ()


# Sira: moduller.py MODULLER. Ana sayfa sirasi HOME_ORDER.
MODULES: tuple[Module, ...] = (
    Module(
        "musteri", "Müşteri Yönetimi", "modul", title_en="Customer Management",
        i18n="musteri.tamPortfoy", card_id="dash-card-modul-portfoy",
        box_id="mod_musteri", permission_group="modules",
        registry_id="portfoy", registry_status="aktif", modal_id="mgmtMusteriModal",
        table="customers",
    ),
    Module(
        "takvim", "İzin&Takvim Yönetimi", "modul", title_en="Leave & Calendar Management", personel_only=True,
        i18n="tab.takvim", card_id="dash-card-modul-takvim",
        box_id="mod_takvim", permission_group="modules",
        note="kişinin kendi takvimi; yalnız TeamMember (yönetici ve admin takvim tutmaz)",
        registry_status="aktif", modal_id="mgmtTakvimModal",
        table="calendar_records",
    ),
    Module(
        "takvim_ozet", "TAM Takvim", "kart", title_en="TAM Calendar",
        i18n="card.takvim.title", card_id="dash-card-takvim",
        box_id="card_takvim_ozet", permission_group="dashboard_cards",
        note="TeamMember yalnız kendi takvimini görür",
        registry_id="takvim", registry_status="aktif", modal_id="takvimModal",
        table="calendar_records",
    ),
    Module(
        "onedesk", "Onedesk", "modul", title_en="Onedesk",
        i18n="card.ats.title", card_id="dash-card-onedesk",
        box_id="mod_onedesk", permission_group="modules",
        registry_status="aktif", modal_id="atsModal",
        table="customers",
    ),
    Module(
        "utilizasyon", "TAM Utilizasyon", "modul", title_en="TAM Utilization", admin_only=True,
        note="ana sayfa kutucuğu yok; yalnız admin",
        registry_status="aktif", modal_id="mgmtUtilizasyonModal",
        table="util_criteria",
    ),
    Module(
        "roller", "Rol Yönetimi", "modul", title_en="Role Management", admin_only=True,
        note="ana sayfa kutucuğu yok; yalnız admin",
        table="users",
    ),
    Module(
        "talep", "Geliştirme Talepleri", "modul", title_en="Development Requests", public=True,
        note="ana sayfada kutucuk değil",
        registry_status="aktif", modal_id="mgmtTalepModal",
        table="gelistirme_talepleri",
    ),
    Module(
        "rapor", "Gönderilen Aylık Rapor", "kart", title_en="Sent Monthly Reports",
        i18n="card.rapor.title", card_id="dash-card-rapor",
        box_id="card_rapor", permission_group="dashboard_cards",
        registry_status="aktif", modal_id="aylikRaporModal",
        table="reports",
    ),
    Module(
        "proje", "Takip Edilen Projeler", "kart", title_en="Tracked Projects",
        i18n="card.proje.title", card_id="dash-card-proje",
        box_id="card_proje", permission_group="dashboard_cards",
        registry_status="aktif", modal_id="projeModal",
        table="project_items",
    ),
    Module(
        "tamsms", "ICT Sms & Gelir", "kart", title_en="ICT SMS & Revenue",
        i18n="card.tamSms.title", card_id="dash-card-tamsms",
        box_id="card_tamsms", permission_group="dashboard_cards",
        registry_id="ictapn", registry_status="aktif", modal_id="ictApnModal",
        table="ict_revenues",
    ),
    Module(
        "tamapn", "APN Gelir ve Kurulum", "kart", title_en="APN Revenue & Installation",
        i18n="card.tamApn.title", card_id="dash-card-tamapn",
        box_id="card_tamapn", permission_group="dashboard_cards",
        table="apn_revenues",
    ),
    Module(
        "gelir_uretim", "Gelir Faydası Sağlanan İşler", "kart", title_en="Revenue-Benefit Work", ready=False,
        i18n="card.gelirUretim.title", card_id="dash-card-gelir-uretim",
        box_id="card_gelir_uretim", permission_group="dashboard_cards",
        note="icerik yakinda detaylandirilacak",
    ),
    Module(
        "sunum", "Çeyrek Bazlı Sunum", "kart", title_en="Quarterly Presentation",
        i18n="card.sunum.title", card_id="dash-card-sunum",
        box_id="card_sunum", permission_group="dashboard_cards",
        registry_status="aktif", modal_id="sunumModal",
        table="qbr_reports",
    ),
    Module(
        "radar", "Müşteri Radar", "kart", title_en="Customer Radar",
        i18n="card.radar.title", card_id="dash-card-radar",
        box_id="card_radar", permission_group="dashboard_cards",
        registry_status="aktif", modal_id="radarModal",
        table="radar_prospects",
    ),
    Module(
        "baglantili", "Bağlantılı Araçlar", "kart", title_en="Connected Tools", ready=False,
        i18n="card.placeholder.title", card_id="dash-card-baglantili",
        box_id="card_baglantili", permission_group="dashboard_cards",
        note="içerik henüz yok",
        registry_status="stub",
    ),
    Module(
        "topoloji", "TopoMaker", "modul", title_en="TopoMaker", in_nav=False, permission="musteri",
        note="ana sayfa kutucuğu yok; müşteri iznine bağlı",
        registry_status="aktif", modal_id="topoMakerModal",
    ),
)

BY_KEY = {item.key: item for item in MODULES}

# Ana sayfa sirasi: ANA_SAYFA_KUTUCUKLARI. Talep, roller, utilizasyon, topoloji yok.
HOME_ORDER: tuple[str, ...] = (
    "takvim_ozet",
    "sunum",
    "radar",
    "musteri",
    "rapor",
    "proje",
    "onedesk",
    "tamsms",
    "tamapn",
    "gelir_uretim",
    "takvim",
    "baglantili",
)

HOME_CARDS: tuple[Module, ...] = tuple(BY_KEY[key] for key in HOME_ORDER)


def get(key: str) -> Module:
    return BY_KEY[key]
