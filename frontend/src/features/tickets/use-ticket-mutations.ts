import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth, type AuthApiClient } from "@/features/auth/auth-context";
import { useTenant } from "@/features/tenant/tenant-context";
import type { components } from "@/types/api";

import { ticketKey } from "./use-ticket";

type Ticket = components["schemas"]["Ticket"];
type TicketStatus = components["schemas"]["TicketStatus"];
type TicketPriority = components["schemas"]["TicketPriority"];

interface OptimisticContext {
  previous: Ticket | undefined;
}

/**
 * Fábrica de mutaciones de ticket con **optimistic-update + rollback** (M3 / cross-cutting §6):
 * `onMutate` cancela las queries en vuelo, guarda un snapshot y aplica el cambio optimista a la caché
 * del ticket; `onError` restaura el snapshot; `onSettled` **invalida** para revalidar contra el servidor
 * (reconcilia respuestas fuera de orden y conflictos 409). No se duplica: los tres hooks la reutilizan.
 *
 * @param ticketId Id del ticket.
 * @param run Ejecuta la mutación real contra la API y devuelve el ticket actualizado.
 * @param optimistic Deriva el ticket optimista a partir del actual y las variables.
 */
function useTicketMutation<Vars>(
  ticketId: string,
  run: (client: AuthApiClient, ticketId: string, vars: Vars) => Promise<Ticket>,
  optimistic: (current: Ticket, vars: Vars) => Ticket,
) {
  const { client } = useAuth();
  const { activeTenantId } = useTenant();
  const queryClient = useQueryClient();
  const key = ticketKey(activeTenantId, ticketId);

  return useMutation<Ticket, unknown, Vars, OptimisticContext>({
    mutationFn: (vars) => run(client, ticketId, vars),
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<Ticket>(key);
      if (previous) {
        queryClient.setQueryData<Ticket>(key, optimistic(previous, vars));
      }
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData<Ticket>(key, context.previous);
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: key });
    },
  });
}

/** Mutación de transición de estado (`POST /tickets/{id}/transition`). */
export function useTransitionTicket(ticketId: string) {
  return useTicketMutation<TicketStatus>(
    ticketId,
    async (client, id, status) => {
      const { data, error } = await client.POST("/tickets/{id}/transition", {
        params: { path: { id } },
        body: { status },
      });
      if (error) throw error;
      return data;
    },
    (current, status) => ({ ...current, status }),
  );
}

/** Mutación de asignación (`POST /tickets/{id}/assign`); `null` desasigna. */
export function useAssignTicket(ticketId: string) {
  return useTicketMutation<string | null>(
    ticketId,
    async (client, id, assigneeId) => {
      const { data, error } = await client.POST("/tickets/{id}/assign", {
        params: { path: { id } },
        body: { assignee_id: assigneeId },
      });
      if (error) throw error;
      return data;
    },
    (current, assigneeId) => ({ ...current, assignee_id: assigneeId }),
  );
}

/** Mutación de prioridad (`PATCH /tickets/{id}`). */
export function useUpdatePriority(ticketId: string) {
  return useTicketMutation<TicketPriority>(
    ticketId,
    async (client, id, priority) => {
      const { data, error } = await client.PATCH("/tickets/{id}", {
        params: { path: { id } },
        body: { priority },
      });
      if (error) throw error;
      return data;
    },
    (current, priority) => ({ ...current, priority }),
  );
}
