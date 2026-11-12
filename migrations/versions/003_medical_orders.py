"""Private medical-order image references; image bytes stay outside PostgreSQL."""
from alembic import op
import sqlalchemy as sa
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("medical_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("professional_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("document_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.String(120), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("thumbnail_bytes", sa.Integer(), nullable=False),
        sa.Column("original_size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("patient_id", "sha256", name="uq_medical_order_patient_hash"))
    op.create_index("ix_medical_orders_patient_id", "medical_orders", ["patient_id"])
    op.create_index("ix_medical_orders_professional_id", "medical_orders", ["professional_id"])

def downgrade():
    op.drop_table("medical_orders")
