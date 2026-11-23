"""CU-002/CU-005: motivo de pedir ofertas a menos de 3 proveedores.

Hay que pedir ofertas a 3 proveedores como mínimo y, si son menos,
justificarlo; el motivo va al texto para SAP. Solo añade una columna, vacía en las necesidades
que ya existen.
"""

from alembic import op
import sqlalchemy as sa

revision = "5e1a7c3b9d20"
down_revision = "3437cbe3bc83"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("necesidades", sa.Column("motivo_pocos_proveedores", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("necesidades", "motivo_pocos_proveedores")
