"""ADR 0008 — Registro de la aplicación (logs) en la base de datos, con respaldo en archivo."""

import io
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError

from app import create_app, registro
from app.modelos.listas import Proveedor
from app.modelos.logs import Log

pytestmark = pytest.mark.usefixtures("limpiar")


def actual():
    # Con varias create_app en las pruebas (test_frontend), vale el registro de la última.
    return registro.activo(logging.getLogger("app"))


def registros(app):
    actual().esperar()
    with app.extensions["remate.sesiones"]() as s:
        return s.scalars(select(Log).order_by(Log.id)).all()


def test_la_informacion_de_la_api_se_guarda_en_la_base_de_datos(app, cliente):
    """No solo los avisos y errores: también la información, como «Necesidad creada»."""
    respuesta = cliente.post("/api/proveedores", json={"nombre": "Acme", "email": "a@acme.example"})
    assert respuesta.status_code == 201
    guardados = [(r.nivel, r.origen, r.mensaje) for r in registros(app)]
    assert ("INFO", "app", f"Alta en proveedores: id {respuesta.json['id']}") in guardados


def test_los_avisos_de_los_modulos_y_su_traza_se_guardan(app):
    log = logging.getLogger("app.integraciones.ia")
    log.warning("La IA ha fallado (%s): %s", 1, "sin conexión")
    try:
        raise ValueError("fallo de prueba")
    except ValueError:
        logging.getLogger("app.servicios.ofertas").exception("Fallo inesperado")
    aviso, error = registros(app)[-2:]
    assert (aviso.nivel, aviso.origen) == ("WARNING", "app.integraciones.ia")
    assert aviso.mensaje == "La IA ha fallado (1): sin conexión"
    assert aviso.traza is None
    assert aviso.creado_en.tzinfo is not None
    assert (error.nivel, error.mensaje) == ("ERROR", "Fallo inesperado")
    assert "ValueError: fallo de prueba" in error.traza


def test_un_mensaje_en_una_transaccion_que_se_deshace_no_se_pierde(app):
    """El mensaje se guarda con su propia conexión: si la petición se deshace, queda guardado."""
    with app.extensions["remate.sesiones"]() as s:
        s.add(Proveedor(nombre="Fantasma", email="f@fantasma.example"))
        s.flush()
        logging.getLogger("app").error("Dentro de una transacción que se deshace")
        s.rollback()
        assert s.scalars(select(Proveedor)).all() == []
    assert registros(app)[-1].mensaje == "Dentro de una transacción que se deshace"


@pytest.mark.parametrize(
    ("args", "esperado"),
    [
        (("Oferta con NUL a\x00b",), "Oferta con NUL a\\x00b"),
        (("Sustituto \udcff suelto",), "Sustituto \\udcff suelto"),
    ],
)
def test_mensajes_raros_se_guardan_igualmente(app, args, esperado):
    """Un NUL, un sustituto suelto o un formato que no cuadra no impiden guardar el mensaje."""
    logging.getLogger("app").info(*args)
    assert registros(app)[-1].mensaje == esperado


def test_un_mensaje_mal_formateado_se_guarda_tal_cual(app):
    """Con argumentos que no cuadran («%s %s» con uno solo), el mensaje no se pierde.
    Se prueba en el manejador: pytest hace fallar sus propios manejadores."""
    mensaje = logging.LogRecord("app", logging.INFO, "", 0, "%s %s", (1,), None)
    actual().manejador.handle(mensaje)
    assert registros(app)[-1].mensaje == "(mensaje mal formateado) '%s %s' (1,)"


def test_las_trazas_no_llevan_los_datos_de_la_consulta(app):
    """Los errores de SQLAlchemy no llevan en la traza los valores de la consulta (importes,
    descripciones de las ofertas)."""
    importe = "".join(["98765", ".43"])  # no aparece tal cual en la línea de la traza
    with app.extensions["remate.sesiones"]() as s:
        try:
            s.execute(text("SELECT CAST(:importe AS numeric(3, 2))"), {"importe": importe})
        except Exception:
            logging.getLogger("app").exception("Fallo al guardar")
    traza = registros(app)[-1].traza
    assert "98765.43" not in traza
    assert "hidden" in traza


