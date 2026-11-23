"""Registro de la aplicación en la base de datos, con respaldo en archivo (ADR 0008).

Los mensajes de la aplicación (desde el nivel de información) se guardan en la tabla `logs`.
Lo que no se puede guardar allí (la base de datos no responde, la tabla no existe…) se escribe
por la salida de errores, que en producción va a `C:\\ReMate\\logs\\remate.log` o
`recordatorios.log` (`app/a_archivo.py` y los scripts de `scripts/windows`). Los errores de antes
de crear la aplicación (por ejemplo, falta una variable del `.env`) también van ahí.

Las peticiones no escriben en la base de datos: dejan el mensaje en una cola y siguen. Un hilo
aparte lo guarda, con su propia conexión y un tiempo máximo, así que una base de datos lenta o
bloqueada no detiene la aplicación. Si la cola se llena, el mensaje va
al respaldo.
"""

import atexit
import copy
import logging
import logging.handlers
import queue
import sys
import threading
import time
from datetime import UTC, datetime

import psycopg
from sqlalchemy import create_engine, insert
from sqlalchemy.engine import URL, Engine

from app.modelos.logs import Log

FORMATO_RESPALDO = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
FORMATO_CONSOLA = "[%(asctime)s] %(levelname)s en %(name)s: %(message)s"
MAXIMO_EN_COLA = 10_000


def _limpio(texto: str | None) -> str | None:
    """PostgreSQL no admite el carácter NUL ni los sustitutos sueltos («\\ud800»)."""
    if texto is None:
        return None
    return texto.replace("\x00", "\\x00").encode("utf-8", "backslashreplace").decode("utf-8")


def _traza(exc_info) -> str:
    """La traza sin el texto de los errores de PostgreSQL, que puede repetir valores (por ejemplo,
    «DETAIL: Key (email)=(…) already exists»): se deja su código y la restricción.
    Los parámetros de las consultas ya los oculta `hide_parameters`."""
    traza = logging.Formatter().formatException(exc_info)
    error, vistos = exc_info[1], set()
    while error is not None and id(error) not in vistos:
        vistos.add(id(error))
        if isinstance(error, psycopg.Error) and str(error):
            restriccion = error.diag.constraint_name
            resumen = f"SQLSTATE {error.sqlstate}" + (
                f", restricción {restriccion}" if restriccion else ""
            )
            traza = traza.replace(str(error), f"({resumen})")
        error = error.__cause__ or error.__context__
    return traza


def _mensaje(registro: logging.LogRecord) -> str:
    """El texto del mensaje; si los argumentos no cuadran con el formato, tal cual."""
    try:
        return registro.getMessage()
    except Exception:  # por ejemplo, log.info("%s %s", 1): el mensaje no se pierde
        return f"(mensaje mal formateado) {registro.msg!r} {registro.args!r}"


class _Respaldo(logging.StreamHandler):
    """Escribe el mensaje y, si la hay, su traza (la cola la separa del mensaje)."""

    def format(self, registro: logging.LogRecord) -> str:
        registro = copy.copy(registro)
        registro.msg, registro.args = _mensaje(registro), None
        texto = super().format(registro)
        traza = getattr(registro, "traza", None)
        return f"{texto}\n{traza}" if traza else texto


class _Consola(_Respaldo):
    """Salida por pantalla en desarrollo (`flask run`)."""


class RegistroEnBaseDeDatos(logging.Handler):
    """Guarda cada mensaje en la tabla `logs`. Lo usa el hilo de la cola."""

    def __init__(self, motor: Engine, respaldo=None):
        super().__init__(level=logging.INFO)
        self.motor = motor
        self.respaldo = _Respaldo(respaldo or sys.stderr)
        self.respaldo.setFormatter(logging.Formatter(FORMATO_RESPALDO))

    def emit(self, registro: logging.LogRecord) -> None:
        try:
            with self.motor.begin() as conexion:
                conexion.execute(
                    insert(Log).values(
                        creado_en=datetime.fromtimestamp(registro.created, UTC),
                        nivel=registro.levelname[:10],
                        origen=registro.name[:100],
                        mensaje=_limpio(registro.getMessage()),
                        traza=_limpio(getattr(registro, "traza", None)),
                    )
                )
        except Exception as error:  # cualquier fallo al guardar: el mensaje no se pierde
            self.respaldo.handle(registro)
            self.respaldo.handle(
                logging.makeLogRecord(
                    {"name": __name__, "levelname": "WARNING", "levelno": logging.WARNING,
                     "msg": "No se ha podido guardar el mensaje anterior en la base de datos (%s).",
                     "args": (type(error).__name__,)}
                )
            )  # fmt: skip

    def close(self) -> None:
        self.motor.dispose()
        super().close()


