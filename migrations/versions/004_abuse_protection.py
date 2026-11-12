"""Persistent automatic anti-abuse counters and one-use registration forms."""
from alembic import op
import sqlalchemy as sa
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("abuse_state",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.Integer(), nullable=False),
        sa.Column("blocked_until", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False))
    op.create_index("ix_abuse_state_expires_at", "abuse_state", ["expires_at"])


def downgrade():
    op.drop_table("abuse_state")
