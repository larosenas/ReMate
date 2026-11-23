"""Necesidades, sus adjuntos, el historial de estados y los retrasos (modelo de datos).

Las columnas se añaden con cada caso de uso y su migración (CU-001, CU-002, CU-005…).
"""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.base_de_datos import Base
from app.modelos.listas import Peticionario, Proveedor

if TYPE_CHECKING:
    from app.modelos.ofertas import Oferta

# Estados del proceso: código y texto visible.
ESTADOS = {
    "necesidad_creada": "Necesidad creada",
    "en_cotizacion": "En cotización",
    "en_evaluacion": "En evaluación",
    "pendiente_solicitud_sap": "Pendiente solicitud SAP",
    "pendiente_pedido_sap": "Pendiente pedido SAP",
    "pendiente_entrega": "Pendiente entrega",
    "entregado": "Entregado",
    "cancelada": "Cancelada",
}

# `solicitud`, `adjudicacion` y `envio_pedido`: los .eml que genera la aplicación (CU-002, CU-005
# y CU-007); `pedido_sap`: el pedido oficial de SAP que sube el ingeniero (CU-007).
TIPOS_ADJUNTO = (
    "necesidad",
    "solicitud",
    "correo_oferta",
    "adjunto_oferta",
    "adjudicacion",
    "pedido_sap",
    "envio_pedido",
    # Correo y adjuntos con los que el proveedor completa su oferta.
    "respuesta_oferta",
)
# Formato que indica el ingeniero en cada adjunto de una oferta (CU-004), para saber cómo leerlo.
FORMATOS_ADJUNTO = ("pdf", "excel", "word", "imagen", "otro")


def _solo(valores, columna: str) -> str:
    lista = ", ".join(f"'{v}'" for v in valores)
    return f"{columna} IN ({lista})"


