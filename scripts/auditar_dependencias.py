"""Busca vulnerabilidades conocidas en las dependencias de producción del backend con pip-audit.

Uso, desde la raíz del repositorio y con el entorno virtual del backend:
    backend/.venv/Scripts/python.exe scripts/auditar_dependencias.py      (Windows)
    backend/.venv/bin/python scripts/auditar_dependencias.py              (Linux)

Para el frontend: `npm audit` dentro de frontend/.

pip-audit consulta una base de datos pública de vulnerabilidades: envía los nombres y las versiones
de los paquetes, nunca código ni datos. En una red que revisa el tráfico HTTPS (con su propio
certificado, como muchas redes de empresa), usa los certificados del sistema operativo mediante el truststore
que trae pip; sin él, falla con «CERTIFICATE_VERIFY_FAILED».
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REQUISITOS = RAIZ / "backend" / "requirements.txt"


def main() -> None:
    try:
        from pip._vendor import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass  # sin truststore, se usan los certificados de Python (vale fuera de redes con proxy)
    from pip_audit._cli import audit

    sys.argv = ["pip-audit", "-r", str(REQUISITOS), "--progress-spinner", "off"]
    audit()


if __name__ == "__main__":
    main()
