"""Configuración de ReMate leída de variables de entorno.

Las variables se toman del entorno o del archivo `.env` de la raíz del repositorio
(ver `.env.example`). Las variables ya definidas en el entorno tienen prioridad.
"""

import os
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from sqlalchemy.engine import URL

RAIZ_REPOSITORIO = Path(__file__).resolve().parents[2]


class ErrorDeConfiguracion(RuntimeError):
    """Falta una variable de entorno obligatoria o tiene un valor no válido."""


def _obligatoria(nombre: str) -> str:
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        raise ErrorDeConfiguracion(
            f"Falta la variable de entorno {nombre} (ver .env.example en la raíz del repositorio)."
        )
    return valor


@dataclass(frozen=True)
class Config:
    entorno: str
    db_host: str
    db_port: int
    db_nombre: str
    db_usuario: str
    db_contrasena: str
    frontend_dist: Path
    archivos_dir: Path
    # OpenAI (opcional): si falta algo, las ofertas se completan a mano.
    ia_api_key: str = ""
    ia_modelo: str = ""
    # Cuánto razona el modelo al leer una oferta; se paga como salida (ADR 0011).
    ia_razonamiento: str = "low"
    # Correo saliente del recordatorio de entrega (CU-009). Sin SMTP_HOST no se envía nada.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_secure: bool = True
    smtp_from: str = ""
    # Dirección de la aplicación para los enlaces de los correos (p. ej. http://remate:2905).
    app_url: str = ""
    # Escucha de Waitress (ADR 0009). `flask run` mantiene su configuración propia.
    host: str = "0.0.0.0"  # noqa: S104
    port: int = 2905
    # Modo admin (ADR 0015): hash de la contraseña (`flask --app app clave-admin`). Vacío: el
    # modo admin está desactivado.
    admin_clave_hash: str = ""
    # Carpeta de las copias de seguridad, solo para ver en el modo admin la última (opcional).
    copias_dir: Path | None = None
    # Nombres o IP con los que se entra a ReMate, además del de APP_URL y localhost (opcional;
    # protección frente a DNS rebinding, app/origen.py).
    hosts_permitidos: tuple[str, ...] = ()
    # IP del proxy inverso (por ejemplo Caddy, ADR 0016) del que se aceptan X-Forwarded-For y
    # -Proto. Vacío: sin proxy, y Waitress borra esas cabeceras.
    proxy_de_confianza: str = ""
    # Nombre de la empresa que usa ReMate: firma de los correos e instrucciones de la IA
    # (opcional; vacío, los correos van sin él y la IA lee «la empresa»).
    empresa_nombre: str = ""

    @property
    def es_produccion(self) -> bool:
        return self.entorno == "production"

    def url_base_de_datos(self, nombre: str | None = None) -> URL:
        """URL de SQLAlchemy para PostgreSQL con psycopg 3 (ADR 0003)."""
        return URL.create(
            "postgresql+psycopg",
            username=self.db_usuario,
            password=self.db_contrasena,
            host=self.db_host,
            port=self.db_port,
            database=nombre or self.db_nombre,
        )


RAZONAMIENTOS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")


def _numero(nombre: str, por_defecto: int) -> int:
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        return por_defecto
    if not valor.isdigit():
        raise ErrorDeConfiguracion(f"{nombre} debe ser un número.")
    return int(valor)


def _app_url(entorno: str) -> str:
    """APP_URL da el enlace de los correos y la única dirección con la que se atiende
    (protección frente a DNS rebinding, app/origen.py). En producción es obligatoria: vacía, la
    protección quedaría desactivada sin avisar. Mal escrita (sin `http://`), toda la aplicación
    respondería «host_no_permitido»; por eso se valida al arrancar."""
    valor = os.environ.get("APP_URL", "").strip().rstrip("/")
    if not valor:
        if entorno == "production":
            raise ErrorDeConfiguracion(
                "Falta APP_URL: en producción es la dirección con la que se entra a ReMate "
                "(por ejemplo, http://<ip_servidor>:2905)."
            )
        return ""
    partes = urlsplit(valor)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise ErrorDeConfiguracion(
            "APP_URL tiene que ser una dirección completa, como http://<ip_servidor>:2905."
        )
    return valor


