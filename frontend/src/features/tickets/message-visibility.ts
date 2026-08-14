import type { components } from "@/types/api";

type Message = components["schemas"]["Message"];

/**
 * Filtra el hilo por visibilidad (**defensa en profundidad**). El backend ya filtra los mensajes
 * `internal`, pero el cliente **no confía** en el payload: si el sujeto no puede leer notas internas,
 * nunca las muestra aunque lleguen en la respuesta (rbac §6 / cross-cutting §1).
 *
 * @param messages Mensajes recibidos del servidor.
 * @param canSeeInternal Si el sujeto tiene `note.internal.read`.
 * @returns Los mensajes visibles para el sujeto.
 */
export function filterByVisibility(messages: Message[], canSeeInternal: boolean): Message[] {
  if (canSeeInternal) return messages;
  return messages.filter((message) => message.visibility !== "internal");
}

/**
 * Ordena el hilo por `created_at` ascendente (cronológico). Defensivo: no asume el orden del servidor.
 * No muta el array de entrada.
 *
 * @param messages Mensajes a ordenar.
 * @returns Una copia ordenada ascendentemente por fecha de creación.
 */
export function sortChronologically(messages: Message[]): Message[] {
  // Las fechas son ISO-8601 → el orden lexicográfico coincide con el cronológico (sin parsear).
  return [...messages].sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? ""));
}

/**
 * Prepara el hilo para render: primero filtra por visibilidad, luego ordena cronológicamente.
 *
 * @param messages Mensajes del servidor.
 * @param canSeeInternal Si el sujeto tiene `note.internal.read`.
 * @returns Mensajes visibles y ordenados.
 */
export function prepareThread(messages: Message[], canSeeInternal: boolean): Message[] {
  return sortChronologically(filterByVisibility(messages, canSeeInternal));
}
