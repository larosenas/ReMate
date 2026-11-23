# Diagramas

Diagramas de ReMate hechos con [PlantUML](https://plantuml.com).

| Diagrama | Fuente | Imágenes |
| --- | --- | --- |
| Stack tecnológico | `fuentes/stack-tecnologico.puml` | `salidas/stack-tecnologico.png`, `salidas/stack-tecnologico.svg` |
| Arquitectura | `fuentes/arquitectura.puml` | `salidas/arquitectura.png`, `salidas/arquitectura.svg` |
| Estados de una necesidad | `fuentes/estados-necesidad.puml` | `salidas/estados-necesidad.png`, `salidas/estados-necesidad.svg` |
| Modelo de datos | `fuentes/modelo-de-datos.puml` | `salidas/modelo-de-datos.png`, `salidas/modelo-de-datos.svg` |
| Modelo de dominio | `fuentes/modelo-de-dominio.puml` | `salidas/modelo-de-dominio.png`, `salidas/modelo-de-dominio.svg` |

- `fuentes/`: archivos `.puml`. **Se edita siempre la fuente**, nunca la imagen.
- `salidas/`: imágenes generadas (PNG para documentos y presentaciones, SVG para verlas con zoom). Se regeneran cada vez que cambia una fuente.

## Cómo generar las imágenes

**Opción recomendada — script del proyecto** (desde la raíz):

```bash
python scripts/regenerar_diagramas.py            # todos los diagramas
python scripts/regenerar_diagramas.py arquitectura
```

Necesita Java 11 o posterior (busca JAVA_HOME, el Java de IntelliJ/PyCharm, Adoptium y el del PATH) y `plantuml.jar` en `~/.plantuml/plantuml.jar` (o en la ruta de la variable `PLANTUML_JAR`), descargado de las *releases* de github.com/plantuml/plantuml.

**Alternativa — VS Code:** extensión «PlantUML» (jebbs.plantuml). `Alt+D` para previsualizar; «PlantUML: Export Current Diagram» para exportar (deja las imágenes en `out/`, que está ignorada: hay que moverlas a `salidas/`).
