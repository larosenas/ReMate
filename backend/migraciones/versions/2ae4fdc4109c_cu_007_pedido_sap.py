"""CU-007 pedido SAP

Revision ID: 2ae4fdc4109c
Revises: 294b63f14f2c
Create Date: 2026-10-26 10:27:06.751123

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2ae4fdc4109c'
down_revision: Union[str, Sequence[str], None] = '294b63f14f2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ANTES = "'necesidad', 'solicitud', 'correo_oferta', 'adjunto_oferta', 'adjudicacion', 'pedido_sap'"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('necesidades', sa.Column('numero_pedido_sap', sa.String(length=50), nullable=True))
    # Nuevo tipo de adjunto: el .eml al proveedor con el pedido SAP.
    op.drop_constraint('tipo_valido', 'adjuntos', type_='check')
    op.create_check_constraint('tipo_valido', 'adjuntos', f"tipo IN ({ANTES}, 'envio_pedido')")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('tipo_valido', 'adjuntos', type_='check')
    op.create_check_constraint('tipo_valido', 'adjuntos', f"tipo IN ({ANTES})")
    op.drop_column('necesidades', 'numero_pedido_sap')
