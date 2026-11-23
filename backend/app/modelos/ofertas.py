"""CU-004 — Ofertas de los proveedores y sus líneas (modelo de datos).

Importes como número decimal exacto (nunca coma flotante). Precios unitarios e importe total,
siempre sin IVA. Las ofertas no se borran: se marcan como
`sustituida` (llegó otra del mismo proveedor) o `borrada`.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.base_de_datos import Base
from app.modelos.listas import Proveedor
from app.modelos.necesidades import Adjunto, Necesidad, _solo

ESTADOS_OFERTA = ("vigente", "sustituida", "borrada")


class Oferta(Base):
    __tablename__ = "ofertas"
    __table_args__ = (
        CheckConstraint(_solo(ESTADOS_OFERTA, "estado_oferta"), name="estado_oferta_valido"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    necesidad_id: Mapped[int] = mapped_column(ForeignKey("necesidades.id"))
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"))
    # Fecha de envío del correo del proveedor (cabecera Date del .eml): de ella se cuenta el plazo.
    fecha_correo: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remitente: Mapped[str | None] = mapped_column(String(254))
    asunto: Mapped[str | None] = mapped_column(String(500))
    registrada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    numero_oferta: Mapped[str | None] = mapped_column(String(100))
    # Código de la moneda de los totales y los precios unitarios (EUR, USD…); EUR por defecto. Sin
    # conversiones: si las ofertas vienen en monedas distintas, convierte el ingeniero (ADR 0010).
    moneda: Mapped[str | None] = mapped_column(String(3), default="EUR")
    importe_sin_iva: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    plazo_entrega_texto: Mapped[str | None] = mapped_column(String(200))
    fecha_entrega_estimada: Mapped[date | None] = mapped_column(Date)
    condiciones_pago: Mapped[str | None] = mapped_column(Text)
    # Información adicional que no encaja en las condiciones.
    otros: Mapped[str | None] = mapped_column(Text)
    # Las nueve condiciones de la oferta, {clave: {estado, texto}}
    # (`app/servicios/condiciones.py`). Vacío: todas «No especificado».
    condiciones: Mapped[dict | None] = mapped_column(JSONB)
    # Respuesta original de la IA, para revisar después qué propuso (CU-004).
    datos_ia: Mapped[dict | None] = mapped_column(JSONB)
    revisada: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    estado_oferta: Mapped[str] = mapped_column(
        String(12), default="vigente", server_default="vigente"
    )

    necesidad: Mapped[Necesidad] = relationship(foreign_keys=[necesidad_id])
    proveedor: Mapped[Proveedor] = relationship()
    lineas: Mapped[list[LineaOferta]] = relationship(
        back_populates="oferta", order_by="LineaOferta.orden", cascade="all, delete-orphan"
    )
    archivos: Mapped[list[Adjunto]] = relationship(order_by="Adjunto.id")


class LineaOferta(Base):
    __tablename__ = "lineas_oferta"

    id: Mapped[int] = mapped_column(primary_key=True)
    oferta_id: Mapped[int] = mapped_column(ForeignKey("ofertas.id"))
    orden: Mapped[int] = mapped_column(Integer)
    # Short Text de SAP: sin límite de longitud.
    descripcion: Mapped[str] = mapped_column(Text)
    cantidad: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    fecha_entrega: Mapped[date | None] = mapped_column(Date)
    # Plazo de la línea tal como lo da el proveedor («18 - 20 días»), si da un plazo y no una
    # fecha: la fecha se cuenta desde el correo y, al adjudicar, desde el día del pedido
    # (CU-004).
    plazo_entrega_texto: Mapped[str | None] = mapped_column(String(200))

    oferta: Mapped[Oferta] = relationship(back_populates="lineas")
