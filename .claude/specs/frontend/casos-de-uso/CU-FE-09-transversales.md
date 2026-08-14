# CU-FE-09 — Transversales (notificaciones, i18n, estados, offline)

> **SDD** (Cockburn + Gherkin). CÓMO para FR-023, FR-025…FR-027 de [`../spec.md`](../spec.md). Políticas:
> [`../cross-cutting.md`](../cross-cutting.md) §2, §4. Backend:
> [CU-BE-10](../../backend/casos-de-uso/CU-BE-10-notificaciones-in-app.md).

- **Ámbito**: frontend (políticas transversales aplicadas por todas las features)
- **Nivel**: subfunción (transversal)
- **Actor primario**: cualquier usuario
- **Interesados e intereses**:
  - Usuario — una experiencia consistente, localizada y robusta ante fallos.
  - Plataforma — estados y a11y homogéneos; sin pérdida de trabajo por navegación.

## Precondiciones

- El usuario está autenticado con su locale y timezone.

## Garantía mínima

- Una clave i18n sin traducir degrada a un fallback legible (nunca la clave cruda ni un fallo).

## Garantía de éxito (postcondición)

- Notificaciones al día por polling; fechas/números localizados; estados loading/error/empty coherentes.

## Disparador

- Cualquier feature con fetch, cambio de idioma, evento notificable o pérdida de conexión.

## Escenario principal (éxito)

1. La app hace **polling** de notificaciones y refleja el contador de **no-leído**.
2. Fechas, números y contadores de SLA se formatean según **locale/timezone**.
3. Cada feature con fetch muestra sus estados **loading/error/empty**.

## Extensiones (flujos alternativos y de error)

- **2a.** Clave EN sin traducir: **degrada** a un fallback legible.
- **4a.** **Offline**: la app degrada de forma legible y reintenta al recuperar conexión.
- **5a.** Navegación fuera con cambios sin guardar: **nav-guard** avisa.

## Reglas de negocio

- **RN-1** — El polling se detiene en logout/desmontar.
- **RN-2** — Pluralización vía ICU; nada de formatos hardcodeados.

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Transversales del helpdesk

  Scenario: Contador de notificaciones no leídas
    Given un usuario con notificaciones nuevas
    When la aplicación sondea las notificaciones
    Then el contador de no leídas se actualiza

  Scenario: Localización de fecha y número
    Given un usuario con un locale y una zona horaria concretos
    When ve fechas y contadores de SLA
    Then se muestran formateados según su locale y zona horaria

  Scenario: Clave sin traducir degrada a fallback
    Given una interfaz en un idioma con una clave sin traducir
    When se renderiza esa clave
    Then se muestra un texto de fallback legible, no la clave cruda

  Scenario: Degradación offline
    Given un usuario que pierde la conexión
    When intenta una acción que requiere red
    Then la interfaz degrada de forma legible y reintenta al recuperar la conexión

  Scenario: Aviso al salir con cambios sin guardar
    Given un formulario con cambios sin guardar
    When el usuario intenta navegar fuera
    Then se le avisa antes de abandonar la vista
```
