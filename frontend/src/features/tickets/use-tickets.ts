import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-context";
import { useTenant } from "@/features/tenant/tenant-context";

import { buildTicketQuery, ticketsQueryKey, type TicketQueryInput } from "./tickets-query";

/**
 * Carga una página de la bandeja de tickets (`GET /tickets`) vía el cliente API tipado + TanStack
 * Query. Orden y paginación son server-driven y deterministas (`buildTicketQuery`). Mantiene la página
 * anterior mientras llega la nueva (`keepPreviousData`) para que filtrar/paginar no parpadee a vacío.
 *
 * @param input Página y filtros de la bandeja.
 * @returns El resultado de `useQuery` con la página de tickets (`{ items, page, page_size, total }`).
 */
export function useTickets(input: TicketQueryInput) {
  const { client } = useAuth();
  const { activeTenantId } = useTenant();
  const query = buildTicketQuery(input);

  return useQuery({
    queryKey: ticketsQueryKey(activeTenantId, query),
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const { data, error } = await client.GET("/tickets", { params: { query } });
      if (error) throw error;
      return data;
    },
  });
}
