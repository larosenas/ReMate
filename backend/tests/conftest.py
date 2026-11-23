"""Configuración común de las pruebas.

Las pruebas usan una base de datos aparte, `<DB_NAME>_test`, que se crea si no existe
(el usuario de la base de datos necesita el permiso CREATEDB). Nunca apuntan a producción.
"""

from dataclasses import replace

import psycopg
import pytest
from psycopg import sql

import app.modelos
from app import create_app
from app.base_de_datos import Base
from app.config import cargar_config


@pytest.fixture(scope="session")
def config_pruebas(tmp_path_factory):
    config = cargar_config()
    if config.es_produccion:
        pytest.exit("Las pruebas no se ejecutan con APP_ENV=production.")
    config = replace(
        config,
        db_nombre=f"{config.db_nombre}_test",
        archivos_dir=tmp_path_factory.mktemp("archivos"),
        # Las pruebas nunca llaman a la IA real: sin configurar, o se simula en cada prueba.
        ia_api_key="",
        ia_modelo="",
        # Ni correo real: las pruebas del recordatorio simulan el servidor SMTP.
        smtp_host="",
        smtp_user="",
        smtp_password="",
        smtp_from="",
        app_url="",
        # Un nombre inventado y fijo, para no depender del .env de quien pasa las pruebas.
        empresa_nombre="Industrias Ficticias",
    )
    _crear_base_de_datos_si_no_existe(config)
    return config


def _crear_base_de_datos_si_no_existe(config):
    with psycopg.connect(
        host=config.db_host,
        port=config.db_port,
        user=config.db_usuario,
        password=config.db_contrasena,
        dbname="postgres",
        autocommit=True,
    ) as conexion:
        existe = conexion.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (config.db_nombre,)
        ).fetchone()
        if not existe:
            conexion.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(config.db_nombre)))


@pytest.fixture(scope="session")
def app(config_pruebas):
    aplicacion = create_app(config_pruebas)
    motor = aplicacion.extensions["remate.motor"]
    Base.metadata.create_all(motor)
    yield aplicacion
    Base.metadata.drop_all(motor)
    motor.dispose()


@pytest.fixture
def cliente(app):
    return app.test_client()


@pytest.fixture
def limpiar(app):
    """Deja la base de datos de pruebas vacía después de cada prueba."""
    from tests.test_necesidades_servicio import vaciar

    yield
    with app.extensions["remate.sesiones"]() as s:
        vaciar(s)


@pytest.fixture
def listas_vacias(app):
    """Deja vacías las listas de proveedores y peticionarios después de cada prueba."""
    from app.modelos.listas import Peticionario, Proveedor

    yield
    with app.extensions["remate.sesiones"]() as s:
        s.query(Proveedor).delete()
        s.query(Peticionario).delete()
        s.commit()
