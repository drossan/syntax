import type { components } from "@/types/api";

type AgentRunStatus = components["schemas"]["AgentRunStatus"];

/**
 * Un run es **terminal** cuando ya no cambiará: `succeeded` o `failed`. Un estado indefinido (aún sin
 * datos) no es terminal.
 *
 * @param status Estado del run (o `undefined` si aún no llegó).
 */
export function isTerminal(status: AgentRunStatus | undefined): boolean {
  return status === "succeeded" || status === "failed";
}

/**
 * Intervalo de polling para `refetchInterval`: `pollMs` mientras el run no sea terminal, `false` (parar)
 * cuando lo sea. Así el sondeo se detiene solo al terminar.
 *
 * @param status Estado actual del run.
 * @param pollMs Intervalo de sondeo en ms.
 */
export function draftPollInterval(status: AgentRunStatus | undefined, pollMs: number): number | false {
  return isTerminal(status) ? false : pollMs;
}

/**
 * Formatea la confianza (0..1) a porcentaje entero como cadena; `null` si no hay confianza.
 *
 * @param confidence Confianza del run (0..1) o `null`/`undefined`.
 */
export function formatConfidencePercent(confidence: number | null | undefined): string | null {
  if (confidence === null || confidence === undefined) return null;
  return `${Math.round(confidence * 100)}`;
}
