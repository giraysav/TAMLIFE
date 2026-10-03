"""Prod MODULLER kopyasi. Tek katalog kaynagi."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class Modul:
    anahtar: str
    ad: str
    tur: str
    yalniz_admin: bool = False
    yalniz_yonetici: bool = False
    herkese_acik: bool = False
    in_nav: bool = True
    yetki: str | None = None


@dataclass(frozen=True)
class AnaSayfaKarti:
    anahtar: str
    ad: str
    i18n: str
    kart_id: str


MODULLER: tuple[Modul, ...] = (
    Modul('musteri', 'Müşteri Yönetimi', 'modul', yalniz_admin=False, herkese_acik=False, in_nav=True),
    Modul('takvim', 'İzin&Takvim Yönetimi', 'modul', yalniz_admin=False, herkese_acik=False, in_nav=True),
    Modul('takvim_ozet', 'TAM Takvim', 'kart', yalniz_admin=False, herkese_acik=False, in_nav=True),
    Modul('onedesk', 'OneDesk', 'modul', yalniz_admin=False, herkese_acik=False, in_nav=True),
    Modul('utilizasyon', 'TAM Utilizasyon', 'modul', yalniz_admin=True, herkese_acik=False, in_nav=False),
    Modul('roller', 'Rol Yönetimi', 'modul', yalniz_admin=True, herkese_acik=False, in_nav=False),
    Modul('talep', 'Geliştirme Talepleri', 'modul', yalniz_admin=False, herkese_acik=True, in_nav=False),
    Modul('ekip', 'TAM Özet', 'kart', yalniz_admin=False, herkese_acik=False, in_nav=True),
    Modul('rapor', 'Gönderilen Aylık Rapor', 'kart', yalniz_admin=False, herkese_acik=False, in_nav=True),
    Modul('proje', 'Takip Edilen Projeler', 'kart', yalniz_admin=False, herkese_acik=False, in_nav=True),
    Modul('tamsms', 'TAM SMS', 'kart', yalniz_admin=False, herkese_acik=False, in_nav=True),
    Modul('tamapn', 'TAM APN', 'kart', yalniz_admin=False, herkese_acik=False, in_nav=True),
    Modul('gelir_uretim', 'TAM GELIR&URETIM', 'kart', yalniz_admin=False, herkese_acik=False, in_nav=True),
    Modul('toptan', 'TAM Toptan', 'kart', yalniz_admin=False, herkese_acik=False, in_nav=True),
    Modul('sunum', 'TAM Sunum', 'kart', yalniz_admin=False, herkese_acik=False, in_nav=True),
    Modul('radar', 'Müşteri Radar', 'kart', yalniz_admin=False, herkese_acik=False, in_nav=True),
    Modul('baglantili', 'Bağlantılı Araçlar', 'kart', yalniz_admin=False, herkese_acik=False, in_nav=True),
    Modul('topoloji', 'TopoMaker', 'modul', in_nav=False, yetki='musteri'),
)
MODUL = {m.anahtar: m for m in MODULLER}
PROD_MODUL_ANAHTARLARI = frozenset(m.anahtar for m in MODULLER if m.anahtar != 'topoloji')

ANA_SAYFA_KARTLARI: tuple[AnaSayfaKarti, ...] = (
    AnaSayfaKarti('ekip', 'TAM Özet', 'card.ekip.title', 'dash-card-ekip'),
    AnaSayfaKarti('takvim_ozet', 'TAM Takvim', 'card.takvim.title', 'dash-card-takvim'),
    AnaSayfaKarti('sunum', 'TAM Sunum', 'card.sunum.title', 'dash-card-sunum'),
    AnaSayfaKarti('radar', 'Müşteri Radar', 'card.radar.title', 'dash-card-radar'),
    AnaSayfaKarti('musteri', 'Müşteri Yönetimi', 'musteri.tamPortfoy', 'dash-card-modul-portfoy'),
    AnaSayfaKarti('rapor', 'Gönderilen Aylık Rapor', 'card.rapor.title', 'dash-card-rapor'),
    AnaSayfaKarti('proje', 'Takip Edilen Projeler', 'card.proje.title', 'dash-card-proje'),
    AnaSayfaKarti('onedesk', 'OneDesk', 'card.ats.title', 'dash-card-onedesk'),
    AnaSayfaKarti('toptan', 'TAM Toptan', 'card.toptan.title', 'dash-card-toptan'),
    AnaSayfaKarti('tamsms', 'TAM SMS', 'card.tamSms.title', 'dash-card-tamsms'),
    AnaSayfaKarti('tamapn', 'TAM APN', 'card.tamApn.title', 'dash-card-tamapn'),
    AnaSayfaKarti('gelir_uretim', 'TAM GELIR&URETIM', 'card.gelirUretim.title', 'dash-card-gelir-uretim'),
    AnaSayfaKarti('takvim', 'İzin&Takvim Yönetimi', 'tab.takvim', 'dash-card-modul-takvim'),
    AnaSayfaKarti('baglantili', 'Bağlantılı Araçlar', 'card.placeholder.title', 'dash-card-baglantili'),
)

BOS_KARTLAR = frozenset({'gelir_uretim', 'toptan'})


def get(anahtar: str) -> Modul:
    return MODUL[anahtar]



def setup(app) -> None:
    """Modul kapisi. Is kurali yok."""
    from fastapi import APIRouter

    from app.core.authz import erisebilir
    from app.core.session import current_user

    router = APIRouter()

    @router.get("/modules/{anahtar}")
    def open_module(anahtar: str, request: Request) -> dict:
        user = current_user(request)
        if user is None:
            raise HTTPException(status_code=401, detail="Oturum gerekli")
        try:
            modul = get(anahtar)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Modul yok") from exc
        if not erisebilir(user, modul, get):
            raise HTTPException(status_code=403, detail="Yetki yok")
        return {"status": "success", "data": {"module": anahtar}}

    app.include_router(router, prefix="/api/v1")
