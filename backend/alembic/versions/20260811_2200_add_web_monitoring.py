"""add web monitoring fields and sources

Revision ID: a11webmonitor
Revises: f216a5c3b49f
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a11webmonitor"
down_revision: Union[str, None] = "f216a5c3b49f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

json_type = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "monitoring_sources",
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("events_received", sa.Integer(), server_default="0", nullable=False),
        sa.Column("malformed_lines", sa.Integer(), server_default="0", nullable=False),
        sa.Column("delivery_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("source_id"),
    )
    op.add_column("log_events", sa.Column("source_id", sa.String(length=100), nullable=True))
    op.add_column("log_events", sa.Column("external_event_id", sa.String(length=128), nullable=True))
    op.add_column("log_events", sa.Column("http_method", sa.String(length=16), nullable=True))
    op.add_column("log_events", sa.Column("http_status", sa.Integer(), nullable=True))
    op.add_column("log_events", sa.Column("response_time_ms", sa.Float(), nullable=True))
    op.add_column("log_events", sa.Column("bytes_sent", sa.Integer(), nullable=True))
    op.add_column("log_events", sa.Column("host", sa.String(length=255), nullable=True))
    op.add_column("log_events", sa.Column("referrer", sa.String(length=2048), nullable=True))
    op.add_column("log_events", sa.Column("event_metadata", json_type, nullable=True))
    op.create_index("ix_log_events_source_id", "log_events", ["source_id"], unique=False)
    op.create_unique_constraint(
        "uq_log_event_source_external", "log_events", ["source_id", "external_event_id"]
    )
    op.add_column("alerts", sa.Column("evidence", json_type, nullable=True))


def downgrade() -> None:
    op.drop_column("alerts", "evidence")
    op.drop_constraint("uq_log_event_source_external", "log_events", type_="unique")
    op.drop_index("ix_log_events_source_id", table_name="log_events")
    for column in (
        "event_metadata", "referrer", "host", "bytes_sent", "response_time_ms",
        "http_status", "http_method", "external_event_id", "source_id",
    ):
        op.drop_column("log_events", column)
    op.drop_table("monitoring_sources")
