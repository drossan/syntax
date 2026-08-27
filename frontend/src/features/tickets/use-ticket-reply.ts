import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-context";
import { useTenant } from "@/features/tenant/tenant-context";
import type { components } from "@/types/api";

import { ticketMessagesKey } from "./use-ticket";

type MessageCreate = components["schemas"]["MessageCreate"];

/**
 * Publica un mensaje en el hilo del ticket (`POST /tickets/{id}/messages`). Sin optimistic-update (a
 * diferencia de `use-ticket-mutations.ts`): el mensaje nuevo no tiene un id hasta que el servidor
 * responde, así que invalida el hilo en éxito en vez de fingir la entrada.
 *
 * @param ticketId Id del ticket.
 */
export function useReplyTicket(ticketId: string) {
  const { client } = useAuth();
  const { activeTenantId } = useTenant();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (body: MessageCreate) => {
      const { data, error } = await client.POST("/tickets/{id}/messages", {
        params: { path: { id: ticketId } },
        body,
      });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ticketMessagesKey(activeTenantId, ticketId),
      });
    },
  });
}
