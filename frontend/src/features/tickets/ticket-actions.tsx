"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { useAuth } from "@/features/auth/auth-context";
import { Can } from "@/features/rbac/can";
import type { components } from "@/types/api";

import { ConfirmDialog } from "./confirm-dialog";
import { allowedTransitions, isDestructiveTransition } from "./ticket-transitions";
import { useAssignTicket, useTransitionTicket, useUpdatePriority } from "./use-ticket-mutations";

type Ticket = components["schemas"]["Ticket"];
type TicketStatus = components["schemas"]["TicketStatus"];
type TicketPriority = components["schemas"]["TicketPriority"];

const PRIORITIES: TicketPriority[] = ["low", "normal", "high", "urgent"];

/**
 * Acciones de mutación del ticket: transición de estado (con **confirm** en destructivas), prioridad y
 * asignación, todas con **optimistic-update + rollback**. Cada bloque se muestra solo si el sujeto tiene
 * la capacidad (`ticket.transition` / `ticket.assign`) sobre el tenant del ticket.
 *
 * @param ticket Ticket actual (fuente del estado que se muta).
 */
export function TicketActions({ ticket }: { ticket: Ticket }) {
  const t = useTranslations("ticketActions");
  const tStatus = useTranslations("tickets.status");
  const tPriority = useTranslations("tickets.priority");
  const { user } = useAuth();
  const transition = useTransitionTicket(ticket.id ?? "");
  const assign = useAssignTicket(ticket.id ?? "");
  const priority = useUpdatePriority(ticket.id ?? "");
  const [confirmTarget, setConfirmTarget] = useState<TicketStatus | null>(null);

  if (!ticket.id) return null;

  const nextStates = ticket.status ? allowedTransitions(ticket.status) : [];
  const hasError = transition.isError || assign.isError || priority.isError;

  function requestTransition(target: TicketStatus) {
    if (isDestructiveTransition(target)) {
      setConfirmTarget(target);
    } else {
      transition.mutate(target);
    }
  }

  return (
    <section aria-label={t("region")} className="flex flex-col gap-4 border-t pt-4">
      {hasError ? (
        <p role="alert" className="text-sm text-destructive">
          {t("error")}
        </p>
      ) : null}

      <Can capability="ticket.transition" resourceTenantId={ticket.tenant_id}>
        <div className="flex flex-col gap-2">
          <span className="text-xs uppercase tracking-wide text-muted-foreground">{t("changeStatus")}</span>
          <div className="flex flex-wrap gap-2">
            {nextStates.map((target) => (
              <button
                key={target}
                type="button"
                onClick={() => requestTransition(target)}
                className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent"
              >
                {tStatus(target)}
              </button>
            ))}
          </div>

          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">{t("changePriority")}</span>
            <select
              aria-label={t("changePriority")}
              value={ticket.priority ?? "normal"}
              onChange={(event) => priority.mutate(event.target.value as TicketPriority)}
              className="rounded-md border px-2 py-1"
            >
              {PRIORITIES.map((value) => (
                <option key={value} value={value}>
                  {tPriority(value)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </Can>

      <Can capability="ticket.assign" resourceTenantId={ticket.tenant_id}>
        <div className="flex gap-2">
          {ticket.assignee_id ? (
            <button
              type="button"
              onClick={() => assign.mutate(null)}
              className="rounded-md border px-3 py-1.5 text-sm"
            >
              {t("unassign")}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => assign.mutate(user?.id ?? "")}
              className="rounded-md border px-3 py-1.5 text-sm"
            >
              {t("assignToMe")}
            </button>
          )}
        </div>
      </Can>

      {confirmTarget ? (
        <ConfirmDialog
          title={t("confirmCloseTitle")}
          description={t("confirmCloseBody")}
          onConfirm={() => {
            transition.mutate(confirmTarget);
            setConfirmTarget(null);
          }}
          onCancel={() => setConfirmTarget(null)}
        />
      ) : null}
    </section>
  );
}
