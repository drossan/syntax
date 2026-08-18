---
id: backend-domain-services-07
package: backend
plan: domain-services
status: pending
priority: 2
depends_on: [backend-domain-services-02]
estimate: 1.5h
actual:
issue:
created: 2026-08-18
updated: 2026-08-18
---

# classification (contrato Classification + classify()) + puerto ChatModel (recortado a classify)

## Description

Contrato de clasificación de tickets: `{categoria, dominio, prioridad, resoluble}` (FR-023), vía
`ChatModel.classify` (structured output). Nace aquí el puerto **`ChatModel`**, recortado a **solo**
`classify` (design-review: `generate`/`grade` son prematuros sin caller — los descubrirá la tarea 15 con
su primer test; el docstring existente de `ports/llm.py` ya documenta la intención completa, no hace
falta fijar esas firmas hoy). **No depende de `ticket_service`**: el servicio solo `classify(ticket_text)
-> Classification`; quien aplica el resultado a `Ticket.domain/priority` es el futuro llamante (el nodo
`classify` del grafo, tarea 15), que conoce la secuencia completa. Guión: `app/domain/services/
classification.py`, `app/domain/ports/llm.py` (recortado). Spec: FR-023/024, CU-BE-05 (parcial).

## Spec

- `app/domain/ports/llm.py`: `ChatModel` (Protocol, async) con **solo** `classify(text: str, schema:
  type[BaseModel]) -> BaseModel` en este plan. `generate`/`grade` quedan documentados en el docstring
  como pendientes de la tarea 15 (no se fijan aquí).
- `Classification` (Pydantic v2, en `entities` o en el propio módulo de servicio — el schema del
  structured output): `categoria: str`, `dominio: KbDomain | None`, `prioridad: TicketPriority`,
  `resoluble: bool`. **`dominio=None` es la señal** de "no clasificable con confianza" (FR-024) — sin
  inventar un campo `confidence` que FR-023 no pide.
- `classify(ticket_text: str, chat_model: ChatModel) -> Classification`: delega en
  `chat_model.classify(ticket_text, Classification)`; no parsea prosa ni usa reglas/regex. Si
  `chat_model.classify` falla (timeout, error de proveedor) o su salida no valida contra `Classification`,
  la excepción se propaga envuelta en `PortError` (mismo criterio del resto del plan — no se traga en
  silencio ni se reintenta aquí).
- Sin efectos en import; puerto por inyección (`ChatModel`).

## Fuera de alcance

- Aplicar el resultado a `Ticket.domain/priority` → el llamante (nodo `classify` del grafo, tarea 15).
- El retrieval (`retrieve`/`grade`, resto de CU-BE-05) → tareas 13/14.
- `ChatModel.generate`/`grade` → tarea 15 (solo documentados, no implementados aquí).
- Adaptador OpenAI real → tarea 09.

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso:
- [CU-BE-05 — Clasificación y retrieval RAG](../../../specs/backend/casos-de-uso/CU-BE-05-clasificacion-y-retrieval-rag.md)

> Nota de alcance: de CU-BE-05, esta tarea cubre **solo** la parte de `classify` de "Clasificación fija el
> dominio y filtra el retrieval" (el "filtra el retrieval" es del nodo `retrieve`, tarea 14, fuera de
> aquí) y "Ticket no clasificable usa fallback sin filtro de dominio" (esta tarea solo produce la señal
> `dominio=None`; el "fallback sin filtro" lo ejecuta `retrieve`, tarea 14). El resto del CU (grade,
> citas, retrieval) está fuera de alcance. Añadido por `scenario-coverage`:
> ```gherkin
> Scenario: fallo del ChatModel se propaga envuelto
>   Given un ChatModel fake que lanza al clasificar (timeout/error de proveedor)
>   When se llama a classify()
>   Then la excepción se propaga envuelta en PortError
>
> Scenario: salida malformada del ChatModel no se acepta silenciosamente
>   Given un ChatModel fake que devuelve un valor que no valida contra Classification
>   When se llama a classify()
>   Then se propaga un error de validación (no un Classification a medias)
> ```

## Provides

`classification.classify()` + el contrato `Classification` en `app.domain.services.classification`, y el
puerto `ChatModel` (recortado) en `app.domain.ports.llm`, consumidos por el nodo `classify` del grafo
(tarea 15) y por el adaptador OpenAI (tarea 09).

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario del CU (alcance de esta tarea) tiene al menos un test, con `ChatModel` fake
  (dominio reconocible → `KbDomain` concreto; dominio incierto → `None`; fallo del fake → `PortError`;
  salida malformada → error de validación).
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible; el dominio no importa `app.infra`; sin dependencia de `ticket_service`.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation `cosmic-ray` (`break: 80`) sobre `classification.py` (`llm.py` es Protocol, N/A).
- [ ] Gate `/sdd-lint` sin ERROR (CU-BE-05 Gherkin bien formado, enlace válido).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings (por qué `dominio: KbDomain | None` en vez de `confidence`, por qué
  `ChatModel` solo tiene `classify` en este plan); session log con la traza a CU-BE-05.
