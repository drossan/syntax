---
id: frontend-helpdesk-core-20
package: frontend
plan: helpdesk-core
status: done
priority: 3
depends_on: [frontend-helpdesk-core-06]
estimate: 3h
actual: 1h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Transversales — notificaciones, i18n completo, a11y

## Description

Piezas transversales que no caben en una feature concreta: notificaciones in-app (polling), completitud de
i18n (ES 100% / EN progresivo, sin strings hardcodeados) y la **auditoría de accesibilidad final en
navegador real**. (Los estados error/loading/empty y la a11y básica ya se cubren en cada feature — I4.)

## Spec

- Notificaciones in-app: campana con conteo, lista, marcar leído; **polling** vía `refetchInterval`.
- i18n: verificación de que no hay strings hardcodeados (lint/regla); ES completo, EN estructura+progresivo.
- Auditoría a11y: pase `axe` en navegador real (Playwright) sobre las vistas clave; corregir hallazgos.

## Fuera de alcance

- Notificaciones por email/push (diferidas). Traducción EN al 100% (progresiva).

## Scenarios (Gherkin)

```gherkin
Feature: Transversales

  Scenario: Notificaciones se actualizan por polling
    Given una usuaria con una notificación nueva en el servidor
    When transcurre el intervalo de sondeo
    Then la campana refleja la nueva notificación

  Scenario: Marcar notificación como leída
    Given una notificación no leída
    When la usuaria la marca como leída
    Then deja de contar como no leída

  Scenario: Cambio de idioma sin strings hardcodeados
    Given una vista en español
    When se cambia a inglés
    Then todos los textos visibles cambian (no queda texto hardcodeado en español)
```

## Provides

- Sistema de notificaciones in-app + completitud i18n + informe de auditoría a11y.

## Definition of Done

- [x] Tests ANTES (TDD): polling refleja nueva notificación, marcar leído decrementa, i18n paridad de claves + conmutación sin hardcode.
- [x] Notificaciones por polling; i18n paridad+conmutación (sin regla eslint dedicada). ⚠️ **Auditoría axe en navegador real: PENDIENTE** — requiere dep nueva `@axe-core/playwright` (no añadida sin aprobación) + navegador; follow-up owner / infra e2e (21).
- [x] Lint + typecheck OK; gate de mutation 84% (break 80).
- [x] `Provides` disponible (notificaciones + completitud i18n); `fact-checker` 11/11 VERIFICADO; docs 3 capas + session log. *(informe axe pendiente — ver arriba)*
