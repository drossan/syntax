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
 * Dispara la descarga de un blob ya obtenido como si fuera un enlace normal: crea una URL de objeto
 * temporal, la "clica" con un `<a>` desechable, y libera la URL. Hace falta este rodeo (en vez de un
 * `<a href={urlDelAdjunto}>` directo) porque la descarga real es autenticada — el token de acceso vive
 * solo en memoria JS (nunca en cookie), así que un `<a href>` plano nunca lo llevaría; hay que pedir el
 * binario con el cliente autenticado primero (`useDownloadAttachment`) y descargar el blob ya en mano.
 * Verificado en vivo: `GET /messages/{id}/attachments/{attachment_id}` sin `Authorization` responde 401
 * (bug real, reproducido con curl, no hipotético).
 *
 * @param blob Binario ya descargado (con el cliente autenticado).
 * @param filename Nombre de fichero sugerido para la descarga.
 */
export function triggerBrowserDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
