"""CU-009 — Recordatorio de entrega. El servidor SMTP se simula: nunca se envía un correo real."""

import smtplib
from dataclasses import replace
from datetime import date
from email import message_from_bytes
from email.policy import default
from typing import ClassVar

import pytest

from app.integraciones import correo_saliente
from app.integraciones.correo_saliente import ErrorCorreo
from app.modelos.necesidades import Necesidad
from app.servicios import recordatorios
from tests.test_adjudicacion import adjudicacion, datos, url  # noqa: F401
from tests.test_entrega import pendiente_entrega, retraso  # noqa: F401
from tests.test_pedido_sap_envio import enviar, pendiente_pedido  # noqa: F401

pytestmark = pytest.mark.usefixtures("limpiar")

PREVISTA = date(2026, 11, 20)  # la de `pendiente_entrega`


class SmtpFalso:
    """Sustituye a smtplib.SMTP: guarda los mensajes; rechaza los destinatarios de `rechazar`."""

    enviados: ClassVar[list] = []
    rechazar: ClassVar[set] = set()
    starttls_llamado = False

    def __init__(self, host, puerto, timeout=None):
        self.host, self.puerto = host, puerto

    def starttls(self, context=None):
        SmtpFalso.starttls_llamado = True

    def login(self, usuario, contrasena):
        pass

    def send_message(self, mensaje):
        if mensaje["To"] in SmtpFalso.rechazar:
            raise smtplib.SMTPRecipientsRefused({mensaje["To"]: (550, b"no existe")})
        SmtpFalso.enviados.append(mensaje)

    def quit(self):
        pass


@pytest.fixture
def smtp(monkeypatch):
    SmtpFalso.enviados, SmtpFalso.rechazar, SmtpFalso.starttls_llamado = [], set(), False
    monkeypatch.setattr(correo_saliente.smtplib, "SMTP", SmtpFalso)
    return SmtpFalso


@pytest.fixture
def config(app):
    return replace(
        app.config["REMATE"],
        smtp_host="smtp.ejemplo.test",
        smtp_port=587,
        smtp_from="ReMate <remate@empresa.test>",
        app_url="http://remate.local:5000",
    )


def ejecutar(app, config, hoy, **opciones):
    with app.extensions["remate.sesiones"]() as sesion:
        return recordatorios.enviar_recordatorios(sesion, config, hoy, **opciones)


def recordatorio_de(app, datos):  # noqa: F811
    with app.extensions["remate.sesiones"]() as sesion:
        return sesion.get(Necesidad, datos["necesidad"]).recordatorio_enviado_en


def test_se_envia_a_7_dias_y_solo_una_vez(app, config, smtp, pendiente_entrega):  # noqa: F811
    # A 8 días, todavía no.
    assert ejecutar(app, config, date(2026, 11, 12)).enviados == []
    resumen = ejecutar(app, config, date(2026, 11, 13))
    assert len(resumen.enviados) == 1
    assert resumen.fallidos == []
    assert smtp.starttls_llamado
    [mensaje] = smtp.enviados
    assert mensaje["To"] == "ana@ejemplo.test"
    assert mensaje["From"] == "ReMate <remate@empresa.test>"
    # El mismo asunto que los demás correos de la necesidad.
    codigo = pendiente_entrega_codigo(app, pendiente_entrega)
    assert mensaje["Subject"].startswith(f"{codigo} | ")
    assert "Entrega prevista" not in mensaje["Subject"]
    cuerpo = mensaje.get_content()
    assert "Hola, Ana Prueba:" in cuerpo
    assert "entrega prevista el 20/11/2026 (dentro de 7 días)" in cuerpo
    assert "Proveedor: FICMEC (ofertas@ficmec.test)" in cuerpo
    assert "Pedido SAP: 4500012345" in cuerpo
    assert f"http://remate.local:5000/necesidades/{pendiente_entrega['necesidad']}" in cuerpo
    assert recordatorio_de(app, pendiente_entrega) is not None
    # Una segunda ejecución el mismo día no envía nada.
    assert ejecutar(app, config, date(2026, 11, 13)).enviados == []
    assert len(smtp.enviados) == 1


def test_fecha_ya_pasada_tambien_se_avisa(app, config, smtp, pendiente_entrega):  # noqa: F811
    ejecutar(app, config, date(2026, 11, 23))
    assert "hace 3 días: la fecha ya ha pasado" in smtp.enviados[0].get_content()


def test_un_retraso_vuelve_a_armar_el_recordatorio(cliente, app, config, smtp, pendiente_entrega):  # noqa: F811
    ejecutar(app, config, date(2026, 11, 13))
    assert retraso(cliente, pendiente_entrega, fecha_nueva="2026-11-27").status_code == 200
    assert recordatorio_de(app, pendiente_entrega) is None
    # Respecto a la nueva fecha: a 8 días no, a 7 sí.
    assert ejecutar(app, config, date(2026, 11, 19)).enviados == []
    assert len(ejecutar(app, config, date(2026, 11, 20)).enviados) == 1
    assert "entrega prevista el 27/11/2026" in smtp.enviados[-1].get_content()


def test_ni_entregadas_ni_canceladas(app, config, smtp, pendiente_entrega):  # noqa: F811
    with app.extensions["remate.sesiones"]() as sesion:
        sesion.get(Necesidad, pendiente_entrega["necesidad"]).estado = "entregado"
        sesion.commit()
    assert ejecutar(app, config, date(2026, 11, 20)).enviados == []
    with app.extensions["remate.sesiones"]() as sesion:
        sesion.get(Necesidad, pendiente_entrega["necesidad"]).estado = "cancelada"
        sesion.commit()
    assert ejecutar(app, config, date(2026, 11, 20)).enviados == []


