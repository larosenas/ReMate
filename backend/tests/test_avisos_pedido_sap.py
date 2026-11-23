"""Aviso del paso 5 (pedido en SAP) y su recordatorio semanal (CU-006). El servidor SMTP se
simula: nunca se envía un correo real."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from email import message_from_bytes
from email.policy import default

import pytest

from app import fechas
from app.modelos.necesidades import Necesidad
from app.servicios import avisos_pedido_sap
from tests.test_adjudicacion import adjudicacion, datos, url  # noqa: F401
from tests.test_pedido_sap_envio import enviar
from tests.test_recordatorios import config, smtp  # noqa: F401

pytestmark = pytest.mark.usefixtures("limpiar")

AVISADOS = "/api/avisados-pedido-sap"


@pytest.fixture
def con_smtp(app, config, monkeypatch):  # noqa: F811
    """La aplicación usa la configuración con SMTP (la de las pruebas no tiene)."""
    monkeypatch.setitem(app.config, "REMATE", config)
    return config


@pytest.fixture
def avisados(cliente):
    """Óscar y Carmen activos; Marcos, desactivado (no recibe nada)."""
    ids = []
    for nombre, email in (
        ("Óscar Prueba", "oscar@empresa.example"),
        ("Carmen Prueba", "carmen@empresa.example"),
        ("Marcos Prueba", "marcos@empresa.example"),
    ):
        respuesta = cliente.post(AVISADOS, json={"nombre": nombre, "email": email})
        assert respuesta.status_code == 201, respuesta.json
        ids.append(respuesta.json["id"])
    assert cliente.patch(f"{AVISADOS}/{ids[2]}", json={"activo": False}).status_code == 200
    return ids


def confirmar_paso_5(cliente, datos):  # noqa: F811
    assert cliente.post(url(datos, "/adjudicacion"), json=adjudicacion(datos)).status_code == 200
    respuesta = cliente.post(
        url(datos, "/pedido-en-sap"),
        json={"peticionario_id": datos["ana"], "fecha_entrega_prevista": "2026-11-20"},
    )
    assert respuesta.status_code == 200, respuesta.json
    return respuesta.json


def aviso_de(app, datos):  # noqa: F811
    with app.extensions["remate.sesiones"]() as sesion:
        return sesion.get(Necesidad, datos["necesidad"]).aviso_pedido_sap_en


def ejecutar(app, config, hoy, **opciones):  # noqa: F811
    with app.extensions["remate.sesiones"]() as sesion:
        return avisos_pedido_sap.enviar_pendientes(sesion, config, hoy, **opciones)


def test_al_confirmar_el_paso_5_se_avisa_al_momento(cliente, app, con_smtp, smtp, datos, avisados):  # noqa: F811
    necesidad = confirmar_paso_5(cliente, datos)
    assert necesidad["avisos"] == []
    assert necesidad["aviso_pedido_sap_en"] is not None
    [mensaje] = smtp.enviados
    assert mensaje["To"] == "carmen@empresa.example, oscar@empresa.example"
    assert mensaje["From"] == "ReMate <remate@empresa.test>"
    assert mensaje["Subject"].startswith(f"{necesidad['codigo']} | ")
    cuerpo = mensaje.get_content()
    assert "Se ha metido en SAP la solicitud de compra de la necesidad" in cuerpo
    assert "(paso 6 en ReMate)" in cuerpo
    assert "Proveedor adjudicado: FICMEC (ofertas@ficmec.test)" in cuerpo
    assert "Fecha de entrega prevista: 20/11/2026" in cuerpo
    assert "Paso 5 confirmado por: Ana Prueba" in cuerpo
    assert f"http://remate.local:5000/necesidades/{datos['necesidad']}" in cuerpo
    # La tarea diaria de hoy no lo repite.
    assert ejecutar(app, con_smtp, fechas.hoy()).enviados == []


def test_sin_avisados_no_se_envia_y_se_dice(cliente, app, con_smtp, smtp, datos):  # noqa: F811
    necesidad = confirmar_paso_5(cliente, datos)
    assert necesidad["avisos"] == [avisos_pedido_sap.AVISO_SIN_AVISADOS]
    assert necesidad["estado"] == "pendiente_pedido_sap"
    assert smtp.enviados == []
    assert aviso_de(app, datos) is None
    resumen = ejecutar(app, con_smtp, fechas.hoy())
    assert resumen.sin_avisados
    assert resumen.enviados == []


def test_si_falla_el_correo_se_reintenta_cada_dia(cliente, app, config, smtp, datos, avisados):  # noqa: F811
    # La configuración de las pruebas no tiene SMTP: el paso 5 se confirma igual y se avisa.
    necesidad = confirmar_paso_5(cliente, datos)
    assert necesidad["estado"] == "pendiente_pedido_sap"
    assert necesidad["avisos"] == [avisos_pedido_sap.AVISO_NO_ENVIADO]
    assert aviso_de(app, datos) is None
    resumen = ejecutar(app, config, fechas.hoy())
    assert len(resumen.enviados) == 1
    assert "Se ha metido en SAP" in smtp.enviados[0].get_content()
    assert aviso_de(app, datos) is not None


def test_recordatorio_cada_semana_hasta_el_paso_6(cliente, app, con_smtp, smtp, datos, avisados):  # noqa: F811
    confirmar_paso_5(cliente, datos)
    with app.extensions["remate.sesiones"]() as sesion:
        necesidad = sesion.get(Necesidad, datos["necesidad"])
        necesidad.aviso_pedido_sap_en = datetime(2026, 11, 2, 9, tzinfo=UTC)
        necesidad.historial[-1].cambiado_en = datetime(2026, 11, 2, 9, tzinfo=UTC)
        sesion.commit()
    assert ejecutar(app, con_smtp, date(2026, 11, 8)).enviados == []
    assert len(ejecutar(app, con_smtp, date(2026, 11, 9)).enviados) == 1
    cuerpo = smtp.enviados[-1].get_content()
    assert "sigue pendiente del pedido en SAP desde el 02/11/2026 (7 días)" in cuerpo
    # El envío se marca con la hora real: se pone la del día 9 para seguir con las fechas fijas.
    with app.extensions["remate.sesiones"]() as sesion:
        sesion.get(Necesidad, datos["necesidad"]).aviso_pedido_sap_en = datetime(
            2026, 11, 9, 9, tzinfo=UTC
        )
        sesion.commit()
    # El mismo día, no; la semana siguiente, otra vez.
    assert ejecutar(app, con_smtp, date(2026, 11, 9)).enviados == []
    assert len(ejecutar(app, con_smtp, date(2026, 11, 16)).enviados) == 1
    # Con el pedido enviado al proveedor (paso 6) ya no hay más.
    assert enviar(cliente, datos).status_code == 200
    assert ejecutar(app, con_smtp, date(2026, 11, 30)).enviados == []


def test_modo_prueba_y_comando(cliente, app, config, smtp, datos, avisados):  # noqa: F811
    confirmar_paso_5(cliente, datos)
    sin_smtp = replace(config, smtp_host="", smtp_from="")
    resumen = ejecutar(app, sin_smtp, fechas.hoy(), prueba=True)
    [codigo] = resumen.enviados
    archivo = sin_smtp.archivos_dir / avisos_pedido_sap.CARPETA_PRUEBA / f"{codigo}-pedido-sap.eml"
    mensaje = message_from_bytes(archivo.read_bytes(), policy=default)
    assert mensaje["To"] == "carmen@empresa.example, oscar@empresa.example"
    assert aviso_de(app, datos) is None
    salida = app.test_cli_runner().invoke(args=["enviar-recordatorios", "--prueba"])
    assert salida.exit_code == 0, salida.output
    assert "Avisos del pedido SAP: 1" in salida.output


def test_lista_de_avisados(cliente, avisados):
    activos = cliente.get(AVISADOS).json
    assert [a["nombre"] for a in activos] == ["Carmen Prueba", "Óscar Prueba"]
    todos = cliente.get(AVISADOS, query_string={"incluir_inactivos": "true"}).json
    assert len(todos) == 3
    duplicado = cliente.post(AVISADOS, json={"nombre": "Otro", "email": "OSCAR@empresa.example"})
    assert duplicado.status_code == 409
    baja = cliente.post(f"{AVISADOS}/{avisados[2]}/baja", json={"motivo": "Registro duplicado"})
    assert baja.status_code == 204
    assert len(cliente.get(AVISADOS, query_string={"incluir_inactivos": "true"}).json) == 2


def test_un_dia_antes_no_toca():
    hace_6 = datetime.now(UTC) - timedelta(days=6)
    necesidad = Necesidad(aviso_pedido_sap_en=hace_6)
    assert not avisos_pedido_sap.toca(necesidad, fechas.hoy())
    assert avisos_pedido_sap.toca(Necesidad(), fechas.hoy())


# --- Casos límite --------------------------------------------------------------------------------


def _dos_en_el_paso_5(cliente, app, datos):  # noqa: F811
    """La necesidad de `datos` y otra copia de ella, las dos en el paso 5 sin avisar."""
    confirmar_paso_5(cliente, datos)
    with app.extensions["remate.sesiones"]() as sesion:
        original = sesion.get(Necesidad, datos["necesidad"])
        otra = Necesidad(
            codigo="2026111799",
            titulo="Otra",
            proyecto="Línea 1",
            descripcion="d",
            estado="pendiente_pedido_sap",
            peticionario_id=datos["ana"],
            oferta_adjudicada_id=original.oferta_adjudicada_id,
        )
        sesion.add(otra)
        sesion.commit()


def test_aviso_una_sola_vez(cliente, app, config, smtp, datos, avisados, monkeypatch):  # noqa: F811
    """Tras un rollback, la otra necesidad se recarga con el valor que acaba de guardar la otra
    ejecución y la guarda no deja pasar el envío."""
    _dos_en_el_paso_5(cliente, app, datos)
    original = avisos_pedido_sap._mensaje
    hecho = []

    def mensaje(c, n, para, hoy):
        if not hecho:
            hecho.append(True)
            with app.extensions["remate.sesiones"]() as otra:
                avisos_pedido_sap.enviar_pendientes(otra, config, hoy)
        return original(c, n, para, hoy)

    monkeypatch.setattr(avisos_pedido_sap, "_mensaje", mensaje)
    with app.extensions["remate.sesiones"]() as sesion:
        resumen = avisos_pedido_sap.enviar_pendientes(sesion, config, fechas.hoy())
    # Cada necesidad, una sola vez entre las dos ejecuciones.
    assert len(resumen.enviados) <= 1
    assert len(smtp.enviados) == 2
    assert len({m["Subject"] for m in smtp.enviados}) == 2


def test_destinatario_rechazado(cliente, app, config, smtp, datos, avisados, monkeypatch):  # noqa: F811
    """Con varios en el «Para», el servidor puede rechazar a uno y aceptar a los demás sin lanzar
    excepción: el rechazado no se pierde sin aviso."""
    confirmar_paso_5(cliente, datos)

    def con_rechazo(self, mensaje):
        smtp.enviados.append(mensaje)
        return {"carmen@empresa.example": (550, b"no existe")}

    monkeypatch.setattr(smtp, "send_message", con_rechazo)
    resumen = ejecutar(app, config, fechas.hoy())
    assert len(resumen.enviados) == 1
    [(_, motivo)] = resumen.rechazados
    assert motivo == "1 destinatario rechazado"
    assert "carmen" not in motivo


def test_un_avisado_con_tilde_en_el_correo_no_se_acepta(cliente, avisados):
    """Un servidor sin SMTPUTF8 rechaza el mensaje entero y no le llega a nadie."""
    respuesta = cliente.post(AVISADOS, json={"nombre": "José", "email": "josé@empresa.example"})
    assert respuesta.status_code == 400
    assert respuesta.json["detalles"] == {"campo": "email"}
    assert "tildes" in respuesta.json["mensaje"]
    cambio = cliente.patch(f"{AVISADOS}/{avisados[0]}", json={"email": "óscar@empresa.example"})
    assert cambio.status_code == 400


def test_el_comando_separa_recordatorios_y_avisos(app, config, monkeypatch):  # noqa: F811
    """Si fallan los avisos, no dice «No se ha enviado ningún recordatorio» cuando sí se han
    enviado."""
    from app.integraciones.correo_saliente import ErrorCorreo
    from app.servicios import recordatorios

    monkeypatch.setitem(app.config, "REMATE", config)
    monkeypatch.setattr(
        recordatorios,
        "enviar_recordatorios",
        lambda *a, **k: recordatorios.Resumen(enviados=["2026111701"]),
    )

    def falla(*a, **k):
        raise ErrorCorreo("No se puede conectar con el servidor de correo: caído")

    monkeypatch.setattr(avisos_pedido_sap, "enviar_pendientes", falla)
    salida = app.test_cli_runner().invoke(args=["enviar-recordatorios"])
    assert salida.exit_code == 1
    assert "Recordatorios enviados: 1" in salida.output
    assert "No se ha enviado ningún aviso del pedido SAP" in salida.output
    assert "No se ha enviado ningún recordatorio" not in salida.output