def _hosts_permitidos() -> tuple[str, ...]:
    """Nombres o IP de HOSTS_PERMITIDOS, sin el puerto si lo traen (con él no coincidirían
    nunca)."""
    nombres = []
    for valor in os.environ.get("HOSTS_PERMITIDOS", "").split(","):
        valor = valor.strip()
        if not valor:
            continue
        nombre = urlsplit(valor if "//" in valor else f"//{valor}").hostname
        if not nombre:
            raise ErrorDeConfiguracion(f"HOSTS_PERMITIDOS: «{valor}» no es un nombre ni una IP.")
        nombres.append(nombre.lower())
    return tuple(nombres)


def _proxy_de_confianza() -> str:
    """Una sola IP, la del proxy: con un nombre o «*», cualquiera podría poner otra IP en
    X-Forwarded-For y saltarse el bloqueo del modo admin (ADR 0016)."""
    valor = os.environ.get("PROXY_DE_CONFIANZA", "").strip()
    if not valor:
        return ""
    try:
        # Escrita como la da Waitress en REMOTE_ADDR, que compara el texto tal cual.
        return str(ip_address(valor))
    except ValueError as error:
        raise ErrorDeConfiguracion(
            "PROXY_DE_CONFIANZA debe ser la IP del proxy (por ejemplo, 127.0.0.1)."
        ) from error


def cargar_config() -> Config:
    load_dotenv(RAIZ_REPOSITORIO / ".env")
    entorno = os.environ.get("APP_ENV", "development").strip() or "development"
    if entorno not in ("development", "production"):
        raise ErrorDeConfiguracion("APP_ENV debe ser 'development' o 'production'.")
    puerto = _obligatoria("DB_PORT")
    if not puerto.isdigit():
        raise ErrorDeConfiguracion("DB_PORT debe ser un número.")
    host = os.environ.get("HOST", "").strip() or "0.0.0.0"  # noqa: S104
    try:
        ip_address(host)
    except ValueError as error:
        raise ErrorDeConfiguracion("HOST debe ser una dirección IP (IPv4 o IPv6).") from error
    # Valores de la API de OpenAI; cada modelo admite algunos (guía «Reasoning»). Mal escrito, la
    # petición fallaría en cada oferta: mejor no arrancar.
    razonamiento = os.environ.get("IA_RAZONAMIENTO", "").strip().lower() or "low"
    if razonamiento not in RAZONAMIENTOS:
        raise ErrorDeConfiguracion("IA_RAZONAMIENTO debe ser uno de: " + ", ".join(RAZONAMIENTOS))
    port = os.environ.get("PORT", "").strip() or "2905"
    if not port.isascii() or not port.isdecimal() or len(port) > 5 or not 1 <= int(port) <= 65535:
        raise ErrorDeConfiguracion("PORT debe ser un número entre 1 y 65535.")
    return Config(
        host=host,
        port=int(port),
        entorno=entorno,
        db_host=_obligatoria("DB_HOST"),
        db_port=int(puerto),
        db_nombre=_obligatoria("DB_NAME"),
        db_usuario=_obligatoria("DB_USER"),
        db_contrasena=_obligatoria("DB_PASSWORD"),
        frontend_dist=Path(
            os.environ.get("FRONTEND_DIST", "").strip() or RAIZ_REPOSITORIO / "frontend" / "dist"
        ),
        # Una ruta relativa se toma desde la raíz del repositorio, como el `.env`.
        archivos_dir=RAIZ_REPOSITORIO / (os.environ.get("ARCHIVOS_DIR", "").strip() or "archivos"),
        ia_api_key=os.environ.get("IA_API_KEY", "").strip(),
        ia_modelo=os.environ.get("IA_MODELO", "").strip(),
        ia_razonamiento=razonamiento,
        smtp_host=os.environ.get("SMTP_HOST", "").strip(),
        smtp_port=_numero("SMTP_PORT", 587),
        smtp_user=os.environ.get("SMTP_USER", "").strip(),
        smtp_password=os.environ.get("SMTP_PASSWORD", ""),
        smtp_secure=os.environ.get("SMTP_SECURE", "true").strip().lower()
        in ("true", "1", "si", "sí"),
        smtp_from=os.environ.get("SMTP_FROM", "").strip(),
        app_url=_app_url(entorno),
        admin_clave_hash=os.environ.get("ADMIN_CLAVE_HASH", "").strip(),
        copias_dir=Path(c) if (c := os.environ.get("COPIAS_DIR", "").strip()) else None,
        hosts_permitidos=_hosts_permitidos(),
        proxy_de_confianza=_proxy_de_confianza(),
        empresa_nombre=os.environ.get("EMPRESA_NOMBRE", "").strip(),
    )
