"""Add sponsor_channels table
Revision ID: 004
Revises: 003
Create Date: 2026-04-09
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "sponsor_channels",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("channel_id", sa.BigInteger, unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, default=True),
    )

def downgrade():
    op.drop_table("sponsor_channels")
