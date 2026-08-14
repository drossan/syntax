import type { components } from "@/types/api";

type KBDomain = components["schemas"]["KBDomain"];
type Package = components["schemas"]["Package"];
type KBEstado = components["schemas"]["KBEstado"];

/** Entrada de la búsqueda KB (q obligatoria; filtros opcionales del contrato). */
export interface KbSearchInput {
  q: string;
  domain?: KBDomain;
  package?: Package;
  estado?: KBEstado;
  page?: number;
}

/** Query final para `GET /kb/search`. */
export interface KbSearchQuery {
  q: string;
  page: number;
  page_size: number;
  domain?: KBDomain;
  package?: Package;
  estado?: KBEstado;
}

/**
 * Construye la query de `GET /kb/search`: `q` siempre, page clampada a `>= 1`, y solo los filtros
 * definidos (nunca claves `undefined`).
 *
 * @param input Término de búsqueda + filtros.
 */
export function buildKbSearchQuery(input: KbSearchInput): KbSearchQuery {
  const query: KbSearchQuery = {
    q: input.q,
    page: Math.max(1, Math.trunc(input.page ?? 1)),
    page_size: 20,
  };
  if (input.domain !== undefined) query.domain = input.domain;
  if (input.package !== undefined) query.package = input.package;
  if (input.estado !== undefined) query.estado = input.estado;
  return query;
}

/** Clave de caché de una búsqueda KB (por su input; `null` mientras no hay término). */
export function kbSearchKey(input: KbSearchInput | null) {
  return ["kb", "search", input] as const;
}

/** Clave de caché de un documento KB por `uc_id`. */
export function kbDocumentKey(ucId: string) {
  return ["kb", "document", ucId] as const;
}

/** Clave de caché de los relacionados de un documento (por dominio + el uc_id excluido). */
export function kbRelatedKey(domain: string | undefined, excludeUcId: string) {
  return ["kb", "related", domain, excludeUcId] as const;
}

/**
 * Deriva los documentos **relacionados** excluyendo el actual. Heurística honesta con el contrato
 * (`KBDocument` no expone un grafo de relacionados): se relacionan por mismo dominio.
 *
 * @param docs Documentos candidatos (del mismo dominio).
 * @param excludeUcId `uc_id` del documento actual, que no se relaciona consigo mismo.
 */
export function relatedDocuments<T extends { uc_id?: string }>(docs: T[], excludeUcId: string): T[] {
  return docs.filter((doc) => doc.uc_id !== excludeUcId);
}
