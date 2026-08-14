/** Estado de un listado compartible por URL: página + filtros/orden. */
export interface ListState {
  page: number;
  status?: string;
  sort?: string;
}

/**
 * Lee el estado de listado desde la query string (compartible / superviviente a recarga). Página
 * clampada a `>= 1` (default 1); filtros/orden solo si están presentes.
 *
 * @param searchParams Parámetros de la URL.
 */
export function readListState(searchParams: URLSearchParams): ListState {
  const pageRaw = Number(searchParams.get("page"));
  const page = Number.isFinite(pageRaw) && pageRaw >= 1 ? Math.trunc(pageRaw) : 1;
  const state: ListState = { page };
  const status = searchParams.get("status");
  if (status) state.status = status;
  const sort = searchParams.get("sort");
  if (sort) state.sort = sort;
  return state;
}

/**
 * Serializa el estado de listado a query string. Omite la página 1 y los filtros vacíos para mantener
 * URLs limpias. Inverso de `readListState`.
 *
 * @param state Estado a serializar.
 */
export function writeListState(state: ListState): string {
  const params = new URLSearchParams();
  if (state.page > 1) params.set("page", String(state.page));
  if (state.status) params.set("status", state.status);
  if (state.sort) params.set("sort", state.sort);
  return params.toString();
}
