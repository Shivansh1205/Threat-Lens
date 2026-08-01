"""add risk scoring

Revision ID: f216a5c3b49f
Revises: ec624ab32c48
Create Date: 2026-08-01 03:00:00.000000

Phase 5 (dynamic risk scoring): adds the columns RiskScorer needs.

- alerts.raw_score / alerts.raw_severity — the detector's original,
  pre-adjustment score/severity, preserved for auditability now that
  alerts.score / alerts.severity hold the risk-ADJUSTED values.
- behavior_profiles.user_risk_score — rolling, decaying per-user risk score,
  indexed because GET /api/v1/users/high-risk sorts on it.

Dev-database note: both new ``alerts`` columns are added as NOT NULL
directly, with no default and no backfill step. That's fine for this
project's dev database — if you've got existing rows from earlier
Phase 3/4 testing, this migration will fail against them with a NOT NULL
violation, and the fix is to wipe the dev data (drop/recreate the DB or
truncate ``alerts``), not to complicate this migration. A real production
deployment could not do this safely: it would need to add the columns
nullable, backfill raw_score/raw_severity from the existing score/severity
values (a reasonable default for pre-Phase-5 rows, since they were never
risk-adjusted), and only then tighten to NOT NULL. Skipped here on purpose —
not needed for a student project's dev database.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f216a5c3b49f'
down_revision: Union[str, None] = 'ec624ab32c48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The `severity` enum type already exists (created by the initial
    # migration for alerts.severity) — create_type=False so this doesn't
    # try to CREATE TYPE severity a second time on Postgres.
    raw_severity_enum = postgresql.ENUM(
        'LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='severity', create_type=False
    )

    op.add_column('alerts', sa.Column('raw_score', sa.Integer(), nullable=False))
    op.add_column('alerts', sa.Column('raw_severity', raw_severity_enum, nullable=False))

    # Same dev-database simplicity as above: straight NOT NULL, no default,
    # no backfill. Fails against existing behavior_profiles rows exactly
    # like the alerts columns above would — expected, same fix (wipe dev
    # data).
    op.add_column(
        'behavior_profiles',
        sa.Column('user_risk_score', sa.Float(), nullable=False),
    )
    op.create_index(
        op.f('ix_behavior_profiles_user_risk_score'),
        'behavior_profiles',
        ['user_risk_score'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_behavior_profiles_user_risk_score'), table_name='behavior_profiles'
    )
    op.drop_column('behavior_profiles', 'user_risk_score')
    op.drop_column('alerts', 'raw_severity')
    op.drop_column('alerts', 'raw_score')
