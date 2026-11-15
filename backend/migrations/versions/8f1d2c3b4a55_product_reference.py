"""product reference column

Revision ID: 8f1d2c3b4a55
Revises: c6fcf76baa62
Create Date: 2026-10-31 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '8f1d2c3b4a55'
down_revision = 'c6fcf76baa62'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('products') as batch:
        batch.add_column(sa.Column('reference', sa.String(length=64), nullable=True))
        batch.create_index('ix_products_reference', ['reference'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('products') as batch:
        batch.drop_index('ix_products_reference')
        batch.drop_column('reference')
