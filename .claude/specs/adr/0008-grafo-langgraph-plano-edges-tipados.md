# 0008. Grafo LangGraph plano con edges condicionales tipados (no supervisor por prompt)

- **Estado**: accepted
- **Fecha**: 2026-08-11
- **Decisores**: Owner; análisis de la 3ª demo (`soc_multiagent`) + `design-review` backend.

## Contexto y planteamiento del problema

El agente debe **clasificar** el ticket, **recuperar** contexto de la KB, **evaluar** su suficiencia,
**generar** el draft y **decidir** si escala — con un flujo **auditable y determinista**. ¿El routing entre
pasos lo decide un LLM en prosa (supervisor) o una lógica tipada?

## Decision drivers

- Routing determinista y depurable (no dependiente de texto libre del LLM).
- Clasificación consumible por código (no parsear strings).
- Encaje con el HITL ([[0007-hitl-asincrono-postgressaver-checkpointer]]) y el filtrado del retrieval.

## Opciones consideradas

- **Opción 1** — Grafo **plano** con **edges condicionales tipados** que leen campos del estado
  (`classification.resoluble`, `grade.suficiente`, `decide.requires_approval`); `classify` con
  **`with_structured_output`**.
- **Opción 2** — **Supervisor por prompt** que decide el siguiente nodo en prosa.
- **Opción 3** — `create_react_agent` como única pieza, sin edges explícitos.

## Resultado de la decisión

Elegida: **Opción 1**. Nodos `classify → retrieve → grade → generate → decide → (interrupt) → respond`;
el **routing** son edges condicionales que leen **campos tipados** del estado, nunca texto libre del LLM.
`classify` usa **`with_structured_output`** → `Classification{categoria, dominio(1-de-17), prioridad,
resoluble}`; el **dominio filtra el retrieval** (no se parsean strings). `resoluble=false` escala directo a
humano; **no-clasificable con confianza** → fallback de retrieval **sin filtro de dominio** (no forzar uno
equivocado). Estado con reducer `add_messages` + `trim_messages` para hilos largos.

### Confirmación

`agent-graph.md` §2–§4; `app/agents/graph.py` + `nodes/` (guión: plano + edges tipados, classify
structured-output + fallback); descartados los anti-patrones de las demos (routing por prompt,
clasificación en prosa).

## Consecuencias

- **Buenas**: flujo determinista, auditable y testeable por rama; clasificación tipada reutilizable.
- **Malas / coste**: el grafo es más explícito (más edges que declarar) que un supervisor genérico; menos
  "flexible" ante casos no previstos (se resuelve añadiendo nodos/edges, no prompt).

## Pros y contras de las opciones

- **Opción 1**: 👍 determinista, tipado, depurable · 👎 más edges explícitos.
- **Opción 2**: 👍 flexible · 👎 no determinista, difícil de testear/auditar; el LLM decide el control-flow.
- **Opción 3**: 👍 rápido de montar · 👎 caja negra sin edges tipados ni puntos de HITL claros.
