"""Sesión del modo admin (ADR 0015).

- La contraseña se comprueba con su hash (`ADMIN_CLAVE_HASH`, de Werkzeug, que ya viene con
  Flask); nunca se guarda ni se registra.
- Al entrar se crea un token al azar que va en una cookie `HttpOnly` y `SameSite=Strict` solo
  para `/api/admin`, sin fecha de caducidad: dura lo que el navegador esté abierto y es el
  servidor quien la da por caducada a los 30 minutos sin uso (con Max-Age, el navegador la
  borraría a los 30 minutos de entrar aunque se estuviera usando). Los tokens se
  guardan en memoria: al reiniciar el servicio hay que volver a entrar.
- Tras 5 intentos fallidos seguidos desde un mismo equipo (IP), ese equipo no puede intentarlo
  durante 15 minutos; los demás, sí. Cada intento se
  comprueba dentro del cerrojo: varios a la vez no pasan del tope.
- La sesión se comprueba antes que el cuerpo de la petición (`registrar`): sin sesión, 401.
"""

import secrets
import threading
import time
from functools import wraps

from flask import current_app, request
from werkzeug.security import check_password_hash

from app.api.errores import respuesta_error

COOKIE = "remate_admin"
RUTA_COOKIE = "/api/admin"
DURACION = 30 * 60  # segundos sin uso
MAXIMO_FALLOS = 5
BLOQUEO = 15 * 60

_cerrojo = threading.Lock()
_sesiones: dict[str, float] = {}  # token → caduca (time.monotonic)
# Intentos fallidos por IP: con un contador común, cualquiera de la red podría bloquear al
# administrador con cinco intentos. `remote_addr` es el equipo que se conecta: detrás de un
# proxy inverso, Waitress lo toma de X-Forwarded-For (ADR 0016).
_fallos: dict[str, dict] = {}  # IP → {n, bloqueado_hasta, ultimo}
# Tope de la tabla. Al llenarse solo se quitan los equipos cuyo último fallo y bloqueo pasaron
# hace más de 15 minutos; si sigue llena, los equipos nuevos quedan bloqueados (no se borran los
# contadores a medias: una misma IP podría intentarlo sin fin).
MAXIMO_IPS = 1000
_llena = {"hasta": 0.0}


def _de(ip: str) -> dict | None:
    """Los fallos del equipo; None si la tabla está llena y no cabe."""
    if ip in _fallos:
        return _fallos[ip]
    if len(_fallos) >= MAXIMO_IPS:
        ahora = _ahora()
        for otra in [
            i
            for i, f in _fallos.items()
            if f["bloqueado_hasta"] <= ahora and f["ultimo"] + BLOQUEO <= ahora
        ]:
            del _fallos[otra]
        if len(_fallos) >= MAXIMO_IPS:
            _llena["hasta"] = ahora + BLOQUEO
            return None
    return _fallos.setdefault(ip, {"n": 0, "bloqueado_hasta": 0.0, "ultimo": 0.0})


def _ip() -> str:
    return request.remote_addr or "desconocida"


def _ahora() -> float:
    return time.monotonic()


def configurado() -> bool:
    return bool(current_app.config["REMATE"].admin_clave_hash)


def bloqueado_durante() -> int:
    """Segundos que le quedan de bloqueo al equipo que hace la petición (0 si no hay)."""
    with _cerrojo:
        fallos = _fallos.get(_ip())
        hasta = fallos["bloqueado_hasta"] if fallos else _llena["hasta"]
        return max(0, int(hasta - _ahora()))


def entrar(clave: str) -> str | None:
    """Token nuevo si la clave es buena; None si no (y cuenta el fallo). Con el bloqueo activo
    no comprueba nada: hay que mirar antes `bloqueado_durante`, y aquí se vuelve a mirar."""
    hash_clave = current_app.config["REMATE"].admin_clave_hash
    with _cerrojo:
        fallos = _de(_ip())
        if fallos is None or fallos["bloqueado_hasta"] > _ahora():
            return None
        try:
            valida = bool(clave) and check_password_hash(hash_clave, clave)
        except ValueError:
            # Un hash mal copiado en el .env: no se puede entrar, pero no da error 500.
            current_app.logger.error("ADMIN_CLAVE_HASH no es un hash válido")
            valida = False
        if not valida:
            fallos["ultimo"] = _ahora()
            fallos["n"] += 1
            if fallos["n"] >= MAXIMO_FALLOS:
                fallos["n"] = 0
                fallos["bloqueado_hasta"] = _ahora() + BLOQUEO
            return None
        fallos["n"] = 0
        token = secrets.token_urlsafe(32)
        _sesiones[token] = _ahora() + DURACION
        return token


def salir(token: str | None) -> None:
    with _cerrojo:
        _sesiones.pop(token or "", None)


def vigente(token: str | None) -> bool:
    """Comprueba el token y, si vale, alarga la sesión otros 30 minutos."""
    if not token:
        return False
    with _cerrojo:
        caduca = _sesiones.get(token)
        if caduca is None or caduca < _ahora():
            _sesiones.pop(token, None)
            return False
        _sesiones[token] = _ahora() + DURACION
        return True


def _sin_sesion():
    if not configurado():
        return respuesta_error(
            503, "admin_no_configurado", "El modo admin no está configurado (ADR 0015)."
        )
    if not vigente(request.cookies.get(COOKIE)):
        return respuesta_error(401, "sin_sesion_admin", "Entra en el modo admin.")
    return None


def registrar(app) -> None:
    """Comprueba la sesión antes de que se valide el cuerpo de la petición (flask-openapi3 lo
    valida antes de llamar a la vista)."""

    @app.before_request
    def comprobar_sesion_admin():
        if request.path.startswith(RUTA_COOKIE + "/") and request.path != RUTA_COOKIE + "/sesion":
            return _sin_sesion()
        return None


def requiere_admin(vista):
    """Las rutas de administración responden 401 sin una sesión de admin vigente."""

    @wraps(vista)
    def protegida(*args, **kwargs):
        # También aquí, por si una ruta nueva quedara fuera de `registrar`.
        return _sin_sesion() or vista(*args, **kwargs)

    return protegida


def reiniciar() -> None:
    """Solo para las pruebas."""
    with _cerrojo:
        _sesiones.clear()
        _fallos.clear()
        _llena["hasta"] = 0.0
