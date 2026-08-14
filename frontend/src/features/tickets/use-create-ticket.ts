import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-context";
import type { components } from "@/types/api";

type TicketCreate = components["schemas"]["TicketCreate"];

/**
 * Mutación de alta de ticket (`POST /tickets`). No es idempotente → en éxito **invalida** la lista de
 * bandejas (cross-cutting §6: creación = revalidación, no optimistic-update). Propaga el envelope de
 * error (problem+json) al llamante para mapear 422 a errores de campo.
 *
 * @returns El objeto `useMutation`; `mutateAsync(body)` resuelve con el `Ticket` creado o rechaza con el `Problem`.
 */
export function useCreateTicket() {
  const { client } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (body: TicketCreate) => {
      const { data, error } = await client.POST("/tickets", { body });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tickets"] });
    },
  });
}
