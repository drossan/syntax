# 0011. Entrega del draft por polling (GET /agent-runs), no streaming SSE en Fase 1

- **Estado**: accepted
- **Fecha**: 2026-08-11
- **Decisores**: Owner; `grilling`/`design-review` (ambos planes); seam `astream` diferido.

## Contexto y planteamiento del problema

El draft IA tarda en generarse. El frontend necesita mostrar su progreso/resultado. ¿Se entrega
**token-a-token** (streaming SSE) o se **consulta** el estado del run hasta que termina? El streaming añade
superficie (SSE, backpressure, reconexión) que puede no justificarse en Fase 1.

## Decision drivers

- Coste/complejidad de SSE (servidor + cliente) frente al valor en Fase 1.
- El flujo ya pasa por **aprobación humana**: la latencia del draft no es crítica de UX en tiempo real.
- No cerrar la puerta a streaming en el futuro.

## Opciones consideradas

- **Opción 1** — **Polling**: disparar `ai-draft` y consultar `GET /agent-runs/{id}` hasta
  `succeeded|failed`; diseñar el grafo con **seam `astream`** para habilitar streaming después.
- **Opción 2** — **Streaming SSE** del draft token-a-token en Fase 1.
- **Opción 3** — WebSocket bidireccional.

## Resultado de la decisión

Elegida: **Opción 1 (polling)**. En Fase 1 el draft se entrega por **request/polling**: el cliente dispara
la generación y hace polling de `GET /agent-runs/{id}` (con manejo de `failed` + reintento). El grafo se
**diseña** para permitir `astream` (streaming token-a-token) en una fase posterior, pero el **SSE queda
fuera de alcance**. El frontend implementa el ciclo de draft con polling ([[0003-frontend-spa-client-rendered]]).

### Confirmación

`api-contract.md` (Fuera de alcance: SSE diferido; draft por `GET /agent-runs/{id}`); `agent-graph.md` §9
(seam `astream`); frontend helpdesk-core tarea 14 (ciclo de draft con polling), verificado 2026-08-13.

## Consecuencias

- **Buenas**: superficie mínima; encaja con HITL (la latencia no es tiempo-real crítico); reversible (seam listo).
- **Malas / coste**: sin feedback token-a-token; el polling consume requests (mitigado con intervalos/backoff).

## Pros y contras de las opciones

- **Opción 1**: 👍 simple, reversible, suficiente para HITL · 👎 sin streaming; polling periódico.
- **Opción 2**: 👍 UX de escritura en vivo · 👎 SSE = más superficie sin valor claro en Fase 1.
- **Opción 3**: 👍 bidireccional · 👎 aún más complejo; innecesario (el flujo no es conversacional en vivo).
