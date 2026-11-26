"""PostgreSQL schema for the panel. No customer seed and no secret columns."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app import musteri_alani


class Base(DeclarativeBase):
    """Ortak panel DB'si (Alembic)."""


class KullaniciBase(DeclarativeBase):
    """Kullanici basina SQLite dosyasi (app.db.kullanici_oturumu): kisinin kendi takvim ve gelir kayitlari."""


TABLE_OWNER = {
    "app_user": "core",
    "audit_event": "core",
    "customer": "musteri",
    "customer_team": "musteri",
    "matrix_config": "musteri",
    "report": "rapor",
    "report_draft": "rapor",
    "report_dispatch": "rapor",
    "report_recipient": "rapor",
    "customer_ci": "musteri",
    "customer_ci_flag": "musteri",
    "util_source_summary": "skor",
    "report_cmdb": "rapor",
    "report_circuit": "rapor",
    "report_circuit_data": "rapor",
    "calendar_day": "takvim",
    "project_item": "proje",
    "project_action": "proje",
    "project_customer_work": "proje",
    "onedesk_record": "onedesk",
    "util_criteria_set": "utilizasyon",
    "score_detail": "utilizasyon",
    "score_history": "utilizasyon",
    "score_approval_request": "utilizasyon",
    "scoring_exclusion": "utilizasyon",
    "affiliate_final_flag": "utilizasyon",
    "urun_tutar_ozet": "utilizasyon",
    "demand": "talep",
    "demand_log": "talep",
    "user_notification": "core",  # kisiye ozel panel bildirimi (ilk ureten: talep)
    "sms_revenue": "tamsms",
    "apn_revenue": "tamapn",
    "apn_work": "tamapn",
    "presentation": "sunum",
    "revenue_benefit": "gelir_uretim",
    "revenue_benefit_person": "gelir_uretim",
    "role_view": "roller",
    "app_setting": "core",
    "ingest_batch": "ingest",
    "ingest_block": "ingest",
    "distribution_rule": "ingest",
    "distribution_log": "ingest",
    "customer_import_run": "ingest",
    "file_import_run": "ingest",
    "source_catalog": "ingest",
    "source_catalog_object": "ingest",
    "fault_event": "yonetim",
}

# Source key names live in app.external. No DSN value is stored here.


class AppUser(Base):
    __tablename__ = "app_user"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[str] = mapped_column(String(40))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # panele son giris; TAM Takvim listesi
    is_ad_user: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())  # giris yalniz AD'den; yerel parolaya dusmez
    ad_domain: Mapped[str] = mapped_column(String(120), default="", server_default="")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)  # yalniz yerel acil hesap (scrypt); AD kullanicisinda bos
    # Profil (kisinin kendi duzenledigi alanlar; kullanici adi AD'den gelir, degistirilemez). Bos ad/soyad display_name'den turetilir.
    first_name: Mapped[str] = mapped_column(String(100), default="", server_default="")
    last_name: Mapped[str] = mapped_column(String(100), default="", server_default="")
    phone: Mapped[str] = mapped_column(String(40), default="", server_default="")
    company: Mapped[str] = mapped_column(String(200), default="", server_default="")
    signature_html: Mapped[str] = mapped_column(Text, default="", server_default="")  # serbest e-posta imzasi (app.imza ile temizlenmis HTML)
    # E-posta imzasi kipi (2026-10-26): "" = imza yok (iletide hazir bant) | "kurumsal" (app.imza.kurumsal: kurumsal tasarim, alanlar
    # asagida + profil) | "serbest" (signature_html). Kurumsal imza her gonderimde guncel profilden yeniden uretilir.
    signature_mode: Mapped[str] = mapped_column(String(20), default="", server_default="")
    title: Mapped[str] = mapped_column(String(120), default="", server_default="")  # imza: gorev / unvan
    department: Mapped[str] = mapped_column(String(120), default="", server_default="")  # imza: birim
    landline: Mapped[str] = mapped_column(String(40), default="", server_default="")  # imza: sabit telefon
    email: Mapped[str] = mapped_column(String(200), default="", server_default="")  # imza: e-posta (AD'den gelmez; kisi yazar)
    website: Mapped[str] = mapped_column(String(200), default="", server_default="")
    permissions: Mapped[list | None] = mapped_column(JSON, nullable=True)  # kisiye verilen ek yetkiler (rolgorunum.YETKILER); role eklenir
    # Sahibi oldugu modul (katalog anahtari: tamsms, tamapn, toptan, baglantili); dolu ise musteri sorumlusu (TAM) secilemez
    module_owner: Mapped[str] = mapped_column(String(40), default="", server_default="")


