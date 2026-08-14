"use client";

import { useTranslations } from "next-intl";

import type { components } from "@/types/api";

type Ticket = components["schemas"]["Ticket"];

/** Un par etiqueta/valor de la cabecera. */
function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

/**
 * Cabecera **de solo lectura** del ticket (asunto + estado/prioridad/dominio/responsable). Las
 * mutaciones (estado/prioridad/asignación) llegan en la task 10; aquí solo se muestran.
 *
 * @param ticket Ticket a mostrar.
 */
export function TicketHeader({ ticket }: { ticket: Ticket }) {
  const t = useTranslations("tickets");
  const status = ticket.status ? t(`status.${ticket.status}`) : "—";
  const priority = ticket.priority ? t(`priority.${ticket.priority}`) : "—";

  return (
    <header className="flex flex-col gap-3 border-b pb-4">
      <h1 className="text-xl font-semibold tracking-tight">{ticket.subject}</h1>
      <dl className="flex flex-wrap gap-6 text-sm">
        <Field label={t("columns.status")} value={status} />
        <Field label={t("columns.priority")} value={priority} />
        <Field label={t("columns.domain")} value={ticket.domain ?? "—"} />
        <Field label={t("columns.assignee")} value={ticket.assignee_id ?? t("unassigned")} />
      </dl>
    </header>
  );
}
