"""Conexión a PostgreSQL con SQLAlchemy 2 (ADR 0003)."""

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Clase base de todos los modelos (`app/modelos/`). Alembic usa su metadata."""


def crear_motor(url: str | URL) -> Engine:
    # pool_pre_ping evita errores si PostgreSQL ha cerrado conexiones inactivas. hide_parameters:
    # los errores no llevan los valores de la consulta, que podrían ser datos de las ofertas y
    # acabar en el registro (ADR 0008).
    return create_engine(url, pool_pre_ping=True, hide_parameters=True)


def crear_fabrica_de_sesiones(motor: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=motor, expire_on_commit=False)
