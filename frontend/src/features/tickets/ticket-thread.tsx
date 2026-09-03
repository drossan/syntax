"use client";

import { useFormatter, useTranslations } from "next-intl";

import { MarkdownText } from "@/components/markdown-text";
import type { components } from "@/types/api";

import { prepareThread } from "./message-visibility";

type Message = components["schemas"]["Message"];

/** Etiqueta del autor del mensaje: asistente IA, sistema (sin autor) o el id del autor. */
function authorLabel(message: Message, t: (key: string) => string): string {
  if (message.is_ai_draft) return t("thread.assistant");
  if (!message.author_id) return t("thread.system");
  return message.author_id;
}

/**
 * Hilo de conversación del ticket. Aplica el filtro de visibilidad en cliente (**defensa en
 * profundidad**) y ordena cronológicamente (`prepareThread`). El cuerpo se renderiza con
 * `MarkdownText` (ADR-0020) — formateado vía un allow-list explícito, sin distinguir autor; el
 * marcado fuera del allow-list o HTML embebido se muestra como texto inerte (anti-XSS,
 * `cross-cutting.md` §1). Marca notas internas y borradores de IA.
 *
 * @param messages Mensajes recibidos del servidor.
 * @param canSeeInternal Si el sujeto puede ver notas internas (`note.internal.read`).
 */
export function TicketThread({
  messages,
  canSeeInternal,
}: {
  messages: Message[];
  canSeeInternal: boolean;
}) {
  const t = useTranslations("ticketDetail");
  const format = useFormatter();
  const thread = prepareThread(messages, canSeeInternal);

  if (thread.length === 0) {
    return (
      <p role="status" className="text-muted-foreground">
        {t("empty")}
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-3">
      {thread.map((message) => (
        <li key={message.id} className="rounded-md border p-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{authorLabel(message, t)}</span>
            {message.created_at ? (
              <span>
                {format.dateTime(new Date(message.created_at), {
                  dateStyle: "medium",
                  timeStyle: "short",
                })}
              </span>
            ) : null}
            {message.visibility === "internal" ? (
              <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-800 dark:bg-amber-950 dark:text-amber-200">
                {t("thread.internal")}
              </span>
            ) : null}
            {message.is_ai_draft ? (
              <span className="rounded bg-accent px-1.5 py-0.5">{t("thread.aiDraft")}</span>
            ) : null}
          </div>
          <div className="mt-1 text-sm">
            <MarkdownText>{message.body ?? ""}</MarkdownText>
          </div>
        </li>
      ))}
    </ul>
  );
}
