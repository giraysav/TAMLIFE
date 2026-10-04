"""PostgreSQL schema for the panel. No customer seed and no secret columns."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


TABLE_OWNER = {
    "app_user": "core",
    "audit_event": "core",
    "customer": "musteri",
    "customer_contact": "musteri",
    "report": "rapor",
    "report_recipient": "rapor",
    "calendar_entry": "takvim",
    "project": "proje",
    "project_item": "proje",
    "project_action": "proje",
    "onedesk_record": "onedesk",
    "util_criteria_set": "utilizasyon",
    "score_detail": "utilizasyon",
    "score_history": "utilizasyon",
    "score_approval_request": "utilizasyon",
    "scoring_exclusion": "utilizasyon",
    "affiliate_final_flag": "utilizasyon",
    "demand": "talep",
    "demand_log": "talep",
    "sms_revenue": "tamsms",
    "apn_revenue": "tamapn",
    "radar_prospect": "radar",
    "presentation": "sunum",
    "income_production": "gelir_uretim",
    "wholesale_item": "toptan",
    "external_source": "ingest",
    "ingest_batch": "ingest",
    "ingest_record": "ingest",
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


class AuditEvent(Base):
    __tablename__ = "audit_event"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(80))
    outcome: Mapped[str] = mapped_column(String(40))
    module_key: Mapped[str] = mapped_column(String(80), default="")
    detail: Mapped[str] = mapped_column(String(500), default="")


class Customer(Base):
    __tablename__ = "customer"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_key: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    segment: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(40), default="")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)  # sorumlu TAM
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"), nullable=True)  # bos = cati
    score: Mapped[float | None] = mapped_column(Float, nullable=True)  # final skor, yalniz cati


class CustomerContact(Base):
    __tablename__ = "customer_contact"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"))
    name: Mapped[str] = mapped_column(String(200), default="")
    channel: Mapped[str] = mapped_column(String(40), default="")


class Report(Base):
    __tablename__ = "report"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"), nullable=True)
    period: Mapped[str] = mapped_column(String(20), default="")
    title: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(40), default="")


class ReportRecipient(Base):
    __tablename__ = "report_recipient"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("report.id"))
    label: Mapped[str] = mapped_column(String(200), default="")


class CalendarEntry(Base):
    __tablename__ = "calendar_entry"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_username: Mapped[str] = mapped_column(String(120), default="")
    kind: Mapped[str] = mapped_column(String(40), default="")
    title: Mapped[str] = mapped_column(String(200), default="")
    starts_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Project(Base):
    __tablename__ = "project"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(40), default="")


class ProjectItem(Base):
    __tablename__ = "project_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"))
    title: Mapped[str] = mapped_column(String(200), default="")
    state: Mapped[str] = mapped_column(String(40), default="")


class ProjectAction(Base):
    __tablename__ = "project_action"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"))
    note: Mapped[str] = mapped_column(String(500), default="")
    acted_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OnedeskRecord(Base):
    __tablename__ = "onedesk_record"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), default="")
    external_key: Mapped[str] = mapped_column(String(80), default="")
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="")


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
    """source: 'sayfa' | 'toplu' | 'kriter_degisikligi'."""

    __tablename__ = "score_history"
    __table_args__ = (Index("ix_score_history_customer_at", "customer_id", "at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"))
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


class Demand(Base):
    __tablename__ = "demand"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(40), default="")
    opened_by: Mapped[str] = mapped_column(String(120), default="")


class DemandLog(Base):
    __tablename__ = "demand_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    demand_id: Mapped[int] = mapped_column(ForeignKey("demand.id"))
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(String(500), default="")


class SmsRevenue(Base):
    __tablename__ = "sms_revenue"
    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(String(20), default="")
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)


class ApnRevenue(Base):
    __tablename__ = "apn_revenue"
    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(String(20), default="")
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)


class RadarProspect(Base):
    __tablename__ = "radar_prospect"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    stage: Mapped[str] = mapped_column(String(40), default="")


class Presentation(Base):
    __tablename__ = "presentation"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"), nullable=True)
    period: Mapped[str] = mapped_column(String(20), default="")
    title: Mapped[str] = mapped_column(String(200), default="")


class IncomeProduction(Base):
    __tablename__ = "income_production"
    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(String(20), default="")
    label: Mapped[str] = mapped_column(String(200), default="")
    amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)


class WholesaleItem(Base):
    __tablename__ = "wholesale_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(String(20), default="")
    label: Mapped[str] = mapped_column(String(200), default="")
    amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)


class ExternalSource(Base):
    __tablename__ = "external_source"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(40), unique=True)
    kind: Mapped[str] = mapped_column(String(40))
    dsn_env: Mapped[str] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class IngestBatch(Base):
    __tablename__ = "ingest_batch"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(40))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="staged")
    note: Mapped[str] = mapped_column(String(300), default="")


class IngestRecord(Base):
    __tablename__ = "ingest_record"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("ingest_batch.id"))
    source_key: Mapped[str] = mapped_column(String(40))
    external_key: Mapped[str] = mapped_column(String(120), default="")
    payload: Mapped[dict] = mapped_column(JSONB)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def seed_source_slots(connection) -> None:
    """Insert production source slots. The row stores the env key name, never a DSN value."""
    from sqlalchemy import insert

    from app.external import SOURCE_SLOTS

    present = {row[0] for row in connection.execute(select(ExternalSource.source_key))}
    for key, kind, env_name in SOURCE_SLOTS:
        if key in present:
            continue
        connection.execute(
            insert(ExternalSource).values(
                source_key=key,
                kind=kind,
                dsn_env=env_name,
                enabled=False,
            )
        )
