# CU-BE-11 — Resumen de analytics

> **SDD** (Cockburn + Gherkin). CÓMO para FR-041 de [`../spec.md`](../spec.md). Ámbito y capacidad:
> [`../rbac.md`](../rbac.md). Entidades agregadas: [`../data-model.md`](../data-model.md)
> (`ticket`, `approval_task`, `agent_run`).

- **Ámbito**: backend (resumen agregado del dashboard)
- **Nivel**: objetivo de usuario
- **Actor primario**: sujeto con la capacidad `analytics.read`
- **Interesados e intereses**:
  - Responsable de soporte — ver de un vistazo la carga de tickets, lo pendiente de aprobar y los SLA vencidos.
  - Plataforma — que el resumen respete el ámbito del sujeto (tenant o `global`), sin fugas entre tenants.

## Precondiciones

- El sujeto está autenticado y tiene la capacidad `analytics.read`, en ámbito `tenant` o `global`.

## Garantía mínima

- El resumen nunca agrega datos fuera del ámbito del sujeto: en ámbito `tenant`, solo los de su tenant.

## Garantía de éxito (postcondición)

- El sujeto recibe las cuatro métricas del resumen: tickets por `status`, aprobaciones pendientes,
  confianza media y tickets con SLA vencido.

## Disparador

- El sujeto consulta el resumen de analytics.

## Escenario principal (éxito)

1. El sujeto con `analytics.read` consulta el resumen.
2. El sistema determina el ámbito: su tenant, o **cross-tenant** si la capacidad es de ámbito `global`.
3. El sistema agrega, dentro de ese ámbito: tickets agrupados por `status`, `approval_task` en `pending`,
   media de `agent_run.confidence` y tickets con SLA vencido.
4. El sistema devuelve las cuatro métricas juntas.

## Extensiones (flujos alternativos y de error)

- **1a.** El sujeto **no** tiene `analytics.read`: la consulta se **deniega** (misma respuesta que
  cualquier otra capacidad ausente, CU-BE-03) y no se agrega nada.
- **3a.** Un `status` de ticket **sin ningún ticket** en el ámbito: aparece igualmente en el resultado
  con valor `0` — las 6 claves de `TicketStatus` están **siempre** presentes, para que el consumidor no
  tenga que distinguir "cero" de "ausente".
- **3b.** **Ningún** `agent_run` con confianza en el ámbito: la confianza media es **nula**, no `0`
  (que sería indistinguible de una confianza media real de cero).
- **3c.** Un ticket con `sla_due` **nulo** nunca cuenta como SLA vencido (no tiene compromiso que
  incumplir).
- **3d.** Un ticket ya `resolved`/`closed` **no** cuenta como SLA vencido aunque su `sla_due` haya
  pasado: el compromiso se cerró.

## Reglas de negocio

- **RN-1** — El ámbito lo fija la capacidad, no un parámetro de la consulta: `analytics.read` en ámbito
  `global` agrega cross-tenant; en ámbito `tenant`, se acota al tenant del sujeto.
- **RN-2** — "SLA vencido" es `sla_due` **estrictamente anterior** al instante de la consulta **y** el
  ticket no está en un estado terminal (`resolved`/`closed`).
- **RN-3** — La confianza media se calcula **solo** sobre los `agent_run` que tienen confianza; los que
  no la tienen no cuentan como cero (no desplazan la media hacia abajo).

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Resumen de analytics

  Scenario: El resumen se acota al tenant del solicitante
    Given tickets en el tenant del solicitante y tickets en otro tenant
      And un sujeto con la capacidad de lectura de analytics en ámbito de su tenant
    When consulta el resumen de analytics
    Then las métricas solo cuentan los datos de su tenant

  Scenario: El ámbito global agrega todos los tenants
    Given tickets repartidos en varios tenants
      And un sujeto con la capacidad de lectura de analytics en ámbito global
    When consulta el resumen de analytics
    Then las métricas cuentan los datos de todos los tenants

  Scenario: Sin la capacidad de lectura de analytics no se accede al resumen
    Given un sujeto sin la capacidad de lectura de analytics
    When intenta consultar el resumen de analytics
    Then la consulta se deniega y no se devuelve ninguna métrica

  Scenario: Todos los estados de ticket están presentes aunque no tengan tickets
    Given un ámbito donde solo algunos estados de ticket tienen tickets
    When se consulta el resumen de analytics
    Then el desglose por estado incluye todos los estados, con cero en los que no tienen tickets

  Scenario: Sin ejecuciones con confianza la media es nula
    Given un ámbito sin ninguna ejecución del agente que tenga confianza registrada
    When se consulta el resumen de analytics
    Then la confianza media es nula, no cero

  Scenario: La confianza media ignora las ejecuciones sin confianza
    Given un ámbito con ejecuciones del agente, algunas con confianza y otras sin ella
    When se consulta el resumen de analytics
    Then la confianza media se calcula solo sobre las que tienen confianza

  Scenario: Las aprobaciones pendientes cuentan solo las que siguen pendientes
    Given un ámbito con tareas de aprobación pendientes y otras ya resueltas
    When se consulta el resumen de analytics
    Then el recuento de aprobaciones pendientes cuenta solo las pendientes

  Scenario Outline: Qué ticket cuenta como SLA vencido
    Given un ticket <situación>
    When se consulta el resumen de analytics
    Then <resultado> en el recuento de SLA vencidos

    Examples:
      | situación                                          | resultado   |
      | con compromiso de SLA ya pasado y sin resolver     | cuenta      |
      | con compromiso de SLA aún por vencer               | no cuenta   |
      | sin ningún compromiso de SLA                       | no cuenta   |
      | con compromiso de SLA pasado pero ya resuelto      | no cuenta   |
```
