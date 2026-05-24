"""admin users table

Revision ID: 609b0d79a962
Revises: 33a0b8e8aad9
Create Date: 2026-05-25 00:56:43.845337

"""
from alembic import op
import sqlalchemy as sa

revision = '609b0d79a962'
down_revision = '33a0b8e8aad9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'admin_users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username', name='uq_admin_username'),
    )

    # Seed default admin user if table is empty
    from passlib.context import CryptContext
    from datetime import datetime
    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
    bind = op.get_bind()
    existing = bind.execute(sa.text("SELECT COUNT(*) FROM admin_users")).scalar()
    if not existing:
        now = datetime.utcnow().isoformat(sep=' ', timespec='seconds')
        bind.execute(
            sa.text(
                "INSERT INTO admin_users (username, password_hash, created_at, updated_at) "
                "VALUES (:u, :h, :c, :c)"
            ),
            {"u": "admin", "h": pwd_ctx.hash("admin114514"), "c": now},
        )


def downgrade():
    op.drop_table('admin_users')
