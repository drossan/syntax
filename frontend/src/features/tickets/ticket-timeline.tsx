"use client";

import { useFormatter, useTranslations } from "next-intl";

import type { components } from "@/types/api";

import { buildTimeline } from "./timeline";

type Message = components["schemas"]["Message"];

/**
 * Timeline de actividad del ticket, derivado del hilo (`buildTimeline`), en orden cronológico y con el
 * actor de cada evento. Respeta la visibilidad. Estado vacío si no hay actividad. El actor y las fechas
 * se muestran localizados; el contenido es texto inerte (anti-XSS).
 *
 * @param messages Mensajes del hilo.
 * @param canSeeInternal Si el sujeto puede ver notas internas.
 */
export function TicketTimeline({
  messages,
  canSeeInternal,
}: {
  messages: Message[];
  canSeeInternal: boolean;
}) {
  const t = useTranslations("timeline");
  const format = useFormatter();
  const events = buildTimeline(messages, canSeeInternal);

  if (events.length === 0) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        {t("empty")}
      </p>
    );
  }

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-sm font-medium">{t("title")}</h2>
      <ol aria-label={t("region")} className="flex flex-col gap-1 text-sm">
        {events.map((event) => (
          <li key={event.id} className="flex flex-wrap items-center gap-2">
            <span className="rounded bg-accent px-1.5 py-0.5 text-xs">{t(`kind.${event.kind}`)}</span>
            <span className="font-medium">{event.actor ?? t("system")}</span>
            {event.at ? (
              <time dateTime={event.at} className="text-muted-foreground">
                {format.dateTime(new Date(event.at), { dateStyle: "medium", timeStyle: "short" })}
              </time>
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}
