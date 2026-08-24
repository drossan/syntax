# Spec — Backend del helpdesk Syntax (API + RAG + agente HITL)

> **Capa SDD** (`features.sdd`). Es el **"QUÉ"** del backend: requisitos en **EARS**, fuente de verdad
> viva. El **"CÓMO"** de cada actor vive en los [casos de uso](#casos-de-uso); las **decisiones** de
> arquitectura, en los [ADR](../adr/adr-index.md). El **detalle técnico** (entidades, catálogo de
> capacidades, diseño del grafo, chunking) vive en las specs de referencia enlazadas por área — este
> `spec.md` **no las duplica**, las gobierna. Fase 1 es **doc-only**
> ([[../adr/0012-backend-fase-1-doc-only-fase-2-diferida]]): estos requisitos fijan el contrato que la
> implementación manual debe cumplir.

## Resumen

Backend Python (FastAPI + LangGraph + Postgres/pgvector) de un **helpdesk multi-tenant con IA
generativa**: gestiona tickets, genera respuestas con RAG sobre la documentación de Syntax y las somete a
**aprobación humana** (HITL) antes de enviarlas, con RBAC por capacidad y aislamiento por tenant.

## User stories

- **US-1 (P1)** — Como **usuario de un cliente**, quiero abrir y seguir tickets de soporte, para resolver mis dudas de producto.
- **US-2 (P1)** — Como **agente de Soporte**, quiero que la IA proponga un borrador de respuesta con citas, para responder más rápido sin perder control.
- **US-3 (P1)** — Como **agente de Soporte**, quiero **aprobar, editar o rechazar** cada borrador IA, para que nada se envíe sin revisión humana.
- **US-4 (P1)** — Como **plataforma**, quiero autorizar por **capacidad + ámbito** y aislar los datos por tenant, para que ningún cliente vea datos de otro.
- **US-5 (P2)** — Como **administrador de un tenant**, quiero gestionar usuarios y componer roles, para adaptar los permisos a mi organización.
- **US-6 (P2)** — Como **plataforma**, quiero ingerir la KB de Syntax y recuperarla semánticamente, para fundamentar las respuestas de la IA.
- **US-7 (P3)** — Como **agente de Soporte**, quiero que los tickets vencidos de SLA escalen y notifiquen, para no incumplir plazos.

## Requisitos funcionales (EARS)

> Notación EARS. Detalle por área en las specs de referencia: autenticación/RBAC → [`rbac.md`](./rbac.md);
> entidades/enums → [`data-model.md`](./data-model.md); agente/HITL → [`agent-graph.md`](./agent-graph.md);
> ingestión/retrieval → [`rag-ingestion.md`](./rag-ingestion.md); superficie HTTP →
> [`../general/api-contract.md`](../general/api-contract.md).

### Autenticación y sesiones — [[../adr/0004-auth-jwt-access-memoria-refresh-cookie-rotacion]]

- **FR-001** — Cuando un usuario presenta credenciales válidas, el sistema DEBERÁ emitir un **access token** (Bearer, TTL corto, sin capacidades embebidas) y establecer un **refresh token** en cookie **httpOnly**.
- **FR-002** — Cuando se presenta un refresh token válido, el sistema DEBERÁ **rotarlo** (nueva cadena `family_id`/`parent_id`) y emitir un access nuevo.
- **FR-003** — Si se presenta un refresh token ya `rotated` o `revoked`, entonces el sistema DEBERÁ **revocar toda su `family_id`** (reuse-detection) y denegar la sesión.
- **FR-004** — Cuando un usuario cierra sesión, el sistema DEBERÁ revocar el refresh vigente **server-side** (logout durable, no solo cliente).
- **FR-005** — El sistema DEBERÁ resolver las **capacidades del sujeto server-side por request** desde la BD, no desde el access token.
- **FR-006** — Si se superan los intentos de login permitidos, entonces el sistema DEBERÁ aplicar **throttling** al login (B.1).

### Contraseña: recuperación e invitación (B.3)

- **FR-007** — Cuando se solicita reset o se invita a un usuario, el sistema DEBERÁ emitir un **`auth_token` de un solo uso** con caducidad y (en Fase 1) enviar el correo en **stub**.
- **FR-008** — Cuando se canjea un `auth_token` válido y no usado, el sistema DEBERÁ fijar la contraseña (Argon2id) y marcar el token `used_at`.
- **FR-009** — Si un `auth_token` está caducado o ya usado, entonces el sistema DEBERÁ rechazar el canje sin revelar la existencia del usuario.

### Autorización y aislamiento multi-tenant — [[../adr/0005-rbac-por-capacidad-y-ambito]] · [[../adr/0006-aislamiento-multi-tenant-app-level-mas-rls]]

- **FR-010** — El sistema DEBERÁ decidir cada acción por **`authorize(subject, capability, scope, resource)`**, nunca por el nombre del rol.
- **FR-011** — Si el sujeto no posee la capacidad requerida en el ámbito del recurso, entonces el sistema DEBERÁ responder **403** con el envelope `problem+json`.
- **FR-012** — Si el sujeto no tiene ningún rol o sus capacidades no se resuelven, entonces el sistema DEBERÁ **denegar todo** (deny-all fail-closed).
- **FR-013** — El sistema DEBERÁ filtrar toda query de negocio por el `tenant_id` del contexto (app-level) **y** aplicar **RLS** de Postgres como defensa en profundidad.
- **FR-014** — Si un sujeto solicita un recurso de otro tenant (sin ámbito `global`), entonces el sistema DEBERÁ responder **404** (no revelar existencia).
- **FR-015** — Donde el sujeto tenga una capacidad de ámbito `global` (Soporte), el sistema DEBERÁ permitir operar cross-tenant (o sobre el tenant del switcher).

### Tickets, mensajes y SLA — [[../adr/0011-entrega-draft-por-polling-no-sse-fase-1]]

- **FR-016** — Cuando un usuario con `ticket.create` abre un ticket, el sistema DEBERÁ crearlo en estado `new` dentro de su tenant.
- **FR-017** — Cuando se solicita una transición de estado, el sistema DEBERÁ aplicarla solo si es válida en la máquina `new→open→pending→resolved→closed→reopened`.
- **FR-018** — Cuando se responde un ticket con `ticket.reply`, el sistema DEBERÁ registrar un `message` de visibilidad **`public`**.
- **FR-019** — Mientras un mensaje sea de visibilidad **`internal`**, el sistema DEBERÁ mostrarlo solo a sujetos con `note.internal.read`.
- **FR-020** — El sistema DEBERÁ registrar toda mutación de negocio en `audit_log` (append-only).
- **FR-021** — Cuando un listado se solicita sin orden explícito, el sistema DEBERÁ aplicar el **orden determinista por defecto** (tickets `-updated_at`; `/approvals` `sla_due,confidence`; `/notifications` `-created_at`).

### Draft IA y aprobación HITL — [[../adr/0007-hitl-asincrono-postgressaver-checkpointer]] · [[../adr/0008-grafo-langgraph-plano-edges-tipados]] · [[../adr/0009-confianza-hibrida-y-auto-approve-por-tenant]]

- **FR-022** — Cuando un sujeto con `agent.trigger` dispara un draft, el sistema DEBERÁ crear un `agent_run` (`thread_id=ticket_{id}_run_{n}`) y ejecutar el grafo `classify→retrieve→grade→generate→decide`.
- **FR-023** — El nodo `classify` DEBERÁ producir `{categoria, dominio(1-de-17), prioridad, resoluble}` con **structured output**, y el dominio DEBERÁ **filtrar el retrieval**.
- **FR-024** — Si el ticket no es clasificable con confianza, entonces el sistema DEBERÁ recuperar **sin filtro de dominio** (fallback) y marcar baja confianza.
- **FR-025** — Cuando la confianza híbrida (similitud + `grade`) queda por debajo del umbral o el contexto es insuficiente, el sistema DEBERÁ **escalar** con `human_note`, sin inventar respuesta.
- **FR-026** — Cuando `decide.requires_approval` es cierto, el sistema DEBERÁ **interrumpir** el grafo (checkpoint Postgres) y crear un `approval_task(pending)`.
- **FR-027** — Cuando llega `approval.decide` (`approved|edited|rejected`), el sistema DEBERÁ reanudar el grafo con `Command(resume=)` y, salvo `rejected`, emitir un `message` **`public`**.
- **FR-028** — Si se decide una `approval_task` ya no-`pending`, entonces el sistema DEBERÁ responder **409** y **no** reanudar el run por segunda vez (idempotencia).
- **FR-029** — Si un nodo del grafo falla, entonces el sistema DEBERÁ marcar `agent_run.status=failed` con `error`, dejando el checkpoint consistente (sin `approval_task` si no se interrumpió).
- **FR-030** — Cuando se reabre un ticket, el sistema DEBERÁ lanzar un **run nuevo** (`run_seq=n+1`, thread nuevo), dejando el anterior superado.
- **FR-031** — El sistema DEBERÁ tratar el contenido del ticket como **input no confiable** (aislado del system-prompt; sin ejecutar instrucciones embebidas) y persistir la traza en `agent_run.langsmith_trace_url`.
- **FR-040** — Si ya hay un `agent_run` no-terminal (`queued`/`running`) para el ticket, o el tenant excede el límite de tasa de `ai-draft` en la ventana actual, entonces el sistema DEBERÁ rechazar el disparo (**409**/**429** respectivamente) sin crear un `agent_run` nuevo.

### KB: ingestión y retrieval — [[../adr/0010-rag-pgvector-chunking-h2-tolerante-estado-peso]]

- **FR-032** — Cuando se ingiere la KB, el sistema DEBERÁ extraer los metadatos de cada documento **según la convención del tipo de fuente configurado** (04 §2), trocear por **H2 tolerante**, embeber y hacer **upsert idempotente por `uc_id`**.
- **FR-033** — Si el frontmatter es malformado o falta `uc_id`, entonces el sistema DEBERÁ **saltar el documento con log** (no entra); si un `uc_id` está **duplicado**, DEBERÁ **fallar el batch** reportando **todos** los ficheros en conflicto para ese `uc_id` (no solo un par).
- **FR-034** — Cuando un documento desaparece del origen, el sistema DEBERÁ **reconciliar** (borrar/tombstone sus `kb_document`/`kb_chunk`/`embedding` huérfanos).
- **FR-035** — Cuando el agente recupera contexto, el sistema DEBERÁ buscar por **similitud coseno** (pgvector, top-k) con filtros `domain/package/estado`, aplicar el peso de `estado` (re-ranking, no filtro duro) y devolver **citas** (`uc_id/title/section_type/source_url`).
- **FR-042** — Cuando se ingiere la KB, el sistema DEBERÁ usar el **tipo de fuente** indicado en la
  invocación y, en su ausencia, el de la configuración, cuyo valor por defecto es el **formato real
  verificado**.
- **FR-043** — Si el tipo de fuente pedido no está registrado, entonces el sistema DEBERÁ terminar como
  **error de uso**, indicando el valor recibido y los válidos, sin tocar la base de datos ni exponer una
  traza cruda.
- **FR-044** — Si la configuración de traducción de packages está presente pero no es un objeto de
  cadena→cadena válido, entonces el sistema DEBERÁ terminar como **error de uso** acotado a la
  ingestión, **sin** impedir el arranque del resto de la aplicación.
- **FR-045** — Si ya hay una ingestión en curso, entonces el sistema DEBERÁ **rechazar de inmediato** la
  segunda (sin esperar y sin ejecutarla en paralelo).
- **FR-046** — Si un run no obtiene ningún documento válido (origen vacío o todo malformado), entonces
  el sistema DEBERÁ terminar con éxito reportando 0 procesados y **no reconciliar nada**, salvo que el
  operador fuerce la reconciliación explícitamente.
- **FR-047** — Si el proveedor de embeddings o la escritura fallan a mitad de un batch, entonces el
  sistema DEBERÁ **abortar el run entero** sin dejar documentos de esa ejecución persistidos.
- **FR-048** — El sistema DEBERÁ tratar el `uc_id` como un espacio de nombres **compartido** entre tipos
  de fuente: los que no reaparecen en el origen actual se reconcilian, y los que reaparecen se
  actualizan en vez de duplicarse, con independencia del tipo de fuente que los ingirió.

### Administración y notificaciones

- **FR-036** — Cuando un sujeto con `user.manage` invita o da de baja usuarios, el sistema DEBERÁ aplicarlo dentro de su ámbito (soft-delete por `status`, sin hard-delete en el flujo normal).
- **FR-037** — Cuando un sujeto con `role.manage` compone un rol custom, el sistema DEBERÁ **rechazar** capacidades de ámbito `global` o que el componedor no posea (no escalada), y limitar el rol a su tenant.
- **FR-038** — Cuando ocurre un evento notificable (aprobación pedida, asignación, respuesta, SLA), el sistema DEBERÁ crear una `notification` in-app para el destinatario (entrega por polling).
- **FR-039** — Mientras un ticket no resuelto tenga `sla_due` vencido o inminente, el scheduler DEBERÁ notificar/escalar de forma **idempotente** (una sola vez por `sla_breached_at`).
- **FR-041** — Cuando un sujeto con `analytics.read` consulta el resumen, el sistema DEBERÁ devolver,
  acotado a su ámbito (tenant, o cross-tenant si `global`): tickets agrupados por `status` (las 6 claves
  de `TicketStatus` siempre presentes, `0` donde no hay datos), el número de `ApprovalTask` `pending`,
  la confianza media de `AgentRun.confidence` (`null` si no hay runs con confianza) y el número de
  tickets con SLA vencido (`sla_due < now()` estricto y no `resolved`/`closed`; un `sla_due` `null`
  nunca cuenta).

## Requisitos no funcionales

- **NFR-001** — **Seguridad**: contraseñas con Argon2id; secretos por entorno (nunca en código); refresh en cookie httpOnly. Detalle: [[../adr/0004-auth-jwt-access-memoria-refresh-cookie-rotacion]].
- **NFR-002** — **Aislamiento**: doble capa app-level + RLS; el aislamiento cross-tenant se verifica con **tests de integración** (footgun `SET app.tenant_id` en pool async).
- **NFR-003** — **Arquitectura hexagonal**: el dominio no importa infra; puertos/adaptadores; Pydantic v2; handlers `async`.
- **NFR-004** — **Observabilidad**: tracing LangSmith de cada run; logging estructurado con **request-id** por request.
- **NFR-005** — **Idempotencia**: doble decisión de aprobación → 409 no-op; upsert de ingestión por `uc_id`; escalado de SLA por `sla_breached_at`.
- **NFR-006** — **Conformidad de contrato**: el `/openapi.json` generado DEBE cubrir el contrato (`OpenAPI generado ⊇ contrato`, [[../adr/0002-contrato-openapi-first]]).
- **NFR-007** — **Internacionalización**: la respuesta del agente se redacta en el **idioma del ticket** (la KB está en español; se traduce si difiere).

## Criterios de éxito

- **SC-001** — Un sujeto sin la capacidad requerida recibe **403**; un recurso de otro tenant recibe **404** (verificable por test de integración RBAC+RLS).
- **SC-002** — Ningún draft se convierte en `message` `public` sin una decisión `approved`/`edited` (o auto explícito con `auto_approve=true`).
- **SC-003** — Una segunda `approval.decide` sobre la misma tarea responde **409** y no duplica el `message`.
- **SC-004** — Tras reiniciar el proceso a mitad de run, la decisión posterior **reanuda** desde el checkpoint sin re-ejecutar nodos completados.
- **SC-005** — Re-ingerir la KB sin cambios **no** genera embeddings nuevos (upsert idempotente); un `uc_id` duplicado aborta el batch.
- **SC-006** — El retrieval devuelve resultados de `draft` (no se vacía por el 81% draft del corpus) y cada respuesta cita sus fuentes.
- **SC-007** — El `/openapi.json` generado supera el gate de conformidad frente a `api-contract.yaml`.

## Casos de uso

- [CU-BE-01: Autenticación y sesiones](./casos-de-uso/CU-BE-01-autenticacion-y-sesiones.md)
- [CU-BE-02: Recuperación e invitación de contraseña](./casos-de-uso/CU-BE-02-recuperacion-e-invitacion-de-contrasena.md)
- [CU-BE-03: Autorización por capacidad y aislamiento tenant](./casos-de-uso/CU-BE-03-autorizacion-y-aislamiento-tenant.md)
- [CU-BE-04: Ciclo de vida del ticket](./casos-de-uso/CU-BE-04-ciclo-de-vida-del-ticket.md)
- [CU-BE-05: Clasificación y retrieval RAG](./casos-de-uso/CU-BE-05-clasificacion-y-retrieval-rag.md)
- [CU-BE-06: Draft IA y aprobación HITL](./casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md)
- [CU-BE-07: Ingestión de la KB](./casos-de-uso/CU-BE-07-ingestion-de-la-kb.md)
- [CU-BE-08: Scheduler de SLA](./casos-de-uso/CU-BE-08-scheduler-de-sla.md)
- [CU-BE-09: Administración de tenants, usuarios y roles](./casos-de-uso/CU-BE-09-administracion-tenants-usuarios-roles.md)
- [CU-BE-10: Notificaciones in-app](./casos-de-uso/CU-BE-10-notificaciones-in-app.md)
- [CU-BE-11: Resumen de analytics](./casos-de-uso/CU-BE-11-resumen-de-analytics.md)

## Fuera de alcance

- **Código de negocio ejecutable** en Fase 1 (esqueleto + guión + specs; [[../adr/0012-backend-fase-1-doc-only-fase-2-diferida]]).
- **SSO/OIDC** (Fase 2), **nota al desarrollador / visibilidad `developer`** (Fase 2), **streaming SSE** del draft (seam `astream`, [[../adr/0011-entrega-draft-por-polling-no-sse-fase-1]]).
- Email real, BM25 híbrido, storage S3 real, colas/workers generales (salvo el scheduler de SLA).

## Aclaraciones pendientes

> Huecos **declarados y acotados** (no bloquean el contrato de Fase 1; se resuelven antes de producción):
> política de **retención/GDPR** (ventana de retención, borrado por solicitud, anonimización — el modelo
> con SET NULL + soft-delete la **habilita**, no la implementa; `data-model.md` §7) y **umbral de confianza**
> del agente (se calibra al implementar; `agent-graph.md` §5). Sin entradas `NECESITA ACLARACIÓN` abiertas.
