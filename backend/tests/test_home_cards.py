"""14 ana sayfa karti, prod ANA_SAYFA sirasi."""

from __future__ import annotations

import re
from pathlib import Path

from app.modules.catalog import ANA_SAYFA_KARTLARI

TS = Path(__file__).resolve().parents[2] / "ekran-react" / "src" / "shell" / "home-cards.ts"


def test_fourteen_home_cards_in_order() -> None:
    text = TS.read_text(encoding="utf-8")
    found = re.findall(r'"cardId": "([^"]+)"', text)
    expected = [card.kart_id for card in ANA_SAYFA_KARTLARI]
    assert found == expected
    assert len(found) == 14
    assert found[0] == "dash-card-ekip"
    assert found[-1] == "dash-card-baglantili"
    assert "dash-card-gelir-uretim" in found
    assert "dash-card-toptan" in found
    nav = (TS.parent / "nav.tsx").read_text(encoding="utf-8")
    layout = (TS.parent / "layout.tsx").read_text(encoding="utf-8")
    assert "ANA_SAYFA_KARTLARI.map" in nav
    assert "ANA_SAYFA_KARTLARI.map" in layout
    assert "Kayit yok" in (TS.parents[1] / "shared" / "empty.tsx").read_text(encoding="utf-8")
