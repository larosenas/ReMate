"""CU-004/CU-005: quitar el importe con IVA de las ofertas.

Todos los importes son sin IVA. La columna se borra con sus datos, sin copia previa. La vuelta
atrás vuelve a crear la columna, vacía.
"""

from alembic import op
import sqlalchemy as sa

revision = "3437cbe3bc83"
down_revision = "d91f26b83a04"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("ofertas", "importe_con_iva")


def downgrade():
    op.add_column(
        "ofertas", sa.Column("importe_con_iva", sa.Numeric(precision=14, scale=2), nullable=True)
    )
