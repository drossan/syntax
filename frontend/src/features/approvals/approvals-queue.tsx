"use client";

import { useFormatter, useTranslations } from "next-intl";
import Link from "next/link";

import { useTicket } from "@/features/tickets/use-ticket";
import { problemToUi, type Problem } from "@/lib/api/problem";

import { ApprovalDecision } from "./approval-decision";
import { useApprovals } from "./use-approvals";

/** Enlace al ticket con su asunto real; cae al enlace genérico mientras carga o si falla. */
function TicketSubjectLink({ ticketId }: { ticketId: string }) {
  const t = useTranslations("approvals");
  const ticket = useTicket(ticketId);
  return (
    <Link href={`/tickets/${ticketId}`} className="font-medium text-primary underline">
      {ticket.data?.subject ?? t("openTicket")}
    </Link>
  );
}

/** Coerción defensiva de un error de query al envelope `problem+json`. */
function toProblem(error: unknown, fallbackTitle: string): Problem {
  if (error && typeof error === "object" && "title" in error) return error as Problem;
  return { type: "about:blank", title: fallbackTitle, status: 0 };
}

/**
 * Cola de aprobaciones (solo Soporte). Lista los `ApprovalTask` pendientes en el **orden recibido** del
 * servidor (política SLA/confianza; el cliente no re-ordena). Cada ítem enlaza al ticket y muestra un
 * preview del draft (texto inerte). Estados loading / error+reintento / empty, más un botón de actualizar
 * (una aprobación resuelta por otro agente desaparece al refrescar).
 */
export function ApprovalsQueue() {
  const t = useTranslations("approvals");
  const format = useFormatter();
  const { data, isLoading, isError, error, refetch, isFetching } = useApprovals();

  if (isLoading) {
    return (
      <div role="status" aria-busy="true" className="p-4 text-muted-foreground">
        {t("loading")}
      </div>
    );
  }

  if (isError) {
    const ui = problemToUi(toProblem(error, t("error")), (k) => t(k));
    return (
      <div role="alert" className="flex flex-col items-start gap-3 p-4">
        <p className="text-destructive">{ui.toast.title}</p>
        <button type="button" onClick={() => refetch()} className="rounded-md border px-3 py-1.5 text-sm">
          {t("retry")}
        </button>
      </div>
    );
  }

  const items = data?.items ?? [];

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="rounded-md border px-3 py-1.5 text-sm disabled:opacity-50"
        >
          {t("refresh")}
        </button>
      </div>

      {items.length === 0 ? (
        <p role="status" className="rounded-md border border-dashed p-8 text-muted-foreground">
          {t("empty")}
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((task) => (
            <li key={task.id} className="flex flex-col gap-1 rounded-md border p-3">
              <div className="flex items-center justify-between gap-2 text-sm">
                <TicketSubjectLink ticketId={task.ticket_id ?? ""} />
                {task.created_at ? (
                  <time dateTime={task.created_at} className="text-xs text-muted-foreground">
                    {format.dateTime(new Date(task.created_at), { dateStyle: "medium", timeStyle: "short" })}
                  </time>
                ) : null}
              </div>
              <ApprovalDecision approval={task} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
