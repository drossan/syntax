# Spec transversal del frontend — políticas que aplican a TODA feature

> Nace de `scenario-coverage` (2026-08-11). Son **políticas transversales**: cada tarea de feature las
> cumple y las cubre con tests donde apliquen (además de sus escenarios propios). Enlazada desde el
> `HOW-TO-START-A-TASK.md` del package.
>
> **SDD** — Doc de **referencia** de políticas transversales de la capa SDD; se referencian como **NFR**
> desde [`spec.md`](./spec.md) y se aplican en los [casos de uso](./casos-de-uso/) del frontend.

## 1. Renderizado seguro (anti-XSS) — T8

- **Todo** contenido de origen usuario/IA se renderiza como **texto inerte**: cuerpos de mensaje y draft,
  citas/snippets de KB, nombres de adjunto, textos de notificación, asunto de ticket, nombres de tenant/usuario.
- Prohibido `dangerouslySetInnerHTML` sobre contenido no confiable. Si hay markdown, sanitizar (allow-list).
- Test mínimo por superficie que renderice contenido externo: "marcado tipo script se muestra como texto y no se ejecuta".

## 2. i18n de fecha / número / timezone — T9

- Fechas, horas, contadores de SLA y números se formatean según el **locale** y la **zona horaria** del usuario
  (next-intl / `Intl`). Nada de formatos hardcodeados.
- EN es progresivo: una **clave sin traducir degrada** a un fallback legible (no la clave cruda, no un fallo).
- Pluralización vía ICU.

## 3. Ciclo de vida de la caché de datos — T2 / T3

- **Logout**: limpiar el estado de TanStack Query (no deben quedar datos de la sesión anterior; el `queryClient`
  se resetea). El polling (draft, notificaciones, colas) se detiene en logout/desmontar.
- **Cambio de tenant** (Soporte): invalidar las cachés dependientes de tenant (bandeja, detalle, dashboard,
  cola); descartar respuestas en vuelo del tenant anterior (evitar que "pisen" la vista del nuevo).

## 4. Estados error / loading / empty por-feature — I4

- Cada feature con fetch declara y **testea** sus tres estados:
  - **loading**: skeleton/spinner accesible (aria-busy / live-region).
  - **error**: mapea el envelope `problem+json` (`problemToUi`, tarea 02) → toast/inline + **reintento**.
  - **empty**: estado vacío con acción útil (limpiar filtros / crear / reformular).
- El **gate de mutation** exige que estos estados tengan aserción real, no solo render.

## 5. Reconciliación cliente↔API — T1 / fail-closed

- El RBAC de cliente es UX/defensa en profundidad; la **API es la fuente de verdad**. Una acción visible que
  la API deniegue (**403**) se informa sin cambiar estado.
- **Fail-closed**: si las capacidades de la sesión no se resuelven, no se ofrece ninguna acción/ruta privilegiada.

## 6. Concurrencia optimista — M3

- Mutaciones idempotentes de ticket: optimistic-update con **rollback por envelope**; el resto, invalidación.
- Respuestas fuera de orden y escrituras obsoletas (409/conflicto de versión) dejan el estado **consistente**
  con la última acción real; **confirm** en acciones destructivas.
