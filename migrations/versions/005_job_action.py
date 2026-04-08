"""Add job_action to jobs
Revision ID: 005
Revises: 004
Create Date: 2026-04-09
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("jobs", sa.Column("job_action", sa.String(20), server_default="clean", nullable=False))

def downgrade():
    op.drop_column("jobs", "job_action")
