import type { components } from "@/types/api";

type Ticket = components["schemas"]["Ticket"];
type TokenResponse = components["schemas"]["TokenResponse"];
type User = components["schemas"]["User"];
type Me = components["schemas"]["Me"];
type Message = components["schemas"]["Message"];
type ApprovalTask = components["schemas"]["ApprovalTask"];
type AgentRun = components["schemas"]["AgentRun"];
type KBSearchHit = components["schemas"]["KBSearchHit"];
type KBDocument = components["schemas"]["KBDocument"];
type Notification = components["schemas"]["Notification"];

/** Página de tickets tal como la devuelve `GET /tickets` (Page + items: Ticket[]). */
export interface TicketPage {
  items: Ticket[];
  page: number;
  page_size: number;
  total: number;
}

/** Fixture de un ticket conforme al contrato. `over` permite variar campos por caso. */
export function ticketFixture(over: Partial<Ticket> = {}): Ticket {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    tenant_id: "22222222-2222-2222-2222-222222222222",
    subject: "No puedo publicar el sitio",
    status: "open",
    priority: "normal",
    domain: "rendering-and-publishing",
    category: null,
    requester_id: null,
    assignee_id: null,
    sla_due: null,
    csat: null,
    created_at: "2026-08-13T10:00:00Z",
    updated_at: "2026-08-13T10:00:00Z",
    ...over,
  };
}

/** Fixture de una página de tickets con un elemento. */
export function ticketPageFixture(): TicketPage {
  return { items: [ticketFixture()], page: 1, page_size: 20, total: 1 };
}

/** Fixture de un mensaje del hilo de un ticket conforme al contrato. */
export function messageFixture(over: Partial<Message> = {}): Message {
  return {
    id: "44444444-4444-4444-4444-444444444444",
    ticket_id: "11111111-1111-1111-1111-111111111111",
    author_id: "33333333-3333-3333-3333-333333333333",
    visibility: "public",
    is_ai_draft: false,
    body: "Hola, ¿en qué podemos ayudarte?",
    created_at: "2026-08-13T10:00:00Z",
    ...over,
  };
}

/** Fixture de una página de mensajes con los elementos dados. */
export function messagePageFixture(items: Message[] = [messageFixture()]) {
  return { items, page: 1, page_size: 20, total: items.length };
}

/** Fixture de una tarea de aprobación (draft IA pendiente) conforme al contrato. */
export function approvalTaskFixture(over: Partial<ApprovalTask> = {}): ApprovalTask {
  return {
    id: "55555555-5555-5555-5555-555555555555",
    ticket_id: "11111111-1111-1111-1111-111111111111",
    agent_run_id: "66666666-6666-6666-6666-666666666666",
    status: "pending",
    draft_body: "Puedes publicar el sitio desde el panel de despliegue…",
    final_body: null,
    human_note: null,
    decided_by: null,
    decided_at: null,
    created_at: "2026-08-13T10:00:00Z",
    ...over,
  };
}

/** Fixture de una página de aprobaciones con los elementos dados. */
export function approvalPageFixture(items: ApprovalTask[] = [approvalTaskFixture()]) {
  return { items, page: 1, page_size: 20, total: items.length };
}

/** Fixture de un AgentRun (ejecución del grafo IA) conforme al contrato. */
export function agentRunFixture(over: Partial<AgentRun> = {}): AgentRun {
  return {
    id: "66666666-6666-6666-6666-666666666666",
    ticket_id: "11111111-1111-1111-1111-111111111111",
    run_seq: 1,
    status: "running",
    confidence: null,
    escalated: false,
    sources: [],
    error: null,
    langsmith_trace_url: null,
    created_at: "2026-08-13T10:00:00Z",
    finished_at: null,
    ...over,
  };
}

/** Fixture de un resultado de búsqueda KB conforme al contrato. */
export function kbSearchHitFixture(over: Partial<KBSearchHit> = {}): KBSearchHit {
  return {
    uc_id: "UC-API-081",
    title: "Publicar un sitio",
    section_type: "howto",
    domain: "rendering-and-publishing",
    estado: "active",
    source_url: "https://docs.syntax.io/UC-API-081",
    score: 0.87,
    snippet: "Para publicar el sitio, abre el panel de despliegue…",
    ...over,
  };
}

/** Fixture de un documento KB conforme al contrato. */
export function kbDocumentFixture(over: Partial<KBDocument> = {}): KBDocument {
  return {
    uc_id: "UC-API-081",
    domain: "rendering-and-publishing",
    package: "syntax-api",
    estado: "active",
    title: "Publicar un sitio",
    source_url: "https://docs.syntax.io/UC-API-081",
    updated: "2026-08-13T10:00:00Z",
    ...over,
  };
}

/** Fixture de una notificación in-app conforme al contrato. */
export function notificationFixture(over: Partial<Notification> = {}): Notification {
  return {
    id: "77777777-7777-7777-7777-777777777777",
    type: "approval_requested",
    payload: {},
    read_at: null,
    created_at: "2026-08-13T10:00:00Z",
    ...over,
  };
}

/** Fixture de la respuesta de token de `POST /auth/login` / `POST /auth/refresh`. */
export function tokenFixture(over: Partial<TokenResponse> = {}): TokenResponse {
  return { access_token: "test-access-token", token_type: "bearer", expires_in: 900, ...over };
}

/** Fixture de un usuario conforme al contrato. */
export function userFixture(over: Partial<User> = {}): User {
  return {
    id: "33333333-3333-3333-3333-333333333333",
    tenant_id: "22222222-2222-2222-2222-222222222222",
    email: "soporte@syntax.io",
    status: "active",
    roles: ["agent"],
    ...over,
  };
}

/** Fixture del sujeto autenticado (`GET /auth/me`): usuario + capacidades efectivas. */
export function meFixture(over: Partial<Me> = {}): Me {
  return {
    user: userFixture(),
    capabilities: [
      { capability: "ticket.reply", scope: "tenant" },
      { capability: "approval.decide", scope: "tenant" },
    ],
    ...over,
  };
}
