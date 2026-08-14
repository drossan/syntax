# Informe QA — scenario-coverage del plan `frontend-helpdesk-core` (2026-08-11)

> Subagente QA fresco sobre las 21 tareas + plan. Referencia para las sesiones TDD: cada sesión debe
> revisar los huecos de SU tarea aquí e incorporarlos como tests (los de mayor valor ya están fijados en
> la spec transversal, la tarea 22 y los `## Refuerzos` de 05/07/09/10/13/15/17). El resto (cola larga)
> se recoge al ejecutar. Las specs de contrato (`api-contract`/`rbac`/`data-model`) son deliverables del
> backend; muchos huecos "spec implícita" se cierran cuando existan.

## Transversales (fijados: T8/T9/T2/T3 → `specs/frontend/cross-cutting.md`; T5/T6/T7/T10 → tarea 22)

- **T1** Reconciliación 403: acción visible en cliente que la API deniega por permiso real → informar, no mutar.
- **T2** Logout limpia el estado de TanStack Query (no quedan datos de la sesión anterior). *(cross-cutting)*
- **T3** Cambio de tenant invalida cachés (bandeja/detalle/dashboard); descartar respuestas en vuelo del tenant viejo. *(cross-cutting)*
- **T4** Sesión expira a mitad de acción: form/mutación en vuelo recibe 401 → refresh transparente → se completa sin perder datos.
- **T5** URL-persistencia de filtros/orden/página (compartible + sobrevive recarga). *(tarea 22)*
- **T6** Confirmación al navegar fuera con cambios sin guardar (08/15/17). *(tarea 22)*
- **T7** Estado sin-conexión + recuperación al volver la red. *(tarea 22)*
- **T8** Política anti-XSS: todo contenido de usuario/IA (mensajes, draft, KB, nombre de adjunto, notificación) se renderiza como texto inerte. *(cross-cutting)*
- **T9** i18n de fecha/número/timezone del usuario (07/09/12/19). *(cross-cutting)*
- **T10** Indicador de "no leído" en tickets (bandeja + detalle). *(tarea 22)*

## Por tarea (cola larga — incorporar al ejecutar)

- **02** cliente: 403/500/red/timeout/non-JSON en el outline; 401 de LOGIN no dispara refresh (bucle); envelope sin `errors[]`→solo toast; `code` sin clave i18n→genérico; 429 con `Retry-After`/máx reintentos.
- **03** auth: login con credenciales inválidas; bootstrap con refresh caducado sin flash; single-flight **multi-tab**; volver al deep-link tras login; logout durante refresh en vuelo / doble-submit login.
- **04** contraseña: política + confirmación no coincide; token **ya usado** vs caducado; 429 en forgot; rama de éxito de invitación (sesión vs redirect) + invitación ya aceptada.
- **05** RBAC: fail-closed si no cargan capacidades; capacidad de ámbito-tenant no aplica a otro tenant; cliente deep-link a otro tenant denegado; reasignación de rol a mitad de sesión. *(fijados en Refuerzos)*
- **06** shell: persistencia del **idioma** tras recarga; colapso responsive móvil; nav con cero entradas; foco/teclado en menús del header.
- **07** bandeja: última página / fuera de rango; estado error/carga; SLA **inminente** + filtros combinados; aislamiento de tenant en la lista; XSS en asunto. *(error+tenant fijados en Refuerzos)*
- **08** alta: doble-submit/idempotencia; red/500/timeout sin perder datos; fronteras de campo (longitud, solo-espacios, enum); soporte crea en el tenant activo; nav-guard (T6).
- **09** detalle: nota interna en payload NUNCA renderizada al cliente (defensa en profundidad); hilo vacío / solo-internal para cliente; ticket inexistente/otro-tenant→404/403; error/carga; XSS en cuerpo; empates de orden + timezone. *(defensa+aislamiento fijados en Refuerzos)*
- **10** mutaciones: cancelar-confirm no muta; escritura obsoleta/409 (dos agentes); respuestas fuera de orden consistentes; idempotencia doble-confirm; matriz de transiciones (reopened/resolved→closed); 403/409; foco/teclado del diálogo; respuesta-pública ambigua (fijar aquí o 15). *(concurrencia+cancel fijados en Refuerzos)*
- **11** adjuntos: enlace caducado/404; tipo/tamaño frontera; aislamiento por tenant del enlace; nombre con marcado malicioso.
- **12** SLA/timeline: SLA **inminente** + sin-SLA; coherencia bandeja↔detalle; timeline vacío/error/carga; timezone/relativo; XSS en actor.
- **13** cola: desempate estable SLA+confianza; error/carga; dos agentes toman la misma (obsoleta desaparece); refresco tras decidir. *(concurrencia+desempate fijados en Refuerzos)*
- **14** draft: el polling PARA siempre (done/failed **y al desmontar**); idempotencia de re-disparo; fallo de transporte durante el sondeo; run colgado en running (máx); draft con fuentes vacías/confianza 0-100; live-region a11y; XSS en draft/citas.
- **15** decisiones: **doble aprobación** idempotente/409; dos agentes deciden el mismo draft; cancelar-reject no rechaza; errores approve/reject (403/409/500); editar a vacío no publica; el público aprobado aparece en el hilo (revalida); "escalar" sin flujo definido. *(doble-aprobación+cancel fijados en Refuerzos)*
- **16** KB: error/carga + documento 404; query corta/solo-espacios/paginación; **race de búsqueda** (respuesta tardía no sobrescribe); visibilidad/tenant/estado-borrador de la KB; XSS en snippet; ciclos en relacionados.
- **17** admin: **confirm de borrado** destructivo; 422/409 (dominio duplicado); escalada cross-tenant por deep-link; auto-borrado/auto-lockout (último admin); fronteras de listado; marcado malicioso en nombre. *(confirm+cross-tenant fijados en Refuerzos)*
- **18** roles: **retirar** rol; escalada de privilegios en asignación (client_admin no asigna rol global); auto-lockout; errores 403/500; acotación por tenant del catálogo.
- **19** dashboard: error/carga; cliente no fuerza agregado global; rango de fechas/datos parciales/números grandes; a11y de gráficas (alternativa textual, contraste dark); race al cambiar rango.
- **20** transversales: cero/muchas notificaciones (99+); el polling para en logout/desmontar; rollback de "marcar leído" si falla; **fallback de clave i18n ausente en EN**; navegación desde la notificación; plurales ICU + notificación de otro tenant; XSS en notificación.
- **21** e2e: recarga dura mantiene sesión (bootstrap por cookie); logout limpia cookie+estado.

## (B) Fuera del alcance declarado — 14 hallazgos (reconocidos, NO convertidos en tarea)

Mapean a bullets del `### Fuera de alcance` del plan: B1 visibilidad `developer`/nota-al-desarrollador · B2 streaming SSE del draft · B3 subida de adjuntos · B4 composer de roles custom · B5 email real · B6 bulk actions · B7 merge/duplicados · B8 canned responses · B9 CSAT UI · B10 impersonation · B11 webhooks/push · B12 SSO/OIDC · B13 BFF/data-fetching en servidor · B14 backend real. Todos correctamente diferidos; disponibles como semilla de Fase 2.
