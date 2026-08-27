import { useMutation, useQuery } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-context";

import { draftPollInterval } from "./agent-run";

/** Intervalo de sondeo por defecto del run (ms). */
const DEFAULT_POLL_MS = 2000;

/**
 * Dispara la generación del draft IA (`POST /tickets/{id}/ai-draft`). Devuelve el `AgentRun` recién
 * creado (con su `id`) para empezar a sondear. Propaga 409 (ya hay run en curso) / 429 al llamante.
 *
 * @param ticketId Id del ticket.
 */
export function useTriggerDraft(ticketId: string) {
  const { client } = useAuth();

  return useMutation({
    mutationFn: async () => {
      const { data, error } = await client.POST("/tickets/{id}/ai-draft", {
        params: { path: { id: ticketId } },
      });
      if (error) throw error;
      return data;
    },
  });
}

/**
 * Descubre el `AgentRun` activo de un ticket (`GET /tickets/{id}/agent-runs/active`) — sin esto, un run
 * disparado por el SERVIDOR (`tenant.ai_auto_draft`, no por este cliente) es invisible: el cliente nunca
 * recibe su `id` en la respuesta de `POST /tickets`. `null` es un resultado válido (sin run activo), no
 * un error. Solo se pide UNA vez al montar (`staleTime: Infinity`) — el ciclo de vida de un run YA
 * conocido lo sondea `useAgentRun`, no este hook.
 *
 * @param ticketId Id del ticket.
 */
export function useActiveAgentRun(ticketId: string) {
  const { client } = useAuth();

  return useQuery({
    queryKey: ["agent-run-active", ticketId],
    staleTime: Infinity,
    queryFn: async () => {
      const { data, error } = await client.GET("/tickets/{id}/agent-runs/active", {
        params: { path: { id: ticketId } },
      });
      if (error) throw error;
      return data;
    },
  });
}

/**
 * Sondea un `AgentRun` (`GET /agent-runs/{id}`) hasta que sea terminal. El `refetchInterval` se detiene
 * (`false`) al alcanzar `succeeded`/`failed` (`draftPollInterval`). No se dispara sin `runId`.
 *
 * @param runId Id del run a sondear, o `null` si aún no se ha disparado.
 * @param pollMs Intervalo de sondeo (default 2000 ms).
 */
export function useAgentRun(runId: string | null, pollMs: number = DEFAULT_POLL_MS) {
  const { client } = useAuth();

  return useQuery({
    queryKey: ["agent-run", runId],
    enabled: runId !== null,
    refetchInterval: (query) => draftPollInterval(query.state.data?.status, pollMs),
    queryFn: async () => {
      const { data, error } = await client.GET("/agent-runs/{id}", {
        params: { path: { id: runId ?? "" } },
      });
      if (error) throw error;
      return data;
    },
  });
}
