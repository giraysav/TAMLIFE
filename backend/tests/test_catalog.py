"""Katalog kumesi prod MODULLER anahtarlari ile esit (topoloji haric)."""

from __future__ import annotations

from app.modules.catalog import ANA_SAYFA_KARTLARI, BOS_KARTLAR, MODULLER, PROD_MODUL_ANAHTARLARI

PROD = frozenset({
    "musteri",
    "takvim",
    "takvim_ozet",
    "onedesk",
    "utilizasyon",
    "roller",
    "talep",
    "ekip",
    "rapor",
    "proje",
    "tamsms",
    "tamapn",
    "gelir_uretim",
    "toptan",
    "sunum",
    "radar",
    "baglantili",
})


def test_prod_anahtar_kumesi() -> None:
    assert PROD_MODUL_ANAHTARLARI == PROD
    assert {m.anahtar for m in MODULLER} == PROD | {"topoloji"}


def test_bayraklar() -> None:
    by_key = {m.anahtar: m for m in MODULLER}
    assert {k for k, m in by_key.items() if m.yalniz_admin} == {"utilizasyon", "roller"}
    assert {k for k, m in by_key.items() if m.herkese_acik} == {"talep"}
    assert by_key["topoloji"].in_nav is False
    assert by_key["topoloji"].yetki == "musteri"
    assert by_key["utilizasyon"].in_nav is False
    assert by_key["roller"].in_nav is False
    assert by_key["talep"].in_nav is False
    assert BOS_KARTLAR <= {k for k, m in by_key.items() if m.in_nav}
    assert len(ANA_SAYFA_KARTLARI) == 14
    assert [k.kart_id for k in ANA_SAYFA_KARTLARI] == [
        "dash-card-ekip",
        "dash-card-takvim",
        "dash-card-sunum",
        "dash-card-radar",
        "dash-card-modul-portfoy",
        "dash-card-rapor",
        "dash-card-proje",
        "dash-card-onedesk",
        "dash-card-toptan",
        "dash-card-tamsms",
        "dash-card-tamapn",
        "dash-card-gelir-uretim",
        "dash-card-modul-takvim",
        "dash-card-baglantili",
    ]
