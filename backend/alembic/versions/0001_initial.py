"""Initial persistent monitoring schema."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    op.create_table(
        "hosts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("host_id", sa.String(36), sa.ForeignKey("hosts.id"), nullable=False),
        sa.Column("sample_id", sa.String(36), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        *[sa.Column(k, sa.Float(), nullable=False) for k in ("cpu", "memory", "disk")],
        *[
            sa.Column(k, sa.BigInteger(), nullable=False)
            for k in ("network_sent_bytes", "network_recv_bytes")
        ],
        sa.UniqueConstraint("host_id", "sample_id"),
    )
    op.create_index("ix_metrics_host_time", "metrics", ["host_id", "timestamp"])
    op.create_index("ix_metrics_timestamp", "metrics", ["timestamp"])
    op.create_table(
        "rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("host_id", sa.String(36), sa.ForeignKey("hosts.id"), nullable=False),
        sa.Column("metric", sa.String(16), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("host_id", "metric"),
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("host_id", sa.String(36), sa.ForeignKey("hosts.id"), nullable=False),
        sa.Column("rule_id", sa.Integer(), sa.ForeignKey("rules.id"), nullable=False),
        sa.Column("metric", sa.String(16), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alerts_host_id", "alerts", ["host_id"])


def downgrade():
    for name in ("alerts", "rules", "metrics", "hosts"):
        op.drop_table(name)
