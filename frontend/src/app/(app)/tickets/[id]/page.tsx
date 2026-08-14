import { RequireCapability } from "@/features/rbac/can";
import { TicketDetail } from "@/features/tickets/ticket-detail";

/**
 * Detalle de un ticket. Ruta dinámica `/tickets/[id]` (Next 16: `params` es una Promise). Protegida por
 * `ticket.read`; el detalle mismo aplica el filtro de visibilidad de mensajes por capacidad.
 */
export default async function TicketDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <RequireCapability capability="ticket.read">
      <TicketDetail ticketId={id} />
    </RequireCapability>
  );
}