def test_las_trazas_no_llevan_los_valores_del_diagnostico_de_postgresql(app):
    """hide_parameters oculta los parámetros, pero el DETAIL de PostgreSQL repite el valor que
    choca (aquí, el correo duplicado): tampoco puede llegar a la traza."""
    correo = "marcador-secreto@proveedor.test"
    with app.extensions["remate.sesiones"]() as s:
        s.add_all([Proveedor(nombre="Uno", email=correo), Proveedor(nombre="Dos", email=correo)])
        try:
            s.commit()
        except Exception:
            logging.getLogger("app").exception("Fallo al guardar")
    traza = registros(app)[-1].traza
    assert "marcador-secreto" not in traza
    assert "UniqueViolation" in traza


def test_una_tabla_bloqueada_no_detiene_las_peticiones(app):
    """Con la tabla bloqueada (por ejemplo, alguien en DBeaver con una transacción abierta), cada
    petición que registra algo no se queda esperando sin límite: el mensaje se deja en una cola
    y sigue."""
    conexion = app.extensions["remate.motor"].connect()
    transaccion = conexion.begin()
    conexion.execute(text("LOCK TABLE logs IN ACCESS EXCLUSIVE MODE"))
    respaldo = io.StringIO()
    manejador = actual().base_de_datos.respaldo
    anterior = manejador.setStream(respaldo)
    try:
        inicio = time.monotonic()
        hilos = [
            threading.Thread(target=logging.getLogger("app").warning, args=(f"bloqueado {n}",))
            for n in range(8)
        ]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(5)
        assert time.monotonic() - inicio < 1  # las 8 «peticiones» siguen sin esperar
        # El hilo del registro tampoco se queda colgado: al pasar el tiempo máximo, al respaldo.
        limite = time.monotonic() + 60
        while respaldo.getvalue().count("bloqueado") < 8 and time.monotonic() < limite:
            time.sleep(0.2)
        assert respaldo.getvalue().count("bloqueado") == 8
    finally:
        transaccion.rollback()
        conexion.close()
        actual().esperar()
        manejador.setStream(anterior)


def test_parar_con_la_cola_llena_no_falla_y_se_puede_repetir(app, monkeypatch):
    """Con la cola llena, parar() no lanza queue.Full y se puede repetir (no queda como parado
    con el hilo vivo)."""
    monkeypatch.setattr(registro, "MAXIMO_EN_COLA", 1)
    logger = logging.getLogger("prueba.parar")
    logger.propagate = False
    motor = create_engine(app.extensions["remate.motor"].url)
    cola_llena = registro.RegistroDeLaAplicacion(logger, motor, respaldo=io.StringIO())
    seguir = threading.Event()
    cola_llena.base_de_datos.emit = lambda r: seguir.wait(5)  # la base de datos no responde
    logger.addHandler(cola_llena.manejador)
    logger.warning("uno")  # el hilo lo coge y se queda esperando
    while cola_llena.cola.qsize():
        time.sleep(0.01)
    logger.warning("dos")  # llena la cola
    try:
        cola_llena.parar(segundos=0.2)
        assert cola_llena.hilo._thread is not None  # sigue vivo: se puede volver a intentar
    finally:
        seguir.set()
        cola_llena.parar()
    assert cola_llena.hilo._thread is None
    assert cola_llena.manejador not in logger.handlers


