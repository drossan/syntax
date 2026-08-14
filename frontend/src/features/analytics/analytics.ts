import type { components } from "@/types/api";

type AnalyticsSummary = components["schemas"]["AnalyticsSummary"];

/**
 * Suma los conteos de tickets por estado. Robusto ante `undefined` (sin datos → 0).
 *
 * @param byStatus Mapa estado→conteo de `AnalyticsSummary.tickets_by_status`.
 */
export function totalTickets(byStatus: Record<string, number> | undefined): number {
  return Object.values(byStatus ?? {}).reduce((sum, count) => sum + count, 0);
}

/**
 * Un resumen está **vacío** (tenant sin actividad) cuando no hay tickets, ni aprobaciones pendientes, ni
 * brechas de SLA. Gobierna el estado vacío del dashboard.
 *
 * @param summary Resumen de analítica.
 */
export function isEmptySummary(summary: AnalyticsSummary): boolean {
  return (
    totalTickets(summary.tickets_by_status) === 0 &&
    (summary.approvals_pending ?? 0) === 0 &&
    (summary.sla_breaches ?? 0) === 0
  );
}
