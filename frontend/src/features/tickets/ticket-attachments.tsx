"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import type { components } from "@/types/api";

import { formatFileSize, triggerBrowserDownload } from "./attachments";
import { useDownloadAttachment } from "./use-attachment-download";

type Attachment = components["schemas"]["Attachment"];

/**
 * Adjuntos del ticket, **solo visualización** — la subida vive en `TicketReplyForm` (un adjunto solo
 * puede subirse a un mensaje ya existente, `POST /messages/{id}/attachments`, así que no tiene sentido
 * un control de subida aquí sin un mensaje al que colgarlo). Lista nombre/tipo/tamaño con un botón de
 * descarga (NO un `<a href>` — la descarga es autenticada, ver `use-attachment-download.ts`), o el
 * estado vacío. El nombre de fichero es texto inerte (anti-XSS).
 *
 * @param attachments Adjuntos a mostrar (de los mensajes visibles para el sujeto — ver `TicketDetail`).
 */
export function TicketAttachments({ attachments }: { attachments: Attachment[] }) {
  const t = useTranslations("attachments");
  const download = useDownloadAttachment();
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [errorId, setErrorId] = useState<string | null>(null);

  if (attachments.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("empty")}</p>;
  }

  function handleDownload(attachment: Attachment) {
    if (!attachment.id || !attachment.message_id) return;
    const { id, message_id, filename } = attachment;
    setErrorId(null);
    setDownloadingId(id);
    download.mutate(
      { messageId: message_id, attachmentId: id },
      {
        onSuccess: (blob) => triggerBrowserDownload(blob, filename ?? id),
        onError: () => setErrorId(id),
        onSettled: () => setDownloadingId(null),
      },
    );
  }

  return (
    <section aria-label={t("region")} className="flex flex-col gap-2">
      <h2 className="text-sm font-medium">{t("title")}</h2>
      <ul className="flex flex-col gap-1 text-sm">
        {attachments.map((attachment) => (
          <li key={attachment.id} className="flex flex-wrap items-center gap-3">
            <span className="font-medium">{attachment.filename}</span>
            <span className="text-muted-foreground">{attachment.content_type}</span>
            <span className="text-muted-foreground">{formatFileSize(attachment.size_bytes)}</span>
            <button
              type="button"
              onClick={() => handleDownload(attachment)}
              disabled={downloadingId === attachment.id}
              aria-label={t("downloadLabel", { name: attachment.filename ?? "" })}
              className="text-primary underline disabled:opacity-50"
            >
              {t("download")}
            </button>
            {errorId === attachment.id ? (
              <span role="alert" className="text-xs text-destructive">
                {t("downloadError")}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
