"use client";

import { useTranslations } from "next-intl";
import { useEffect } from "react";

import { AiDraftPanel } from "@/features/ai-flow/ai-draft-panel";
import { useTicketReads } from "@/features/cross-cutting/use-ticket-reads";
import { useCan } from "@/features/rbac/use-can";

import { filterByVisibility } from "./message-visibility";
import { TicketActions } from "./ticket-actions";
import { TicketAttachments } from "./ticket-attachments";
import { TicketHeader } from "./ticket-header";
import { TicketReplyForm } from "./ticket-reply-form";
import { TicketSla } from "./ticket-sla";
import { TicketThread } from "./ticket-thread";
import { TicketTimeline } from "./ticket-timeline";
import { useTicket, useTicketMessages } from "./use-ticket";

/**
 * Detalle de ticket: cabecera read-only + hilo con filtro de visibilidad (`note.internal.read`) +
 * respuesta (`TicketReplyForm`, gateada por `ticket.reply`/`note.internal.write`). Un ticket inaccesible
 * (403/404) muestra no-encontrado/sin-acceso sin filtrar datos (no renderiza cabecera ni hilo).
 *
 * @param ticketId Id del ticket.
 */
export function TicketDetail({ ticketId }: { ticketId: string }) {
  const t = useTranslations("ticketDetail");
  const canSeeInternal = useCan("note.internal.read");
  const ticketQuery = useTicket(ticketId);
  const messagesQuery = useTicketMessages(ticketId);

  // No leído (task 22): abrir el detalle sella la visita → el ticket deja de contar como no leído.
  const { markVisited } = useTicketReads();
  useEffect(() => {
    markVisited(ticketId);
  }, [ticketId, markVisited]);

  if (ticketQuery.isError) {
    return (
      <div role="alert" className="p-4">
        <h2 className="text-lg font-semibold">{t("notFound")}</h2>
      </div>
    );
  }

  if (ticketQuery.isLoading || messagesQuery.isLoading) {
    return (
      <div role="status" aria-busy="true" className="p-4 text-muted-foreground">
        {t("loading")}
      </div>
    );
  }

  if (messagesQuery.isError) {
    return (
      <div role="alert" className="flex flex-col items-start gap-3 p-4">
        <p className="text-destructive">{t("error")}</p>
        <button
          type="button"
          onClick={() => messagesQuery.refetch()}
          className="rounded-md border px-3 py-1.5 text-sm"
        >
          {t("retry")}
        </button>
      </div>
    );
  }

  return (
    <section className="flex flex-col gap-4">
      {ticketQuery.data ? <TicketHeader ticket={ticketQuery.data} /> : null}
      {ticketQuery.data ? <TicketSla slaDue={ticketQuery.data.sla_due} /> : null}
      {ticketQuery.data ? <TicketActions ticket={ticketQuery.data} /> : null}
      {ticketQuery.data?.id ? (
        <AiDraftPanel
          ticketId={ticketQuery.data.id}
          resourceTenantId={ticketQuery.data.tenant_id}
        />
      ) : null}
      <TicketThread messages={messagesQuery.data ?? []} canSeeInternal={canSeeInternal} />
      {ticketQuery.data ? (
        <TicketReplyForm ticketId={ticketId} resourceTenantId={ticketQuery.data.tenant_id} />
      ) : null}
      <TicketTimeline messages={messagesQuery.data ?? []} canSeeInternal={canSeeInternal} />
      {/* Adjuntos de los mensajes VISIBLES para este sujeto — el mismo filtro que `TicketThread`
          (defensa en profundidad): un adjunto de una nota interna no debe listarse para quien no
          puede leer esa nota, aunque el adjunto en sí no lleve su propio `visibility`. */}
      <TicketAttachments
        attachments={filterByVisibility(messagesQuery.data ?? [], canSeeInternal).flatMap(
          (message) => message.attachments ?? [],
        )}
      />
    </section>
  );
}
