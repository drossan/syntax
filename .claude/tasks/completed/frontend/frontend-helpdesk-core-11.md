---
id: frontend-helpdesk-core-11
package: frontend
plan: helpdesk-core
status: done
priority: 3
depends_on: [frontend-helpdesk-core-09]
estimate: 2h
actual: 0.7h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Adjuntos del ticket — solo visualización

## Description

Listado y descarga de adjuntos del ticket. **Solo visualización** (design-review M2): la subida se difiere
hasta que el puerto de storage del backend sea real (hoy es stub).

## Spec

- Listar adjuntos (nombre, tipo, tamaño) con enlace de descarga; iconografía por tipo.
- Estado empty (sin adjuntos). **Sin** UI de subida en Fase 1.

## Fuera de alcance

- Subida de adjuntos (diferida). Antivirus/límites (backend).

## Scenarios (Gherkin)

```gherkin
Feature: Adjuntos (visualización)

  Scenario: Listar adjuntos existentes
    Given un ticket con dos adjuntos
    When se abre el detalle
    Then se listan ambos con nombre, tipo y tamaño, y enlace de descarga

  Scenario: Ticket sin adjuntos
    Given un ticket sin adjuntos
    When se abre el detalle
    Then se muestra el estado vacío de adjuntos y no hay control de subida
```

## Provides

- Componente de adjuntos (view-only) dentro del detalle.

## Definition of Done

- [x] Tests ANTES (TDD); cada escenario con ≥1 test (con/sin adjuntos, sin control de subida ni input file).
- [x] Solo visualización; enlaces de descarga; estado empty. *(datos en vivo bloqueados: contrato sin GET de adjuntos — ver session log)*
- [x] Lint + typecheck OK; gate de mutation 95.65% (break 80); a11y (`aria-label` de descarga, lista semántica).
- [x] `Provides` disponible (componente en el detalle); `fact-checker` 9/9 VERIFICADO; docs 3 capas + session log.