class Necesidad(Base):
    __tablename__ = "necesidades"
    __table_args__ = (CheckConstraint(_solo(ESTADOS, "estado"), name="estado_valido"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # AAAAMMDDNN: la restricción única impide repetirlo aunque se creen dos a la vez.
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    titulo: Mapped[str] = mapped_column(String(200))
    proyecto: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(30))
    peticionario_id: Mapped[int] = mapped_column(ForeignKey("peticionarios.id"))
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    motivo_cancelacion: Mapped[str | None] = mapped_column(Text)
    # CU-002: por qué se pidieron ofertas a menos de 3 proveedores; va al texto para SAP.
    motivo_pocos_proveedores: Mapped[str | None] = mapped_column(Text)
    # CU-005: oferta elegida, texto para SAP y fecha de entrega de la oferta elegida.
    # `use_alter`: necesidades y ofertas se referencian entre sí.
    oferta_adjudicada_id: Mapped[int | None] = mapped_column(
        ForeignKey("ofertas.id", use_alter=True, name="necesidades_oferta_adjudicada_id_fkey")
    )
    texto_sap: Mapped[str | None] = mapped_column(Text)
    fecha_entrega_inicial: Mapped[date | None] = mapped_column(Date)
    # CU-006: fecha confirmada al meter el pedido en SAP; referencia de retrasos y recordatorio.
    fecha_entrega_prevista: Mapped[date | None] = mapped_column(Date)
    # CU-007: número del pedido oficial de SAP (opcional).
    numero_pedido_sap: Mapped[str | None] = mapped_column(String(50))
    # CU-008: fecha en que llegó el pedido.
    fecha_entrega_real: Mapped[date | None] = mapped_column(Date)
    # Comentario opcional al confirmar la entrega (por ejemplo, «llegó el paquete destrozado»);
    # sale en la comparativa de ofertas futuras del proveedor y se pasa a la IA al adjudicar.
    comentario_entrega: Mapped[str | None] = mapped_column(Text)
    # CU-009: cuándo se envió el recordatorio de la fecha prevista actual (vacío = sin enviar).
    recordatorio_enviado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Último aviso a los avisados del pedido SAP (al entrar en el paso 5 y cada semana mientras
    # siga en él); vacío = sin enviar todavía (lo reintenta la tarea diaria).
    aviso_pedido_sap_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    peticionario: Mapped[Peticionario] = relationship()
    oferta_adjudicada: Mapped[Oferta | None] = relationship(
        foreign_keys=[oferta_adjudicada_id], post_update=True
    )
    adjuntos: Mapped[list[Adjunto]] = relationship(
        back_populates="necesidad", order_by="Adjunto.id"
    )
    historial: Mapped[list[CambioEstado]] = relationship(
        back_populates="necesidad", order_by="CambioEstado.id"
    )
    cambios_peticionario: Mapped[list[CambioPeticionario]] = relationship(
        back_populates="necesidad", order_by="CambioPeticionario.id"
    )
    solicitados: Mapped[list[ProveedorSolicitado]] = relationship(back_populates="necesidad")
    retrasos: Mapped[list[Retraso]] = relationship(
        back_populates="necesidad", order_by="Retraso.id"
    )

    def ultimo_adjunto(self, tipo: str) -> Adjunto | None:
        """El último adjunto de un tipo: el .eml de la solicitud o de la adjudicación, el pedido
        SAP o el .eml del pedido (se guardan todos; vale el último)."""
        return next((a for a in reversed(self.adjuntos) if a.tipo == tipo), None)


class Adjunto(Base):
    __tablename__ = "adjuntos"
    __table_args__ = (
        CheckConstraint(_solo(TIPOS_ADJUNTO, "tipo"), name="tipo_valido"),
        CheckConstraint(
            f"formato IS NULL OR {_solo(FORMATOS_ADJUNTO, 'formato')}", name="formato_valido"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    necesidad_id: Mapped[int] = mapped_column(ForeignKey("necesidades.id"))
    tipo: Mapped[str] = mapped_column(String(20))
    # Nombre original (para mostrarlo y descargarlo) y ruta dentro de ARCHIVOS_DIR.
    nombre_archivo: Mapped[str] = mapped_column(String(255))
    ruta: Mapped[str] = mapped_column(String(500))
    tipo_mime: Mapped[str] = mapped_column(String(255))
    tamano: Mapped[int] = mapped_column(BigInteger)
    subido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Solo en el correo y los adjuntos de una oferta (CU-004).
    oferta_id: Mapped[int | None] = mapped_column(ForeignKey("ofertas.id"))
    formato: Mapped[str | None] = mapped_column(String(10))
    # ADR 0014: cuándo se borró el archivo por antigüedad; la fila se queda (nombre, tipo,
    # tamaño) y la descarga responde 410.
    caducado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    necesidad: Mapped[Necesidad] = relationship(back_populates="adjuntos")


class CambioEstado(Base):
    __tablename__ = "cambios_estado"

    id: Mapped[int] = mapped_column(primary_key=True)
    necesidad_id: Mapped[int] = mapped_column(ForeignKey("necesidades.id"))
    estado_anterior: Mapped[str | None] = mapped_column(String(30))
    estado_nuevo: Mapped[str] = mapped_column(String(30))
    # Sin login, el peticionario que hace la acción deja constancia de quién fue.
    peticionario_id: Mapped[int] = mapped_column(ForeignKey("peticionarios.id"))
    cambiado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    necesidad: Mapped[Necesidad] = relationship(back_populates="historial")
    peticionario: Mapped[Peticionario] = relationship()


class CambioPeticionario(Base):
    """CU-003 — Paso de una necesidad en curso a otro peticionario al dar de baja definitiva al
    que la llevaba."""

    __tablename__ = "cambios_peticionario"

    id: Mapped[int] = mapped_column(primary_key=True)
    necesidad_id: Mapped[int] = mapped_column(ForeignKey("necesidades.id"))
    peticionario_anterior_id: Mapped[int] = mapped_column(ForeignKey("peticionarios.id"))
    peticionario_nuevo_id: Mapped[int] = mapped_column(ForeignKey("peticionarios.id"))
    cambiado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    necesidad: Mapped[Necesidad] = relationship(back_populates="cambios_peticionario")
    peticionario_anterior: Mapped[Peticionario] = relationship(
        foreign_keys=[peticionario_anterior_id]
    )
    peticionario_nuevo: Mapped[Peticionario] = relationship(foreign_keys=[peticionario_nuevo_id])


class ProveedorSolicitado(Base):
    """CU-002 — Proveedores a los que se pidió oferta (van en CCO en el .eml)."""

    __tablename__ = "proveedores_solicitados"

    necesidad_id: Mapped[int] = mapped_column(ForeignKey("necesidades.id"), primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"), primary_key=True)
    solicitado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    necesidad: Mapped[Necesidad] = relationship(back_populates="solicitados")
    proveedor: Mapped[Proveedor] = relationship()


class Retraso(Base):
    """CU-008 — Cada retraso de la entrega con su motivo. Solo en «Pendiente entrega»; el
    proveedor es el de la oferta adjudicada (histórico de retrasos por proveedor, CU-010)."""

    __tablename__ = "retrasos"

    id: Mapped[int] = mapped_column(primary_key=True)
    necesidad_id: Mapped[int] = mapped_column(ForeignKey("necesidades.id"))
    fecha_anterior: Mapped[date] = mapped_column(Date)
    fecha_nueva: Mapped[date] = mapped_column(Date)
    motivo: Mapped[str] = mapped_column(Text)
    peticionario_id: Mapped[int] = mapped_column(ForeignKey("peticionarios.id"))
    registrado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    necesidad: Mapped[Necesidad] = relationship(back_populates="retrasos")
    peticionario: Mapped[Peticionario] = relationship()


class CodigoBorrado(Base):
    """ADR 0015: códigos de las necesidades borradas con el modo admin. No se vuelven a
    usar: los correos ya enviados con ese código apuntarían a otra necesidad."""

    __tablename__ = "codigos_borrados"

    codigo: Mapped[str] = mapped_column(String(10), primary_key=True)
    borrado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
