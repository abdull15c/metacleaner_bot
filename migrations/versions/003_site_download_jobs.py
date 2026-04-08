"""Add site_download_jobs table
Revision ID: 003
Revises: 001
Create Date: 2026-04-09
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "001"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "site_download_jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("uuid", sa.String(36), unique=True, nullable=False, index=True),
        sa.Column("telegram_id", sa.BigInteger, index=True, nullable=False),
        sa.Column("ip_address", sa.String(64), index=True, nullable=True),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("format", sa.String(20), nullable=False),
        sa.Column("clean_metadata", sa.Boolean, default=False),
        sa.Column("original_title", sa.String(500), nullable=True),
        sa.Column("file_path", sa.Text, nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("status", sa.String(20), default="pending", nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("cleanup_done", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), index=True),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )

def downgrade():
    op.drop_table("site_download_jobs")
