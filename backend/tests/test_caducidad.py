"""Caducidad de los archivos de las necesidades cerradas y de la tabla `logs` (ADR 0014)."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.integraciones import archivos
from app.modelos.logs import Log
from app.modelos.necesidades import Adjunto, Necesidad
from app.servicios import caducidad
from tests.test_adjudicacion import adjudicacion, datos, url  # noqa: F401
from tests.test_entrega import hoy, pendiente_entrega  # noqa: F401
from tests.test_pedido_sap_envio import enviar, pendiente_pedido  # noqa: F401

pytestmark = pytest.mark.usefixtures("limpiar")

CIERRE = datetime(2026, 1, 10, 9, tzinfo=UTC)


@pytest.fixture
def entregada(app, cliente, pendiente_entrega, hoy):  # noqa: F811
    """Necesidad entregada el 2026-01-10, con un plano propio en el disco."""
    hoy(date(2026, 11, 19))
    respuesta = cliente.post(
        url(pendiente_entrega, "/entrega"), json={"peticionario_id": pendiente_entrega["ana"]}
    )
    assert respuesta.status_code == 200, respuesta.json
    raiz = app.config["REMATE"].archivos_dir
    with app.extensions["remate.sesiones"]() as sesion:
        necesidad = sesion.get(Necesidad, pendiente_entrega["necesidad"])
        necesidad.historial[-1].cambiado_en = CIERRE
        ruta = archivos.guardar(raiz, necesidad.codigo, "plano.step", b"plano")
        sesion.add(
            Adjunto(
                necesidad=necesidad,
                tipo="necesidad",
                nombre_archivo="plano.step",
                ruta=ruta,
                tipo_mime="application/octet-stream",
                tamano=5,
            )
        )
        sesion.commit()
    return pendiente_entrega


def adjuntos(app, datos):  # noqa: F811
    with app.extensions["remate.sesiones"]() as sesion:
        return [
            (a.tipo, a.caducado_en, a.ruta)
            for a in sesion.scalars(
                select(Adjunto).where(Adjunto.necesidad_id == datos["necesidad"])
            )
        ]


def caducar(app, dia, **opciones):
    with app.extensions["remate.sesiones"]() as sesion:
        return caducidad.caducar(sesion, app.config["REMATE"].archivos_dir, dia, **opciones)


def test_documentos_a_los_6_meses_y_planos_a_los_24(app, cliente, entregada):
    raiz = app.config["REMATE"].archivos_dir
    antes = adjuntos(app, entregada)
    tipos = {tipo for tipo, _, _ in antes}
    assert {"necesidad", "solicitud", "adjudicacion", "pedido_sap", "envio_pedido"} <= tipos
    # El día antes de cumplir 6 meses, nada.
    assert caducar(app, date(2026, 7, 9)).archivos == 0
    resumen = caducar(app, date(2026, 7, 10))
    despues = adjuntos(app, entregada)
    assert resumen.archivos == len(antes) - 1
    assert resumen.no_borrados == 0
    for tipo, caducado_en, ruta in despues:
        if tipo == "necesidad":
            assert caducado_en is None
            assert archivos.ruta_absoluta(raiz, ruta).is_file()
        else:
            assert caducado_en is not None
            assert not archivos.ruta_absoluta(raiz, ruta).exists()
    # La necesidad conserva sus datos; lo caducado se marca y su descarga responde 410.
    detalle = cliente.get(f"/api/necesidades/{entregada['necesidad']}").json
    assert detalle["estado"] == "entregado"
    assert detalle["pedido_sap"]["caducado"] is True
    assert [a["caducado"] for a in detalle["adjuntos"]] == [False]
    descarga = cliente.get(url(entregada, "/pedido-sap.eml"))
    assert descarga.status_code == 410
    assert descarga.json["error"] == "archivo_caducado"
    # El plano, a los 24 meses.
    assert caducar(app, date(2028, 1, 9)).archivos == 0
    assert caducar(app, date(2028, 1, 10)).archivos == 1
    plano = detalle["adjuntos"][0]["id"]
    assert cliente.get(url(entregada, f"/adjuntos/{plano}")).status_code == 410


def test_modo_prueba_no_borra(app, entregada):
    resumen = caducar(app, date(2026, 7, 10), prueba=True)
    assert resumen.archivos > 0
    assert resumen.bytes > 0
    assert all(c is None for _, c, _ in adjuntos(app, entregada))


def test_las_necesidades_abiertas_no_caducan(app, pendiente_entrega):  # noqa: F811
    assert caducar(app, date(2030, 1, 1)).archivos == 0


def test_si_no_se_puede_borrar_del_disco_se_avisa(app, entregada, monkeypatch):
    def falla(raiz, ruta):
        raise PermissionError("en uso")

    monkeypatch.setattr(caducidad.archivos, "borrar", falla)
    resumen = caducar(app, date(2026, 7, 10))
    assert resumen.no_borrados == resumen.archivos > 0
    # Se queda marcado: nunca una fila que apunte a un archivo que ya no está.
    assert all(c is not None for t, c, _ in adjuntos(app, entregada) if t != "necesidad")


def test_los_logs_se_guardan_6_meses(app):
    with app.extensions["remate.sesiones"]() as sesion:
        for dia in (datetime(2026, 5, 16, 21, tzinfo=UTC), datetime(2026, 5, 17, 9, tzinfo=UTC)):
            sesion.add(Log(creado_en=dia, nivel="INFO", origen="prueba", mensaje="x"))
        sesion.commit()
    # Hoy, 17/11/2026: se borra lo anterior al 17/05/2026 (hora de España).
    assert caducar(app, date(2026, 11, 17), prueba=True).logs == 1
    assert caducar(app, date(2026, 11, 17)).logs == 1
    with app.extensions["remate.sesiones"]() as sesion:
        quedan = sesion.scalars(select(Log.creado_en).where(Log.origen == "prueba")).all()
    assert len(quedan) == 1


def test_el_comando_diario_aplica_la_caducidad(app, entregada, monkeypatch):
    monkeypatch.setattr(caducidad, "MESES_DOCUMENTOS", 0)
    documentos = sum(1 for t, _, _ in adjuntos(app, entregada) if t != "necesidad")
    salida = app.test_cli_runner().invoke(args=["enviar-recordatorios", "--prueba"])
    assert salida.exit_code == 0, salida.output
    assert f"Caducidad: Se borrarían {documentos} archivo(s)" in salida.output
    # En prueba no se borra nada.
    assert all(c is None for _, c, _ in adjuntos(app, entregada))


# --- Casos límite --------------------------------------------------------------------------------


def test_lo_que_no_se_pudo_borrar_se_reintenta(app, entregada, monkeypatch):
    """Un archivo abierto (descarga, antivirus, copia) no se puede borrar en Windows: antes se
    quedaba en el disco para siempre."""
    raiz = app.config["REMATE"].archivos_dir
    original = caducidad.archivos.borrar

    def falla(raiz, ruta):
        raise PermissionError("en uso")

    monkeypatch.setattr(caducidad.archivos, "borrar", falla)
    primera = caducar(app, date(2026, 7, 10))
    assert primera.no_borrados == primera.archivos > 0
    monkeypatch.setattr(caducidad.archivos, "borrar", original)
    segunda = caducar(app, date(2026, 7, 11))
    assert segunda.archivos == 0
    assert segunda.reintentados == primera.no_borrados
    assert segunda.no_borrados == 0
    for tipo, _, ruta in adjuntos(app, entregada):
        if tipo != "necesidad":
            assert not archivos.ruta_absoluta(raiz, ruta).exists()


def test_dos_ejecuciones_a_la_vez_no_cuentan_lo_mismo(app, entregada):
    with app.extensions["remate.sesiones"]() as primera:
        bloqueados = caducidad.caducados(primera, date(2026, 7, 10), bloquear=True)
        assert bloqueados
        # Mientras la primera los tiene, la segunda no los ve.
        assert caducar(app, date(2026, 7, 10)).archivos == 0
        primera.rollback()
    assert caducar(app, date(2026, 7, 10)).archivos == len(bloqueados)


def test_si_los_avisos_fallan_con_la_base_de_datos_sigue_lo_demas(app, entregada, monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app.servicios import avisos_pedido_sap

    def falla(*a, **k):
        raise OperationalError("SELECT", {}, Exception("se ha caído"))

    monkeypatch.setattr(caducidad, "MESES_DOCUMENTOS", 0)
    monkeypatch.setattr(avisos_pedido_sap, "enviar_pendientes", falla)
    salida = app.test_cli_runner().invoke(args=["enviar-recordatorios", "--prueba"])
    assert salida.exit_code == 1
    assert "recordatorio(s) guardados" in salida.output
    assert "No se ha enviado ningún aviso del pedido SAP" in salida.output
    assert "Caducidad: Se borrarían" in salida.output
