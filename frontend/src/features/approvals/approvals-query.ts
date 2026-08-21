/** Orden por defecto de la cola (contrato `GET /approvals`): lo más urgente / menos confiable primero. */
export const DEFAULT_APPROVALS_SORT = "sla_due,confidence";

/** Query de la cola de aprobaciones (solo pendientes, orden por política de la cola). */
export interface ApprovalsQuery {
  page: number;
  page_size: number;
  status: "pending";
  sort: string;
}

/**
 * Construye la query de `GET /approvals` de forma determinista: solo `pending`, orden por política
 * (`sla_due,confidence`), página clampada a `>= 1`. El orden lo aplica el servidor (paginación estable);
 * el cliente no re-ordena.
 *
 * @param input Página deseada (opcional).
 */
export function buildApprovalsQuery(input: { page?: number } = {}): ApprovalsQuery {
  return {
    page: Math.max(1, Math.trunc(input.page ?? 1)),
    page_size: 20,
    status: "pending",
    sort: DEFAULT_APPROVALS_SORT,
  };
}

/**
 * Clave de caché de la cola de aprobaciones. Incluye el **tenant activo** (igual que `tickets`/
 * `analytics`) para que una respuesta tardía del tenant anterior no pise la vista del nuevo tras un
 * cambio de tenant (la caché solo se limpia tras confirmar el éxito del switch, no de forma optimista).
 *
 * @param activeTenantId Tenant activo (del switcher o el del sujeto).
 */
export function approvalsQueryKey(activeTenantId: string | null, query: ApprovalsQuery) {
  return ["approvals", activeTenantId, query] as const;
}
