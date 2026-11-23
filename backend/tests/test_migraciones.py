"""Las migraciones de Alembic crean el mismo esquema que los modelos y se pueden deshacer.

Se ejecutan en una base de datos aparte, `<DB_NAME>_migraciones`, que se crea si no existe y se
vacía al empezar. Las demás pruebas crean las tablas desde los modelos y no comprueban esto.
"""

from dataclasses import replace
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config as ConfigAlembic
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text

import app.modelos  # noqa: F401
from app.base_de_datos import Base, crear_motor
from tests.conftest import _crear_base_de_datos_si_no_existe

CARPETA_BACKEND = Path(__file__).resolve().parents[1]


def test_migraciones_de_principio_a_fin(config_pruebas):
    config = replace(
        config_pruebas, db_nombre=config_pruebas.db_nombre.replace("_test", "_migraciones")
    )
    _crear_base_de_datos_si_no_existe(config)
    motor = crear_motor(config.url_base_de_datos())
    alembic = ConfigAlembic(str(CARPETA_BACKEND / "alembic.ini"))
    alembic.set_main_option("script_location", str(CARPETA_BACKEND / "migraciones"))
    try:
        with motor.begin() as conexion:
            conexion.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
        with motor.begin() as conexion:
            alembic.attributes["connection"] = conexion
            command.upgrade(alembic, "c47e24f16d32")
            conexion.execute(
                text(
                    "INSERT INTO registros (creado_en, nivel, origen, mensaje) "
                    "VALUES (CURRENT_TIMESTAMP, 'INFO', 'prueba', 'Mensaje conservado')"
                )
            )
            command.upgrade(alembic, "head")
            assert conexion.execute(text("SELECT mensaje FROM logs")).scalar_one() == (
                "Mensaje conservado"
            )
            diferencias = compare_metadata(MigrationContext.configure(conexion), Base.metadata)
            assert diferencias == []
            command.downgrade(alembic, "c47e24f16d32")
            assert conexion.execute(text("SELECT mensaje FROM registros")).scalar_one() == (
                "Mensaje conservado"
            )
            command.downgrade(alembic, "base")
            tablas = conexion.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
            assert set(tablas) == {"alembic_version"}
    finally:
        motor.dispose()
