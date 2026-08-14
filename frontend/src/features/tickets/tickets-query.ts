import type { components } from "@/types/api";

type TicketStatus = components["schemas"]["TicketStatus"];
type TicketPriority = components["schemas"]["TicketPriority"];
type KBDomain = components["schemas"]["KBDomain"];

/** Tamaño de página por defecto (coherente con el contrato: `page_size` default 20). */
export const DEFAULT_PAGE_SIZE = 20;
/** Orden por defecto determinista de `GET /tickets` (contrato: `-updated_at`). */
export const DEFAULT_SORT = "-updated_at";

/**
 * Filtros de la bandeja soportados por el contrato (`GET /tickets`). Búsqueda de texto (`q`) y `tag`
 * NO existen en el OpenAPI v0.1.0 → no se emiten (no se inventan parámetros). El aislamiento por
 * tenant es server-side (no hay parámetro de tenant): el cliente nunca amplía su alcance.
 */
export interface TicketFilters {
  status?: TicketStatus;
  priority?: TicketPriority;
  domain?: KBDomain;
  assignee_id?: string;
}

/** Entrada del hook de bandeja: página + filtros (todo opcional; se aplican defaults deterministas). */
export interface TicketQueryInput {
  page?: number;
  page_size?: number;
  sort?: string;
  filters?: TicketFilters;
}

/** Parámetros de query finales para `GET /tickets` (solo claves definidas). */
export interface TicketQuery {
  page: number;
  page_size: number;
  sort: string;
  status?: TicketStatus;
  priority?: TicketPriority;
  domain?: KBDomain;
  assignee_id?: string;
}

/**
 * Construye los parámetros de `GET /tickets` de forma **determinista**: página clampada a `>= 1`,
 * `page_size`/`sort` con defaults del contrato, y solo los filtros definidos (nunca claves `undefined`
 * ni un parámetro de tenant). Es la fuente única de la query para que orden y paginación sean estables.
 *
 * @param input Página y filtros deseados (todo opcional).
 * @returns Objeto de query listo para openapi-fetch.
 */
export function buildTicketQuery(input: TicketQueryInput = {}): TicketQuery {
  const page = Math.max(1, Math.trunc(input.page ?? 1));
  const query: TicketQuery = {
    page,
    page_size: input.page_size ?? DEFAULT_PAGE_SIZE,
    sort: input.sort ?? DEFAULT_SORT,
  };

  const filters = input.filters ?? {};
  if (filters.status !== undefined) query.status = filters.status;
  if (filters.priority !== undefined) query.priority = filters.priority;
  if (filters.domain !== undefined) query.domain = filters.domain;
  if (filters.assignee_id !== undefined) query.assignee_id = filters.assignee_id;

  return query;
}

/**
 * Clave de caché de TanStack Query para una bandeja. Incluye el **tenant activo** para aislar la
 * caché entre tenants (cross-cutting §3: un cambio de tenant no arrastra datos del anterior).
 *
 * @param activeTenantId Tenant activo (del switcher de Soporte o el del sujeto).
 * @param query Query ya construida (`buildTicketQuery`).
 */
export function ticketsQueryKey(activeTenantId: string | null, query: TicketQuery) {
  return ["tickets", activeTenantId, query] as const;
}
