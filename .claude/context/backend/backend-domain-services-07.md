# Session log — backend-domain-services-07

Tarea: `classification` (contrato `Classification` + `classify()`) + puerto `ChatModel` recortado a
`classify`. Nivel: unit. Traza: CU-BE-05 (parcial: solo la parte de `classify`).

## Entradas

- 2026-08-18 — Arranque y cierre en la misma sesión. TDD (tests antes de implementar).

## Resumen

`app/domain/ports/llm.py`: `ChatModel` (`Protocol`, async) con un único método `classify(text, schema)
-> BaseModel` — `generate`/`grade` quedan documentados como guión futuro (tarea 15), sin firma fijada,
porque no tienen caller todavía (decisión de design-review: no adivinar un contrato sin consumidor).
`app/domain/services/classification.py`: `Classification` (Pydantic v2: `categoria`, `dominio: KbDomain |
None`, `prioridad`, `resoluble`) + `classify(ticket_text, chat_model) -> Classification`, que delega en
`chat_model.classify` sin parsear prosa ni depender de `ticket_service`.

## Decisiones técnicas + porqué

- **`dominio: KbDomain | None` en vez de un campo `confidence`.** FR-023/024 solo piden la señal "no
  clasificable con confianza" (`dominio=None`); inventar un campo de confianza numérica sería construir
  para un requisito que la spec no pide.
- **No doble-envolver un `PortError` que el propio `ChatModel` ya lanzó.** El puerto documenta que un
  adaptador real puede lanzar `PortError` directamente; `classify()` distingue `except PortError: raise`
  (antes del `except Exception` genérico) para no anidar un `PortError` dentro de otro y perder la causa
  original. Verificado con un test que compara identidad (`exc_info.value is original`).
- **Validación explícita de tipo en la salida (`isinstance(result, Classification)`).** Aunque la firma
  del puerto declara `-> BaseModel`, un `ChatModel` fake (o un adaptador con bug) podría devolver
  cualquier cosa; `classify()` no confía ciegamente en la anotación de tipo y rechaza con `Validation`
  cualquier salida que no sea realmente una `Classification` (incl. `None` y un `dict` crudo).

## Tests corridos + resultado

- `tests/test_classification.py`: **6 tests**, todos verdes.
- Suite completa `pytest -q`: verde, sin fallos.
- `ruff check .` OK · `ruff format --check .` OK (118 ficheros) · `mypy app` strict: `Success: no issues
  found in 92 source files`.
- Mutation (`cosmic-ray` sobre `classification.py`): **0.00% survival** (4/4 mutantes matados). Fichero
  pequeño con pocos operadores mutables; sin survivors que documentar.
- `/sdd-lint`: mecánico limpio (CU-BE-05 enlazado, sin `[NECESITA ACLARACIÓN`, ids `FR-0NN` bien
  formados, secciones Cockburn+Gherkin presentes). Semántico (subagente, acotado a los dos escenarios de
  esta tarea): **1 AVISO menor**, no bloqueante — nota que la marca de "baja confianza" del escenario de
  fallback es lógicamente un efecto de `classify`, no de `retrieve` (donde el Gherkin la sitúa); no es una
  contradicción con el FR (que también los conflaciona) y no bloquea esta tarea, queda anotado para
  cuando se implemente `retrieve` (tarea 14). Gate PASA.
- `fact-checker` (sonnet): **8/8 VERIFICADO, 0 INCORRECTO**.

## Docs actualizadas

- Docstrings de `llm.py` (por qué `ChatModel` solo tiene `classify` en este plan) y `classification.py`
  (por qué `dominio: KbDomain | None` en vez de `confidence`, por qué no doble-envolver `PortError`).
  Session log (este fichero) con la traza a CU-BE-05.
