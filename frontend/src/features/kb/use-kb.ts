import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-context";
import type { components } from "@/types/api";

import {
  buildKbSearchQuery,
  kbDocumentKey,
  kbRelatedKey,
  kbSearchKey,
  relatedDocuments,
  type KbSearchInput,
} from "./kb-query";

type KBDomain = components["schemas"]["KBDomain"];

/**
 * Búsqueda semántica en la KB (`GET /kb/search`). Solo se dispara con una `q` no vacía (sin término no
 * hay búsqueda). Orden por `score desc` server-side.
 *
 * @param input Término + filtros; `null` mientras no haya término.
 */
export function useKbSearch(input: KbSearchInput | null) {
  const { client } = useAuth();

  return useQuery({
    queryKey: kbSearchKey(input),
    enabled: input !== null,
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const { data, error } = await client.GET("/kb/search", {
        params: { query: buildKbSearchQuery(input as KbSearchInput) },
      });
      if (error) throw error;
      return data;
    },
  });
}

/**
 * Documento KB por `uc_id` (`GET /kb/documents/{uc_id}`). Propaga 404 para mostrar no-encontrado.
 *
 * @param ucId Clave del documento.
 */
export function useKbDocument(ucId: string) {
  const { client } = useAuth();

  return useQuery({
    queryKey: kbDocumentKey(ucId),
    queryFn: async () => {
      const { data, error } = await client.GET("/kb/documents/{uc_id}", {
        params: { path: { uc_id: ucId } },
      });
      if (error) throw error;
      return data;
    },
  });
}

/**
 * Documentos **relacionados** por dominio (`GET /kb/documents?domain=`), excluyendo el actual. Solo se
 * dispara cuando se conoce el dominio del documento.
 *
 * @param domain Dominio del documento actual (o `undefined` mientras carga).
 * @param excludeUcId `uc_id` a excluir de los relacionados.
 */
export function useKbRelated(domain: KBDomain | undefined, excludeUcId: string) {
  const { client } = useAuth();

  return useQuery({
    queryKey: kbRelatedKey(domain, excludeUcId),
    enabled: domain !== undefined,
    queryFn: async () => {
      const { data, error } = await client.GET("/kb/documents", {
        params: { query: { domain } },
      });
      if (error) throw error;
      return relatedDocuments(data.items, excludeUcId);
    },
  });
}
