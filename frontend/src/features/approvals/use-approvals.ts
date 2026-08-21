import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-context";
import { useTenant } from "@/features/tenant/tenant-context";

import { approvalsQueryKey, buildApprovalsQuery } from "./approvals-query";

/**
 * Carga la cola de aprobaciones pendientes (`GET /approvals`), ordenada por política (SLA/confianza)
 * server-side. Solo tiene sentido para Soporte (`approval.decide`); el guard de ruta lo impone.
 *
 * @param input Página deseada (opcional).
 */
export function useApprovals(input: { page?: number } = {}) {
  const { client } = useAuth();
  const { activeTenantId } = useTenant();
  const query = buildApprovalsQuery(input);

  return useQuery({
    queryKey: approvalsQueryKey(activeTenantId, query),
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const { data, error } = await client.GET("/approvals", { params: { query } });
      if (error) throw error;
      return data;
    },
  });
}
