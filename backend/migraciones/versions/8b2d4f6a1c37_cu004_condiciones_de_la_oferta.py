"""CU-004: condiciones de la oferta en una tabla.

En lugar del texto libre «Otros», nueve condiciones con su estado y
su texto, para compararlas. Solo añade una columna JSONB, vacía en las ofertas que ya existen
(se ven como «No especificado» y se pueden reanalizar). `otros` se queda.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "8b2d4f6a1c37"
down_revision = "5e1a7c3b9d20"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ofertas",
        sa.Column("condiciones", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade():
    op.drop_column("ofertas", "condiciones")
