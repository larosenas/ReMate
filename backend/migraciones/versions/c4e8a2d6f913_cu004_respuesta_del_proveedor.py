"""CU-004: tipo de adjunto para la respuesta del proveedor.

Con «Añadir datos del proveedor», el correo y los adjuntos con los que el proveedor completa su
oferta se guardan en la misma oferta con el tipo `respuesta_oferta`. Solo cambia la restricción
de tipos. La vuelta atrás falla si ya hay adjuntos de ese tipo: así no se borra nada sin querer.
"""

from alembic import op

revision = "c4e8a2d6f913"
down_revision = "8b2d4f6a1c37"
branch_labels = None
depends_on = None

ANTES = (
    "'necesidad', 'solicitud', 'correo_oferta', 'adjunto_oferta', 'adjudicacion', "
    "'pedido_sap', 'envio_pedido'"
)


def upgrade():
    op.drop_constraint("tipo_valido", "adjuntos", type_="check")
    op.create_check_constraint("tipo_valido", "adjuntos", f"tipo IN ({ANTES}, 'respuesta_oferta')")


def downgrade():
    op.drop_constraint("tipo_valido", "adjuntos", type_="check")
    op.create_check_constraint("tipo_valido", "adjuntos", f"tipo IN ({ANTES})")