class AuditEvent(Base):
    __tablename__ = "audit_event"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(80))
    outcome: Mapped[str] = mapped_column(String(40))
    module_key: Mapped[str] = mapped_column(String(80), default="")
    detail: Mapped[str] = mapped_column(String(500), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")  # 2026-11-26: giris olaylarinda istemci IP'si (security.client_ip)


class Customer(Base):
    __tablename__ = "customer"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_key: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    segment: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(40), default="")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)  # sorumlu TAM
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"), nullable=True)  # bos = cati
    # Kartin modulu (musteri | toptan | baglantili; app.musteri_alani): sorgular istegin alanina suzulur, yeni kart o alanda acilir
    modul: Mapped[str] = mapped_column(String(20), default=musteri_alani.secili, server_default="musteri", index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)  # final skor, yalniz cati
    # --- Musteri karti (uretim customers). Tutarlar uretimdeki gibi metin: "0,00 TL" bicimi
    customer_no: Mapped[str | None] = mapped_column(String(200), nullable=True)  # birden cok numara virgulle
    ncst: Mapped[str] = mapped_column(String(50), default="")  # uretimde pinned_entries JSON icindeydi
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    inventory_count: Mapped[int] = mapped_column(Integer, default=0)
    ft_volume: Mapped[str] = mapped_column(String(100), default="0,00 ₺")
    tam_ft: Mapped[str] = mapped_column(String(100), default="0,00 ₺")
    alarm_count: Mapped[int] = mapped_column(Integer, default=0)
    complaint_count: Mapped[int] = mapped_column(Integer, default=0)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    alarm_closed_count: Mapped[int] = mapped_column(Integer, default=0)
    complaint_closed_count: Mapped[int] = mapped_column(Integer, default=0)
    request_closed_count: Mapped[int] = mapped_column(Integer, default=0)
    report_count: Mapped[int] = mapped_column(Integer, default=0)
    separate_report: Mapped[bool] = mapped_column(Boolean, default=False)  # istirak icin ayri aylik rapor
    report_exempt: Mapped[bool] = mapped_column(Boolean, default=False)  # aylik raporu atilmayan musteri: bekleyen sayimina girmez


class CustomerTeam(Base):
    """Ekip ve iletisim (uretim destech_contacts). Uretimde unvan METNIYLE bagliydi; burada musteri kimligine."""

    __tablename__ = "customer_team"
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), primary_key=True)
    sales_manager: Mapped[str | None] = mapped_column(String(100), nullable=True)
    presales_manager: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tac_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tac_gsm: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tac_email: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sol_kmt_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sol_kmt_gsm: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sol_kmt_email: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mobil_kmt_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mobil_kmt_gsm: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mobil_kmt_email: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mobil_kmt_detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class MatrixConfig(Base):
    """Destech / CI / RACI matrisleri (Excel'den): baslik ve satirlar; musteriye unvan eslesmesiyle baglanir."""

    __tablename__ = "matrix_config"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    headers: Mapped[list] = mapped_column(JSON, default=list)
    rows: Mapped[list] = mapped_column(JSON, default=list)
    updated_by: Mapped[str] = mapped_column(String(100), default="")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class Report(Base):
    """Aylik rapor (uretim reports). Alan adlari uretimle birebir; anlamlari uretim kodunda yorumlanmadi."""

    __tablename__ = "report"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    report_month: Mapped[int] = mapped_column(Integer)
    report_year: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"))
    sun_success_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cloud_issue_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    flag_escalation_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggestions_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    bubble_report_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    excel_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_edited_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    flag_count: Mapped[int] = mapped_column(Integer, default=0)
    is_submitted: Mapped[bool] = mapped_column(Boolean, default=False)


