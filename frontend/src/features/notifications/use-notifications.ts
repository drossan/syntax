import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-context";

/** Intervalo de sondeo por defecto de notificaciones (ms). */
const DEFAULT_POLL_MS = 15000;

/**
 * Carga las notificaciones del usuario (`GET /notifications`, orden `created_at desc`) y **sondea** cada
 * `pollMs` (in-app polling; sin push/SSE en Fase 1).
 *
 * @param pollMs Intervalo de sondeo (default 15 s).
 */
export function useNotifications(pollMs: number = DEFAULT_POLL_MS) {
  const { client } = useAuth();

  return useQuery({
    queryKey: ["notifications"],
    refetchInterval: pollMs,
    queryFn: async () => {
      const { data, error } = await client.GET("/notifications", {});
      if (error) throw error;
      return data.items;
    },
  });
}

/** Marca una notificación como leída (`PATCH /notifications/{id}/read`); invalida la lista en éxito. */
export function useMarkRead() {
  const { client } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      const { data, error } = await client.PATCH("/notifications/{id}/read", {
        params: { path: { id } },
      });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}
