"""alembic/versions/0001_initial_schema — migración inicial (GUIÓN, no implementada).

GUIÓN (→ tarea 08) — materializa data-model (03)
------------------------------------------------
Este fichero es el **guión** de la primera migración; la implementación real (``op.create_table`` etc.)
la escribe el owner. Orden de ``upgrade()``:

1. ``CREATE EXTENSION IF NOT EXISTS vector;`` (pgvector — habilita el tipo ``vector(N)``).
2. Crear tablas de **identidad/RBAC**, **negocio** y **KB** (todas las de ``models/``), con enums nativos,
   FKs y las cascadas de 03 §7 (SET NULL requester/assignee/author/actor; CASCADE agregado ticket + KB;
   RESTRICT en ``tenant``).
3. Índices (03 §9): único ``kb_document.uc_id``; único ``user(tenant_id,email)``; ``ticket`` compuestos;
   ``message(ticket_id,created_at)``; ``agent_run(ticket_id,run_seq)``; y el **índice pgvector** sobre
   ``embedding.vector`` (ivfflat con ``lists`` + ``ANALYZE``, o hnsw — decidir aquí; 03/14).
4. **RLS en las tablas de NEGOCIO** (ticket, message, attachment, approval_task, agent_run, audit_log,
   notification). Por cada una:
       ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
       CREATE POLICY tenant_isolation ON <t>
         USING (tenant_id = current_setting('app.tenant_id')::uuid)
         WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
   (Considerar ``FORCE ROW LEVEL SECURITY`` y una policy de bypass para el rol de Soporte/global.)
   Las tablas **KB** (kb_document/kb_chunk/embedding) e **identidad/RBAC** **NO** llevan esta RLS de
   tenant (KB global; identidad gobernada por RBAC).

``downgrade()``: DROP POLICY + DISABLE RLS + DROP tablas en orden inverso; (la extensión ``vector`` se
suele dejar).

⚠️ El SET del contexto (``app.tenant_id``) NO va aquí sino por conexión/transacción — ver el footgun en
``app/infra/db/session.py`` (exige tests de integración contra Postgres real).

Identificadores de la revisión: revision ``0001_initial_schema``; down_revision ``None`` (es la primera).
"""