class ReportDraft(Base):
    """Aylik rapor taslagi (uretim analiz.db rapor_taslak): musteri + yil + ay basina tek taslak."""

    __tablename__ = "report_draft"
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[int] = mapped_column(Integer, primary_key=True)
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_by: Mapped[str] = mapped_column(String(120), default="")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReportDispatch(Base):
    """Gonderim kaydi (uretim rapor_gonderim). Ayda tek gonderim: durum 'sent' icin kismi benzersiz indeks.
    status: 'sent' | 'reverted' (geri alma yalniz admin; ay yeniden acilir, kayit arsivde kalir)."""

    __tablename__ = "report_dispatch"
    __table_args__ = (
        Index(
            "uq_report_dispatch_month",
            "customer_id",
            "year",
            "month",
            unique=True,
            sqlite_where=text("status = 'sent'"),
            postgresql_where=text("status = 'sent'"),
        ),
        Index("ix_report_dispatch_period", "year", "month"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"))
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    sender: Mapped[str] = mapped_column(String(120), default="")
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    subject: Mapped[str] = mapped_column(String(300), default="")
    report_id: Mapped[int | None] = mapped_column(ForeignKey("report.id"), nullable=True)
    pdf_file: Mapped[str | None] = mapped_column(String(300), nullable=True)
    pdf_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pdf_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="sent")
    reverted_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reverted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 2026-10-31: gecmis rapor ice aktarma (Gonderilen Aylik Rapor > Rapor ice aktar): panel disinda gonderilmis raporun dosyasi
    source: Mapped[str] = mapped_column(String(20), default="panel")  # panel | ice_aktarma
    archive_file: Mapped[str | None] = mapped_column(String(300), nullable=True)  # rapor_klasoru() altinda goreli yol
    archive_name: Mapped[str | None] = mapped_column(String(200), nullable=True)  # yuklenen dosyanin asil adi

class ReportRecipient(Base):
    """Musterinin aylik rapor iletisi alicilari (uretim rapor_alicilari). Adresler ';' ile ayrilir.
    Iletiyi gonderen her zaman personeldir; panel yalnizca taslagi hazirlar."""

    __tablename__ = "report_recipient"
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), primary_key=True)
    to_addrs: Mapped[str] = mapped_column(Text, default="")
    cc_addrs: Mapped[str] = mapped_column(Text, default="")


# --- Musteri envanteri / Kritik CI (2026-11-20; ONENT NEMS_CMDB, app.musteri.envanter) --------------------------------------
class CustomerCi(Base):
    """Musterinin CMDB envanteri: ONENT'te CRM_MUSTERI_NO ozelligi kartin Musteri No'suna esit CI'lar. Isci birkac saatte bir
    bastan yazar; kartin Kritik CI alani bunu okur (2026-11-20 kullanici: "kritik ci artik excel ile degil onent db'den dinamik")."""

    __tablename__ = "customer_ci"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_key: Mapped[str] = mapped_column(String(40), index=True)  # CRM_MUSTERI_NO karsilastirma anahtari
    ci_no: Mapped[str] = mapped_column(String(40), default="")
    ci_name: Mapped[str] = mapped_column(String(300), default="")
    service: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(40), default="")
    attrs: Mapped[dict] = mapped_column(JSON, default=dict)  # yalniz izinli ozellikler (envanter.OZELLIKLER)
    refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CustomerCiFlag(Base):
    """Kartta kullanicinin CI isaretleri: kritik CI (EVET/HAYIR) ve duzeltilmis lokasyon adi (2026-11-24 kullanici: "envanter CI
    listesinde lokasyon adi alanini duzenlenebilir yap"; bos = envanterdeki deger). Envanter (customer_ci) yenilense de korunur;
    anahtar CMDB CI no."""

    __tablename__ = "customer_ci_flag"
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), primary_key=True)
    ci_no: Mapped[str] = mapped_column(String(40), primary_key=True)
    critical: Mapped[bool] = mapped_column(Boolean, default=False)
    location_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    updated_by: Mapped[str] = mapped_column(String(120), default="")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UtilSourceSummary(Base):
    """Utilizasyon veri ozeti (2026-11-21 kullanici: "her sabah 06:00'da isci calissin ve skoru guncellesin"): musteri karti basina
    Kayit Hacmi (2026-11-24: bu yil kapanan + su an acik alarm / sikayet / talep, panel kayitlarindan) ve aktif CI /
    lokasyon (ONENT envanteri). Gunluk isci (skor/gunluk.py) bastan yazar; skor ve Yonetim > Veri Ozeti buradan okur."""

    __tablename__ = "util_source_summary"
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), primary_key=True)
    year: Mapped[int] = mapped_column(Integer)
    alarm: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = kaynak okunamadi
    sikayet: Mapped[int | None] = mapped_column(Integer, nullable=True)
    talep: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ci: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lokasyon: Mapped[int | None] = mapped_column(Integer, nullable=True)
    servisler: Mapped[list | None] = mapped_column(JSON, nullable=True)  # ONENT servis -> Servis Cesitliligi kategorileri (0030)
    baglanti: Mapped[list | None] = mapped_column(JSON, nullable=True)  # ONENT erisim/servis -> baglanti tipleri
    refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Aylik rapor devre grafikleri (2026-11-20; ReportDB LOE sorgusu, app.rapor.loe) ---------------------------------------
