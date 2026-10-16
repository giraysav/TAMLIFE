"""Runtime settings. Production key names, empty defaults, no stored secret."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.external import source_key_names

AD_LDAP_KEYS: tuple[str, ...] = (
    "AD_ENABLED",
    "AD_SERVER",
    "AD_DOMAIN",
    "AD_USE_SSL",
    "AD_CA_CERT_FILE",
    "AD_IZINLI_ALANLAR",
    "AD_ALAN_KONTROLU",
    "AD_KIMLIK_KONTROLU",
    "AD_IZINLI_GRUPLAR",
    "AD_ARAMA_KOKU",
    "AD_OTOMATIK_AC",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TAMLIFE_",
        env_file=None,
        extra="ignore",
    )

    env: str = "dev"
    database_url: str = "postgresql+psycopg://localhost:5432/tamlife"
    sqlite_izin: bool = False  # dev/test disinda SQLite icin acik onay (PostgreSQL gelene kadar)
    kullanici_db_dizini: str = ""  # kullanici basina SQLite dosyalari; bos = panel DB'sinin yaninda kullanicilar/

    cookie_name: str = "tamlife_session"
    cookie_secure: bool | None = None  # bos: dev disinda otomatik true
    session_idle_minutes: int = 30
    session_max_hours: int = 12
    login_max_attempts: int = 5
    login_window_seconds: int = 300
    login_lockout_seconds: int = 300
    login_ip_carpani: int = 20  # ayni IP icin kilit esigi = login_max_attempts x bu; Citrix gibi ortak IP herkesi kilitlemesin
    allowed_origins: str = ""  # virgulle ayrilmis ek Origin listesi
    allowed_hosts: str = "127.0.0.1,localhost,testserver"
    trusted_proxies: str = ""  # virgulle ayrilmis proxy IP'leri; X-Forwarded-For yalniz bunlardan kabul

    base_path: str = "/"  # cerez yolu; arayuz bir alt yolda sunulacaksa (orn. "/panel") oraya kisitlanir
    static_dir: str = ""  # derlenmis arayuz (ekran-react/dist); bos = yok, yalniz API

    # Yonetim: dosya gunlugu ve yedek klasorleri. Bos = backend/var/logs ve veritabani klasorunun yanindaki yedek/.
    # Yedek, veri ile AYNI diskte durmasin diye (tek disk ikisini birlikte kaybeder) uretimde ayri bir yola ayarlanmali.
    log_dir: str = ""
    backup_dir: str = ""
    backup_keep: int = 30
    # Tampon (Veri Girisi) sinirlari.
    ingest_max_rows: int = 300_000
    ingest_max_mb: int = 20
    ingest_keep_batches: int = 3  # kaynak basina saklanan hazir parti

    # Panel session only. Not a directory bind.
    local_user: str = ""
    local_password: str = Field(default="", repr=False)
    local_role: str = "TeamMember"

    # AD/LDAPS (eski servisle ayni AD_* adlari; degerler backend/.env). Bind kullanicinin kendi hesabiyla: servis hesabi ve sir yok.
    ad_enabled: str = Field(default="false", validation_alias="AD_ENABLED")
    ad_server: str = Field(default="", validation_alias="AD_SERVER")  # ldaps://dc.alan:636
    ad_domain: str = Field(default="", validation_alias="AD_DOMAIN")  # UPN alani: kisa ad -> kisa@AD_DOMAIN
    ad_use_ssl: str = Field(default="true", validation_alias="AD_USE_SSL")
    ad_ca_cert_file: str = Field(default="", validation_alias="AD_CA_CERT_FILE")  # kurum ara+kok CA (.pem); bos = Windows kok deposu
    ad_izinli_alanlar: str = Field(default="", validation_alias="AD_IZINLI_ALANLAR")  # virgullu; AD_DOMAIN her zaman dahil
    ad_alan_kontrolu: str = Field(default="zorunlu", validation_alias="AD_ALAN_KONTROLU")  # izle | zorunlu
    ad_kimlik_kontrolu: str = Field(default="izle", validation_alias="AD_KIMLIK_KONTROLU")  # izle | zorunlu (Who-Am-I eslesmesi)
    ad_izinli_gruplar: str = Field(default="", validation_alias="AD_IZINLI_GRUPLAR")  # noktali virgulle ayrilmis grup DN; doluysa AD_ARAMA_KOKU zorunlu
    ad_arama_koku: str = Field(default="", validation_alias="AD_ARAMA_KOKU")
    ad_otomatik_ac: str = Field(default="true", validation_alias="AD_OTOMATIK_AC")  # AD'de dogrulanan, panelde olmayan kisi TeamMember acilir
    # Panel kullanicisini SILEBILEN tek hesap (kullanici adi). Admin rolu verilmis baska kisi bile silemez. Sir degildir.
    kullanici_silme_yetkilisi: str = Field(default="admin", validation_alias="KULLANICI_SILME_YETKILISI")

    @property
    def cookie_secure_effective(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.env not in {"dev", "test"}

    @property
    def allowed_origins_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @property
    def trusted_proxies_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_proxies.split(",") if item.strip()]

    @property
    def cookie_path(self) -> str:
        yol = "/" + self.base_path.strip().strip("/")
        return yol if yol != "/" else "/"

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]

    def present(self, key: str) -> bool:
        allowed = set(AD_LDAP_KEYS) | set(source_key_names())
        if key not in allowed:
            raise KeyError(key)
        return bool(os.environ.get(key, "").strip())


ENV_DOSYASI = Path(__file__).resolve().parents[1] / ".env"  # backend/.env (git disi; sir burada durur, kodda degil)


def env_dosyasi_yukle(yol: Path | None = None) -> None:
    """backend/.env (ya da TAMLIFE_ENV_DOSYASI) satirlarini ortama ekler; var olan ortam degiskenini EZMEZ. Degerler hic yazdirilmaz.

    Testte (TAMLIFE_ENV=test) yol verilmedikce okunmaz: yerel .env test sonucunu degistirmesin.
    """
    if yol is None and os.environ.get("TAMLIFE_ENV") == "test":
        return
    dosya = Path(yol or os.environ.get("TAMLIFE_ENV_DOSYASI") or ENV_DOSYASI)
    if not dosya.is_file():
        return
    for satir in dosya.read_text(encoding="utf-8-sig").splitlines():
        satir = satir.strip()
        if not satir or satir.startswith("#") or "=" not in satir:
            continue
        ad, deger = (p.strip() for p in satir.split("=", 1))
        if len(deger) >= 2 and deger[0] == deger[-1] and deger[0] in "\"'":
            deger = deger[1:-1]
        os.environ.setdefault(ad, deger)


_AYAR_ONBELLEGI: tuple[tuple[str | None, ...], Settings] | None = None
_AYAR_ADLARI: tuple[str, ...] | None = None


def _ayar_adlari() -> tuple[str, ...]:
    """Settings'in okudugu ortam degiskeni adlari (TAMLIFE_<alan> ya da validation_alias)."""
    onek = Settings.model_config.get("env_prefix", "")
    return tuple(
        (alan.validation_alias if isinstance(alan.validation_alias, str) else f"{onek}{ad}").upper()
        for ad, alan in Settings.model_fields.items()
    )


def get_settings() -> Settings:
    """Ayarlar ortamdan okunur; Settings'in okudugu degiskenler degismedikce ayni nesne doner. Eskiden her cagri pydantic ile
    ~1 ms yeniden kuruluyordu (istek basina onlarca cagri; oturum budamasi her oturum icin bir kez, giris sinirlayici her
    denemede). Ortam degisince (test monkeypatch, env_dosyasi_yukle) parmak izi degisir ve yeniden kurulur.
    Donen nesneyi degistirmeyin (paylasilir)."""
    global _AYAR_ONBELLEGI, _AYAR_ADLARI
    if _AYAR_ADLARI is None:
        _AYAR_ADLARI = _ayar_adlari()
    iz = tuple(map(os.environ.get, _AYAR_ADLARI))
    onbellek = _AYAR_ONBELLEGI
    if onbellek is not None and onbellek[0] == iz:
        return onbellek[1]
    ayar = Settings()
    _AYAR_ONBELLEGI = (iz, ayar)
    return ayar

