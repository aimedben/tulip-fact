"""supplier_fiscal_fields

Revision ID: b3c7d91e4a20
Revises: f697fecdf29e
Create Date: 2026-11-14 08:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b3c7d91e4a20'
down_revision = 'f697fecdf29e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Champs Tulip CLIENTS conservés aussi dans la base locale : ville,
    # matricule fiscal (MF) et numéro d'identification statistique (NIS).
    op.add_column('suppliers', sa.Column('city', sa.String(length=100), nullable=True))
    op.add_column('suppliers', sa.Column('mf', sa.String(length=20), nullable=True))
    op.add_column('suppliers', sa.Column('nis', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('suppliers', 'nis')
    op.drop_column('suppliers', 'mf')
    op.drop_column('suppliers', 'city')
