"""CU-003 — Listas maestras: proveedores, peticionarios y avisados del pedido SAP (modelo de datos).

Un registro desactivado se puede eliminar después (baja definitiva): no se borra, porque aparece
en necesidades antiguas, sino que se marca con la fecha y el motivo y deja de salir en las listas.
El correo solo es único entre los no eliminados, para poder dar de alta otro registro con el
correo de uno eliminado.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.base_de_datos import Base


class Proveedor(Base):
    __tablename__ = "proveedores"
    __table_args__ = (
        Index(
            "proveedores_email_vigente",
            "email",
            unique=True,
            postgresql_where=text("eliminado_en IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200))
    # Se guarda normalizado (minúsculas, sin espacios): así el índice único
    # no distingue mayúsculas.
    email: Mapped[str] = mapped_column(String(254))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    eliminado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_eliminacion: Mapped[str | None] = mapped_column(Text)


class Peticionario(Base):
    __tablename__ = "peticionarios"
    __table_args__ = (
        Index(
            "peticionarios_email_vigente",
            "email",
            unique=True,
            postgresql_where=text("eliminado_en IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre_completo: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    eliminado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_eliminacion: Mapped[str | None] = mapped_column(Text)


class AvisadoPedidoSap(Base):
    """Quién recibe el aviso al entrar en el paso 5 (pedido en SAP) y su recordatorio semanal.
    Se gestiona en «Listas» como las otras dos; sus datos no van en el repositorio."""

    __tablename__ = "avisados_pedido_sap"
    __table_args__ = (
        Index(
            "avisados_pedido_sap_email_vigente",
            "email",
            unique=True,
            postgresql_where=text("eliminado_en IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    eliminado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_eliminacion: Mapped[str | None] = mapped_column(Text)