class ReportCmdb(Base):
    """ReportDB CMDB kopyasi (ODS_RPT.CORPORATE_FOR_CMDB): yalniz paneldeki musteri numaralarinin devreleri. Isci gunde bir yeniler;
    aylik rapordaki devre aramasi bu kopyada yapilir (panel sureci Oracle'a baglanmaz)."""

    __tablename__ = "report_cmdb"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_key: Mapped[str] = mapped_column(String(40), index=True)  # CUSTOMERNO karsilastirma anahtari (eslestirme.anahtar)
    ciname: Mapped[str] = mapped_column(String(200), index=True)
    fields: Mapped[dict] = mapped_column(JSON, default=dict)  # satirin tum sutunlari (ad -> deger)
    search_text: Mapped[str] = mapped_column(Text, default="")  # kucuk harfli birlesik metin (esnek arama)
    refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReportCircuit(Base):
    """Musterinin aylik rapor devreleri: kullanici aramadan ekler; kaldirilana kadar her ayin raporunda grafigi cizilir."""

    __tablename__ = "report_circuit"
    __table_args__ = (UniqueConstraint("customer_id", "ciname", name="uq_report_circuit"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), index=True)
    ciname: Mapped[str] = mapped_column(String(200))
    label: Mapped[str] = mapped_column(String(300), default="")  # eklendigi andaki aciklama (grafik basligi)
    added_by: Mapped[str] = mapped_column(String(120), default="")
    added_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReportCircuitData(Base):
    """Devrenin bir aylik saatlik olcumleri (BRIX.CORPORATE_HR) + LOE formuluyle aylik ozet. Isci yazar, rapor okur."""

    __tablename__ = "report_circuit_data"
    ciname: Mapped[str] = mapped_column(String(200), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[int] = mapped_column(Integer, primary_key=True)
    points: Mapped[list] = mapped_column(JSON, default=list)  # [[epoch_ms, erisim, gecikme, jitter, kayip, pencere], ...]
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    exchours: Mapped[str] = mapped_column(String(100), default="")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class CalendarDay(KullaniciBase):
    """Izin&Takvim Yonetimi: gun durumu ve toplanti sayilari (uretim calendar_records). Dosya kisinin kendisidir."""

    __tablename__ = "calendar_day"
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, unique=True)
    status: Mapped[str] = mapped_column(String(30), default="calisiyor")
    online_count: Mapped[int] = mapped_column(Integer, default=0)
    face_count: Mapped[int] = mapped_column(Integer, default=0)  # yuz yuze toplanti
    meeting_notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # toplanti ozeti (serbest metin, satir satir); eski dosyalara db._eksik_sutunlari_ekle ekler
    work_notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # o gun yapilan isler (2026-10-14); eski dosyalara db._eksik_sutunlari_ekle ekler
    status2: Mapped[str | None] = mapped_column(String(30), nullable=True)  # yarim gun bolunmesi (2026-10-15): gunun ikinci yarisi; her yari 0,5 gun


