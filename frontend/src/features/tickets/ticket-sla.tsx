"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { SlaBadge } from "./sla-badge";

/**
 * Indicador de SLA del detalle: nivel (coherente con la bandeja, `SlaBadge`) + tiempo relativo hasta el
 * vencimiento y la fecha límite. Sin SLA → aviso neutro. `now` lo inyecta el contenedor (determinismo).
 * Solo indicador visual; el cómputo/escalado del SLA es del backend (task 18).
 *
 * @param slaDue Fecha límite del SLA (ISO) o `null`.
 * @param now Instante de referencia (default: reloj al montar).
 */
export function TicketSla({ slaDue, now }: { slaDue: string | null | undefined; now?: number }) {
  const t = useTranslations("ticketSla");
  const format = useFormatter();
  const [mountedNow] = useState(() => Date.now());
  const effectiveNow = now ?? mountedNow;

  if (!slaDue) {
    return <p className="text-sm text-muted-foreground">{t("none")}</p>;
  }

  return (
    <div aria-label={t("region")} className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-muted-foreground">{t("label")}</span>
      <SlaBadge slaDue={slaDue} now={effectiveNow} />
      <time dateTime={slaDue}>
        {format.relativeTime(new Date(slaDue), effectiveNow)} ·{" "}
        {format.dateTime(new Date(slaDue), { dateStyle: "medium", timeStyle: "short" })}
      </time>
    </div>
  );
}
