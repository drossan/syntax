import { http, HttpResponse } from "msw";

import type { components } from "@/types/api";

type Ticket = components["schemas"]["Ticket"];
type Message = components["schemas"]["Message"];
type AgentRun = components["schemas"]["AgentRun"];
type ApprovalTask = components["schemas"]["ApprovalTask"];

/**
 * Mock **stateful** en memoria para los smokes e2e (Playwright) contra la app real. Encadena el camino
 * dorado: login → crear ticket → generar draft IA → aprobar → mensaje público publicado. Vive solo en el
 * navegador (dev/e2e con `NEXT_PUBLIC_ENABLE_MSW=true`); los tests unitarios usan `handlers.ts` (Node).
 *
 * El estado se mantiene en la memoria de la página y se reinicia en cada carga completa (`page.goto`),
 * por lo que los smokes navegan por clics (client-side) para preservarlo.
 */
const TENANT = "22222222-2222-2222-2222-222222222222";

const TOKEN = { access_token: "e2e-token", token_type: "bearer", expires_in: 900 };

const SUPPORT_ME = {
  user: { id: "agent-1", tenant_id: "syntax", email: "soporte@syntax.io", status: "active", roles: ["support_admin"] },
  capabilities: [
    { capability: "ticket.read", scope: "global" },
    { capability: "ticket.create", scope: "global" },
    { capability: "ticket.transition", scope: "global" },
    { capability: "ticket.assign", scope: "global" },
    { capability: "agent.trigger", scope: "global" },
    { capability: "approval.decide", scope: "global" },
    { capability: "note.internal.read", scope: "global" },
    { capability: "kb.read", scope: "global" },
    { capability: "analytics.read", scope: "global" },
    { capability: "tenant.manage", scope: "global" },
  ],
};

interface Store {
  session: boolean;
  tickets: Ticket[];
  messages: Record<string, Message[]>;
  runs: Record<string, AgentRun>;
  approvals: ApprovalTask[];
}

function seededStore(): Store {
  const seed: Ticket = {
    id: "seed-ticket-1",
    tenant_id: TENANT,
    subject: "Ticket de ejemplo",
    status: "open",
    priority: "normal",
    domain: "rendering-and-publishing",
    category: null,
    requester_id: null,
    assignee_id: null,
    sla_due: null,
    csat: null,
    created_at: "2026-08-13T09:00:00Z",
    updated_at: "2026-08-13T09:00:00Z",
  };
  return { session: false, tickets: [seed], messages: { "seed-ticket-1": [] }, runs: {}, approvals: [] };
}

const store = seededStore();

function page<T>(items: T[]) {
  return { items, page: 1, page_size: 20, total: items.length };
}

function unauthorized() {
  return HttpResponse.json({ type: "about:blank", title: "No autenticado", status: 401 }, { status: 401 });
}