class ProjectItem(Base):
    """Takip edilen proje (uretim project_items): TAM'in tekil isi, 5 sabit kategoriden biri. Durum/oncelik degisimi aksiyon olarak yazilir."""

    __tablename__ = "project_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), index=True)  # sorumlu TAM
    category: Mapped[str] = mapped_column(String(20))  # proje / calisma / ddos / dc_tasima / topoloji
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="acik", index=True)  # acik / devam / beklemede / kapandi
    priority: Mapped[str] = mapped_column(String(20), default="orta")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProjectAction(Base):
    """Proje aksiyon gecmisi: kim, ne zaman, ne yapti (acilis ve durum/oncelik degisimi dahil)."""

    __tablename__ = "project_action"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("project_item.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(200), default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProjectCustomerWork(Base):
    """Musteri bazli calisma isareti (uretim analiz.db proje_musteri_calisma): musteri + kategori basina tek kayit."""

    __tablename__ = "project_customer_work"
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), primary_key=True)
    category: Mapped[str] = mapped_column(String(20), primary_key=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    detail: Mapped[str] = mapped_column(Text, default="")
    updated_by: Mapped[str] = mapped_column(String(200), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


RCA_INDEKS_KOSULU = "status = 'closed' AND root_cause <> ''"


class OnedeskRecord(Base):
    """Onedesk alarm / talep / sikayet kaydi. Kaynak: admin Veri Girisi hatti (canli Onedesk DB baglantisi ileride). kind: alarm|talep|sikayet; status: open|closed."""

    __tablename__ = "onedesk_record"
    __table_args__ = (
        Index("ix_onedesk_kind_status", "kind", "status"),
        Index("ix_onedesk_closed_at", "closed_at"),
        Index("ix_onedesk_opened_at", "opened_at"),
        Index("ix_onedesk_customer", "customer_id"),
        Index("ix_onedesk_source_key", "source", "external_key"),  # TEMIP artimli yazimi: (source, IDENTIFIER) ile bulunur
        Index("ix_onedesk_source_mno", "source", "customer_no"),  # TAM Radar: kartsiz kayitlar Musteri No'ya gore
        Index("ix_onedesk_durum_musteri", "status", "customer_id"),  # Musteri Yonetimi: portfoyun acik kayitlari
        Index("ix_onedesk_musteri_durum_kapanis", "customer_id", "status", "closed_at"),  # kart: yil boyu kapananlar
        # 2026-10-20 performans (353 bin TEMIP kaydi): Veri Girisi akislari (kaynak + durum sayimi, ortu indeks) ve RCA / oneriler
        # (yalniz kok sebebi dolu kapananlar: kucuk kismi indeks; sorgu kosulu ayni literal ile yazilir, onedesk.servis._kapananlar)
        Index("ix_onedesk_kaynak_durum_musteri", "source", "status", "customer_id"),
        Index("ix_onedesk_rca", "closed_at", sqlite_where=text(RCA_INDEKS_KOSULU), postgresql_where=text(RCA_INDEKS_KOSULU)),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), default="")
    external_key: Mapped[str] = mapped_column(String(80), default="")
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="")
    customer_label: Mapped[str] = mapped_column(String(200), default="")  # kaynaktaki musteri adi (musteriyle eslesmeyen kayitlar icin)
    location: Mapped[str] = mapped_column(String(200), default="")  # lokasyon / CI adi
    category: Mapped[str] = mapped_column(String(200), default="")
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    root_cause: Mapped[str] = mapped_column(Text, default="")  # RCA: kok sebep
    resolution: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20), default="import")  # import | temip (ReportDB TEMIP alarmi; external_key = IDENTIFIER)
    ticket_no: Mapped[str] = mapped_column(String(40), default="", server_default="")  # OneDesk ticket no (TEMIP ALARMOBJECTOPERATORNO)
    customer_no: Mapped[str] = mapped_column(String(20), default="", server_default="")  # kaynaktaki Musteri No (kartsiz kayit -> TAM Radar)
    detail: Mapped[str] = mapped_column(String(80), default="", server_default="")  # kaynak durumu: TEMIP STATE/PROBLEMSTATUS ya da Closed/<kapatan>


