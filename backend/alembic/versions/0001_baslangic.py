"""Panel DB baslangic semasi: acik op.create_table (2026-10-10; once create_all idi).

Revision ID: 0001_baslangic
Revises:
Create Date: 2026-10-09

Yalniz ortak panel DB'si (models.Base). Kullanici basina dosyalar (models.KullaniciBase) Alembic'e girmez;
app.db.kullanici_oturumu ilk acilista kurar. Sema burada donmustur: app.models import edilmez, model sonradan
degisse de bu revizyon ayni tablolari kurar. 0002-0004'un ekledigi sutun/tablolar burada YOKTUR, o revizyonlar ekler.
Revizyon kimligi degismedi: eski create_all ile kurulmus DB'ler (dev.db) icin islem gerekmez.
Modelle zincirin esitligi tests/test_alembic.py ile denetlenir; yeni sema degisikligi yeni revizyondur.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_baslangic"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "audit_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("module_key", sa.String(length=80), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "demand",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("opened_by", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "distribution_rule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("source_key", sa.String(length=40), nullable=False),
        sa.Column("match_field", sa.String(length=20), nullable=False),
        sa.Column("key_column", sa.String(length=160), nullable=False),
        sa.Column("target", sa.String(length=60), nullable=False),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("value_column", sa.String(length=160), nullable=False),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("zero_unmatched", sa.Boolean(), nullable=False),
        sa.Column("max_age_minutes", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "fault_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("record_no", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("source", sa.String(length=160), nullable=False),
        sa.Column("message", sa.String(length=300), nullable=False),
        sa.Column("exc_type", sa.String(length=120), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=False),
        sa.Column("resolved_by", sa.String(length=120), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("record_no"),
    )
    op.create_index(op.f("ix_fault_event_at"), "fault_event", ["at"], unique=False)
    op.create_index(op.f("ix_fault_event_code"), "fault_event", ["code"], unique=False)
    op.create_index(op.f("ix_fault_event_status"), "fault_event", ["status"], unique=False)
    op.create_table(
        "income_production",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "ingest_batch",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=40), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=300), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "matrix_config",
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("rows", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.String(length=100), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "radar_prospect",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "role_view",
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("modules", sa.JSON(), nullable=False),
        sa.Column("landing", sa.String(length=80), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.String(length=120), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("role"),
    )
    op.create_table(
        "util_criteria_set",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("criteria", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.String(length=120), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "version", name="uq_util_criteria_scope_version"),
    )
    op.create_table(
        "customer",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("segment", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("customer_no", sa.String(length=50), nullable=True),
        sa.Column("ncst", sa.String(length=50), nullable=False),
        sa.Column("sector", sa.String(length=100), nullable=True),
        sa.Column("inventory_count", sa.Integer(), nullable=False),
        sa.Column("ft_volume", sa.String(length=100), nullable=False),
        sa.Column("tam_ft", sa.String(length=100), nullable=False),
        sa.Column("alarm_count", sa.Integer(), nullable=False),
        sa.Column("complaint_count", sa.Integer(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("alarm_closed_count", sa.Integer(), nullable=False),
        sa.Column("complaint_closed_count", sa.Integer(), nullable=False),
        sa.Column("request_closed_count", sa.Integer(), nullable=False),
        sa.Column("report_count", sa.Integer(), nullable=False),
        sa.Column("cacti_urls", sa.JSON(), nullable=False),
        sa.Column("separate_report", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["customer.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_key"),
    )
    op.create_table(
        "demand_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("demand_id", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=False),
        sa.ForeignKeyConstraint(["demand_id"], ["demand.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "ingest_block",
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("block_no", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["ingest_batch.id"]),
        sa.PrimaryKeyConstraint("batch_id", "block_no"),
    )
    op.create_table(
        "scoring_exclusion",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("set_by", sa.String(length=120), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "affiliate_final_flag",
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("included", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.PrimaryKeyConstraint("customer_id"),
    )
    op.create_table(
        "customer_team",
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("sales_manager", sa.String(length=100), nullable=True),
        sa.Column("presales_manager", sa.String(length=100), nullable=True),
        sa.Column("tac_name", sa.String(length=100), nullable=True),
        sa.Column("tac_gsm", sa.String(length=50), nullable=True),
        sa.Column("tac_email", sa.String(length=100), nullable=True),
        sa.Column("sol_kmt_name", sa.String(length=100), nullable=True),
        sa.Column("sol_kmt_gsm", sa.String(length=50), nullable=True),
        sa.Column("sol_kmt_email", sa.String(length=100), nullable=True),
        sa.Column("mobil_kmt_name", sa.String(length=100), nullable=True),
        sa.Column("mobil_kmt_gsm", sa.String(length=50), nullable=True),
        sa.Column("mobil_kmt_email", sa.String(length=100), nullable=True),
        sa.Column("mobil_kmt_detail", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.PrimaryKeyConstraint("customer_id"),
    )
    op.create_table(
        "distribution_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("target", sa.String(length=60), nullable=False),
        sa.Column("old_value", sa.String(length=200), nullable=True),
        sa.Column("new_value", sa.String(length=200), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("reverted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["ingest_batch.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.ForeignKeyConstraint(["rule_id"], ["distribution_rule.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_distribution_log_run_id"), "distribution_log", ["run_id"], unique=False)
    op.create_table(
        "onedesk_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("external_key", sa.String(length=80), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("customer_label", sa.String(length=200), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=200), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("root_cause", sa.Text(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_onedesk_closed_at", "onedesk_record", ["closed_at"], unique=False)
    op.create_index("ix_onedesk_customer", "onedesk_record", ["customer_id"], unique=False)
    op.create_index("ix_onedesk_kind_status", "onedesk_record", ["kind", "status"], unique=False)
    op.create_index("ix_onedesk_opened_at", "onedesk_record", ["opened_at"], unique=False)
    op.create_table(
        "presentation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("sent_by", sa.String(length=120), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_presentation_period_source",
        "presentation",
        ["period", "source"],
        unique=True,
        sqlite_where=sa.text("source <> ''"),
        postgresql_where=sa.text("source <> ''"),
    )
    op.create_table(
        "project",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "report",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report_month", sa.Integer(), nullable=False),
        sa.Column("report_year", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("sun_success_text", sa.Text(), nullable=True),
        sa.Column("cloud_issue_text", sa.Text(), nullable=True),
        sa.Column("flag_escalation_text", sa.Text(), nullable=True),
        sa.Column("suggestions_text", sa.Text(), nullable=True),
        sa.Column("bubble_report_text", sa.Text(), nullable=True),
        sa.Column("excel_data", sa.Text(), nullable=True),
        sa.Column("cacti_data", sa.Text(), nullable=True),
        sa.Column("last_edited_by", sa.String(length=100), nullable=True),
        sa.Column("last_edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("flag_count", sa.Integer(), nullable=False),
        sa.Column("is_submitted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "report_draft",
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.String(length=120), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.PrimaryKeyConstraint("customer_id", "year", "month"),
    )
    op.create_table(
        "report_recipient",
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("to_addrs", sa.Text(), nullable=False),
        sa.Column("cc_addrs", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.PrimaryKeyConstraint("customer_id"),
    )
    op.create_table(
        "score_approval_request",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("resolved_by", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.ForeignKeyConstraint(["requested_by"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["resolved_by"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_score_request_pending",
        "score_approval_request",
        ["customer_id"],
        unique=True,
        sqlite_where=sa.text("status = 'pending'"),
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_table(
        "score_detail",
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.PrimaryKeyConstraint("customer_id"),
    )
    op.create_table(
        "score_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_score_history_customer_at", "score_history", ["customer_id", "at"], unique=False)
    op.create_table(
        "project_action",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=False),
        sa.Column("acted_on", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "project_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "report_dispatch",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=True),
        sa.Column("sender", sa.String(length=120), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=True),
        sa.Column("pdf_file", sa.String(length=300), nullable=True),
        sa.Column("pdf_size", sa.Integer(), nullable=True),
        sa.Column("pdf_sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reverted_by", sa.String(length=120), nullable=True),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.ForeignKeyConstraint(["report_id"], ["report.id"]),
        sa.ForeignKeyConstraint(["sender_id"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_dispatch_period", "report_dispatch", ["year", "month"], unique=False)
    op.create_index(
        "uq_report_dispatch_month",
        "report_dispatch",
        ["customer_id", "year", "month"],
        unique=True,
        sqlite_where=sa.text("status = 'sent'"),
        postgresql_where=sa.text("status = 'sent'"),
    )


def downgrade() -> None:
    # indeksler tabloyla birlikte duser; tablolar bagimliliktan once
    op.drop_table("report_dispatch")
    op.drop_table("project_item")
    op.drop_table("project_action")
    op.drop_table("score_history")
    op.drop_table("score_detail")
    op.drop_table("score_approval_request")
    op.drop_table("report_recipient")
    op.drop_table("report_draft")
    op.drop_table("report")
    op.drop_table("project")
    op.drop_table("presentation")
    op.drop_table("onedesk_record")
    op.drop_table("distribution_log")
    op.drop_table("customer_team")
    op.drop_table("affiliate_final_flag")
    op.drop_table("scoring_exclusion")
    op.drop_table("ingest_block")
    op.drop_table("demand_log")
    op.drop_table("customer")
    op.drop_table("util_criteria_set")
    op.drop_table("role_view")
    op.drop_table("radar_prospect")
    op.drop_table("matrix_config")
    op.drop_table("ingest_batch")
    op.drop_table("income_production")
    op.drop_table("fault_event")
    op.drop_table("distribution_rule")
    op.drop_table("demand")
    op.drop_table("audit_event")
    op.drop_table("app_user")