class _Cola(logging.handlers.QueueHandler):
    """Deja el mensaje en la cola sin esperar. Prepara en el hilo de la petición el texto del
    mensaje y la traza, que se guardan en columnas distintas."""

    def __init__(self, cola: queue.Queue, respaldo: logging.Handler):
        super().__init__(cola)
        self.respaldo = respaldo

    def prepare(self, registro: logging.LogRecord) -> logging.LogRecord:
        preparado = copy.copy(registro)
        preparado.msg, preparado.args = _mensaje(registro), None
        preparado.traza = _traza(registro.exc_info) if registro.exc_info else None
        preparado.exc_info = preparado.exc_text = None
        return preparado

    def enqueue(self, registro: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(registro)
        except queue.Full:
            self.respaldo.handle(registro)


class RegistroDeLaAplicacion:
    """La cola, su hilo y el manejador que guarda en la base de datos."""

    def __init__(self, logger: logging.Logger, motor: Engine, respaldo=None):
        self.logger = logger
        self.cola: queue.Queue = queue.Queue(MAXIMO_EN_COLA)
        self.base_de_datos = RegistroEnBaseDeDatos(motor, respaldo)
        self.manejador = _Cola(self.cola, self.base_de_datos.respaldo)
        self.manejador.setLevel(logging.INFO)
        self.hilo = logging.handlers.QueueListener(self.cola, self.base_de_datos)
        self.hilo.start()
        self._parado = False
        atexit.register(self.parar)

    def esperar(self, segundos: float = 30) -> None:
        """Espera, como mucho `segundos`, a que se guarde lo que hay en la cola (pruebas)."""
        limite = time.monotonic() + segundos
        while self.cola.unfinished_tasks and time.monotonic() < limite:
            time.sleep(0.01)

    def parar(self, segundos: float = 20) -> None:
        """Guarda lo que quede en la cola y suelta el logger (al salir y al volver a instalar).
        Espera como mucho `segundos` (WinSW da 30 al parar el servicio). Si la cola sigue llena
        porque la base de datos no responde, lo deja y se puede volver a llamar (sin lanzar
        queue.Full ni quedar a medias)."""
        if self._parado:
            return
        self.logger.removeHandler(self.manejador)
        self.esperar(segundos)
        try:
            self.hilo.stop()
        except queue.Full:
            self.base_de_datos.respaldo.handle(
                logging.makeLogRecord(
                    {"name": __name__, "levelname": "WARNING", "levelno": logging.WARNING,
                     "msg": "Al parar, la cola del registro seguía llena: se pierde lo que queda."}
                )
            )  # fmt: skip
            return
        self._parado = True
        self.base_de_datos.close()


_cerrojo = threading.Lock()


def instalar(
    logger: logging.Logger, url: str | URL, consola: bool = False
) -> RegistroDeLaAplicacion:
    """Guarda en la base de datos los mensajes de `logger` (el de la aplicación, «app») y de sus
    módulos («app.integraciones.ia»…). `consola`: en desarrollo, también por pantalla. Si se
    vuelve a llamar (otra `create_app`), sustituye a la anterior."""
    from flask.logging import default_handler

    with _cerrojo:
        anterior = getattr(logger, "_registro_remate", None)
        if anterior is not None:
            anterior.parar()
        for sobrante in [h for h in logger.handlers if isinstance(h, _Cola | _Consola)]:
            logger.removeHandler(sobrante)
        logger.removeHandler(default_handler)
        # No pasa al logger raíz: Waitress configura uno que escribiría cada mensaje otra vez en
        # remate.log, sin fecha.
        logger.propagate = False
        # Motor propio y pequeño, con tiempos máximos: una base de datos lenta o una tabla
        # bloqueada no deja el hilo del registro esperando sin fin. Sin los parámetros de las
        # consultas en los errores, que podrían llevar datos de las ofertas.
        motor = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=1,
            max_overflow=1,
            pool_timeout=5,
            hide_parameters=True,
            connect_args={
                "connect_timeout": 5,
                "options": "-c statement_timeout=5000 -c lock_timeout=2000",
            },
        )
        registro = RegistroDeLaAplicacion(logger, motor)
        logger.addHandler(registro.manejador)
        if consola:
            pantalla = _Consola(sys.stderr)
            pantalla.setFormatter(logging.Formatter(FORMATO_CONSOLA))
            logger.addHandler(pantalla)
        logger.setLevel(logging.INFO)
        logger._registro_remate = registro
        return registro


def activo(logger: logging.Logger) -> RegistroDeLaAplicacion | None:
    """El registro instalado ahora en `logger` (con varias `create_app`, el de la última)."""
    return getattr(logger, "_registro_remate", None)
