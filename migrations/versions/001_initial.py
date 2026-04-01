"""Initial schema
Revision ID: 001
Revises:
Create Date: 2024-01-01
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("telegram_id", sa.BigInteger, unique=True, nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("is_banned", sa.Boolean, default=False),
        sa.Column("daily_job_count", sa.Integer, default=0),
        sa.Column("daily_reset_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime, nullable=True),
    )
    op.create_table("admins",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("telegram_id", sa.BigInteger, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime, nullable=True),
    )
    op.create_table("jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("uuid", sa.String(36), unique=True, nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("youtube_consent", sa.Boolean, nullable=True),
        sa.Column("youtube_consent_at", sa.DateTime, nullable=True),
        sa.Column("original_filename", sa.String(500), nullable=True),
        sa.Column("original_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("processed_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("temp_original_path", sa.Text, nullable=True),
        sa.Column("temp_processed_path", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), default="pending", nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("metadata_before", sa.JSON, nullable=True),
        sa.Column("metadata_after", sa.JSON, nullable=True),
        sa.Column("cleanup_done", sa.Boolean, default=False),
        sa.Column("cleanup_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )
    op.create_table("job_reports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("event", sa.String(100), nullable=False),
        sa.Column("details", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table("broadcasts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("message_text", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), default="draft", nullable=False),
        sa.Column("target_count", sa.Integer, default=0),
        sa.Column("sent_count", sa.Integer, default=0),
        sa.Column("failed_count", sa.Integer, default=0),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("admins.id"), nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("paused_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table("broadcast_recipients",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("broadcast_id", sa.Integer, sa.ForeignKey("broadcasts.id"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("sent_at", sa.DateTime, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_table("system_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("module", sa.String(100), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("context", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table("settings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(100), unique=True, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
        sa.Column("updated_by", sa.Integer, sa.ForeignKey("admins.id"), nullable=True),
    )


def downgrade():
    for t in ["settings","system_logs","broadcast_recipients","broadcasts",
              "job_reports","jobs","admins","users"]:
        op.drop_table(t)
