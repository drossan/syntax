const KILO = 1024;

/**
 * Formatea un tamaño en bytes a una cadena legible (B / KB / MB, una decimal). Un tamaño desconocido
 * (`undefined`) se muestra como guion.
 *
 * @param bytes Tamaño en bytes, o `undefined` si el contrato no lo trae.
 */
export function formatFileSize(bytes: number | undefined): string {
  if (bytes === undefined) return "—";
  if (bytes < KILO) return `${bytes} B`;
  const kb = bytes / KILO;
  if (kb < KILO) return `${kb.toFixed(1)} KB`;
  return `${(kb / KILO).toFixed(1)} MB`;
}

/**
 * Construye la URL de descarga de un adjunto. **Gap de contrato v0.1.0**: el schema `Attachment` no trae
 * URL y no hay endpoint de descarga; se usa la ruta convencional `…/attachments/{id}` que el backend
 * proveerá cuando el puerto de storage deje de ser stub (design-review M2). Placeholder documentado.
 *
 * @param attachment Adjunto (se usa su `id`).
 * @param apiBase Origen de la API (default: relativo).
 */
export function attachmentDownloadHref(attachment: { id?: string }, apiBase = ""): string {
  return `${apiBase}/api/v1/attachments/${attachment.id ?? ""}`;
}
