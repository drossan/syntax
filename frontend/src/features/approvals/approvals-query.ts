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

/** Clave de caché de la cola de aprobaciones. */
export function approvalsQueryKey(query: ApprovalsQuery) {
  return ["approvals", query] as const;
}
