r"""Ejecuta ReMate en producción con toda su salida en un archivo de log (ADR 0006 y 0008).

Uso, desde `backend`:

    python -m app.servir --log C:\ReMate\logs\remate.log
    python -m app.a_archivo C:\ReMate\logs\recordatorios.log flask --app app enviar-recordatorios

Es el respaldo del registro: lo que no se puede guardar en la tabla `logs` (y los errores de
antes de crear la aplicación, como una variable del `.env` que falta). Lo escribe Python, en
UTF-8 y añadiendo al final, en vez de la redirección de PowerShell 5.1 (`*>>`), que escribe en
UTF-16 y, con `$ErrorActionPreference = 'Stop'`, puede pararse en la primera línea de la salida
de errores.
"""

import faulthandler
import sys


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("waitress", "flask", "servir"):
        print(
            "Uso: python -m app.a_archivo <log> waitress|flask|servir <argumentos>", file=sys.stderr
        )
        return 2
    ruta, orden, argumentos = argv[0], argv[1], argv[2:]
    archivo = open(ruta, "a", encoding="utf-8", errors="backslashreplace", buffering=1)  # noqa: SIM115
    sys.stdout = sys.stderr = archivo
    # Si Python se cae del todo, su traza también queda en el log.
    faulthandler.enable(archivo)
    try:
        if orden == "servir":
            from app.servir import servir

            servir()
            return 0
        if orden == "waitress":
            from waitress.runner import run

            return run(argv=["waitress-serve", *argumentos]) or 0
        from flask.cli import main as flask

        sys.argv = ["flask", *argumentos]
        try:
            flask()
        except SystemExit as salida:
            return (
                salida.code if isinstance(salida.code, int) else (0 if salida.code is None else 1)
            )
        return 0
    except Exception:
        import traceback

        traceback.print_exc()
        return 1
    finally:
        archivo.flush()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
