import { RequireCapability } from "@/features/rbac/can";
import { TicketCreateForm } from "@/features/tickets/ticket-create-form";

/** Alta de ticket. Protegida por la capacidad `ticket.create`. */
export default function NewTicketPage() {
  return (
    <RequireCapability capability="ticket.create">
      <TicketCreateForm />
    </RequireCapability>
  );
}
