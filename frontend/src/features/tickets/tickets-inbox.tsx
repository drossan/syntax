"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useMemo } from "react";

import { useTicketReads } from "@/features/cross-cutting/use-ticket-reads";
import { useUrlListState } from "@/features/cross-cutting/use-url-list-state";
import { Can } from "@/features/rbac/can";
import { isUnread } from "@/lib/unread";
import { problemToUi, type Problem } from "@/lib/api/problem";
import type { components } from "@/types/api";

import { TicketsTable } from "./tickets-table";
import { useTickets } from "./use-tickets";

type TicketStatus = components["schemas"]["TicketStatus"];

const STATUSES: TicketStatus[] = ["new", "open", "pending", "resolved", "closed", "reopened"];

/** Coerción defensiva de un error de query (desconocido) al envelope `problem+json`. */
function toProblem(error: unknown, fallbackTitle: string): Problem {
  if (error && typeof error === "object" && "title" in error) {
    return error as Problem;
  }
  return { type: "about:blank", title: fallbackTitle, status: 0 };
}

/**
 * Bandeja de tickets: filtro por estado, paginación server-driven con orden determinista, indicadores
 * de SLA y los tres estados (loading / error+reintento / empty+limpiar). Respeta el aislamiento por
 * tenant (la petición nunca lleva parámetro de tenant; el servidor escopa por sujeto).
 */
export function TicketsInbox() {
  const t = useTranslations("tickets");
  // URL-state (task 22): filtros/página compartibles por enlace y supervivientes a la recarga.
  const [listState, setListState] = useUrlListState();
  const status = (listState.status ?? "") as TicketStatus | "";
  const page = listState.page;
  const { visits } = useTicketReads();

  const filters = useMemo(() => (status ? { status } : {}), [status]);
  const { data, isLoading, isError, error, refetch } = useTickets({ page, filters });

  function setStatus(next: TicketStatus | "") {
    setListState({ page: 1, status: next || undefined, sort: listState.sort });
  }
  function setPage(next: number) {
    setListState({ ...listState, page: Math.max(1, next) });
  }
  function resetFilters() {
    setListState({ page: 1 });
  }

  if (isLoading) {
    return (
      <div role="status" aria-busy="true" className="p-4 text-muted-foreground">
        {t("loading")}
      </div>
    );
  }

  if (isError) {
    const ui = problemToUi(toProblem(error, t("genericError")), (k) => t(k));
    return (
      <div role="alert" className="flex flex-col items-start gap-3 p-4">
        <p className="text-destructive">{ui.toast.title}</p>
        <button type="button" onClick={() => refetch()} className="rounded-md border px-3 py-1.5 text-sm">
          {t("retry")}
        </button>
      </div>
    );
  }

  const pageData = data ?? { items: [], page: 1, page_size: 20, total: 0 };
  const hasNext = pageData.page * pageData.page_size < pageData.total;
  const unreadIds = new Set(
    pageData.items
      .filter((ticket) => ticket.id && isUnread(ticket.updated_at, visits[ticket.id]))
      .map((ticket) => ticket.id as string),
  );

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>
        <Can capability="ticket.create">
          <Link href="/tickets/new" className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent">
            {t("new")}
          </Link>
        </Can>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">{t("statusFilter")}</span>
          <select
            aria-label={t("statusFilter")}
            value={status}
            onChange={(event) => setStatus(event.target.value as TicketStatus | "")}
            className="rounded-md border px-2 py-1"
          >
            <option value="">{t("status.all")}</option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {t(`status.${value}`)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {pageData.items.length === 0 ? (
        <div role="status" className="flex flex-col items-start gap-3 rounded-md border border-dashed p-8">
          <p className="text-muted-foreground">{t("empty")}</p>
          <button type="button" onClick={resetFilters} className="rounded-md border px-3 py-1.5 text-sm">
            {t("clearFilters")}
          </button>
        </div>
      ) : (
        <TicketsTable tickets={pageData.items} caption={t("title")} unreadIds={unreadIds} />
      )}

      <nav aria-label={t("title")} className="flex items-center gap-3 text-sm">
        <button
          type="button"
          onClick={() => setPage(page - 1)}
          disabled={pageData.page <= 1}
          className="rounded-md border px-3 py-1.5 disabled:opacity-50"
        >
          {t("pagination.prev")}
        </button>
        <span aria-current="page">{t("pagination.page", { page: pageData.page })}</span>
        <button
          type="button"
          onClick={() => setPage(page + 1)}
          disabled={!hasNext}
          className="rounded-md border px-3 py-1.5 disabled:opacity-50"
        >
          {t("pagination.next")}
        </button>
      </nav>
    </section>
  );
}