class UtilCriteriaSet(Base):
    """Final skor kriter tablosu. scope: 'parent' (cati) | 'affiliate' (istirak). Her kayit yeni surum."""

    __tablename__ = "util_criteria_set"
    __table_args__ = (UniqueConstraint("scope", "version", name="uq_util_criteria_scope_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)
    criteria: Mapped[list] = mapped_column(JSON, default=list)
    updated_by: Mapped[str] = mapped_column(String(120), default="")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScoreDetail(Base):
    __tablename__ = "score_detail"
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), primary_key=True)
    score: Mapped[float] = mapped_column(Float)
    detail: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScoreHistory(Base):
    """source: 'sayfa' | 'toplu' | 'kriter_degisikligi'. old_score: yazilmadan onceki skor (uretim skor_gecmisi.eski)."""

    __tablename__ = "score_history"
    __table_args__ = (Index("ix_score_history_customer_at", "customer_id", "at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"))
    old_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(120), default="")
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[list | None] = mapped_column(JSON, nullable=True)


class ScoreApprovalRequest(Base):
    """Musteri basina tek bekleyen talep: kismi benzersiz indeks."""

    __tablename__ = "score_approval_request"
    __table_args__ = (
        Index(
            "uq_score_request_pending",
            "customer_id",
            unique=True,
            sqlite_where=text("status = 'pending'"),
            postgresql_where=text("status = 'pending'"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"))
    requested_by: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScoringExclusion(Base):
    """Puanlamaya girmeyen personel."""

    __tablename__ = "scoring_exclusion"
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), primary_key=True)
    set_by: Mapped[str] = mapped_column(String(120), default="")
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AffiliateFinalFlag(Base):
    __tablename__ = "affiliate_final_flag"
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), primary_key=True)
    included: Mapped[bool] = mapped_column(Boolean, default=False)


