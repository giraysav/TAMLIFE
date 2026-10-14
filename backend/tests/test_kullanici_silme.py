"""Panel kullanicisi silme: yalniz silme yetkilisi hesap (varsayilan `admin`); admin rolu verilmis baska kisi bile silemez."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import hesap, kullanicilar
from app.db import engine
from app.models import (
    AppUser,
    Customer,
    Demand,
    DemandLog,
    ProjectItem,
    Report,
    ReportDispatch,
    ScoreApprovalRequest,
    ScoringExclusion,
)
from app.session import Principal
from tests.conftest import login_ok

SIMDI = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


def _cikis(client, hdr):
    assert client.post("/api/v1/session/logout", headers=hdr).status_code == 200


def _kisi_ekle(**alanlar) -> int:
    with Session(engine()) as db:
        satir = AppUser(**alanlar)
        db.add(satir)
        db.commit()
        return satir.id


def _giris(client, monkeypatch, kullanici: str, rol: str) -> dict[str, str]:
    """Yerel dev hesabi olarak baska bir adla giris (test ortaminda TAMLIFE_LOCAL_* ile)."""
    monkeypatch.setenv("TAMLIFE_LOCAL_USER", kullanici)
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", rol)
    r = client.post("/api/v1/session/login", json={"username": kullanici, "password": "test-parola-1"})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": client.cookies.get("tamlife_csrf") or ""}


def _var(kimlik: int) -> bool:
    with Session(engine()) as db:
        return db.get(AppUser, kimlik) is not None


def _admin_kimligi() -> int:
    with Session(engine()) as db:
        return db.scalar(select(AppUser.id).where(AppUser.username == "admin"))


# --- yetki -------------------------------------------------------------------------------------------------------------
def test_silme_yalniz_silme_yetkilisi_hesapta_admin_rolu_yetmez(client, monkeypatch):
    hdr = login_ok(client)
    hedef = _kisi_ekle(username="ayse.demir", display_name="Ayşe Demir", role="TeamMember", is_ad_user=True)
    yonetici = _kisi_ekle(username="ikinci.admin", display_name="İkinci Admin", role="admin")  # AD kullanicisi degil: dev yerel girisi calissin

    # silme yetkilisi (varsayilan admin): arayuz bayragi acik, kendi satiri silinemez, digerleri silinebilir
    d = client.get("/api/v1/roller").json()["data"]
    assert d["can_delete_users"] is True and d["delete_account"] == "admin"
    bayrak = {u["username"]: u["deletable"] for u in d["users"]}
    assert bayrak == {"admin": False, "ayse.demir": True, "ikinci.admin": True}  # admin rolu verilmis kisi de silinebilir
    _cikis(client, hdr)

    # admin ROLUNDEKI baska bir hesap: Yonetim alanina girer ama silemez
    hdr2 = _giris(client, monkeypatch, "ikinci.admin", "admin")
    d = client.get("/api/v1/roller").json()["data"]
    assert d["can_delete_users"] is False and d["delete_account"] == "admin"
    assert not any(u["deletable"] for u in d["users"])
    r = client.delete(f"/api/v1/roller/kisiler/{hedef}", headers=hdr2)
    assert r.status_code == 403 and "yalnızca 'admin'" in r.json()["detail"]
    assert client.delete(f"/api/v1/roller/kisiler/{_admin_kimligi()}", headers=hdr2).status_code == 403  # silme yetkilisi hesap da korunur
    assert _var(hedef) and _var(_admin_kimligi())
    _cikis(client, hdr2)

    # admin olmayan rol: Yonetim alani kapali (router)
    hdr3 = _giris(client, monkeypatch, "mudur", "TeamMngr")
    assert client.get("/api/v1/roller").status_code == 403
    assert client.delete(f"/api/v1/roller/kisiler/{hedef}", headers=hdr3).status_code == 403
    assert _var(hedef)
    _cikis(client, hdr3)

    # silme yetkilisi: siler; ikinci istek 404; kendini silemez
    monkeypatch.setenv("TAMLIFE_LOCAL_USER", "admin")
    monkeypatch.setenv("TAMLIFE_LOCAL_ROLE", "admin")
    hdr = login_ok(client)
    assert client.delete(f"/api/v1/roller/kisiler/{hedef}").status_code == 403  # CSRF'siz
    r = client.delete(f"/api/v1/roller/kisiler/{hedef}", headers=hdr)
    assert r.status_code == 200 and r.json()["data"]["username"] == "ayse.demir"
    assert not _var(hedef) and _var(yonetici)
    assert client.delete(f"/api/v1/roller/kisiler/{hedef}", headers=hdr).status_code == 404
    r = client.delete(f"/api/v1/roller/kisiler/{_admin_kimligi()}", headers=hdr)
    assert r.status_code == 400 and "Kendi hesabınızı" in r.json()["detail"]
    assert client.delete(f"/api/v1/roller/kisiler/{yonetici}", headers=hdr).status_code == 200  # admin rolundeki kisiyi de silebilir
    d = client.get("/api/v1/roller").json()["data"]
    assert {u["username"] for u in d["users"]} == {"admin", "mudur"}  # silinenler listeden gitti; "mudur" giriste kayit acmisti


def test_silme_yetkilisi_ayardan_degisir_ve_bos_ayar_kimseye_vermez(client, monkeypatch):
    hdr = login_ok(client)
    hedef = _kisi_ekle(username="ayse.demir", display_name="Ayşe Demir", role="TeamMember")
    monkeypatch.setenv("KULLANICI_SILME_YETKILISI", "ikinci.admin")  # ayar buyuk/kucuk harfe duyarsiz karsilastirilir
    assert client.delete(f"/api/v1/roller/kisiler/{hedef}", headers=hdr).status_code == 403  # admin artik yetkili degil
    _cikis(client, hdr)
    hdr2 = _giris(client, monkeypatch, "Ikinci.Admin", "admin")
    assert client.get("/api/v1/roller").json()["data"]["can_delete_users"] is True
    assert client.delete(f"/api/v1/roller/kisiler/{hedef}", headers=hdr2).status_code == 200
    monkeypatch.setenv("KULLANICI_SILME_YETKILISI", "")
    assert not kullanicilar.silebilir_mi(Principal("Ikinci.Admin", "admin", True))
    assert not kullanicilar.silebilir_mi(Principal("", "admin", True))


def test_silebilir_mi_rol_admin_degilse_ad_tek_basina_yetmez(monkeypatch):
    monkeypatch.delenv("KULLANICI_SILME_YETKILISI", raising=False)
    assert kullanicilar.silebilir_mi(Principal("admin", "admin", True))
    assert kullanicilar.silebilir_mi(Principal("ADMIN", "admin", True))
    assert not kullanicilar.silebilir_mi(Principal("admin", "TeamMember", False))  # rolu dusurulmus 'admin' hesabi silemez
    assert not kullanicilar.silebilir_mi(Principal("ikinci.admin", "admin", True))


# --- bagli kayitlar ----------------------------------------------------------------------------------------------------
def test_silme_bagli_kayitlari_devreder_bosaltir_ve_siler(client, monkeypatch):
    hdr = login_ok(client)
    kapatilan: list[str] = []
    monkeypatch.setattr("app.rol_api.kullanici_oturumlarini_kapat", lambda ad: kapatilan.append(ad) or 1)
    admin_id = _admin_kimligi()
    hedef = _kisi_ekle(username="ayse.demir", display_name="Ayşe Demir", role="TeamMember", is_ad_user=True)
    diger = _kisi_ekle(username="mehmet.kaya", display_name="Mehmet Kaya", role="TeamMember", is_ad_user=True)
    with Session(engine()) as db:
        musteri = Customer(external_key="c1", name="Alfa A.Ş.", owner_id=hedef)
        baskasinin = Customer(external_key="c2", name="Beta Ltd.", owner_id=diger)
        db.add_all([musteri, baskasinin])
        db.flush()
        talep = Demand(title="T", current_state="a", expected_state="b", opened_by_id=hedef, assignee_id=hedef, opened_at=SIMDI)
        db.add(talep)
        db.flush()
        db.add_all(
            [
                DemandLog(demand_id=talep.id, field="durum", actor_id=hedef, at=SIMDI),
                ProjectItem(owner_id=hedef, category="proje", title="P", created_at=SIMDI, updated_at=SIMDI),
                ScoringExclusion(user_id=hedef),
                Report(report_month=9, report_year=2026, user_id=hedef, customer_id=musteri.id),
                ScoreApprovalRequest(customer_id=musteri.id, requested_by=hedef, resolved_by=hedef, status="approved"),
                ReportDispatch(customer_id=musteri.id, year=2026, month=9, sender_id=hedef, status="sent"),
                ProjectItem(owner_id=diger, category="proje", title="Baskasinin", created_at=SIMDI, updated_at=SIMDI),
                ScoringExclusion(user_id=diger),
            ]
        )
        db.commit()
        musteri_id, baskasinin_id, talep_id = musteri.id, baskasinin.id, talep.id

    r = client.delete(f"/api/v1/roller/kisiler/{hedef}", headers=hdr)
    assert r.status_code == 200, r.text
    ozet = r.json()["data"]
    # bos olabilen baglar: customer.owner_id, demand.assignee_id, demand_log.actor_id, score_approval_request.resolved_by, report_dispatch.sender_id
    # zorunlu baglar (devir): demand.opened_by_id, project_item.owner_id, report.user_id, score_approval_request.requested_by
    assert (ozet["bosaltilan"], ozet["devredilen"], ozet["silinen"]) == (5, 4, 1)
    assert kapatilan == ["ayse.demir"]  # acik oturumlari da kapanir

    with Session(engine()) as db:
        assert db.get(AppUser, hedef) is None
        m = db.get(Customer, musteri_id)
        assert m is not None and m.owner_id is None  # musteri silinmez, sorumlusuz kalir
        assert db.get(Customer, baskasinin_id).owner_id == diger
        t = db.get(Demand, talep_id)
        assert t.opened_by_id == admin_id and t.assignee_id is None  # talep kaydi korunur, silen hesaba devredilir
        assert db.scalar(select(DemandLog.actor_id).where(DemandLog.demand_id == talep_id)) is None
        assert db.scalar(select(ProjectItem.owner_id).where(ProjectItem.title == "P")) == admin_id
        assert db.scalar(select(Report.user_id).where(Report.customer_id == musteri_id)) == admin_id  # gonderim gecmisi (rapor) silinmez
        talep_kaydi = db.scalar(select(ScoreApprovalRequest).where(ScoreApprovalRequest.customer_id == musteri_id))
        assert talep_kaydi.requested_by == admin_id and talep_kaydi.resolved_by is None
        assert db.scalar(select(ReportDispatch.sender_id).where(ReportDispatch.customer_id == musteri_id)) is None
        assert db.scalar(select(func.count()).select_from(ScoringExclusion).where(ScoringExclusion.user_id == hedef)) == 0
        # baska kisinin kayitlarina dokunulmadi
        assert db.scalar(select(ProjectItem.owner_id).where(ProjectItem.title == "Baskasinin")) == diger
        assert db.scalar(select(func.count()).select_from(ScoringExclusion).where(ScoringExclusion.user_id == diger)) == 1


def test_silme_app_user_baglarinin_hepsini_kapsar():
    """Yeni bir tabloya app_user'a FK eklenirse silme onu da ele almali: sutunlar metadata'dan bulunur; burada yalniz bilinen listeyi kilitliyoruz."""
    import app.main  # noqa: F401  (tum modelleri yukler)
    from app.models import Base

    baglar = {
        (t.name, c.name)
        for t in Base.metadata.sorted_tables
        for c in t.columns
        if any(fk.column.table.name == "app_user" for fk in c.foreign_keys)
    }
    assert baglar == {
        ("customer", "owner_id"),
        ("demand", "opened_by_id"),
        ("demand", "assignee_id"),
        ("project_item", "owner_id"),
        ("scoring_exclusion", "user_id"),
        ("demand_log", "actor_id"),
        ("report", "user_id"),
        ("score_approval_request", "requested_by"),
        ("score_approval_request", "resolved_by"),
        ("report_dispatch", "sender_id"),
        ("revenue_benefit_person", "user_id"),
    }, "app_user'a yeni bir baglanti eklendi: kullanicilar.sil ona gore (bosalt / devret / sil) dogru davranmali; sonra bu listeyi guncelleyin"


# --- komut satiri: python -m app.hesap sil ... ------------------------------------------------------------------------------
def _eski_hesap_kaydi(musteri_adi="Gama A.Ş."):
    """Elle acilmis eski hesap (AD'siz) + ayni kisinin AD hesabi; eskisi bir musteriye sorumlu ve bir taleple atanmis."""
    eski = _kisi_ekle(username="tolga.avtan", display_name="Tolga Avtan", role="TeamMember", active=False)
    ad = _kisi_ekle(username="tctoavtan", display_name="TOLGA AVTAN", role="TeamMember", is_ad_user=True)
    with Session(engine()) as db:
        musteri = Customer(external_key="g1", name=musteri_adi, owner_id=eski)
        db.add(musteri)
        db.flush()
        db.add(Demand(title="T", current_state="a", expected_state="b", opened_by_id=eski, assignee_id=eski, opened_at=SIMDI))
        db.add(ScoringExclusion(user_id=eski))
        db.commit()
        return eski, ad, musteri.id


def test_hesap_sil_once_deneme_sonra_evet(client, capsys):
    login_ok(client)  # 'admin' kaydi (silme yetkilisi hesap) olussun
    eski, _, musteri_id = _eski_hesap_kaydi()
    assert hesap.main(["sil", "tolga.avtan"]) == 0
    cikti = capsys.readouterr().out
    assert "DENEME" in cikti and "devredilen=1" in cikti and "bosaltilan=2" in cikti and "silinen=1" in cikti
    assert _var(eski)  # deneme hicbir sey silmez
    with Session(engine()) as db:
        assert db.get(Customer, musteri_id).owner_id == eski

    assert hesap.main(["sil", "tolga.avtan", "--evet"]) == 0
    assert "SILINDI" in capsys.readouterr().out and not _var(eski)
    with Session(engine()) as db:
        assert db.get(Customer, musteri_id).owner_id is None  # devir hedefi verilmedi: sorumlusuz


def test_hesap_sil_devret_ayni_kisinin_ad_hesabina_aktarir(client, capsys):
    login_ok(client)
    eski, ad, musteri_id = _eski_hesap_kaydi()
    assert hesap.main(["sil", "tolga.avtan", "--devret", "tctoavtan", "--evet"]) == 0
    assert "-> tctoavtan" in capsys.readouterr().out
    with Session(engine()) as db:
        assert db.get(AppUser, eski) is None
        assert db.get(Customer, musteri_id).owner_id == ad  # musteri sorumlusu kaybolmadi
        t = db.scalar(select(Demand))
        assert (t.opened_by_id, t.assignee_id) == (ad, ad)
        assert db.scalar(select(func.count()).select_from(ScoringExclusion)) == 0


def test_hesap_sil_hata_varsa_hicbir_sey_silinmez(client, capsys):
    login_ok(client)
    eski, _, _ = _eski_hesap_kaydi()
    assert hesap.main(["sil", "tolga.avtan", "yok.kisi", "--evet"]) == 1  # biri yok: hepsi geri alinir
    assert "yok.kisi: kullanici yok" in capsys.readouterr().out and _var(eski)
    assert hesap.main(["sil", "admin", "--evet"]) == 1  # silme yetkilisi hesap kendini silemez
    assert hesap.main(["sil", "tolga.avtan", "--devret", "tolga.avtan", "--evet"]) == 1  # kendine devir olmaz
    assert hesap.main(["sil", "tolga.avtan", "--devret", "yok.hedef"]) == 1
    assert hesap.main(["sil"]) == 2 and hesap.main(["sil", "--evet"]) == 2
    assert _var(eski)


def test_hesap_sil_silme_yetkilisi_hesap_yoksa_calismaz(client, monkeypatch, capsys):
    eski, _, _ = _eski_hesap_kaydi()  # 'admin' kaydi yok (giris yapilmadi)
    assert hesap.main(["sil", "tolga.avtan", "--evet"]) == 1
    assert "KULLANICI_SILME_YETKILISI" in capsys.readouterr().out and _var(eski)
    monkeypatch.setenv("KULLANICI_SILME_YETKILISI", "")
    assert hesap.main(["sil", "tolga.avtan", "--evet"]) == 1 and _var(eski)
