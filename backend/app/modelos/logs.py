"""Registro de la aplicación (logs) en la base de datos (ADR 0008).

Cada fila es un mensaje del registro: información («Necesidad creada: …»), avisos y errores, con
su traza si la hay. No caduca. Se consulta con SQL (DBeaver, manual de operación). Solo lleva
códigos e identificadores, nunca importes ni datos de las ofertas.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.base_de_datos import Base


class Log(Base):
    __tablename__ = "logs"
    __table_args__ = (Index("logs_creado_en", "creado_en"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # La hora del mensaje, no la de la inserción.
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    nivel: Mapped[str] = mapped_column(String(10))  # INFO, WARNING, ERROR o CRITICAL
    # De dónde viene: el módulo (por ejemplo, «app.integraciones.ia») o «app» si es de la API.
    origen: Mapped[str] = mapped_column(String(100))
    mensaje: Mapped[str] = mapped_column(Text)
    traza: Mapped[str | None] = mapped_column(Text)
