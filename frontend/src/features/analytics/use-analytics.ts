import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-context";
import { useTenant } from "@/features/tenant/tenant-context";

/**
 * Carga el resumen del dashboard (`GET /analytics/summary`). El servidor escopa por sujeto/tenant activo
 * (no hay parámetros). La queryKey incluye `activeTenantId` para refetch al cambiar de tenant
 * (cross-cutting §3).
 */
export function useAnalyticsSummary() {
  const { client } = useAuth();
  const { activeTenantId } = useTenant();

  return useQuery({
    queryKey: ["analytics", activeTenantId],
    queryFn: async () => {
      const { data, error } = await client.GET("/analytics/summary", {});
      if (error) throw error;
      return data;
    },
  });
}