def test_si_la_base_de_datos_no_responde_va_al_archivo():
    """Lo que no se puede guardar (base de datos caída, tabla sin crear) va a la salida de errores,
    que en producción es remate.log, con la traza y el motivo."""

    def sin_conexion():
        raise OperationalError("SELECT 1", {}, Exception("la base de datos no responde"))

    salida = io.StringIO()
    manejador = registro.RegistroEnBaseDeDatos(
        SimpleNamespace(begin=sin_conexion, dispose=lambda: None), respaldo=salida
    )
    try:
        raise RuntimeError("se cayó")
    except RuntimeError:
        mensaje = logging.LogRecord(
            "app", logging.ERROR, "", 0, "La base de datos no responde", (), None
        )
        mensaje.traza = "RuntimeError: se cayó"
    manejador.handle(mensaje)
    manejador.close()
    texto = salida.getvalue()
    assert "ERROR app: La base de datos no responde\nRuntimeError: se cayó" in texto
    assert (
        "No se ha podido guardar el mensaje anterior en la base de datos (OperationalError)"
        in texto
    )


def test_no_pasa_al_logger_raiz(app):
    """Waitress configura el logger raíz: si se pasara a él, cada mensaje saldría otra vez en
    remate.log, sin fecha."""
    capturado = io.StringIO()
    raiz = logging.StreamHandler(capturado)
    logging.getLogger().addHandler(raiz)
    try:
        logging.getLogger("app").info("Solo en la tabla")
    finally:
        logging.getLogger().removeHandler(raiz)
    assert capturado.getvalue() == ""
    assert registros(app)[-1].mensaje == "Solo en la tabla"


def test_create_app_dos_veces_deja_un_solo_registro(config_pruebas, app):
    """Con varias create_app (pruebas, CLI) queda un solo manejador en el logger «app», sin la
    salida por pantalla de Flask ni manejadores repetidos."""
    otra = create_app(config_pruebas)
    try:
        logger = logging.getLogger("app")
        colas = [h for h in logger.handlers if isinstance(h, registro._Cola)]
        assert colas == [otra.extensions["remate.registro"].manejador]
        assert len([h for h in logger.handlers if isinstance(h, registro._Consola)]) == 1
        assert logger.propagate is False
        assert logger.level == logging.INFO
    finally:
        # Las demás pruebas siguen con el registro de la aplicación de conftest.
        app.extensions["remate.registro"] = registro.instalar(
            app.logger, config_pruebas.url_base_de_datos()
        )
        otra.extensions["remate.motor"].dispose()


def test_el_recordatorio_deja_su_resumen_en_la_tabla(app):
    """El recordatorio diario deja su resumen en el registro, como dicen el ADR y el manual."""
    resultado = app.test_cli_runner().invoke(args=["enviar-recordatorios", "--prueba"])
    assert resultado.exit_code == 0, resultado.output
    mensajes = [r.mensaje for r in registros(app)]
    assert mensajes[-3] == (
        "Recordatorio de entrega (prueba): enviados ninguno; omitidos ninguno; fallidos ninguno"
    )
    # También el de los avisos del pedido SAP y el de la caducidad (ADR 0014).
    assert mensajes[-2] == "Avisos del pedido SAP (prueba): enviados ninguno; fallidos ninguno"
    assert mensajes[-1].startswith("Caducidad (prueba): archivos 0 (0.0 MB); logs ")


def test_a_archivo_escribe_en_utf8_al_final_del_log(tmp_path):
    """Los scripts de Windows ejecutan ReMate con app.a_archivo: la salida va al log en UTF-8 y
    añadiendo al final, también si el comando falla."""
    log = tmp_path / "remate.log"
    log.write_text("línea anterior\n", encoding="utf-8")
    backend = Path(__file__).resolve().parent.parent
    salida = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "app.a_archivo", str(log), "flask", "--app", "app", "no-existe"],
        cwd=backend, capture_output=True, text=True, check=False, timeout=60,
    )  # fmt: skip
    assert salida.returncode != 0
    assert salida.stdout == salida.stderr == ""  # nada por pantalla: todo en el log
    contenido = log.read_text(encoding="utf-8")
    assert contenido.startswith("línea anterior\n")
    assert "no-existe" in contenido
