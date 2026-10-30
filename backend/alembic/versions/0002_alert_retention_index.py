"""Index alert timestamps for retention cleanup."""

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade():
    op.create_index("ix_alerts_timestamp", "alerts", ["timestamp"])


def downgrade():
    op.drop_index("ix_alerts_timestamp", table_name="alerts")
