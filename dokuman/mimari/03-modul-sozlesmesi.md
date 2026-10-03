# 03 ? Modul sozlesmesi

## Kararlar

- Her is modulu su bes dosyaya sahiptir: `models.py`, `schemas.py`, `service.py`, `routes.py`, `summary.py`, arti bos birakilabilir `__init__.py`.
- Modul kendi tablolarinin sahibi tek yerdir. Baska modulun tablosuna `SELECT`/`INSERT`/`UPDATE`/`DELETE` yok. Ortak okuma `summary.py` donus tipidir.
- Katalog bayraklari tek dosyada: `app/modules/catalog.py`. Prod'da bu rol `backend/app/moduller.py` `MODULLER` + `kutucuklar/registry.py` `KUTU_TANIMLARI`. v3.5'te ayni listenin bir kopyasi `backend/api.py` sozlukleri ve `veri/ortak.db` `modul` tablosudur. Hedef tek kaynak katalogdur; uc kopya kalkar.
- `import-linter` ihlali derleme kapisidir. Kural metni asagida taslaktir; `pyproject.toml` bugun yok, diskte konmaz (`10`).

## Acik sorular

- `takvim` ile `takvim_ozet` prod saglik tablosunda ikisi de `calendar_records` (`moduller.py` `MODUL_TABLOLARI`). Iki sahip olamaz. Oneri: sahip `takvim`, `takvim_ozet` yalniz `summary`. Karar acik.
- `topoloji` prod `MODULLER` icinde yok, registry'de var (`dash_card_id` None). Modul mu adapt?r mu ? `04` ve `00`.
- `roller` prod katalogda var (`yalniz_admin=True`), v3.5 `modul` tablosunda yok (15 satir sayildi, `roller` yok).
- `talep` prod'da `herkese_acik=True`, v3.5 `modul` tablosunda yok.
- `yalniz_yonetici` alani `Modul` sinifinda var; `MODULLER` satirlarinin hicbiri `yalniz_yonetici=True` gecmez (dogrulandi).

## Zorunlu dosyalar

| Dosya | Disari verir | Yasak |
|---|---|---|
| `models.py` | SQLAlchemy 2 `Mapped` modeller, yalniz bu modulun tablolari | Flask/FastAPI importu, baska modul modeli |
| `schemas.py` | Pydantic v2 DTO | ORM nesnesini response olarak sizdirmak, gizli alan (`pin_code`, `totp_secret`) |
| `service.py` | Is fonksiyonlari, kendi `Session` kullanimi | `request`, status kodu, baska modul `models` |
| `routes.py` | `APIRouter`, bagimlilik: oturum + `catalog` kapisi | Dogrudan SQL, baska modul `service` (ozet hari?) |
| `summary.py` | Saf fonksiyon: kimlik + filtre girer, kucuk DTO cikar | Yazma, sayfalama disi ham dump, baska modul cagirma |

`summary` imzasi `contracts.py` icinde tekrar edilir. Uygulama `summary.py`dedir. Cagiran, `contracts` tipini kullanir; `import app.modules.ekip.service` yasaktir, `import app.modules.ekip.summary` serbesttir.

Ornek sozlesme (is kurali yok):

```python
# app/modules/contracts.py
from typing import Protocol

class TeamSummary(Protocol):
    def card(self, user_id: int) -> dict: ...
```

Donus sozlugu anahtarlari modul acilinca dondurulur. Bu belge anahtar uydurmaz. Prod `kutucuklar/registry.py` `ozet` alani cogu kutuda `"ozet.kart_ozeti"` dir. Fonksiyon govdesi bu taramada tek tek acilmadi; varlik klasor listesinden dogrulandi (`ekip/ozet.py` 1243 bayt, vb.).

## Cagri yonu

Izin verilen:

1. `routes` -> kendi `service` -> kendi `models`.
2. `routes` -> `core.authz` ve `catalog`.
3. `service` -> baska modulun `summary` (okuma).
4. `service` -> `adapters` yalniz `onedesk`, `utilizasyon`, `musteri` icin sahte kaynak. Hangi modulun hangi adapt?ru cagirdigi prod blueprint satirina gore `04`tedir; yeni cagri eklenmez.
5. Her `service` yazmasi `core.audit` cagirabilir. Audit tablosuna modul SQL yazmaz.

