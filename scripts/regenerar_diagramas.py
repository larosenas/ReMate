"""Regenera las imágenes (PNG y SVG) de los diagramas PlantUML de ReMate.

Uso, desde la raíz del repositorio:
    python scripts/regenerar_diagramas.py            # todos los diagramas
    python scripts/regenerar_diagramas.py arquitectura modelo-de-datos

Necesita Java 11 o posterior y plantuml.jar:
- Java: se usa JAVA_HOME si existe; si no, se buscan instalaciones conocidas (IntelliJ, Adoptium, PATH).
- plantuml.jar: variable de entorno PLANTUML_JAR o, por defecto, ~/.plantuml/plantuml.jar.
  Se descarga desde las releases de https://github.com/plantuml/plantuml (no se versiona en el repo).
"""

import glob
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FUENTES = RAIZ / "docs" / "diagramas" / "fuentes"
SALIDAS = RAIZ / "docs" / "diagramas" / "salidas"


def version_java(java: str) -> int:
    """Devuelve la versión mayor de Java (8, 11, 17…) o 0 si no se puede ejecutar."""
    try:
        r = subprocess.run([java, "-version"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return 0
    m = re.search(r'version "(\d+)(?:\.(\d+))?', r.stderr + r.stdout)
    if not m:
        return 0
    mayor = int(m.group(1))
    return int(m.group(2) or 0) if mayor == 1 else mayor  # "1.8" -> 8


def buscar_java() -> str | None:
    candidatos = []
    if os.environ.get("JAVA_HOME"):
        candidatos.append(str(Path(os.environ["JAVA_HOME"]) / "bin" / "java"))
    for patron in (
        r"C:\Program Files\JetBrains\*\jbr\bin\java.exe",
        r"C:\Program Files\Eclipse Adoptium\*\bin\java.exe",
        r"C:\Program Files\Java\*\bin\java.exe",
        "/usr/lib/jvm/*/bin/java",
    ):
        candidatos.extend(sorted(glob.glob(patron), reverse=True))
    if shutil.which("java"):
        candidatos.append(shutil.which("java"))
    for java in candidatos:
        if version_java(java) >= 11:
            return java
    return None


def main() -> int:
    jar = Path(os.environ.get("PLANTUML_JAR", Path.home() / ".plantuml" / "plantuml.jar"))
    if not jar.is_file():
        print(f"ERROR: no se encuentra plantuml.jar en {jar}.")
        print("Descárgalo de https://github.com/plantuml/plantuml/releases (plantuml-<versión>.jar),")
        print("guárdalo en esa ruta o indica otra con la variable de entorno PLANTUML_JAR.")
        return 2

    java = buscar_java()
    if not java:
        print("ERROR: hace falta Java 11 o posterior (Java 8 no sirve para PlantUML).")
        print("Instala un JDK reciente o define JAVA_HOME.")
        return 2

    nombres = sys.argv[1:]
    if nombres:
        fuentes = [FUENTES / (n if n.endswith(".puml") else n + ".puml") for n in nombres]
        faltan = [f.name for f in fuentes if not f.is_file()]
        if faltan:
            print("ERROR: no existen estas fuentes: " + ", ".join(faltan))
            return 2
    else:
        fuentes = sorted(FUENTES.glob("*.puml"))
    if not fuentes:
        print(f"No hay diagramas en {FUENTES}.")
        return 0

    SALIDAS.mkdir(parents=True, exist_ok=True)
    print(f"Java: {java}\nPlantUML: {jar}")
    for formato in ("png", "svg"):
        orden = [java, "-jar", str(jar), "-charset", "UTF-8", f"-t{formato}", "-o", str(SALIDAS)]
        r = subprocess.run(orden + [str(f) for f in fuentes], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"ERROR al generar {formato.upper()}:\n{r.stdout}{r.stderr}")
            return 1

    for f in fuentes:
        print(f"OK  {f.stem}: salidas/{f.stem}.png y salidas/{f.stem}.svg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
