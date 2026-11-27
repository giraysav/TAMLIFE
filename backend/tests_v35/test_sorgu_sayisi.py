# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""N+1 backtest: okuma uclarinin SQL sayisi veri buyudukce artmamali (5 -> 40 cati musteri, her birine 2 istirak ve ayri sahip)."""

from __future__ import annotations

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db import engine
from app.models import AppUser, Customer, Demand, ProjectItem
from app.ortak import simdi
from tests_v35.conftest import login_ok

UCLAR = (
    "/api/v1/musteri",
    "/api/v1/musteri/portfoy",
    "/api/v1/musteri/{ilk}",
    "/api/v1/ekip/ozet",
    "/api/v1/proje",
    "/api/v1/proje/musteri",
    "/api/v1/talep",
    "/api/v1/rapor/durum",
    "/api/v1/rapor/gonderilenler",
    "/api/v1/skor/agac",
    "/api/v1/skor/siralama",
    "/api/v1/takvim/ekip",
    "/api/v1/yonetim/musteriler",
    "/api/v1/radar",
    "/api/v1/onedesk/top10",
    "/api/v1/gelir-uretim",
)


def _tohumla(bas: int, adet: int) -> int:
    with Session(engine()) as db:
        kisiler = [AppUser(username=f"tam{i}", display_name=f"Tam {i}", role="TeamMember") for i in range(bas, bas + adet)]
        db.add_all(kisiler)
        db.flush()
        ilk = 0
        for n, kisi in enumerate(kisiler):
            i = bas + n
            cati = Customer(external_key=f"C{i}", name=f"Cati {i}", owner_id=kisi.id, score=50.0 + i, alarm_count=i, complaint_count=1)
            db.add(cati)
            db.flush()
            ilk = ilk or cati.id
            for j in range(2):
                db.add(Customer(external_key=f"C{i}-{j}", name=f"Istirak {i}-{j}", owner_id=kisiler[(n + j + 1) % adet].id, parent_id=cati.id))
            zaman = simdi()
            db.add(ProjectItem(title=f"P{i}", owner_id=kisi.id, category="proje", created_at=zaman, updated_at=zaman))
            db.add(Demand(title=f"T{i}", current_state="a", expected_state="b", opened_by_id=kisi.id, opened_at=zaman))
        db.commit()
        return ilk


def _say(client, yol: str) -> int:
    sayac = [0]

    def dinle(*_a):  # type: ignore[no-untyped-def]
        sayac[0] += 1

    event.listen(engine(), "before_cursor_execute", dinle)
    try:
        r = client.get(yol)
    finally:
        event.remove(engine(), "before_cursor_execute", dinle)
    assert r.status_code == 200, (yol, r.status_code, r.text[:200])
    return sayac[0]


@pytest.mark.parametrize("yol", UCLAR)
def test_sorgu_sayisi_veriyle_buyumez(client, yol):
    login_ok(client)
    ilk = _tohumla(0, 5)
    az = _say(client, yol.format(ilk=ilk))
    _tohumla(5, 35)
    cok = _say(client, yol.format(ilk=ilk))
    assert cok <= az + 2, f"{yol}: 5 kayitta {az} sorgu, 40 kayitta {cok} sorgu (N+1)"
