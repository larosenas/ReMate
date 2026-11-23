"""Modelos de SQLAlchemy. Importarlos aquí los registra en Base.metadata (Alembic y pruebas)."""

from app.modelos.listas import AvisadoPedidoSap, Peticionario, Proveedor
from app.modelos.logs import Log
from app.modelos.necesidades import (
    Adjunto,
    CambioEstado,
    CambioPeticionario,
    CodigoBorrado,
    Necesidad,
    ProveedorSolicitado,
    Retraso,
)
from app.modelos.ofertas import LineaOferta, Oferta

__all__ = [
    "Adjunto",
    "AvisadoPedidoSap",
    "CambioEstado",
    "CambioPeticionario",
    "CodigoBorrado",
    "LineaOferta",
    "Log",
    "Necesidad",
    "Oferta",
    "Peticionario",
    "Proveedor",
    "ProveedorSolicitado",
    "Retraso",
]
