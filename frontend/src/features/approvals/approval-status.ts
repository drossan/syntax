import type { components } from "@/types/api";

type ApprovalStatus = components["schemas"]["ApprovalStatus"];

/**
 * Una aprobación es decidible solo si está `pending`. Cualquier otro estado (o indefinido) ya está
 * resuelta → no se vuelve a decidir (idempotencia del HITL; el server responde 409 en carrera).
 *
 * @param status Estado de la `ApprovalTask`.
 */
export function isPending(status: ApprovalStatus | undefined): boolean {
  return status === "pending";
}

/**
 * La nota-al-humano del rechazo es obligatoria: válida solo si tiene contenido no en blanco.
 *
 * @param note Texto de la nota.
 */
export function noteProvided(note: string): boolean {
  return note.trim().length > 0;
}
