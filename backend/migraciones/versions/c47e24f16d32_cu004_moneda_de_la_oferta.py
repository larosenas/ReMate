"""CU-004/CU-005: moneda de la oferta (ADR 0010), sin conversiones.

Las ofertas anteriores pasan a EUR, la moneda por defecto.
"""

from alembic import op
import sqlalchemy as sa

revision = "c47e24f16d32"
down_revision = "a8804a7f53fc"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ofertas", sa.Column("moneda", sa.String(3), nullable=True))
    op.execute("UPDATE ofertas SET moneda = 'EUR'")


def downgrade():
    op.drop_column("ofertas", "moneda")
