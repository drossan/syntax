import { useMutation } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-context";

/**
 * Descarga el binario de un adjunto con el cliente autenticado (`GET /messages/{id}/attachments/
 * {attachment_id}`, `parseAs: "blob"`) — un `<a href>` plano no llevaría el Bearer (vive solo en
 * memoria JS, no en cookie) ni resolvería la URL contra el origen del backend, no el del front (ambos
 * bugs reales, verificados con curl: 401 sin el header, 404 en el origen equivocado).
 */
export function useDownloadAttachment() {
  const { client } = useAuth();

  return useMutation({
    mutationFn: async ({
      messageId,
      attachmentId,
    }: {
      messageId: string;
      attachmentId: string;
    }) => {
      const { data, error } = await client.GET("/messages/{id}/attachments/{attachment_id}", {
        params: { path: { id: messageId, attachment_id: attachmentId } },
        parseAs: "blob",
      });
      if (error) throw error;
      return data;
    },
  });
}
