/** Nivel del indicador de SLA de un ticket (solo visual). */
export type SlaLevel = "none" | "normal" | "imminent" | "overdue";

/** Ventana por defecto para considerar un SLA "inminente" (1 hora). */
export const SLA_IMMINENT_WINDOW_MS = 60 * 60 * 1000;

/**
 * Clasifica el SLA de un ticket para pintarlo en la bandeja. **Solo indicador visual**: el cómputo y
 * el escalado del SLA los hace el backend (task 18); aquí se compara `sla_due` con el instante actual.
 *
 * @param slaDue Fecha límite del SLA (ISO-8601) o `null`/`undefined` si el ticket no tiene SLA.
 * @param now Instante de referencia en ms (epoch) — inyectable para tests deterministas.
 * @param imminentWindowMs Ventana previa al vencimiento que se considera "inminente" (default 1h).
 * @returns `overdue` si ya venció (`sla_due <= now`), `imminent` dentro de la ventana, `normal` más
 *   allá, y `none` cuando no hay fecha o no es parseable.
 */
export function slaLevel(
  slaDue: string | null | undefined,
  now: number,
  imminentWindowMs: number = SLA_IMMINENT_WINDOW_MS,
): SlaLevel {
  if (!slaDue) return "none";
  const due = Date.parse(slaDue);
  if (Number.isNaN(due)) return "none";

  const remaining = due - now;
  if (remaining <= 0) return "overdue";
  if (remaining <= imminentWindowMs) return "imminent";
  return "normal";
}
