# 10 ? Iskelet onerisi

Bu sayfadaki agac ve kod **yalniz metindir**. Diskte klasor acilmaz, `backend/` ve `ekran-react/` degismez. Is kurali yok: fonksiyonlar `NotImplementedError` veya bos liste doner.

## Kararlar

- Dosya adlari: `models.py`, `schemas.py`, `service.py`, `routes.py`, `summary.py`.
- Ornek modul: `ekip` (prod anahtar). v3.5 `modul.id=ozet` kullanilmaz.
- `topoloji` klasoru acilir, router `main.py` listesine yorum satiri olarak girer; dahil etme karari `00`.
- import-linter konfigurasyonu burada tam taslaktir. `03` ozetler.

## Acik sorular

- Ilk acilacak modul `ekip` mi `musteri` mi? `OZET` P0'da ikisini de acmaz; once `core` + `catalog`. `ekip` ornegi kopya sablonudur.
- `mail_fake.py` adi `04` onerisidir; bu iskelette dosya gosterilmez (P2).

## Agac (olusturulmayacak)

```
backend/app/__init__.py
backend/app/main.py
backend/app/core/__init__.py
backend/app/core/config.py
backend/app/core/errors.py
backend/app/core/session.py
backend/app/core/authz.py
backend/app/core/audit.py
backend/app/core/rate_limit.py
backend/app/data/__init__.py
backend/app/data/base.py
backend/app/data/gateway.py
backend/app/data/migrate.py
backend/app/adapters/__init__.py
backend/app/adapters/ad_fake.py
backend/app/adapters/oracle_fake.py
backend/app/modules/__init__.py
backend/app/modules/catalog.py
backend/app/modules/contracts.py
backend/app/modules/ekip/__init__.py
backend/app/modules/ekip/models.py
backend/app/modules/ekip/schemas.py
backend/app/modules/ekip/service.py
backend/app/modules/ekip/routes.py
backend/app/modules/ekip/summary.py
```

Diger modul klasorleri ayni bes dosyayi bos govdeyle kopyalar: `musteri`, `takvim`, `onedesk`, `utilizasyon`, `roller`, `talep`, `rapor`, `proje`, `tamsms`, `tamapn`, `gelir_uretim`, `toptan`, `sunum`, `radar`, `baglantili`, `topoloji`. `takvim_ozet` ayri klasor degildir; `takvim/summary.py` icinde ikinci fonksiyon durur (sahip karari acikken yazma yok).

## Ornek: ekip

```python
# backend/app/modules/ekip/__init__.py
```

```python
# backend/app/modules/ekip/models.py
from sqlalchemy.orm import Mapped, mapped_column
from app.data.base import Base

class TeamNote(Base):
    __tablename__ = "team_note"
    id: Mapped[int] = mapped_column(primary_key=True)
    # kolonlar faz 2'de. Prod ekip tablosu dogrulanmadi; users sahibi core.
```

```python
# backend/app/modules/ekip/schemas.py
from pydantic import BaseModel

class TeamCard(BaseModel):
    module: str = "ekip"
```

```python
# backend/app/modules/ekip/summary.py
from app.modules.ekip.schemas import TeamCard

def card(user_id: int) -> TeamCard:
    raise NotImplementedError
```

```python
# backend/app/modules/ekip/service.py
from app.modules.ekip.summary import card

def load_card(user_id: int):
    return card(user_id)
```

```python
# backend/app/modules/ekip/routes.py
from fastapi import APIRouter

router = APIRouter(prefix="/teams", tags=["ekip"])

@router.get("")
def list_cards() -> dict:
    return {"status": "success", "data": {"items": [], "page": 1, "per_page": 20, "total": 0}}
```

`GET /api/v1/teams` sablon yoldur. Prod karsiligi `GET /api/tam_personal_summary/<user_id>` (`07`). Sablon, o yolun yerine gectigi anlamina gelmez; faz 2'de ya o isim ya da bu isim secilir (`00`).

## main.py (baglama)

```python
# backend/app/main.py
from fastapi import FastAPI
from app.modules.ekip.routes import router as ekip_router

def create_app() -> FastAPI:
    app = FastAPI(title="TAMLIFE", version="3.5")
    app.include_router(ekip_router, prefix="/api/v1")
    return app
```

## import-linter

Yasak: bir modul, baska modulun `service` veya `models` modulunu import eder. `summary`, `contracts`, `catalog`, `core`, `data`, `adapters` yasak degil. `core` ve `adapters` ve `data`, `modules` import etmez (ayri sozlesme).

```ini
[importlinter]
root_package = app

[importlinter:contract:no-cross-service]
name = No cross-module service or models import
type = forbidden
source_modules =
    app.modules.musteri
    app.modules.takvim
    app.modules.onedesk
    app.modules.utilizasyon
    app.modules.roller
    app.modules.talep
    app.modules.ekip
    app.modules.rapor
    app.modules.proje
    app.modules.tamsms
    app.modules.tamapn
    app.modules.gelir_uretim
    app.modules.toptan
    app.modules.sunum
    app.modules.radar
    app.modules.baglantili
    app.modules.topoloji
forbidden_modules =
    app.modules.musteri.service
    app.modules.musteri.models
    app.modules.takvim.service
    app.modules.takvim.models
    app.modules.onedesk.service
    app.modules.onedesk.models
    app.modules.utilizasyon.service
    app.modules.utilizasyon.models
    app.modules.roller.service
    app.modules.roller.models
    app.modules.talep.service
    app.modules.talep.models
    app.modules.ekip.service
    app.modules.ekip.models
    app.modules.rapor.service
    app.modules.rapor.models
    app.modules.proje.service
    app.modules.proje.models
    app.modules.tamsms.service
    app.modules.tamsms.models
    app.modules.tamapn.service
    app.modules.tamapn.models
    app.modules.gelir_uretim.service
    app.modules.gelir_uretim.models
    app.modules.toptan.service
    app.modules.toptan.models
    app.modules.sunum.service
    app.modules.sunum.models
    app.modules.radar.service
    app.modules.radar.models
    app.modules.baglantili.service
    app.modules.baglantili.models
    app.modules.topoloji.service
    app.modules.topoloji.models

[importlinter:contract:core-independent]
name = Core data adapters do not import modules
type = forbidden
source_modules =
    app.core
    app.data
    app.adapters
forbidden_modules =
    app.modules
```

Bilinen sinir: `forbidden` sozlesmesi kendi modulunun `service` importunu da yasaklayabilir (kaynak `app.modules.ekip`, yasak `app.modules.ekip.service`). Arac bunu ihlal sayarsa sozlesme `independence` tipine cevrilir; her modul `(ekip, ekip.summary)` haric digerlerine bagimsiz olur. Bu ince ayar faz 0 cikis testinde gorulur, belge uydurma kural eklemez.

`routes.py` baska modul `summary` import edebilir. `service.py` yalniz kendi `models` ve baskasinin `summary`. Bunu linter tam gormezse pytest `test_import_boundaries.py` `ast` ile ayni listeyi tarar (faz 0 isi, govde yok).
