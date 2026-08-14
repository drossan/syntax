import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-context";

/**
 * Lista de tenants para el switcher de Soporte (`GET /admin/tenants`). Solo se dispara con `enabled`
 * (ámbito global). Nota de contrato: el endpoint exige `tenant.manage`; un Soporte global sin esa
 * capacidad recibirá 403 (lista vacía, fail-closed) — gap del contrato a resolver en backend.
 *
 * @param enabled Si se debe cargar (típicamente `canSwitchTenant`).
 */
export function useTenants(enabled: boolean) {
  const { client } = useAuth();

  return useQuery({
    queryKey: ["admin", "tenants"],
    enabled,
    queryFn: async () => {
      const { data, error } = await client.GET("/admin/tenants", {});
      if (error) throw error;
      return data.items;
    },
  });
}
