import { z } from "zod";

import type { components } from "@/types/api";

type TicketCreate = components["schemas"]["TicketCreate"];

/** Prioridades del contrato (`TicketPriority`). */
const PRIORITIES = ["low", "normal", "high", "urgent"] as const;

/**
 * Esquema de validación de cliente del alta de ticket. Coherente con el contrato `TicketCreate`
 * (`subject` requerido, `body`/`priority` opcionales). **No** incluye `domain`: la clasificación de
 * dominio es del backend (fuera de alcance), y el contrato no acepta `domain` en la creación.
 */
export const ticketCreateSchema = z.object({
  subject: z.string().trim().min(1, "El asunto es obligatorio"),
  body: z.string(),
  priority: z.enum(PRIORITIES),
});

/** Valores del formulario de alta. */
export type TicketCreateValues = z.infer<typeof ticketCreateSchema>;

/**
 * Construye el body de `POST /tickets` a partir de los valores del formulario. Omite `body` cuando está
 * vacío o es solo espacios (no envía un primer mensaje en blanco). `tenant_id` no se envía: lo deriva
 * el servidor del sujeto/tenant activo.
 *
 * @param values Valores validados del formulario.
 * @returns Body conforme a `TicketCreate`.
 */
export function toTicketCreateBody(values: TicketCreateValues): TicketCreate {
  const body: TicketCreate = { subject: values.subject.trim(), priority: values.priority };
  const trimmedBody = values.body.trim();
  if (trimmedBody.length > 0) {
    body.body = trimmedBody;
  }
  return body;
}
