import type { components } from "@/types/api";

import { prepareThread } from "./message-visibility";

type Message = components["schemas"]["Message"];

/** Un evento del timeline de actividad del ticket. */
export interface TimelineEvent {
  id: string;
  at: string;
  actor: string | null;
  kind: "message" | "ai_draft";
}

/**
 * Construye el timeline de actividad **derivado del hilo** (el contrato v0.1.0 no expone un endpoint de
 * audit). Reutiliza `prepareThread`: respeta la visibilidad (un cliente no ve eventos de notas internas)
 * y el orden cronológico. Eventos de transición/asignación quedan pendientes de un endpoint de actividad.
 *
 * @param messages Mensajes del hilo recibidos del servidor.
 * @param canSeeInternal Si el sujeto puede ver notas internas.
 * @returns Eventos ordenados cronológicamente.
 */
export function buildTimeline(messages: Message[], canSeeInternal: boolean): TimelineEvent[] {
  return prepareThread(messages, canSeeInternal).map((message) => ({
    id: message.id ?? "",
    at: message.created_at ?? "",
    actor: message.author_id ?? null,
    kind: message.is_ai_draft ? "ai_draft" : "message",
  }));
}
