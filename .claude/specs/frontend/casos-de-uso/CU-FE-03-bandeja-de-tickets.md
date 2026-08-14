# CU-FE-03 — Bandeja de tickets

> **SDD** (Cockburn + Gherkin). CÓMO para FR-012 de [`../spec.md`](../spec.md). Datos:
> [`../../backend/data-model.md`](../../backend/data-model.md) (`ticket`). Contrato:
> [`../../general/api-contract.md`](../../general/api-contract.md) (orden determinista, paginación).

- **Ámbito**: frontend (feature tickets — lista)
- **Nivel**: objetivo de usuario
- **Actor primario**: agente/usuario
- **Interesados e intereses**:
  - Agente — encontrar y priorizar tickets rápido; compartir vistas por URL.
  - Usuario — ver sus tickets con su estado y SLA.

## Precondiciones

- El sujeto tiene `ticket.read`.

## Garantía mínima

- Los filtros/orden nunca muestran tickets fuera del tenant/permiso del sujeto.

## Garantía de éxito (postcondición)

- Se muestra la lista filtrada, ordenada de forma determinista, con el estado reflejado en la URL.

## Disparador

- El usuario abre la bandeja o cambia filtros/búsqueda/orden.

## Escenario principal (éxito)

1. La app carga la bandeja (TanStack Table) con el **orden determinista por defecto** (`-updated_at`).
2. El usuario filtra por estado/prioridad/asignación y busca por texto.
3. Los filtros/orden/página se reflejan en la **URL** (compartible, recargable).

## Extensiones (flujos alternativos y de error)

- **1a.** Cargando: skeleton accesible (aria-busy).
- **1b.** Error de API: mensaje mapeado desde `problem+json` + **reintento**.
- **1c.** Sin resultados: estado **empty** con acción útil (limpiar filtros).
- **2a.** Indicadores de **SLA** (vencido/inminente) visibles en cada fila.

## Reglas de negocio

- **RN-1** — El orden por defecto es determinista y estable ante paginación.
- **RN-2** — El estado de la vista (filtros/orden/página) vive en la URL (URL-state).

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Bandeja de tickets

  Scenario: Carga con orden determinista
    Given un usuario con acceso a tickets
    When abre la bandeja sin elegir orden
    Then los tickets se muestran con el orden por defecto por fecha de actualización descendente

  Scenario: Filtrar refleja el estado en la URL
    Given la bandeja de tickets abierta
    When el usuario filtra por estado y prioridad
    Then la lista se actualiza y los filtros quedan reflejados en la URL

  Scenario: Restaurar la vista desde la URL
    Given una URL con filtros y orden concretos
    When el usuario abre esa URL
    Then la bandeja se muestra ya filtrada y ordenada según la URL

  Scenario: Estado vacío con acción
    Given un conjunto de filtros que no devuelve tickets
    When se aplica el filtro
    Then se muestra un estado vacío que permite limpiar los filtros

  Scenario: Error de carga con reintento
    Given un fallo de la API al cargar la bandeja
    When se produce el error
    Then se muestra el mensaje mapeado y una acción de reintento
```