Yasak: dongusel ozet. `ekip.summary` diger ozetleri okur (prod TAM Ozet karti personel secince alt kutulari gosterir: `EKIP_OZET_ALANLARI`). Alt modulun ozeti `ekip.summary` cagiramaz.

## Olay / ozet

Yazma sonrasi ikinci modulun tablosunu guncellemek yok. Yerine:

- Yazan `service` kendi tablosunu commit eder.
- Dashbord `GET` aninda her gorunur modulun `summary` fonksiyonunu cagirir. Biri patlarsa digerleri doner. Prod `ozet_hepsi` ayni kalibi kurar: hata listesi `_hatalar`, o kutu `visible: False`.
- `registry.register_all` prod'da kutuyu import eder; incelenen `__init__.py` dosyalarinda `register` `return None` (no-op). Hedefte `register` yok; router `main.py` icinde acik listeyle eklenir.

## Katalog bayraklari (prod, dogrulandi)

Kaynak: `backend/app/moduller.py` sat?r 45-71 ve `kutucuklar/registry.py`.

| Anahtar | Tur | Bayrak | Registry id | Registry durum | Ana sayfa karti |
|---|---|---|---|---|---|
| musteri | modul | ? | portfoy | aktif | dash-card-modul-portfoy |
| takvim | modul | ? | takvim (ek giris mgmtTakvimModal) | aktif | dash-card-modul-takvim |
| takvim_ozet | kart | ? | takvim ile ayni klasor | aktif | dash-card-takvim |
| onedesk | modul | ? | onedesk | aktif | dash-card-onedesk |
| utilizasyon | modul | yalniz_admin | utilizasyon | aktif | dash_card_id None |
| roller | modul | yalniz_admin | klasor yok | ? | ANA_SAYFA listesinde yok |
| talep | modul | herkese_acik | talep | aktif | ANA_SAYFA listesinde yok (yorum: kullanici menusu) |
| ekip | kart | ? | ekip | aktif | dash-card-ekip |
| rapor | kart | ? | rapor | aktif | dash-card-rapor |
| proje | kart | ? | proje | aktif | dash-card-proje |
| tamsms | kart | ? | ictapn | aktif | dash-card-tamsms |
| tamapn | kart | ? | ayri klasor yok | ? | dash-card-tamapn |
| gelir_uretim | kart | ? | klasor yok | ? | dash-card-gelir-uretim |
| toptan | kart | ? | klasor yok | ? | dash-card-toptan |
| sunum | kart | ? | sunum | aktif | dash-card-sunum |
| radar | kart | ? | radar | aktif | dash-card-radar |
| baglantili | kart | ? | baglantili | stub | dash-card-baglantili |
| topoloji | katalogda yok | ? | topoloji | aktif | dash_card_id None |

v3.5 `ortak.db` `modul` (15 satir) anahtarlari: `ozet`, `takvim_ozet`, `sunum`, `radar`, `musteri`, `rapor`, `proje`, `onedesk`, `toptan`, `tamsms`, `tamapn`, `gelir_uretim`, `takvim`, `baglantili`, `utilizasyon`. `yalniz_admin=1` yalniz `utilizasyon`. `roller` ve `talep` bu tabloda yok. `id` alani prod anahtariyla ayni degil: ornek `id=ozet` / `anahtar=ozet` (prod anahtar `ekip`), `id=sms` / `anahtar=tamsms`, `id=izin` / `anahtar=takvim`.

Hedef katalog prod anahtarini kullanir (`ekip`, `tamsms`). v3.5 `id` alani yalniz mevcut React anahtarlarina eslenir; yeni API yolu o `id` ile acilmaz.

## import-linter taslagi

Sozlesme: `modules` alt paketleri birbirinin `service`/`models`/`routes` sembollerini import edemez. `summary` ve `contracts` serbest. `core` ve `adapters` hicbir `modules.*` import etmez (yon: modul -> adapt?r).

```ini
[importlinter]
root_package = app

[importlinter:contract:modules-do-not-import-siblings]
name = Modules stay behind summary
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
    app.modules.ekip.service
    app.modules.ekip.models
allow_indirect_imports = False
```

Tam yasak listesi her modulun `service` ve `models` satirini icerir; yukaridaki kisaltma ornektir, `10` icindeki blok tam listeyi tasir. `catalog.py` herkese aciktir. Test paketinin ic importu `test` sozlesmesiyle ayri tutulur; test, modulu sinamak icin `service` import edebilir, baska modulu onun `models`i uzerinden degil.
