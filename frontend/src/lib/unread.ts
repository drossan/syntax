/**
 * Deriva si un ticket está **no leído**: hay actividad (`updatedAt`) posterior a la última visita. Sin
 * fecha de actualización → leído (nada que mostrar). Nunca visitado (`lastVisitIso` ausente) → no leído.
 * Las fechas ISO-8601 se comparan lexicográficamente (coincide con el orden cronológico).
 *
 * @param updatedAt Última actualización del ticket (ISO) o `undefined`.
 * @param lastVisitIso Última visita del usuario a ese ticket (ISO) o `undefined` si nunca lo abrió.
 */
export function isUnread(updatedAt: string | undefined, lastVisitIso: string | undefined): boolean {
  if (!updatedAt) return false;
  if (!lastVisitIso) return true;
  return updatedAt > lastVisitIso;
}
