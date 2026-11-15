"""add_prix_vente_to_invoice_lines

Revision ID: f697fecdf29e
Revises: 8f1d2c3b4a55
Create Date: 2026-11-01 16:24:17.759648

"""
from alembic import op
import sqlalchemy as sa


revision = 'f697fecdf29e'
down_revision = '8f1d2c3b4a55'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ajouter la colonne prix_vente à invoice_lines
    op.add_column('invoice_lines', sa.Column('prix_vente', sa.Numeric(precision=18, scale=4), nullable=True))


def downgrade() -> None:
    # Supprimer la colonne prix_vente de invoice_lines
    op.drop_column('invoice_lines', 'prix_vente')
