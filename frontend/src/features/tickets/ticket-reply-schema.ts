import { z } from "zod";

import type { components } from "@/types/api";

type MessageCreate = components["schemas"]["MessageCreate"];

/** Visibilidades del contrato (`MessageVisibility`). */
const VISIBILITIES = ["public", "internal"] as const;

/** Esquema de validación de cliente de la respuesta a un ticket. Coherente con `MessageCreate`. */
export const ticketReplySchema = z.object({
  body: z.string().trim().min(1, "El mensaje no puede estar vacío"),
  visibility: z.enum(VISIBILITIES),
});

/** Valores del formulario de respuesta. */
export type TicketReplyValues = z.infer<typeof ticketReplySchema>;

/**
 * Construye el body de `POST /tickets/{id}/messages` a partir de los valores del formulario.
 *
 * @param values Valores validados del formulario.
 */
export function toMessageCreateBody(values: TicketReplyValues): MessageCreate {
  return { body: values.body.trim(), visibility: values.visibility };
}
