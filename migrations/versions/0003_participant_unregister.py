"""participant soft-unregister column

Revision ID: 7d3e9c1a4b08
Revises: 609b0d79a962
Create Date: 2026-05-26 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '7d3e9c1a4b08'
down_revision = '609b0d79a962'
branch_labels = None
depends_on = None


def upgrade():
    # batch_alter_table for SQLite compat (rest of codebase follows this pattern).
    with op.batch_alter_table('participants') as batch:
        batch.add_column(sa.Column('unregistered_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('participants') as batch:
        batch.drop_column('unregistered_at')
