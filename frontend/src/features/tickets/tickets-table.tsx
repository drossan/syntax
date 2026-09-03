"use client";

import { createColumnHelper, tableFeatures, useTable } from "@tanstack/react-table";
import { useFormatter, useTranslations } from "next-intl";
import Link from "next/link";
import { useMemo, useState } from "react";

import type { components } from "@/types/api";

import { SlaBadge } from "./sla-badge";

type Ticket = components["schemas"]["Ticket"];

/** Cabecera de columna localizada (`tickets.columns.*`). */
function ColHeader({ k }: { k: string }) {
  const t = useTranslations("tickets.columns");
  return <>{t(k)}</>;
}

/** Estado del ticket localizado (`tickets.status.*`). */
function StatusCell({ value }: { value: Ticket["status"] }) {
  const t = useTranslations("tickets.status");
  return <>{value ? t(value) : null}</>;
}

/** Prioridad del ticket localizada (`tickets.priority.*`). */
function PriorityCell({ value }: { value: Ticket["priority"] }) {
  const t = useTranslations("tickets.priority");
  return <>{value ? t(value) : null}</>;
}

/** Responsable del ticket, o "sin asignar" si no hay `assignee_id`. */
function AssigneeCell({ value }: { value: Ticket["assignee_id"] }) {
  const t = useTranslations("tickets");
  return <>{value ?? t("unassigned")}</>;
}

/** Fecha de actualización formateada según locale y timezone del usuario (cross-cutting §2). */
function UpdatedCell({ value }: { value: string | undefined }) {
  const format = useFormatter();
  return <>{value ? format.dateTime(new Date(value), { dateStyle: "medium", timeStyle: "short" }) : null}</>;
}

/**
 * Celda de asunto: enlaza al detalle del ticket (única vía para abrirlo desde la bandeja) y marca
 * "no leído" (task 22) si el ticket está en `unreadIds`.
 */
function SubjectCell({
  id,
  subject,
  unread,
}: {
  id: string | undefined;
  subject: string | undefined;
  unread: boolean;
}) {
  const t = useTranslations("tickets");
  if (!id) return <span>{subject}</span>;
  return (
    <Link href={`/tickets/${id}`} className={unread ? "font-semibold underline" : "underline"}>
      {unread ? (
        <span aria-label={t("unread")} title={t("unread")} className="mr-1 text-primary">
          ●
        </span>
      ) : null}
      {subject}
    </Link>
  );
}

const features = tableFeatures({});
const helper = createColumnHelper<typeof features, Ticket>();

/**
 * Tabla de la bandeja de tickets (TanStack Table v9, headless). El orden/paginación son server-driven;
 * aquí solo se renderiza la página recibida. Semántica de tabla accesible (`aria-label`, `scope` de
 * cabecera). El contenido de origen usuario (asunto) se renderiza como texto inerte (anti-XSS).
 *
 * @param tickets Página de tickets a renderizar (ya ordenada por el servidor).
 * @param caption Etiqueta accesible de la tabla.
 * @param now Instante de referencia para el indicador de SLA (default: reloj al montar).
 * @param unreadIds Ids de tickets no leídos (task 22); marca el asunto.
 */
export function TicketsTable({
  tickets,
  caption,
  now,
  unreadIds,
}: {
  tickets: Ticket[];
  caption: string;
  now?: number;
  unreadIds?: Set<string>;
}) {
  const [mountedNow] = useState(() => Date.now());
  const effectiveNow = now ?? mountedNow;

  const columns = useMemo(
    () =>
      helper.columns([
        helper.accessor("subject", {
          header: () => <ColHeader k="subject" />,
          cell: (c) => (
            <SubjectCell
              id={c.row.original.id}
              subject={c.getValue()}
              unread={unreadIds?.has(c.row.original.id ?? "") ?? false}
            />
          ),
        }),
        helper.accessor("status", {
          header: () => <ColHeader k="status" />,
          cell: (c) => <StatusCell value={c.getValue()} />,
        }),
        helper.accessor("priority", {
          header: () => <ColHeader k="priority" />,
          cell: (c) => <PriorityCell value={c.getValue()} />,
        }),
        helper.accessor("domain", { header: () => <ColHeader k="domain" />, cell: (c) => c.getValue() }),
        helper.accessor("assignee_id", {
          header: () => <ColHeader k="assignee" />,
          cell: (c) => <AssigneeCell value={c.getValue()} />,
        }),
        helper.accessor("sla_due", {
          header: () => <ColHeader k="sla" />,
          cell: (c) => <SlaBadge slaDue={c.getValue()} now={effectiveNow} />,
        }),
        helper.accessor("updated_at", {
          header: () => <ColHeader k="updated" />,
          cell: (c) => <UpdatedCell value={c.getValue()} />,
        }),
      ]),
    [effectiveNow, unreadIds],
  );

  const table = useTable({ features, columns, data: tickets });

  return (
    <div className="overflow-x-auto">
      <table aria-label={caption} className="w-full min-w-[640px] border-collapse text-sm">
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id} className="border-b text-left">
              {group.headers.map((header) => (
                <th key={header.id} scope="col" className="px-3 py-2 font-medium">
                  {header.isPlaceholder ? null : <table.FlexRender header={header} />}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} className="border-b hover:bg-accent/50">
              {row.getAllCells().map((cell) => (
                <td key={cell.id} className="px-3 py-2">
                  <table.FlexRender cell={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
