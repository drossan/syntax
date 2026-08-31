import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

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

/** Cuántas veces reintenta `useActiveAgentRun` si no encuentra nada, y cada cuánto por defecto (ms). */
const DISCOVERY_RETRY_ATTEMPTS = 20;
const DEFAULT_DISCOVERY_RETRY_MS = 1500;

/**
 * Descubre el `AgentRun` activo de un ticket (`GET /tickets/{id}/agent-runs/active`) — sin esto, un run
 * disparado por el SERVIDOR (`tenant.ai_auto_draft`, no por este cliente) es invisible: el cliente nunca
 * recibe su `id` en la respuesta de `POST /tickets`. `null` es un resultado válido (sin run activo), no
 * un error.
 *
 * Reintenta hasta `DISCOVERY_RETRY_ATTEMPTS` veces (cada `retryMs`) mientras siga sin encontrar nada —
 * **no** una sola consulta al montar. Ventana ~30s por defecto (20×1.5s), no unos pocos segundos:
 * **limitación conocida, reproducida en vivo (e2e real)**: `_trigger_ai_draft_in_background`
 * (`tickets.py`) mantiene su transacción abierta durante TODO el ciclo real classify→retrieve→
 * grade→generate→decide contra OpenAI (5-15s+ medidos) — la fila `queued`/`running` que crea NO es
 * visible a otras conexiones (esta consulta incluida) hasta que esa transacción hace commit al
 * terminar, así que "descubrir pronto" en la práctica significa "descubrir en cuanto el ciclo
 * completo termina", no en cuanto se crea. Separar esa transacción en dos (fila `queued` + commit
 * inmediato, luego el resto) arreglaría esto de raíz, pero toca `LangGraphAgentRunner`/
 * `AgentRunRepository` — sin hacerlo (comprometería mucho código ya cerrado y testeado, sin margen en
 * esta pasada) — follow-up explícito, no un descuido.
 *
 * `stillSearching` en el resultado: `true` mientras no haya encontrado nada Y no se hayan agotado los
 * reintentos — usar `isLoading`/`isFetching` para esto (como hacía `ai-draft-panel.tsx` antes de este
 * fix) **parpadea**: esos campos solo son `true` MIENTRAS hay una petición en vuelo, no durante los
 * ~`retryMs` de espera ENTRE reintentos — así que un consumidor basado en ellos mostraba "Generar
 * borrador" a ráfagas durante casi toda la ventana de 30s (reproducido en vivo, e2e real, no
 * hipotético: intermitente porque depende de en qué hueco caiga la comprobación). `stillSearching`
 * usa el mismo contador (`dataUpdateCount`, vía `dataUpdatedAt` — no expuesto directo por `useQuery`)
 * que ya gobierna cuándo `refetchInterval` se rinde, así que ambos coinciden siempre.
 *
 * @param ticketId Id del ticket.
 * @param retryMs Intervalo entre reintentos (default 1500 ms).
 */
export function useActiveAgentRun(ticketId: string, retryMs: number = DEFAULT_DISCOVERY_RETRY_MS) {
  const { client } = useAuth();

  const query = useQuery({
    queryKey: ["agent-run-active", ticketId],
    refetchInterval: (q) => {
      if (q.state.data != null) return false; // ya lo encontró
      if (q.state.dataUpdateCount >= DISCOVERY_RETRY_ATTEMPTS) return false; // se rinde
      return retryMs;
    },
    queryFn: async () => {
      const { data, error } = await client.GET("/tickets/{id}/agent-runs/active", {
        params: { path: { id: ticketId } },
      });
      if (error) throw error;
      return data;
    },
  });

  // Cuenta asentamientos (`dataUpdatedAt` cambia una vez por fetch resuelto, con datos o `null`) SIN
  // efecto: comparar-y-ajustar durante el propio render (patrón "adjusting state when a prop changes"
  // de React) evita el cascading-render de `setState` dentro de un `useEffect`
  // (react-hooks/set-state-in-effect) — mismo motivo que ya obligó a evitar un efecto en
  // `ai-draft-panel.tsx`.
  const [seenAt, setSeenAt] = useState(query.dataUpdatedAt);
  const [attempts, setAttempts] = useState(0);
  if (query.dataUpdatedAt !== seenAt) {
    setSeenAt(query.dataUpdatedAt);
    setAttempts((count) => count + 1);
  }

  return { ...query, stillSearching: query.data == null && attempts < DISCOVERY_RETRY_ATTEMPTS };
}

/**
 * Sondea un `AgentRun` (`GET /agent-runs/{id}`) hasta que sea terminal O quede esperando aprobación
 * humana (`draftPollInterval`, `escalated=true` + `status=running` — no tiene sentido seguir
 * sondeando algo que solo cambiará cuando alguien decida en la cola de aprobaciones). No se dispara
 * sin `runId`.
 *
 * @param runId Id del run a sondear, o `null` si aún no se ha disparado.
 * @param pollMs Intervalo de sondeo (default 2000 ms).
 */
export function useAgentRun(runId: string | null, pollMs: number = DEFAULT_POLL_MS) {
  const { client } = useAuth();

  return useQuery({
    queryKey: ["agent-run", runId],
    enabled: runId !== null,
    refetchInterval: (query) =>
      draftPollInterval(query.state.data?.status, query.state.data?.escalated, pollMs),
    queryFn: async () => {
      const { data, error } = await client.GET("/agent-runs/{id}", {
        params: { path: { id: runId ?? "" } },
      });
      if (error) throw error;
      return data;
    },
  });
}
