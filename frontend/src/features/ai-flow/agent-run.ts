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
 * `escalated` (HITL) queda `true` desde el `interrupt()` — el `status` del `AgentRun` no tiene un
 * valor propio para "listo, esperando aprobación humana": se queda en `running` hasta que alguien
 * decide (`approval.decide`), que puede tardar minutos u horas. Sin distinguir este caso de "todavía
 * generando", la UI mostraría "Generando…" indefinidamente para el camino HITL — que es el
 * **default** del producto (`tenant.auto_approve=false`), no un caso raro.
 *
 * @param status Estado actual del run.
 * @param escalated `AgentRun.escalated`.
 */
export function isAwaitingApproval(
  status: AgentRunStatus | undefined,
  escalated: boolean | undefined,
): boolean {
  return status === "running" && escalated === true;
}

/**
 * Intervalo de polling para `refetchInterval`: `pollMs` mientras el run no sea terminal NI esté
 * esperando aprobación humana, `false` (parar) en ambos casos — nada va a cambiar por sí solo
 * mientras espera una decisión, así que seguir sondeando cada `pollMs` es solo ruido de red.
 *
 * @param status Estado actual del run.
 * @param escalated `AgentRun.escalated`.
 * @param pollMs Intervalo de sondeo en ms.
 */
export function draftPollInterval(
  status: AgentRunStatus | undefined,
  escalated: boolean | undefined,
  pollMs: number,
): number | false {
  return isTerminal(status) || isAwaitingApproval(status, escalated) ? false : pollMs;
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
