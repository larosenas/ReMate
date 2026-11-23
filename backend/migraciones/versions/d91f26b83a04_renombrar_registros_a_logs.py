"""ADR 0008: renombrar registros a logs conservando los mensajes existentes."""

from alembic import op

revision = "d91f26b83a04"
down_revision = "c47e24f16d32"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("registros", "logs")
    op.execute("ALTER INDEX registros_creado_en RENAME TO logs_creado_en")
    op.execute("ALTER TABLE logs RENAME CONSTRAINT registros_pkey TO logs_pkey")
    op.execute("ALTER SEQUENCE registros_id_seq RENAME TO logs_id_seq")


def downgrade() -> None:
    op.execute("ALTER SEQUENCE logs_id_seq RENAME TO registros_id_seq")
    op.execute("ALTER TABLE logs RENAME CONSTRAINT logs_pkey TO registros_pkey")
    op.execute("ALTER INDEX logs_creado_en RENAME TO registros_creado_en")
    op.rename_table("logs", "registros")