class UrunTutarOzet(Base):
    """Urun-Tutar Excel ozeti (uretim analiz.db urun_tutar): musteri basina son yukleme degistirir. summary skor icin ozet
    (servisler, lokasyon, baglanti, fatura...); circuits yalniz AKTIF satirlarin devre no / acik adres / urun grubu listesi
    (2026-11-24 kullanici: TopoMaker devre no + acik adres eslesmesi). Fiyat ve diger ham alanlar saklanmaz. Bkz. app/skor/urun_tutar.py."""

    __tablename__ = "urun_tutar_ozet"
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), primary_key=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    circuits: Mapped[list | None] = mapped_column(JSON, nullable=True)
    file_name: Mapped[str] = mapped_column(String(200), default="")
    uploaded_by: Mapped[str] = mapped_column(String(120), default="")
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Demand(Base):
    """Gelistirme talebi / oneri (uretim gelistirme_talepleri). Mevcut ve beklenen durum ayri ayri zorunlu."""

    __tablename__ = "demand"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(20), default="ozellik")  # ozellik / iyilestirme / hata
    priority: Mapped[str] = mapped_column(String(20), default="orta")  # dusuk / orta / yuksek / kritik
    module: Mapped[str] = mapped_column(String(40), default="")  # ilgili ekran
    current_state: Mapped[str] = mapped_column(Text)
    expected_state: Mapped[str] = mapped_column(Text)
    acceptance: Mapped[str] = mapped_column(Text, default="")
    opened_by_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), index=True)  # talebi panele giren
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # 2026-10-31 kullanici: talep e-postayla da gelebilir; talep eden giren kisiden farkli secilebilir (bos = giren kisi).
    requester_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(20), default="panel")  # gelis yolu: panel / eposta
    status: Mapped[str] = mapped_column(String(20), default="yeni", index=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    target_version: Mapped[str] = mapped_column(String(40), default="")
    admin_note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DemandLog(Base):
    """Talep degisiklik gecmisi: kim, ne zaman, hangi alan, eski -> yeni ('olusturma' satiri acilisi kaydeder)."""

    __tablename__ = "demand_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    demand_id: Mapped[int] = mapped_column(ForeignKey("demand.id"), index=True)
    field: Mapped[str] = mapped_column(String(30))
    old_value: Mapped[str] = mapped_column(String(200), default="")
    new_value: Mapped[str] = mapped_column(String(200), default="")
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserNotification(Base):
    """Kisiye ozel panel bildirimi (2026-10-31: talep durumu degisince talep sahibine). Ust cubuk zilinde gorunur; okununca read_at dolar."""

    __tablename__ = "user_notification"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # talep
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # ilgili kayit (talep id)
    message: Mapped[str] = mapped_column(String(400))
    link: Mapped[str] = mapped_column(String(200), default="")  # panel ici adres (#/talep)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SmsRevenue(KullaniciBase):
    """ICT SMS gelir kaydi (uretim ict_revenues). Musteriye unvan eslesmesiyle baglanir."""

    __tablename__ = "sms_revenue"
    id: Mapped[int] = mapped_column(primary_key=True)
    tam_name: Mapped[str] = mapped_column(String(100))
    customer_name: Mapped[str] = mapped_column(String(200))
    amount: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(10), default="TRY")
    project: Mapped[str] = mapped_column(String(200), default="")  # proje bilgisi
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class ApnRevenue(KullaniciBase):
    """APN gelir ve kurulum kaydi (uretim apn_revenues)."""

    __tablename__ = "apn_revenue"
    id: Mapped[int] = mapped_column(primary_key=True)
    tam_name: Mapped[str] = mapped_column(String(100))
    customer_name: Mapped[str] = mapped_column(String(200))
    amount: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(10), default="TRY")
    installation_pct: Mapped[float] = mapped_column(Float, default=0)
    apn_name: Mapped[str] = mapped_column(String(200), default="")
    request_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # talep tarihi
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # teslim tarihi
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApnWork(KullaniciBase):
    """APN > Musteri Calismalari: toplanti konusu, tarihi, planli calisma tarihi, APN adi, musteri."""

    __tablename__ = "apn_work"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_name: Mapped[str] = mapped_column(String(200))
    meeting_subject: Mapped[str] = mapped_column(String(300), default="")
    meeting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    apn_name: Mapped[str] = mapped_column(String(200), default="")
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class Presentation(Base):
    """Ceyrek sunum ogesi: kaynagin (app.sunum.servis.KAYNAKLAR, ornek 'takvim') o ceyrekteki donmus goruntusu (period '2026-Q4').
    Ceyrek+kaynak basina tek kayit. Elle gonderimde sent_by kisinin adi; ceyrek bitince kendiliginden dondurulende bos."""

    __tablename__ = "presentation"
    __table_args__ = (
        Index("uq_presentation_period_source", "period", "source", unique=True, sqlite_where=text("source <> ''"), postgresql_where=text("source <> ''")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"), nullable=True)
    period: Mapped[str] = mapped_column(String(20), default="")
    title: Mapped[str] = mapped_column(String(200), default="")
    source: Mapped[str] = mapped_column(String(30), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    sent_by: Mapped[str] = mapped_column(String(120), default="")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RoleView(Base):
    """Rolun gorunumu: hangi modul/alt modulleri gorur, hangi sayfayla acilir. Admin belirler."""

    __tablename__ = "role_view"
    role: Mapped[str] = mapped_column(String(40), primary_key=True)
    modules: Mapped[list] = mapped_column(JSON, default=list)
    landing: Mapped[str] = mapped_column(String(80), default="ozet")
    permissions: Mapped[list] = mapped_column(JSON, default=list)  # ek yetkiler (rolgorunum.YETKILER), ornek sunum.gonder
    updated_by: Mapped[str] = mapped_column(String(120), default="")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AppSetting(Base):
    """Panel geneli ayar (anahtar -> JSON). Ornek 'sunum.kaynaklar': ceyrek sunuma kendiliginden akan kaynaklar."""

    __tablename__ = "app_setting"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[list | dict] = mapped_column(JSON, default=list)
    updated_by: Mapped[str] = mapped_column(String(120), default="")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IngestBatch(Base):
    """Tampon partisi: bir kaynaktan gelen ham verinin tek kopyasi (satirlar ingest_block'ta). Durum: receiving | ready | failed | rejected."""

    __tablename__ = "ingest_batch"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(40))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="staged")
    note: Mapped[str] = mapped_column(String(300), default="")
    label: Mapped[str] = mapped_column(String(200), default="")
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    columns: Mapped[list] = mapped_column(JSON, default=list)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(120), default="")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(String(300), default="")


# Ozellik paketlerinin tablolari ayni Base'e baglanir (alembic ve create_all hepsini gorur). Dosyanin SONUNDA kalmali.
from app.gelir_uretim import models as _gelir_uretim_models  # noqa: F401
from app.tampon import models as _tampon_models  # noqa: F401
from app.yonetim import models as _yonetim_models  # noqa: F401
