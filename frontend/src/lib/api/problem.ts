import type { components } from "@/types/api";

/** Envelope de error del contrato (problem+json, RFC 9457). */
export type Problem = components["schemas"]["Problem"];

/** Función de traducción (p.ej. `useTranslations()` de next-intl) usada como fallback. */
export type Translate = (key: string) => string;

/** Forma de error lista para la UI: toast (localizado) + errores por campo para RHF. */
export interface UiError {
  toast: { title: string; detail?: string };
  fieldErrors: Record<string, string>;
}

/**
 * Traduce un envelope `problem+json` a la forma que consume la UI.
 *
 * - `errors[]` (con `field` y `message`) → `fieldErrors` para React Hook Form.
 * - `title`/`detail` → toast. El servidor ya los localiza por `Accept-Language`; si `title`
 *   viene vacío se usa `translate("errors.generic")` como fallback de cliente.
 *
 * @param problem Envelope de error recibido de la API.
 * @param translate Traductor opcional (fallback cuando el `title` del servidor viene vacío).
 * @returns `{ toast, fieldErrors }` para pintar en la UI.
 */
export function problemToUi(problem: Problem, translate?: Translate): UiError {
  const fieldErrors: Record<string, string> = {};
  for (const entry of problem.errors ?? []) {
    if (entry.field && entry.message) {
      fieldErrors[entry.field] = entry.message;
    }
  }

  const title = problem.title || translate?.("errors.generic") || problem.title;
  const toast: UiError["toast"] = { title };
  if (problem.detail !== undefined) {
    toast.detail = problem.detail;
  }

  return { toast, fieldErrors };
}
