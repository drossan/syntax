import type { components } from "@/types/api";

type Notification = components["schemas"]["Notification"];

/**
 * Cuenta las notificaciones **no leídas** (sin `read_at`). Gobierna el badge de la campana.
 *
 * @param items Notificaciones del usuario.
 */
export function unreadCount(items: Notification[]): number {
  return items.filter((notification) => !notification.read_at).length;
}
