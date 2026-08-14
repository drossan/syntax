"use client";

import { useTranslations } from "next-intl";

import type { components } from "@/types/api";

import { attachmentDownloadHref, formatFileSize } from "./attachments";

type Attachment = components["schemas"]["Attachment"];

/**
 * Adjuntos del ticket, **solo visualización** (design-review M2: la subida se difiere hasta que el
 * storage del backend sea real). Lista nombre/tipo/tamaño con enlace de descarga, o el estado vacío.
 * **Nunca** renderiza control de subida en Fase 1. El nombre de fichero es texto inerte (anti-XSS).
 *
 * @param attachments Adjuntos a mostrar.
 * @param apiBase Origen de la API para los enlaces de descarga.
 */
export function TicketAttachments({
  attachments,
  apiBase,
}: {
  attachments: Attachment[];
  apiBase?: string;
}) {
  const t = useTranslations("attachments");

  if (attachments.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("empty")}</p>;
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
            <a
              href={attachmentDownloadHref(attachment, apiBase)}
              download
              aria-label={t("downloadLabel", { name: attachment.filename ?? "" })}
              className="text-primary underline"
            >
              {t("download")}
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
