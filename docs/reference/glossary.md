# Referencia · Glosario

Términos del dominio de Syntax.

- **Tenant** — un cliente. En Syntax, cliente = dominio. Existe un tenant-sistema `syntax` para el
  personal de Soporte.
- **Sujeto (subject)** — el usuario autenticado con su conjunto efectivo de `(capacidad, ámbito)`.
- **Capacidad (capability)** — permiso accionable atómico (p.ej. `ticket.reply`). La unidad que un rol
  concede.
- **Ámbito (scope)** — dónde aplica una capacidad: `tenant` o `global` (cross-tenant, solo Soporte).
- **Rol** — conjunto nombrado de capacidades; de sistema (semilla, inmutable) o custom por tenant.
- **RLS (Row Level Security)** — políticas Postgres que filtran filas por `tenant_id` de la conexión
  (`SET app.tenant_id`). Defensa en profundidad sobre el filtro app-level.
- **KB (Knowledge Base)** — la documentación de Syntax (`domains/*/uc/*.md`) ingerida a pgvector.
  **Compartida** entre tenants (sin RLS).
- **UC (caso de uso)** — un documento de la KB (`UC-API-###`), con frontmatter y bloque de Trazabilidad.
- **Estado (`draft`/`active`)** — señal de madurez de un UC; usada como **peso** de retrieval, no como
  filtro (el ~81% del corpus es `draft`).
- **Chunk** — trozo de un UC (por sección H2 tolerante) con su vector y metadatos.
- **Embedding** — vector `vector(N)` de un chunk (N = `EMBEDDING_DIM`, default 1536).
- **Confianza híbrida** — combinación de similitud (retrieval) + `grade` (LLM) que decide auto vs escalado.
- **HITL (Human-In-The-Loop)** — aprobación humana asíncrona del borrador de la IA antes de enviarlo.
- **AgentRun** — una ejecución del grafo para un ticket (`thread_id = ticket_{id}_run_{n}`).
- **ApprovalTask** — la tarea de aprobación de un borrador (pending → approved/edited/rejected).
- **Checkpointer** — `PostgresSaver` de LangGraph que persiste el estado del run (permite reanudar).
- **Visibilidad** — `public` (cliente + Syntax) o `internal` (solo Syntax). Sin `developer` (Fase 2).
- **SLA** — `priority` + `sla_due` en el ticket; el scheduler notifica/escala al vencer.
- **Contrato de API** — el OpenAPI 3.1 (`api-contract.yaml`), única fuente de verdad backend↔frontend.