def test_si_falla_el_envio_no_se_marca(app, config, smtp, pendiente_entrega):  # noqa: F811
    smtp.rechazar = {"ana@ejemplo.test"}
    resumen = ejecutar(app, config, date(2026, 11, 13))
    assert resumen.enviados == []
    assert [codigo for codigo, _ in resumen.fallidos] == [
        pendiente_entrega_codigo(app, pendiente_entrega)
    ]
    assert recordatorio_de(app, pendiente_entrega) is None


def pendiente_entrega_codigo(app, datos):  # noqa: F811
    with app.extensions["remate.sesiones"]() as sesion:
        return sesion.get(Necesidad, datos["necesidad"]).codigo


def test_modo_prueba_guarda_eml_y_no_marca(app, config, smtp, pendiente_entrega):  # noqa: F811
    sin_smtp = replace(config, smtp_host="", smtp_from="")
    resumen = ejecutar(app, sin_smtp, date(2026, 11, 13), prueba=True)
    codigo = pendiente_entrega_codigo(app, pendiente_entrega)
    assert resumen.enviados == [codigo]
    assert smtp.enviados == []
    archivo = sin_smtp.archivos_dir / recordatorios.CARPETA_PRUEBA / f"{codigo}.eml"
    mensaje = message_from_bytes(archivo.read_bytes(), policy=default)
    assert mensaje["To"] == "ana@ejemplo.test"
    assert recordatorio_de(app, pendiente_entrega) is None


def test_sin_configurar_no_envia(app, config, smtp, pendiente_entrega):  # noqa: F811
    with pytest.raises(ErrorCorreo, match="SMTP_HOST"):
        ejecutar(app, replace(config, smtp_host=""), date(2026, 11, 13))
    assert recordatorio_de(app, pendiente_entrega) is None


def test_el_detalle_muestra_el_recordatorio(cliente, app, config, smtp, pendiente_entrega):  # noqa: F811
    assert (
        cliente.get(f"/api/necesidades/{pendiente_entrega['necesidad']}").json[
            "recordatorio_enviado_en"
        ]
        is None
    )
    ejecutar(app, config, date(2026, 11, 13))
    detalle = cliente.get(f"/api/necesidades/{pendiente_entrega['necesidad']}").json
    assert detalle["recordatorio_enviado_en"] is not None


def test_comando(app, pendiente_entrega):  # noqa: F811
    """Sin recordatorios pendientes hoy (la entrega es en noviembre): termina bien y lo dice."""
    salida = app.test_cli_runner().invoke(args=["enviar-recordatorios", "--prueba"])
    assert salida.exit_code == 0, salida.output
    assert "Prueba:" in salida.output


def test_no_envia_la_contrasena_sin_cifrar(app, config, smtp, pendiente_entrega):  # noqa: F811
    """Con usuario y sin TLS, la contraseña viajaría en claro."""
    sin_tls = replace(config, smtp_secure=False, smtp_user="remate", smtp_password="x")
    with pytest.raises(ErrorCorreo, match="cifr"):
        ejecutar(app, sin_tls, date(2026, 11, 13))


def test_los_fallidos_no_llevan_el_correo_del_peticionario(app, config, smtp, pendiente_entrega):  # noqa: F811
    """La salida del comando acaba en el log del planificador."""
    smtp.rechazar = {"ana@ejemplo.test"}
    [(_, motivo)] = ejecutar(app, config, date(2026, 11, 13)).fallidos
    assert "ana@ejemplo.test" not in motivo
    assert "SMTPRecipientsRefused" in motivo


def test_un_retraso_mientras_se_envia_no_se_pisa(app, config, smtp, pendiente_entrega, monkeypatch):  # noqa: F811
    """Si se registra un retraso entre la consulta y el envío, no se
    envía el aviso de la fecha antigua ni se marca como enviado el de la nueva."""
    consultar = recordatorios.pendientes

    def pendientes_y_retraso(sesion, hoy):
        encontradas = consultar(sesion, hoy)
        with app.extensions["remate.sesiones"]() as otra:
            necesidad = otra.get(Necesidad, pendiente_entrega["necesidad"])
            necesidad.fecha_entrega_prevista = date(2026, 11, 27)
            necesidad.recordatorio_enviado_en = None
            otra.commit()
        return encontradas

    monkeypatch.setattr(recordatorios, "pendientes", pendientes_y_retraso)
    resumen = ejecutar(app, config, date(2026, 11, 13))
    assert resumen.enviados == []
    assert smtp.enviados == []
    assert recordatorio_de(app, pendiente_entrega) is None


def test_peticionario_dado_de_baja_no_se_envia_y_se_avisa(app, config, smtp, pendiente_entrega):  # noqa: F811
    """Si el peticionario está desactivado o eliminado, su
    buzón puede no existir; no se envía, no se marca y el comando lo avisa."""
    from app.modelos.listas import Peticionario

    with app.extensions["remate.sesiones"]() as sesion:
        sesion.get(Peticionario, pendiente_entrega["ana"]).activo = False
        sesion.commit()
    resumen = ejecutar(app, config, date(2026, 11, 13))
    assert resumen.enviados == []
    assert smtp.enviados == []
    [(_, motivo)] = resumen.omitidos
    assert "Ana Prueba" in motivo
    assert "dado de baja" in motivo
    assert recordatorio_de(app, pendiente_entrega) is None
