import { RequireCapability } from "@/features/rbac/can";
import { TicketsInbox } from "@/features/tickets/tickets-inbox";

/**
 * Home de la app autenticada = **bandeja de tickets** (la entrada de nav "inbox" apunta a `/`).
 * Protegida por la capacidad `ticket.read` (guard de cliente; la API es la fuente de verdad).
 */
export default function InboxPage() {
  return (
    <RequireCapability capability="ticket.read">
      <TicketsInbox />
    </RequireCapability>
  );
}
