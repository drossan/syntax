import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-context";
import { useTenant } from "@/features/tenant/tenant-context";

/** Nº de mensajes que se piden para el hilo (una sola página amplia; sin paginación de hilo en Fase 1). */
const THREAD_PAGE_SIZE = 100;

/** Clave de caché de la cabecera del ticket (aislada por tenant activo). */
export function ticketKey(activeTenantId: string | null, ticketId: string) {
  return ["ticket", activeTenantId, ticketId] as const;
}

/** Clave de caché del hilo del ticket (aislada por tenant activo). */
export function ticketMessagesKey(activeTenantId: string | null, ticketId: string) {
  return ["ticket", activeTenantId, ticketId, "messages"] as const;
}

/**
 * Carga la cabecera de un ticket (`GET /tickets/{id}`). Propaga el envelope de error (403/404) para que
 * el detalle muestre no-encontrado/sin-acceso sin filtrar datos.
 *
 * @param ticketId Id del ticket.
 */
export function useTicket(ticketId: string) {
  const { client } = useAuth();
  const { activeTenantId } = useTenant();

  return useQuery({
    queryKey: ticketKey(activeTenantId, ticketId),
    queryFn: async () => {
      const { data, error } = await client.GET("/tickets/{id}", {
        params: { path: { id: ticketId } },
      });
      if (error) throw error;
      return data;
    },
  });
}

/**
 * Carga el hilo de mensajes de un ticket (`GET /tickets/{id}/messages`, orden `created_at asc`
 * server-side). El filtro de visibilidad se aplica además en cliente (defensa en profundidad).
 *
 * @param ticketId Id del ticket.
 */
export function useTicketMessages(ticketId: string) {
  const { client } = useAuth();
  const { activeTenantId } = useTenant();

  return useQuery({
    queryKey: ticketMessagesKey(activeTenantId, ticketId),
    queryFn: async () => {
      const { data, error } = await client.GET("/tickets/{id}/messages", {
        params: { path: { id: ticketId }, query: { page_size: THREAD_PAGE_SIZE } },
      });
      if (error) throw error;
      return data.items;
    },
  });
}
