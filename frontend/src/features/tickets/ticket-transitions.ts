import type { components } from "@/types/api";

type TicketStatus = components["schemas"]["TicketStatus"];

/**
 * Máquina de estados **de cliente**: qué transiciones se ofrecen desde cada estado. El backend es la
 * fuente de verdad (una transición que él rechace → 409 → rollback); esto solo evita ofrecer acciones
 * inválidas en la UI. El data-model fija el enum de estados pero no el grafo, así que se define aquí.
 */
const TRANSITIONS: Record<TicketStatus, TicketStatus[]> = {
  new: ["open", "pending", "resolved", "closed"],
  open: ["pending", "resolved", "closed"],
  pending: ["open", "resolved", "closed"],
  resolved: ["closed", "reopened"],
  closed: ["reopened"],
  reopened: ["open", "pending", "resolved", "closed"],
};

/** Estados cuya transición es **destructiva** y exige confirmación. */
const DESTRUCTIVE_STATUSES: readonly TicketStatus[] = ["closed"];

/**
 * Transiciones válidas ofrecidas desde un estado dado (nunca incluye el estado actual).
 *
 * @param status Estado actual del ticket.
 * @returns Los estados a los que se puede transitar desde `status`.
 */
export function allowedTransitions(status: TicketStatus): TicketStatus[] {
  return TRANSITIONS[status] ?? [];
}

/**
 * Indica si transitar a `target` es una acción destructiva (p.ej. cerrar) que requiere confirmación.
 *
 * @param target Estado destino.
 */
export function isDestructiveTransition(target: TicketStatus): boolean {
  return DESTRUCTIVE_STATUSES.includes(target);
}
