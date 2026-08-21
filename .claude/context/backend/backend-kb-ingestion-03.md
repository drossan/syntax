# Session log — `backend-kb-ingestion-03` — Loader + parser (frontmatter + Trazabilidad + glosario)

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-21 — Implementación y cierre

- **TDD**: `tests/test_loader.py` (13 tests) + `tests/test_parser.py` (28 tests) escritos antes de
  `loader.py`/`parser.py`; rojo confirmado (import fallaba) antes de implementar, verde después.
- **Implementado**: `app/ingestion/loader.py` (`RawDoc` + `load(path) -> Iterator[RawDoc]`, validación
  EAGER del path vía función envolvente no-generadora + generador interno); `app/ingestion/parser.py`
  (`ParsedUC`/`ParseError` + `parse(raw, *, kb_root) -> ParsedUC | ParseError`).
- **Decisiones de implementación sin precedente en la spec (no hay fuente real en esta máquina, ver
  `## Contexto` del plan)**, documentadas en el docstring de `parser.py`:
  1. **Formato exacto de `::: info Trazabilidad`**: interpretación propia de `rag-ingestion.md` §2
     (lista `- **Estado**: ...` / `- **Package**: ...` / `- **Traza**: ...` dentro del contenedor
     VitePress `::: info Trazabilidad ... :::`) — a confirmar cuando el owner tenga la fuente real
     (ya scoped como verificación manual futura en el plan, fuera de los gates de cualquier tarea).
  2. **`uc_id` sintético para `index.md`**: `f"__glosario__:{domain}"` — nunca colisiona con un
     `uc_id` real (`UC-*`); el resto de campos no aplicables (`package`/`estado`/`traza`) quedan
     vacíos/`[]` en vez de `None` (mismo `ParsedUC` unificado para UC e `index.md`).
  3. **`parse()` recibe `kb_root: Path`** (no está en la firma abreviada del texto de la tarea, que
     solo decía `parse(raw) -> ParsedUC | ParseError`) — necesario para `source_url =
     str(raw.path.relative_to(kb_root))`.
  4. **`RawDoc.mtime`** capturado por el LOADER (no por el parser): mantiene el parser puro (sin
     tocar el filesystem), testeable 100% in-memory con paths sintéticos que no existen en disco.
- **sdd-lint**: N/A — la tarea no toca `spec.md`/CU/ADR.
- **Mutation testing (cosmic-ray)**, `module-path = "app/ingestion"` (el resto de ficheros del paquete
  siguen GUIÓN, sin código que mutar): 8.67% supervivencia inicial (17/196) → analizados uno a uno:
  - 6 reales, corregidos con tests nuevos: `==`→`>=` en `raw.path.name == "index.md"` (test con un
    nombre de fichero lexicográficamente posterior a "index.md"); `!=`→`<` en la comparación de
    `package` (test con la dirección alfabética opuesta); `frozen=True`→`False` en `ParsedUC`/
    `ParseError`/`RawDoc` (3 tests de inmutabilidad); `or`→`and` en la validación de `uc_id` (el caso
    "uc vacío" pasaba `uc: ` que YAML parsea a `None`, no `""` — corregido a `uc: ""` explícito para
    ejercitar la rama real); `continue`→`break` en el loop de dominios del loader (test con 2 dominios,
    el primero sin `uc/`).
  - 9 supervivientes finales, **todos equivalentes** (4.59%): 3× el `*` keyword-only de las firmas
    (artefacto de la herramienta sobre sintaxis no-operador); `re.DOTALL | re.MULTILINE` (equivalente a
    `+`/`^` para flags de bits disjuntos); `count=1` en un `re.sub` con patrón anclado `\A` (solo puede
    haber una coincidencia posible); 2× `.group(1)` donde `.group(0)` no cambia el resultado observable
    (las búsquedas posteriores toleran texto extra alrededor).
- **fact-checker** (subagente independiente, agentId `ab12ef44c56f75f07`): 10/10 VERIFICADO, 0
  INCORRECTO. Confirmó, re-ejecutando él mismo: `pytest test_loader.py test_parser.py` → 41 passed;
  suite completa → **838 passed**; `ruff check` limpio; `mypy --strict` limpio; `cosmic-ray` desde cero
  → 4.59% supervivencia, mismos 9 survivors exactos.
- **Dependencia dev añadida**: ninguna nueva — `pyyaml` ya estaba en `requirements.txt`; solo se agregó
  `"yaml.*"` a `[[tool.mypy.overrides]]` (`pyproject.toml`), mismo patrón ya usado para
  `pgvector.*`/`asyncpg.*` (lib sin type-hints completos, no bloquea el strict del código propio).
- **DoD**: todos los checkboxes cumplidos. Sin pendientes.
- Excluido de este commit: `backend/docs/domain-services-explicado.md` (cambio no relacionado, de una
  sesión anterior, sigue sin commitear).
