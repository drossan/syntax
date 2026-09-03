"use client";

import { useTranslations } from "next-intl";

import { formatConfidencePercent } from "@/features/ai-flow/agent-run";
import type { components } from "@/types/api";

import { isEmptySummary, totalTickets } from "./analytics";
import { useAnalyticsSummary } from "./use-analytics";

type TicketStatus = components["schemas"]["TicketStatus"];

/** Tarjeta de métrica accesible (grupo etiquetado con su valor). */
function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div role="group" aria-label={label} className="flex flex-col gap-1 rounded-md border p-4">
      <span className="text-xs uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="text-2xl font-semibold tabular-nums">{value}</span>
    </div>
  );
}

/**
 * Dashboard de métricas del helpdesk (`GET /analytics/summary`): total de tickets, aprobaciones
 * pendientes, SLA en riesgo, confianza media, y un desglose por estado (barras accesibles). Acotado por
 * tenant/rol server-side. Estados loading / empty / error+reintento.
 */
export function Dashboard() {
  const t = useTranslations("dashboard");
  const tStatus = useTranslations("tickets.status");
  const { data, isLoading, isError, refetch } = useAnalyticsSummary();

  if (isLoading) {
    return (
      <div role="status" aria-busy="true" className="p-4 text-muted-foreground">
        {t("loading")}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div role="alert" className="flex flex-col items-start gap-3 p-4">
        <p className="text-destructive">{t("error")}</p>
        <button type="button" onClick={() => refetch()} className="rounded-md border px-3 py-1.5 text-sm">
          {t("retry")}
        </button>
      </div>
    );
  }

  const total = totalTickets(data.tickets_by_status);
  const confidence = formatConfidencePercent(data.avg_confidence);
  const byStatus = Object.entries(data.tickets_by_status ?? {});
  const maxCount = byStatus.reduce((max, [, count]) => Math.max(max, count), 0);

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>

      {isEmptySummary(data) ? (
        <p role="status" className="rounded-md border border-dashed p-8 text-muted-foreground">
          {t("empty")}
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard label={t("totalTickets")} value={String(total)} />
            <StatCard label={t("approvalsPending")} value={String(data.approvals_pending ?? 0)} />
            <StatCard label={t("slaBreaches")} value={String(data.sla_breaches ?? 0)} />
            <StatCard label={t("avgConfidence")} value={confidence !== null ? `${confidence} %` : "—"} />
          </div>

          <div className="flex flex-col gap-2">
            <h2 className="text-sm font-medium">{t("byStatus")}</h2>
            <ul className="flex flex-col gap-1">
              {byStatus.map(([status, count]) => (
                <li key={status} className="flex items-center gap-2 text-sm">
                  <span className="w-24 text-muted-foreground">
                    {tStatus(status as TicketStatus)}
                  </span>
                  <span
                    aria-hidden="true"
                    className="h-3 rounded bg-primary/70"
                    style={{ width: `${maxCount > 0 ? (count / maxCount) * 100 : 0}%` }}
                  />
                  <span className="tabular-nums">{count}</span>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </section>
  );
}
