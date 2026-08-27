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

/**
 * Sube un adjunto a un mensaje ya creado (`POST /messages/{id}/attachments`). Invalida el hilo del
 * ticket en éxito para que aparezca en `Message.attachments` (`GET /tickets/{id}/messages`).
 *
 * @param ticketId Id del ticket (para invalidar su hilo — el endpoint en sí solo pide el id del mensaje).
 */
export function useUploadAttachment(ticketId: string) {
  const { client } = useAuth();
  const { activeTenantId } = useTenant();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ messageId, file }: { messageId: string; file: File }) => {
      const formData = new FormData();
      formData.append("file", file, file.name);
      const { data, error } = await client.POST("/messages/{id}/attachments", {
        params: { path: { id: messageId } },
        // El contrato tipa el body multipart como `{ file: string }` — `format: binary` se traduce a
        // `string` (limitación conocida de openapi-typescript, no un modelado real). En runtime hace
        // falta un `FormData` de verdad para que el navegador fije el boundary multipart; el cast es
        // deliberado.
        body: formData as unknown as { file: string },
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