/** Handlers stateful del camino dorado (baseUrl con comodín para cualquier origen). */
export const e2eHandlers = [
  http.post("*/api/v1/auth/login", () => {
    store.session = true;
    // El middleware redirige por presencia de la cookie `refresh_token` (UX, no seguridad). El backend
    // real la pone httpOnly; aquí (dev/e2e) la fija el mock como cookie de cliente para que la app deje
    // pasar a las rutas protegidas. Cualquier email/contraseña vale (el mock no valida credenciales).
    if (typeof document !== "undefined") document.cookie = "refresh_token=mock; path=/";
    return HttpResponse.json(TOKEN);
  }),
  http.post("*/api/v1/auth/refresh", () => (store.session ? HttpResponse.json(TOKEN) : unauthorized())),
  http.get("*/api/v1/auth/me", () => (store.session ? HttpResponse.json(SUPPORT_ME) : unauthorized())),
  http.post("*/api/v1/auth/logout", () => {
    store.session = false;
    if (typeof document !== "undefined") document.cookie = "refresh_token=; path=/; max-age=0";
    return new HttpResponse(null, { status: 204 });
  }),

  http.get("*/api/v1/tickets", () => HttpResponse.json(page(store.tickets))),
  http.post("*/api/v1/tickets", async ({ request }) => {
    const body = (await request.json()) as { subject: string; body?: string; priority?: Ticket["priority"] };
    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    const ticket: Ticket = {
      id,
      tenant_id: TENANT,
      subject: body.subject,
      status: "new",
      priority: body.priority ?? "normal",
      domain: "rendering-and-publishing",
      category: null,
      requester_id: null,
      assignee_id: null,
      sla_due: null,
      csat: null,
      created_at: now,
      updated_at: now,
    };
    store.tickets = [ticket, ...store.tickets];
    store.messages[id] = body.body
      ? [{ id: crypto.randomUUID(), ticket_id: id, author_id: "agent-1", visibility: "public", is_ai_draft: false, body: body.body, created_at: now }]
      : [];
    return HttpResponse.json(ticket, { status: 201 });
  }),
  http.get("*/api/v1/tickets/:id/messages", ({ params }) =>
    HttpResponse.json(page(store.messages[params.id as string] ?? [])),
  ),
  http.get("*/api/v1/tickets/:id", ({ params }) => {
    const ticket = store.tickets.find((t) => t.id === params.id);
    return ticket
      ? HttpResponse.json(ticket)
      : HttpResponse.json({ type: "about:blank", title: "No encontrado", status: 404 }, { status: 404 });
  }),

  http.post("*/api/v1/tickets/:id/ai-draft", ({ params }) => {
    const ticketId = params.id as string;
    const runId = crypto.randomUUID();
    const run: AgentRun = {
      id: runId,
      ticket_id: ticketId,
      run_seq: 1,
      status: "succeeded",
      confidence: 0.9,
      escalated: false,
      sources: [{ uc_id: "UC-API-081", title: "Publicar un sitio", section_type: "howto", source_url: "https://docs.syntax.io/UC-API-081", score: 0.8 }],
      error: null,
      langsmith_trace_url: null,
      created_at: new Date().toISOString(),
      finished_at: new Date().toISOString(),
    };
    store.runs[runId] = run;
    store.approvals = [
      {
        id: crypto.randomUUID(),
        ticket_id: ticketId,
        agent_run_id: runId,
        status: "pending",
        draft_body: "Puedes publicar el sitio desde el panel de despliegue.",
        final_body: null,
        human_note: null,
        decided_by: null,
        decided_at: null,
        created_at: new Date().toISOString(),
      },
      ...store.approvals,
    ];
    return HttpResponse.json(run, { status: 202 });
  }),
  http.get("*/api/v1/agent-runs/:id", ({ params }) => {
    const run = store.runs[params.id as string];
    return run
      ? HttpResponse.json(run)
      : HttpResponse.json({ type: "about:blank", title: "No encontrado", status: 404 }, { status: 404 });
  }),

  http.get("*/api/v1/approvals", () =>
    HttpResponse.json(page(store.approvals.filter((a) => a.status === "pending"))),
  ),
  http.post("*/api/v1/approvals/:id/approve", ({ params }) => {
    const approval = store.approvals.find((a) => a.id === params.id);
    if (!approval) {
      return HttpResponse.json({ type: "about:blank", title: "No encontrado", status: 404 }, { status: 404 });
    }
    approval.status = "approved";
    approval.decided_at = new Date().toISOString();
    const message: Message = {
      id: crypto.randomUUID(),
      ticket_id: approval.ticket_id,
      author_id: "agent-1",
      visibility: "public",
      is_ai_draft: false,
      body: approval.draft_body ?? "",
      created_at: new Date().toISOString(),
    };
    store.messages[approval.ticket_id ?? ""] = [
      ...(store.messages[approval.ticket_id ?? ""] ?? []),
      message,
    ];
    return HttpResponse.json(approval);
  }),

  http.get("*/api/v1/admin/tenants", () =>
    HttpResponse.json(
      page([
        { id: TENANT, slug: "acme", name: "Acme", status: "active" },
        { id: "33333333-3333-3333-3333-333333333333", slug: "globex", name: "Globex", status: "active" },
      ]),
    ),
  ),
  http.get("*/api/v1/notifications", () => HttpResponse.json(page([]))),
];
