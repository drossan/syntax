"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Can } from "@/features/rbac/can";

import { formatConfidencePercent, isAwaitingApproval, isTerminal } from "./agent-run";
import { useActiveAgentRun, useAgentRun, useTriggerDraft } from "./use-agent-draft";

/**
 * Panel del **ciclo de draft IA**: dispara la generación (`agent.trigger`), sondea el `AgentRun` hasta
 * terminal y muestra el estado (sin-draft / generando / listo / fallido). En `succeeded` muestra fuentes
 * (citas) y confianza; en `failed`, el error y un reintento. Mientras hay un run activo **no** ofrece
 * re-disparar (idempotencia). El texto del draft y las decisiones viven en la task 15 (`ApprovalTask`).
 *
 * Al montar, descubre si YA hay un run activo (`useActiveAgentRun`) antes de decidir qué mostrar —
 * `tenant.ai_auto_draft` puede haberlo disparado el servidor al crear el ticket, sin que este cliente
 * lo pidiera; sin este descubrimiento, el panel mostraría "Generar borrador" como si nada, y pulsarlo
 * fallaría con 409 (ya hay un run en curso).
 *
 * @param ticketId Id del ticket.
 * @param resourceTenantId Tenant del ticket (para el ámbito de `agent.trigger`).
 * @param pollMs Intervalo de sondeo (default del hook).
 */
export function AiDraftPanel({
  ticketId,
  resourceTenantId,
  pollMs,
}: {
  ticketId: string;
  resourceTenantId?: string | null;
  pollMs?: number;
}) {
  const t = useTranslations("aiDraft");
  const trigger = useTriggerDraft(ticketId);
  // Reusa `pollMs` también para el intervalo de reintento del descubrimiento (mismo prop que ya
  // aceptan los tests para acelerar el polling — no duplica una segunda prop para lo mismo).
  const activeRun = useActiveAgentRun(ticketId, pollMs);
  // `triggeredRunId`: solo el run que ESTE cliente disparó explícitamente. El id efectivo prioriza
  // ese sobre el descubierto (`activeRun.data`) — una vez el usuario dispara, ya no depende del
  // descubrimiento inicial. Derivado en render, sin `useEffect`: evita el cascading-render de
  // `setState` dentro de un efecto (react-hooks/set-state-in-effect).
  const [triggeredRunId, setTriggeredRunId] = useState<string | null>(null);
  const runId = triggeredRunId ?? activeRun.data?.id ?? null;
  const run = useAgentRun(runId, pollMs);

  const status = runId === null ? undefined : run.data?.status;
  const awaitingApproval = runId !== null && isAwaitingApproval(status, run.data?.escalated);
  const active = runId !== null && !isTerminal(status) && !awaitingApproval;
  // Mientras `useActiveAgentRun` sigue reintentando (todavía sin encontrar nada, ver su docstring —
  // el run del auto-disparo puede tardar hasta ~30s en ser descubrible) no decidimos qué pintar aún:
  // evita mostrar "Generar borrador" solo para que desaparezca un segundo después. `stillSearching`
  // (no `isLoading`/`isFetching`) es la señal correcta — esos dos parpadean entre reintentos
  // (bug real, reproducido en vivo: "Generar borrador" aparecía a ráfagas durante casi toda la
  // ventana de descubrimiento), `stillSearching` no.
  const discovering = triggeredRunId === null && activeRun.stillSearching;

  function generate() {
    trigger.mutate(undefined, { onSuccess: (agentRun) => setTriggeredRunId(agentRun.id ?? null) });
  }

  const generateButton = (
    <Can capability="agent.trigger" resourceTenantId={resourceTenantId}>
      <button
        type="button"
        onClick={generate}
        disabled={trigger.isPending}
        className="rounded-md border px-3 py-1.5 text-sm"
      >
        {t("generate")}
      </button>
    </Can>
  );

  return (
    <section aria-label={t("region")} className="flex flex-col gap-3 border-t pt-4">
      <h2 className="text-sm font-medium">{t("title")}</h2>

      {discovering ? (
        <p role="status" aria-live="polite" className="text-muted-foreground">
          {t("checking")}
        </p>
      ) : status === "failed" ? (
        <div role="alert" className="flex flex-col items-start gap-2">
          <p className="text-destructive">{run.data?.error ?? t("failed")}</p>
          <Can capability="agent.trigger" resourceTenantId={resourceTenantId}>
            <button
              type="button"
              onClick={generate}
              className="rounded-md border px-3 py-1.5 text-sm"
            >
              {t("retry")}
            </button>
          </Can>
        </div>
      ) : active ? (
        <p role="status" aria-live="polite" className="text-muted-foreground">
          {t("generating")}
        </p>
      ) : awaitingApproval ? (
        <p role="status" aria-live="polite" className="text-muted-foreground">
          {t("awaitingApproval")}
        </p>
      ) : status === "succeeded" ? (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium text-emerald-600 dark:text-emerald-400">{t("ready")}</p>
          {formatConfidencePercent(run.data?.confidence) !== null ? (
            <p className="text-sm">
              {t("confidence")}: {formatConfidencePercent(run.data?.confidence)} %
            </p>
          ) : null}
          {(run.data?.sources ?? []).length > 0 ? (
            <div className="flex flex-col gap-1">
              <span className="text-xs uppercase tracking-wide text-muted-foreground">
                {t("sources")}
              </span>
              <ul className="flex flex-col gap-1 text-sm">
                {(run.data?.sources ?? []).map((source) => (
                  <li key={source.uc_id}>
                    <span className="font-mono text-xs">{source.uc_id}</span> {source.title}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {run.data?.langsmith_trace_url ? (
            <a href={run.data.langsmith_trace_url} className="text-sm text-primary underline">
              {t("trace")}
            </a>
          ) : null}
        </div>
      ) : (
        generateButton
      )}
    </section>
  );
}
