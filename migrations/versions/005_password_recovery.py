"""Single-use password recovery tokens; only their SHA-256 hashes are stored."""
from alembic import op
import sqlalchemy as sa
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("password_resets",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("session_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False))
    op.create_index("ix_password_resets_expires_at", "password_resets", ["expires_at"])


def downgrade():
    op.drop_table("password_resets")
